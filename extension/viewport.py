"""Viewport tools: screenshot, collage, angle, framing, orbit, camera positioning."""

import base64
import math
import os
import tempfile

import bpy
import blf
import mathutils


_screenshot_overlay_text = ""


def _draw_screenshot_overlay():
    text = _screenshot_overlay_text
    if not text:
        return
    try:
        font_id = 0
        blf.size(font_id, 18)
        blf.color(font_id, 1.0, 0.95, 0.3, 1.0)
        blf.position(font_id, 8, 8, 0)
        blf.draw(font_id, text)
    except Exception:
        pass


PANEL_AXIS_LABELS = {
    "FRONT": "FRONT  X-Z plane  (+Y into screen)",
    "RIGHT": "RIGHT  Y-Z plane  (+X into screen)",
    "TOP":   "TOP    X-Y plane  (+Z into screen)",
    "BACK":  "BACK   X-Z plane  (-Y into screen)",
    "LEFT":  "LEFT   Y-Z plane  (-X into screen)",
    "PERSP": "PERSP  3D view",
}


def find_view3d_context():
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return window, screen, area, region
    return None, None, None, None


def _capture_viewport(scene, window, screen, area, region, path, width, height):
    scene.render.filepath = path
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        bpy.ops.render.opengl(write_still=True)


def _write_png(rgba_float, path):
    import struct, zlib
    import numpy as np
    h, w = rgba_float.shape[:2]
    pixels = (np.clip(rgba_float, 0, 1) * 255).astype(np.uint8)

    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    ihdr = chunk(b'IHDR', struct.pack('>II', w, h) + bytes([8, 6, 0, 0, 0]))
    raw = b''.join(b'\x00' + pixels[r].tobytes() for r in range(h))
    idat = chunk(b'IDAT', zlib.compress(raw, 6))
    iend = chunk(b'IEND', b'')

    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + ihdr + idat + iend)


def get_viewport_screenshot(params):
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    width = params.get("width", 960)
    height = params.get("height", 540)

    scene = bpy.context.scene
    old_path = scene.render.filepath
    old_format = scene.render.image_settings.file_format
    old_res_x = scene.render.resolution_x
    old_res_y = scene.render.resolution_y
    old_res_pct = scene.render.resolution_percentage

    tmp = os.path.join(tempfile.gettempdir(), "bb_viewport.png")
    scene.render.image_settings.file_format = 'PNG'
    scene.render.resolution_percentage = 100

    global _screenshot_overlay_text
    _screenshot_overlay_text = "+Z up   (Blender world)"
    overlay_handle = bpy.types.SpaceView3D.draw_handler_add(
        _draw_screenshot_overlay, (), 'WINDOW', 'POST_PIXEL'
    )
    try:
        _capture_viewport(scene, window, screen, area, region, tmp, width, height)
    finally:
        bpy.types.SpaceView3D.draw_handler_remove(overlay_handle, 'WINDOW')
        _screenshot_overlay_text = ""

    scene.render.filepath = old_path
    scene.render.image_settings.file_format = old_format
    scene.render.resolution_x = old_res_x
    scene.render.resolution_y = old_res_y
    scene.render.resolution_percentage = old_res_pct

    with open(tmp, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    return {"image": data, "format": "png"}


def get_viewport_collage(params):
    import numpy as np

    target = params.get("target", "ALL")
    zoom = params.get("zoom", 1.0)
    panel_w = max(160, int(320 * zoom))
    panel_h = max(90,  int(180 * zoom))

    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    r3d = next((s.region_3d for s in area.spaces if s.type == 'VIEW_3D'), None)
    if r3d is None:
        return {"error": "No region_3d found"}

    target_up = target.upper() if isinstance(target, str) else "ALL"
    if target_up == "ALL":
        target_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    elif target_up == "SELECTED":
        target_objs = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    else:
        obj = bpy.data.objects.get(target)
        target_objs = [obj] if obj else []

    if not target_objs:
        return {"error": f"No mesh objects to frame for target='{target}'"}

    bbox_pts = []
    for o in target_objs:
        for c in o.bound_box:
            bbox_pts.append(o.matrix_world @ mathutils.Vector(c))
    xs = [p.x for p in bbox_pts]
    ys = [p.y for p in bbox_pts]
    zs = [p.z for p in bbox_pts]
    framed_bbox = {
        "x": [round(min(xs), 4), round(max(xs), 4)],
        "y": [round(min(ys), 4), round(max(ys), 4)],
        "z": [round(min(zs), 4), round(max(zs), 4)],
    }

    active = bpy.context.view_layer.objects.active
    was_edit = active is not None and active.mode == 'EDIT'
    if was_edit:
        bpy.ops.object.mode_set(mode='OBJECT')
    saved_active = bpy.context.view_layer.objects.active
    saved_selected = list(bpy.context.selected_objects)

    bpy.ops.object.select_all(action='DESELECT')
    for o in target_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = target_objs[0]

    scene = bpy.context.scene
    old_path   = scene.render.filepath
    old_format = scene.render.image_settings.file_format
    old_res_x  = scene.render.resolution_x
    old_res_y  = scene.render.resolution_y
    old_res_pct = scene.render.resolution_percentage

    scene.render.image_settings.file_format = 'PNG'
    scene.render.resolution_percentage = 100

    views = ["FRONT", "RIGHT", "TOP", "BACK", "LEFT", "PERSP"]
    panels = []

    global _screenshot_overlay_text
    overlay_handle = bpy.types.SpaceView3D.draw_handler_add(
        _draw_screenshot_overlay, (), 'WINDOW', 'POST_PIXEL'
    )
    try:
        for label in views:
            tmp = os.path.join(tempfile.gettempdir(), f"bb_col_{label.lower()}.png")
            _screenshot_overlay_text = PANEL_AXIS_LABELS.get(label, label)

            with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
                if label != "PERSP":
                    bpy.ops.view3d.view_axis(type=label)
                    bpy.ops.view3d.view_selected(use_all_regions=False)
                else:
                    bpy.ops.view3d.view_axis(type='FRONT')
                    bpy.ops.view3d.view_selected(use_all_regions=False)
                    r3d.view_perspective = 'PERSP'
                    q_az = mathutils.Quaternion((0.0, 0.0, 1.0), math.radians(-35))
                    r3d.view_rotation = q_az @ r3d.view_rotation
                    q_el = mathutils.Quaternion((1.0, 0.0, 0.0), math.radians(-20))
                    r3d.view_rotation = r3d.view_rotation @ q_el

                _capture_viewport(scene, window, screen, area, region, tmp, panel_w, panel_h)

            img = bpy.data.images.load(tmp, check_existing=False)
            px = np.array(img.pixels[:], dtype=np.float32).reshape(panel_h, panel_w, 4)
            px = np.flipud(px)
            bpy.data.images.remove(img)
            panels.append(px)
    finally:
        bpy.types.SpaceView3D.draw_handler_remove(overlay_handle, 'WINDOW')
        _screenshot_overlay_text = ""

    row1 = np.concatenate(panels[0:3], axis=1)
    row2 = np.concatenate(panels[3:6], axis=1)
    grid = np.concatenate([row1, row2], axis=0)

    out = os.path.join(tempfile.gettempdir(), "bb_collage.png")
    _write_png(grid, out)

    bpy.ops.object.select_all(action='DESELECT')
    for o in saved_selected:
        try:
            o.select_set(True)
        except Exception:
            pass
    if saved_active:
        bpy.context.view_layer.objects.active = saved_active
    if was_edit and saved_active:
        bpy.ops.object.mode_set(mode='EDIT')

    scene.render.filepath = old_path
    scene.render.image_settings.file_format = old_format
    scene.render.resolution_x = old_res_x
    scene.render.resolution_y = old_res_y
    scene.render.resolution_percentage = old_res_pct

    with open(out, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    return {
        "image": data,
        "format": "png",
        "layout": "row1: FRONT | RIGHT | TOP   row2: BACK | LEFT | PERSP",
        "panel_size": f"{panel_w}x{panel_h}",
        "target": target,
        "target_objects": [o.name for o in target_objs],
        "framed_bbox": framed_bbox,
    }


def set_viewport_angle(params):
    angle = params.get("angle", "FRONT").upper()
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        if angle == "CAMERA":
            bpy.ops.view3d.view_camera()
        else:
            bpy.ops.view3d.view_axis(type=angle)

    return {"success": True, "angle": angle}


def frame_scene(params):
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}
    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        bpy.ops.view3d.view_all(center=False)
    return {"success": True}


def zoom_to_selected(params):
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}
    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        bpy.ops.view3d.view_selected()
    return {"success": True}


def orbit_viewport(params):
    azimuth  = params.get("azimuth",  45.0)
    elevation = params.get("elevation", 25.0)
    distance  = params.get("distance",  8.0)
    tx = params.get("target_x", 0.0)
    ty = params.get("target_y", 0.0)
    tz = params.get("target_z", 1.0)

    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    r3d = next((s.region_3d for s in area.spaces if s.type == 'VIEW_3D'), None)
    if r3d is None:
        return {"error": "Could not access view"}

    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        bpy.ops.view3d.view_axis(type='FRONT')

    r3d.view_perspective = 'PERSP'
    r3d.view_location = mathutils.Vector((tx, ty, tz))
    r3d.view_distance = distance

    q_az = mathutils.Quaternion((0.0, 0.0, 1.0), math.radians(azimuth))
    r3d.view_rotation = q_az @ r3d.view_rotation
    q_el = mathutils.Quaternion((1.0, 0.0, 0.0), math.radians(-elevation))
    r3d.view_rotation = r3d.view_rotation @ q_el

    return {"success": True}


def set_camera_position(params):
    x  = params.get("x", 5.0)
    y  = params.get("y", -5.0)
    z  = params.get("z", 5.0)
    tx = params.get("target_x", 0.0)
    ty = params.get("target_y", 0.0)
    tz = params.get("target_z", 0.0)

    cam = next((o for o in bpy.data.objects if o.type == 'CAMERA'), None)
    if cam is None:
        return {"error": "No camera in scene"}

    cam.location = (x, y, z)
    direction = mathutils.Vector((tx, ty, tz)) - mathutils.Vector((x, y, z))
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    return {"success": True, "camera": cam.name}


_SHADING_TYPES = {"WIREFRAME", "SOLID", "MATERIAL", "RENDERED"}


def set_viewport_shading(params):
    """Switch the 3D viewport's shading mode.

    mode: WIREFRAME | SOLID | MATERIAL | RENDERED
          - SOLID: matcap/default flat shading (no materials visible)
          - MATERIAL: previews materials with built-in studio lighting (cheap, fast)
          - RENDERED: full Eevee/Cycles preview using your scene lights + world
          - WIREFRAME: edges only

    Required to actually see materials and lighting in subsequent screenshots —
    without this, get_viewport_screenshot shows whatever mode is currently set
    (usually SOLID), which hides every material decision.
    """
    mode = params.get("mode", "MATERIAL").upper()
    if mode not in _SHADING_TYPES:
        return {"error": f"Invalid mode '{mode}'. Use one of {sorted(_SHADING_TYPES)}"}
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}
    space = next((s for s in area.spaces if s.type == 'VIEW_3D'), None)
    if space is None:
        return {"error": "No VIEW_3D space found"}
    space.shading.type = mode
    return {"success": True, "mode": mode}


TOOLS = {
    "get_viewport_screenshot": get_viewport_screenshot,
    "get_viewport_collage":    get_viewport_collage,
    "set_viewport_angle":      set_viewport_angle,
    "set_viewport_shading":    set_viewport_shading,
    "frame_scene":             frame_scene,
    "zoom_to_selected":        zoom_to_selected,
    "orbit_viewport":          orbit_viewport,
    "set_camera_position":     set_camera_position,
}

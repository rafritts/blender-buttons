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


def _normalize_format(fmt):
    """Return (blender_enum, file_ext, response_format) for a user-supplied format string."""
    f = (fmt or "PNG").upper()
    if f in ("JPG", "JPEG"):
        return "JPEG", "jpg", "jpeg"
    if f == "PNG":
        return "PNG", "png", "png"
    raise ValueError(f"format must be PNG or JPEG, got '{fmt}'")


def _apply_image_settings(scene, blender_fmt, quality, compression):
    """Apply file_format + quality + compression. Returns the saved prior state for restore."""
    saved = {
        "file_format": scene.render.image_settings.file_format,
        "quality":     scene.render.image_settings.quality,
        "compression": scene.render.image_settings.compression,
    }
    scene.render.image_settings.file_format = blender_fmt
    scene.render.image_settings.quality = int(quality)
    scene.render.image_settings.compression = int(compression)
    return saved


def _restore_image_settings(scene, saved):
    scene.render.image_settings.file_format = saved["file_format"]
    scene.render.image_settings.quality     = saved["quality"]
    scene.render.image_settings.compression = saved["compression"]


def _save_array_image(rgba_float, path, blender_fmt, quality, compression):
    """Save a numpy (H, W, 4) float RGBA array via Blender's image API. Handles PNG + JPEG."""
    import numpy as np
    h, w = rgba_float.shape[:2]
    img = bpy.data.images.new("__bb_collage_export__", w, h, alpha=True, float_buffer=False)
    flipped = np.flipud(rgba_float).astype(np.float32)
    img.pixels.foreach_set(flipped.ravel())
    scene = bpy.context.scene
    saved = _apply_image_settings(scene, blender_fmt, quality, compression)
    try:
        img.save_render(path)
    finally:
        _restore_image_settings(scene, saved)
        bpy.data.images.remove(img)


def get_viewport_screenshot(params):
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    width = params.get("width", 960)
    height = params.get("height", 540)
    hide_overlays = bool(params.get("hide_overlays", False))
    try:
        blender_fmt, ext, response_fmt = _normalize_format(params.get("format", "PNG"))
    except ValueError as e:
        return {"error": str(e)}
    quality = int(params.get("quality", 85))
    compression = int(params.get("compression", 15))

    scene = bpy.context.scene
    old_path = scene.render.filepath
    old_res_x = scene.render.resolution_x
    old_res_y = scene.render.resolution_y
    old_res_pct = scene.render.resolution_percentage

    tmp = os.path.join(tempfile.gettempdir(), f"bb_viewport.{ext}")
    saved_img_settings = _apply_image_settings(scene, blender_fmt, quality, compression)
    scene.render.resolution_percentage = 100

    space = next((s for s in area.spaces if s.type == 'VIEW_3D'), None)
    saved_overlays = None
    if hide_overlays and space is not None and hasattr(space, "overlay"):
        saved_overlays = space.overlay.show_overlays
        space.overlay.show_overlays = False

    global _screenshot_overlay_text
    _screenshot_overlay_text = "" if hide_overlays else "+Z up   (Blender world)"
    overlay_handle = bpy.types.SpaceView3D.draw_handler_add(
        _draw_screenshot_overlay, (), 'WINDOW', 'POST_PIXEL'
    )
    try:
        _capture_viewport(scene, window, screen, area, region, tmp, width, height)
    finally:
        bpy.types.SpaceView3D.draw_handler_remove(overlay_handle, 'WINDOW')
        _screenshot_overlay_text = ""
        if saved_overlays is not None and space is not None:
            space.overlay.show_overlays = saved_overlays

    scene.render.filepath = old_path
    _restore_image_settings(scene, saved_img_settings)
    scene.render.resolution_x = old_res_x
    scene.render.resolution_y = old_res_y
    scene.render.resolution_percentage = old_res_pct

    with open(tmp, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    return {"image": data, "format": response_fmt, "bytes": len(data) * 3 // 4}


def get_viewport_collage(params):
    import numpy as np

    target = params.get("target", "ALL")
    zoom = params.get("zoom", 1.0)
    panel_w = max(160, int(320 * zoom))
    panel_h = max(90,  int(180 * zoom))
    try:
        blender_fmt, ext, response_fmt = _normalize_format(params.get("format", "PNG"))
    except ValueError as e:
        return {"error": str(e)}
    quality = int(params.get("quality", 85))
    compression = int(params.get("compression", 15))

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
    old_res_x  = scene.render.resolution_x
    old_res_y  = scene.render.resolution_y
    old_res_pct = scene.render.resolution_percentage

    # Per-panel intermediate is always PNG (lossless) so the final assembly is clean.
    # Final output is encoded per the requested format below.
    panel_saved = _apply_image_settings(scene, 'PNG', 100, 15)
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

    out = os.path.join(tempfile.gettempdir(), f"bb_collage.{ext}")
    _save_array_image(grid, out, blender_fmt, quality, compression)

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
    _restore_image_settings(scene, panel_saved)
    scene.render.resolution_x = old_res_x
    scene.render.resolution_y = old_res_y
    scene.render.resolution_percentage = old_res_pct

    with open(out, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    return {
        "image": data,
        "format": response_fmt,
        "bytes": len(data) * 3 // 4,
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
    """Fit objects in the viewport. By default ignores lights/cameras so they don't
    blow out the framing.

    targets: optional comma-separated names or single name. If given, fit only those.
    include_lights: include LIGHT/CAMERA objects in the fit. Default False.
    """
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    targets = params.get("targets") or ""
    include_lights = bool(params.get("include_lights", False))

    if targets or not include_lights:
        if isinstance(targets, list):
            names = [str(s).strip() for s in targets if s]
        else:
            names = [s.strip() for s in str(targets).split(",") if s.strip()]

        if names:
            from .common import resolve_targets
            objs, err = resolve_targets(names if len(names) > 1 else names[0])
            if err:
                return {"error": err}
        else:
            objs = [o for o in bpy.context.scene.objects
                    if include_lights or o.type not in {'LIGHT', 'CAMERA'}]

        if not objs:
            return {"error": "No objects to frame"}

        active = bpy.context.view_layer.objects.active
        was_edit = active is not None and active.mode == 'EDIT'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        saved_active = bpy.context.view_layer.objects.active
        saved_selected = list(bpy.context.selected_objects)

        bpy.ops.object.select_all(action='DESELECT')
        for o in objs:
            try:
                o.select_set(True)
            except Exception:
                pass
        bpy.context.view_layer.objects.active = objs[0]

        with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
            bpy.ops.view3d.view_selected(use_all_regions=False)

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

        return {"success": True, "framed": [o.name for o in objs],
                "include_lights": include_lights}

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


def add_camera(params):
    """Create a new camera and set it as the active scene camera.

    name:     required, unique.
    x, y, z:  world position (default 7, -7, 5).
    target:   optional object name to aim at. If omitted, uses target_x/y/z.
    target_x, target_y, target_z: world point to aim at (default 0, 0, 0).
    lens:     focal length in mm (default 50).
    """
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    if bpy.data.objects.get(name) is not None:
        return {"error": f"Object '{name}' already exists"}

    x = params.get("x", 7.0)
    y = params.get("y", -7.0)
    z = params.get("z", 5.0)
    lens = float(params.get("lens", 50.0))

    target = params.get("target")
    if target:
        tgt = bpy.data.objects.get(target)
        if tgt is None:
            return {"error": f"target '{target}' not found"}
        from .common import world_center
        tx, ty, tz = world_center(tgt)
    else:
        tx = params.get("target_x", 0.0)
        ty = params.get("target_y", 0.0)
        tz = params.get("target_z", 0.0)

    cam_data = bpy.data.cameras.new(name=name)
    cam_data.lens = lens
    obj = bpy.data.objects.new(name=name, object_data=cam_data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (x, y, z)

    direction = mathutils.Vector((tx, ty, tz)) - mathutils.Vector((x, y, z))
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    bpy.context.scene.camera = obj
    bpy.context.view_layer.update()

    return {
        "success": True,
        "camera": obj.name,
        "location": [round(x, 4), round(y, 4), round(z, 4)],
        "target": [round(tx, 4), round(ty, 4), round(tz, 4)],
        "lens": lens,
        "active": True,
    }


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
    "add_camera":              add_camera,
}

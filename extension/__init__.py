import bpy
import mathutils
import socket
import threading
import json
import base64
import os
import tempfile
import queue
import math
import hashlib
import time
import blf

PORT = 8765
_request_queue = queue.Queue()
_server_thread = None
_running = False

# --- History ---

_history = []

_NO_LOG_TOOLS = {
    "get_scene_tree", "get_viewport_screenshot", "get_viewport_collage",
    "get_history", "undo_steps", "undo_to",
}

# Tools that should NOT auto-append blender_status (read-only visual/query tools)
_NO_STATUS_TOOLS = {
    "get_blender_status", "get_viewport_screenshot", "get_viewport_collage",
    "get_scene_tree", "get_history",
}

def _log_operation(tool, params, label=""):
    op_id = hashlib.md5(
        f"{tool}{json.dumps(params, sort_keys=True)}{time.time()}".encode()
    ).hexdigest()[:8]
    _history.append({"id": op_id, "label": label or tool, "tool": tool, "params": params})
    return op_id


def _push_undo(label):
    """Push an explicit undo checkpoint. Needed after bmesh mutations since they
    bypass Blender's operator-driven undo system."""
    try:
        bpy.ops.ed.undo_push(message=str(label)[:64])
    except Exception:
        pass


def _world_bbox(obj):
    """World-space bounding box: (xmin, ymin, zmin, xmax, ymax, zmax)."""
    bb = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    xs = [v.x for v in bb]; ys = [v.y for v in bb]; zs = [v.z for v in bb]
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def _world_center(obj):
    """World-space bbox center of an object."""
    xmin, ymin, zmin, xmax, ymax, zmax = _world_bbox(obj)
    return ((xmin + xmax) * 0.5, (ymin + ymax) * 0.5, (zmin + zmax) * 0.5)


def _nearby_objects(world_pos, exclude_names=(), max_count=3):
    """Return up to max_count nearest mesh objects to world_pos, sorted by distance."""
    px, py, pz = world_pos
    cands = []
    for o in bpy.context.scene.objects:
        if o.name in exclude_names or o.type != 'MESH':
            continue
        cx, cy, cz = _world_center(o)
        d = math.sqrt((cx - px) ** 2 + (cy - py) ** 2 + (cz - pz) ** 2)
        cands.append((d, o.name, (cx, cy, cz)))
    cands.sort()
    return [
        {"name": n, "center": [round(c[0], 3), round(c[1], 3), round(c[2], 3)], "dist": round(d, 4)}
        for d, n, c in cands[:max_count]
    ]


# --- Screenshot overlay (blf-based axis label) ---

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


# --- Viewport helpers ---

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


# --- Tools (all run on main thread) ---

def get_scene_tree():
    def fmt_collection(col, depth=0):
        pad = "│   " * depth
        lines = [f"{pad}├── {col.name}/"]
        for obj in col.objects:
            active = " ● active" if obj == bpy.context.active_object else ""
            sel = " ◆" if obj.select_get() else ""
            lines.append(f"{pad}│   ├── {obj.name} [{obj.type}]{active}{sel}")
        for child in col.children:
            lines += fmt_collection(child, depth + 1)
        return lines

    lines = ["Scene Collection"]
    for col in bpy.context.scene.collection.children:
        lines += fmt_collection(col)
    for obj in bpy.context.scene.collection.objects:
        active = " ● active" if obj == bpy.context.active_object else ""
        sel = " ◆" if obj.select_get() else ""
        lines.append(f"├── {obj.name} [{obj.type}]{active}{sel}")
    return {"tree": "\n".join(lines)}


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

    # Resolve target objects to frame on
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

    # Save state so framing changes don't leak to user's session
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

    # Restore selection + mode
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


def get_history(params):
    return {"history": _history, "count": len(_history)}


def undo_steps(params):
    steps = max(1, min(params.get("steps", 1), len(_history)))
    window = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=window):
        for _ in range(steps):
            bpy.ops.ed.undo()
    for _ in range(steps):
        if _history:
            _history.pop()
    return {"success": True, "steps": steps, "history_remaining": len(_history)}


def undo_to(params):
    target_id = params.get("id")
    idx = next((i for i, h in enumerate(_history) if h["id"] == target_id), None)
    if idx is None:
        return {"error": f"ID '{target_id}' not found in history"}
    steps = len(_history) - idx - 1
    if steps > 0:
        window = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=window):
            for _ in range(steps):
                bpy.ops.ed.undo()
        del _history[idx + 1:]
    return {"success": True, "steps": steps}


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


def add_primitive(params):
    ptype = params.get("type", "CUBE").upper()
    name = params.get("name")
    if not name:
        return {"error": "'name' is required — give the object a meaningful name (e.g. 'Blade', 'Crossguard')"}

    location = params.get("location", [0, 0, 0])
    rotation_deg = params.get("rotation_deg", [0.0, 0.0, 0.0])
    rotation_rad = tuple(math.radians(a) for a in rotation_deg)

    bpy.ops.object.select_all(action='DESELECT')

    common = {"location": tuple(location), "rotation": rotation_rad}

    if ptype == "CUBE":
        bpy.ops.mesh.primitive_cube_add(size=params.get("size", 2.0), **common)
    elif ptype == "PLANE":
        bpy.ops.mesh.primitive_plane_add(size=params.get("size", 2.0), **common)
    elif ptype == "CYLINDER":
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=params.get("vertices", 32),
            radius=params.get("radius", 1.0),
            depth=params.get("depth", 2.0),
            end_fill_type=params.get("cap_fill", "NGON").upper(),
            **common,
        )
    elif ptype == "SPHERE":
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=params.get("segments", 32),
            ring_count=params.get("rings", 16),
            radius=params.get("radius", 1.0),
            **common,
        )
    elif ptype == "CONE":
        bpy.ops.mesh.primitive_cone_add(
            vertices=params.get("vertices", 32),
            radius1=params.get("radius1", 1.0),
            radius2=params.get("radius2", 0.0),
            depth=params.get("depth", 2.0),
            end_fill_type=params.get("cap_fill", "NGON").upper(),
            **common,
        )
    else:
        return {"error": f"Unknown primitive: {ptype}. Valid: CUBE, PLANE, CYLINDER, SPHERE, CONE"}

    obj = bpy.context.active_object
    if obj:
        obj.name = name
        if obj.data:
            obj.data.name = name
    return {"success": True, "object_name": obj.name if obj else None,
            "dimensions": [round(v, 4) for v in obj.dimensions] if obj else None}


def rename_object(params):
    old_name = params.get("old_name")
    new_name = params.get("new_name")
    if not old_name or not new_name:
        return {"error": "'old_name' and 'new_name' are required"}
    obj = bpy.data.objects.get(old_name)
    if obj is None:
        return {"error": f"Object '{old_name}' not found"}
    obj.name = new_name
    if obj.data:
        obj.data.name = new_name
    return {"success": True, "old_name": old_name, "new_name": obj.name}


def select_object(params):
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}

    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return {"success": True, "selected": name}


def scale_object(params):
    x = params.get("x", 1.0)
    y = params.get("y", 1.0)
    z = params.get("z", 1.0)
    bpy.ops.transform.resize(value=(x, y, z))
    return {"success": True}


def move_object(params):
    x = params.get("x", 0.0)
    y = params.get("y", 0.0)
    z = params.get("z", 0.0)
    bpy.ops.transform.translate(value=(x, y, z))
    return {"success": True}


def rotate_object(params):
    angle = params.get("angle", 0.0)
    axis = params.get("axis", "Z").upper()
    bpy.ops.transform.rotate(value=math.radians(angle), orient_axis=axis)
    return {"success": True}


def snap_to(params):
    """Move the active object so one of its bbox faces aligns with a face of a target object."""
    target_name = params.get("target")
    side = params.get("side", "Z_MAX").upper()
    source_side = params.get("source_side", "AUTO").upper()
    offset = params.get("offset", 0.0)

    obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if not target_name:
        return {"error": "'target' is required"}
    target = bpy.data.objects.get(target_name)
    if target is None:
        return {"error": f"Target '{target_name}' not found"}
    if target == obj:
        return {"error": "Cannot snap object to itself"}

    side_map = {
        "X_MIN": (0, "min"), "X_MAX": (0, "max"),
        "Y_MIN": (1, "min"), "Y_MAX": (1, "max"),
        "Z_MIN": (2, "min"), "Z_MAX": (2, "max"),
    }
    if side not in side_map:
        return {"error": f"Invalid side '{side}'. Use X_MIN|X_MAX|Y_MIN|Y_MAX|Z_MIN|Z_MAX"}
    axis_idx, target_which = side_map[side]

    if source_side == "AUTO":
        source_which = "max" if target_which == "min" else "min"
    elif source_side == "CENTER":
        source_which = "center"
    elif source_side in side_map:
        ax2, which2 = side_map[source_side]
        if ax2 != axis_idx:
            return {"error": f"source_side '{source_side}' must be on the same axis as side '{side}'"}
        source_which = which2
    else:
        return {"error": f"Invalid source_side '{source_side}'"}

    def _coord(o, ax, which):
        xmin, ymin, zmin, xmax, ymax, zmax = _world_bbox(o)
        lo = (xmin, ymin, zmin)[ax]
        hi = (xmax, ymax, zmax)[ax]
        if which == "min": return lo
        if which == "max": return hi
        return 0.5 * (lo + hi)

    target_coord = _coord(target, axis_idx, target_which)
    source_coord = _coord(obj, axis_idx, source_which)
    delta = target_coord - source_coord + offset
    obj.location[axis_idx] += delta

    return {
        "success": True,
        "target": target_name,
        "axis": "XYZ"[axis_idx],
        "target_side": side,
        "source_side": source_which,
        "target_coord": round(target_coord, 5),
        "source_coord_before": round(source_coord, 5),
        "source_coord_after": round(source_coord + delta, 5),
        "delta": round(delta, 5),
    }


def snap_to_grid(params):
    """Round the active object's location to multiples of `size` on the chosen axes."""
    obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    size = params.get("size", 0.1)
    axes = params.get("axes", "XYZ").upper()
    if size <= 0:
        return {"error": "size must be > 0"}

    snapped = []
    for i, ax in enumerate(("X", "Y", "Z")):
        if ax in axes:
            old = obj.location[i]
            new = round(old / size) * size
            obj.location[i] = new
            snapped.append({"axis": ax, "from": round(old, 5), "to": round(new, 5), "moved": round(new - old, 5)})

    return {"success": True, "grid_size": size, "axes": axes, "snapped": snapped,
            "location_after": [round(v, 5) for v in obj.location]}


def set_mode(params):
    mode = params.get("mode", "OBJECT").upper()
    bpy.ops.object.mode_set(mode=mode)
    return {"success": True, "mode": mode}


def delete_object(params):
    name = params.get("name")
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    active = bpy.context.active_object
    if active is None:
        return {"error": "No active object to delete"}
    deleted = active.name
    bpy.ops.object.delete()
    return {"success": True, "deleted": deleted}


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


def bevel(params):
    factor   = params.get("factor", 0.05)
    segments = params.get("segments", 1)
    affect   = params.get("affect", "EDGES").upper()
    obj = bpy.context.active_object
    dims = obj.dimensions if obj and obj.type == 'MESH' else None
    if dims:
        min_dim = min(d for d in [dims.x, dims.y, dims.z] if d > 0) if any(d > 0 for d in [dims.x, dims.y, dims.z]) else 1.0
        offset = factor * min_dim
    else:
        offset = factor
    bpy.ops.mesh.bevel(offset=offset, segments=segments, affect=affect)
    return {"success": True, "offset_world": round(offset, 5)}


def extrude(params):
    fx = params.get("x", 0.0)
    fy = params.get("y", 0.0)
    fz = params.get("z", 0.0)
    obj = bpy.context.active_object
    dims = obj.dimensions if obj and obj.type == 'MESH' else None
    x = fx * (dims.x if dims else 1.0)
    y = fy * (dims.y if dims else 1.0)
    z = fz * (dims.z if dims else 1.0)
    bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": (x, y, z)})
    return {"success": True, "translation_world": [round(x, 4), round(y, 4), round(z, 4)]}


def select_all(params):
    action = params.get("action", "SELECT").upper()
    bpy.ops.mesh.select_all(action=action)
    return {"success": True}


def select_by_axis(params):
    import bmesh
    axis       = params.get("axis", "Z").upper()
    factor     = params.get("factor", 0.5)
    comparison = params.get("comparison", "GREATER").upper()
    action     = params.get("action", "SELECT").upper()  # SELECT | DESELECT

    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with an active object"}

    bm = bmesh.from_edit_mesh(obj.data)
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)

    world_vals = [(obj.matrix_world @ v.co)[axis_idx] for v in bm.verts]
    v_min, v_max = min(world_vals), max(world_vals)
    threshold = v_min + factor * (v_max - v_min)

    for vert in bm.verts:
        val = (obj.matrix_world @ vert.co)[axis_idx]
        matches = (val > threshold) if comparison == "GREATER" else (val < threshold)
        if action == "DESELECT":
            if matches:
                vert.select = False
        else:
            vert.select = matches

    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    return {"success": True, "threshold_world": round(threshold, 4)}


def loop_cut(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    cuts     = params.get("cuts", 1)
    axis     = params.get("axis", "Z").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)

    bm = bmesh.from_edit_mesh(obj.data)
    mat = obj.matrix_world

    edges_to_cut = [
        e for e in bm.edges
        if abs(((mat @ e.verts[1].co) - (mat @ e.verts[0].co)).normalized()[axis_idx]) > 0.7
    ]

    if not edges_to_cut:
        return {"error": f"No edges found running along {axis} axis"}

    bmesh.ops.subdivide_edges(bm, edges=edges_to_cut, cuts=cuts, use_grid_fill=True)
    bmesh.update_edit_mesh(obj.data)
    _push_undo(f"loop_cut {axis} x{cuts}")

    return {"success": True, "cuts": cuts, "edges_subdivided": len(edges_to_cut)}


def add_modifier(params):
    mod_type = params.get("type", "SUBSURF").upper()
    name     = params.get("name", mod_type.capitalize())
    obj      = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    mod = obj.modifiers.new(name=name, type=mod_type)
    if hasattr(mod, 'levels'):
        mod.levels = params.get("levels", 2)
    if hasattr(mod, 'render_levels'):
        mod.render_levels = params.get("render_levels", params.get("levels", 2))
    if hasattr(mod, 'width'):
        mod.width = params.get("width", 0.1)
    if hasattr(mod, 'segments'):
        mod.segments = params.get("segments", 1)
    return {"success": True, "modifier": mod.name}


def move_vertices(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    fx = params.get("x", 0.0)
    fy = params.get("y", 0.0)
    fz = params.get("z", 0.0)
    dims = obj.dimensions
    scale = obj.scale
    sx = abs(scale.x) or 1.0
    sy = abs(scale.y) or 1.0
    sz = abs(scale.z) or 1.0
    # local-space deltas (v.co is local); world delta = local * scale
    dx = fx * dims.x / sx
    dy = fy * dims.y / sy
    dz = fz * dims.z / sz
    bm = bmesh.from_edit_mesh(obj.data)
    selected = [v for v in bm.verts if v.select]
    if not selected:
        return {"error": "No vertices selected"}
    for v in selected:
        v.co.x += dx
        v.co.y += dy
        v.co.z += dz
    bmesh.update_edit_mesh(obj.data)
    _push_undo("move_vertices")
    world_delta = [round(fx * dims.x, 5), round(fy * dims.y, 5), round(fz * dims.z, 5)]
    return {"success": True, "verts_moved": len(selected), "delta_world": world_delta}


def scale_vertices(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    sx = params.get("x", 1.0)
    sy = params.get("y", 1.0)
    sz = params.get("z", 1.0)
    pivot = params.get("pivot", "SELECTION")  # SELECTION | CURSOR | ORIGIN
    bm = bmesh.from_edit_mesh(obj.data)
    selected = [v for v in bm.verts if v.select]
    if not selected:
        return {"error": "No vertices selected"}
    if pivot == "SELECTION":
        cx = sum(v.co.x for v in selected) / len(selected)
        cy = sum(v.co.y for v in selected) / len(selected)
        cz = sum(v.co.z for v in selected) / len(selected)
    else:
        cx = cy = cz = 0.0
    for v in selected:
        v.co.x = cx + (v.co.x - cx) * sx
        v.co.y = cy + (v.co.y - cy) * sy
        v.co.z = cz + (v.co.z - cz) * sz
    bmesh.update_edit_mesh(obj.data)
    _push_undo("scale_vertices")
    return {"success": True, "verts_scaled": len(selected)}


def get_object_info(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    loc = obj.location
    scale = obj.scale
    rot = obj.rotation_euler
    bb = obj.bound_box
    world_bb = [obj.matrix_world @ mathutils.Vector(c) for c in bb]
    xs = [v.x for v in world_bb]
    ys = [v.y for v in world_bb]
    zs = [v.z for v in world_bb]
    info = {
        "name": obj.name,
        "type": obj.type,
        "location": [round(loc.x, 4), round(loc.y, 4), round(loc.z, 4)],
        "scale": [round(scale.x, 4), round(scale.y, 4), round(scale.z, 4)],
        "rotation_deg": [round(math.degrees(rot.x), 2), round(math.degrees(rot.y), 2), round(math.degrees(rot.z), 2)],
        "dimensions": [round(obj.dimensions.x, 4), round(obj.dimensions.y, 4), round(obj.dimensions.z, 4)],
        "world_bounds": {
            "x": [round(min(xs), 4), round(max(xs), 4)],
            "y": [round(min(ys), 4), round(max(ys), 4)],
            "z": [round(min(zs), 4), round(max(zs), 4)],
        },
    }
    if obj.type == 'MESH':
        info["vertex_count"] = len(obj.data.vertices)
        info["edge_count"] = len(obj.data.edges)
        info["face_count"] = len(obj.data.polygons)
    return {"success": True, "info": info}


def get_mesh_profile(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "No active mesh object"}
    axis = params.get("axis", "Z").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    other = [(i, n) for i, n in enumerate(['X', 'Y', 'Z']) if i != axis_idx]

    was_edit = obj.mode == 'EDIT'
    if was_edit:
        bm = bmesh.from_edit_mesh(obj.data)
    else:
        bm = bmesh.new()
        bm.from_mesh(obj.data)

    rings = {}
    for v in bm.verts:
        wco = obj.matrix_world @ v.co
        key = round(wco[axis_idx], 4)
        if key not in rings:
            rings[key] = {n: [] for _, n in other}
        for i, n in other:
            rings[key][n].append(wco[i])

    if not was_edit:
        bm.free()

    profile = []
    for pos in sorted(rings.keys()):
        entry = {axis: round(pos, 4)}
        for _, n in other:
            vals = rings[pos][n]
            lo, hi = min(vals), max(vals)
            entry[f"{n}_range"] = [round(lo, 4), round(hi, 4)]
            entry[f"{n}_width"] = round(hi - lo, 4)
        profile.append(entry)

    return {"success": True, "axis": axis, "rings": len(profile), "profile": profile}


def set_component_mode(params):
    mode = params.get("mode", "VERT").upper()
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    mode_map = {
        'VERT': (True, False, False),
        'EDGE': (False, True, False),
        'FACE': (False, False, True),
    }
    if mode not in mode_map:
        return {"error": f"Invalid mode '{mode}'. Use VERT, EDGE, or FACE"}
    bpy.context.tool_settings.mesh_select_mode = mode_map[mode]
    return {"success": True, "component_mode": mode}


def grow_selection(params):
    direction = params.get("direction", "GROW").upper()
    steps = params.get("steps", 1)
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    op = bpy.ops.mesh.select_more if direction == "GROW" else bpy.ops.mesh.select_less
    for _ in range(max(1, steps)):
        op()
    return {"success": True, "direction": direction, "steps": steps}


def _compute_rings(obj, axis_idx, decimals=4):
    """Group mesh vertices into rings by world-space coordinate on the given axis.
    Returns (bmesh, [(position_world, [vert_indices]), ...]) sorted by position ascending."""
    import bmesh
    bm = bmesh.from_edit_mesh(obj.data)
    mat = obj.matrix_world
    buckets = {}
    for i, v in enumerate(bm.verts):
        coord = (mat @ v.co)[axis_idx]
        key = round(coord, decimals)
        buckets.setdefault(key, []).append(i)
    sorted_keys = sorted(buckets.keys())
    return bm, [(k, buckets[k]) for k in sorted_keys]


def get_rings(params):
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = params.get("axis", "Z").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    _, rings = _compute_rings(obj, axis_idx)
    return {
        "success": True,
        "axis": axis,
        "ring_count": len(rings),
        "rings": [
            {"index": i, "position_world": round(pos, 4), "verts": len(verts)}
            for i, (pos, verts) in enumerate(rings)
        ],
    }


def select_ring(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = params.get("axis", "Z").upper()
    index = params.get("index", 0)
    action = params.get("action", "SELECT").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    bm, rings = _compute_rings(obj, axis_idx)
    if not rings:
        return {"error": "No rings found"}
    n = len(rings)
    if index < 0:
        index = n + index
    if index < 0 or index >= n:
        return {"error": f"Ring index {index} out of range [0, {n-1}]"}
    pos, vert_indices = rings[index]
    target = set(vert_indices)
    for i, v in enumerate(bm.verts):
        match = i in target
        if action == "DESELECT":
            if match:
                v.select = False
        elif action == "ADD":
            if match:
                v.select = True
        else:
            v.select = match
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    return {
        "success": True,
        "ring_index": index,
        "ring_count": n,
        "position_world": round(pos, 4),
        "verts_in_ring": len(vert_indices),
    }


def taper_end(params):
    """Collapse the extreme ring on an axis to a point in the two non-axis directions."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = params.get("axis", "Z").upper()
    end = params.get("end", "MAX").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    bm, rings = _compute_rings(obj, axis_idx)
    if not rings:
        return {"error": "No rings found"}
    ring_idx = len(rings) - 1 if end == "MAX" else 0
    pos, vert_indices = rings[ring_idx]
    verts = [bm.verts[i] for i in vert_indices]
    other_idxs = [i for i in range(3) if i != axis_idx]
    centroid = [0.0, 0.0, 0.0]
    for v in verts:
        centroid[0] += v.co.x; centroid[1] += v.co.y; centroid[2] += v.co.z
    centroid = [c / len(verts) for c in centroid]
    for v in verts:
        for ax in other_idxs:
            v.co[ax] = centroid[ax]
    bmesh.update_edit_mesh(obj.data)
    _push_undo(f"taper_end {axis} {end}")

    world_centroid = obj.matrix_world @ mathutils.Vector(centroid)
    nearby = _nearby_objects(
        (world_centroid.x, world_centroid.y, world_centroid.z),
        exclude_names={obj.name},
        max_count=2,
    )
    return {
        "success": True,
        "axis": axis,
        "end": end,
        "ring_index": ring_idx,
        "ring_count": len(rings),
        "collapsed_verts": len(verts),
        "position_world": round(pos, 4),
        "collapsed_world": [round(world_centroid.x, 4), round(world_centroid.y, 4), round(world_centroid.z, 4)],
        "nearby_objects": nearby,
    }


def taper_section(params):
    """Linearly interpolate scale across a span of rings on the two non-axis directions."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = params.get("axis", "Z").upper()
    from_idx = params.get("from_ring", 0)
    to_idx = params.get("to_ring", -1)
    x_start = params.get("x_start", 1.0)
    x_end = params.get("x_end", 1.0)
    y_start = params.get("y_start", 1.0)
    y_end = params.get("y_end", 1.0)
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    bm, rings = _compute_rings(obj, axis_idx)
    n = len(rings)
    if n == 0:
        return {"error": "No rings found"}
    if from_idx < 0: from_idx = n + from_idx
    if to_idx < 0: to_idx = n + to_idx
    if from_idx > to_idx:
        from_idx, to_idx = to_idx, from_idx
    if from_idx < 0 or to_idx >= n:
        return {"error": f"Ring range [{from_idx}, {to_idx}] out of [0, {n-1}]"}
    other_idxs = [i for i in range(3) if i != axis_idx]
    span = max(1, to_idx - from_idx)
    affected = 0
    for ring_i in range(from_idx, to_idx + 1):
        _, vert_indices = rings[ring_i]
        t = (ring_i - from_idx) / span
        sx = x_start + t * (x_end - x_start)
        sy = y_start + t * (y_end - y_start)
        verts = [bm.verts[i] for i in vert_indices]
        centroid = [0.0, 0.0, 0.0]
        for v in verts:
            centroid[0] += v.co.x; centroid[1] += v.co.y; centroid[2] += v.co.z
        centroid = [c / len(verts) for c in centroid]
        scales = {other_idxs[0]: sx, other_idxs[1]: sy} if len(other_idxs) == 2 else {}
        for v in verts:
            for ax, sc in scales.items():
                v.co[ax] = centroid[ax] + (v.co[ax] - centroid[ax]) * sc
        affected += len(verts)
    bmesh.update_edit_mesh(obj.data)
    _push_undo(f"taper_section {axis} {from_idx}..{to_idx}")
    return {
        "success": True,
        "axis": axis,
        "from_ring": from_idx,
        "to_ring": to_idx,
        "ring_count": n,
        "rings_scaled": to_idx - from_idx + 1,
        "verts_affected": affected,
    }


def select_between(params):
    import bmesh
    axis       = params.get("axis", "Z").upper()
    lo         = params.get("lo", 0.0)
    hi         = params.get("hi", 1.0)
    action     = params.get("action", "SELECT").upper()
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with an active object"}
    bm = bmesh.from_edit_mesh(obj.data)
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    world_vals = [(obj.matrix_world @ v.co)[axis_idx] for v in bm.verts]
    v_min, v_max = min(world_vals), max(world_vals)
    lo_thresh = v_min + lo * (v_max - v_min)
    hi_thresh = v_min + hi * (v_max - v_min)
    count = 0
    for vert in bm.verts:
        val = (obj.matrix_world @ vert.co)[axis_idx]
        in_range = lo_thresh <= val <= hi_thresh
        if action == "DESELECT":
            if in_range:
                vert.select = False
        else:
            vert.select = in_range
        if vert.select:
            count += 1
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    return {
        "success": True,
        "lo_world": round(lo_thresh, 4),
        "hi_world": round(hi_thresh, 4),
        "selected_count": count,
    }


def get_current_selection(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    bm = bmesh.from_edit_mesh(obj.data)
    sel = [v for v in bm.verts if v.select]
    if not sel:
        return {"success": True, "selected_count": 0, "centroid_world": None, "bbox_world": None}
    world_pos = [obj.matrix_world @ v.co for v in sel]
    xs = [p.x for p in world_pos]
    ys = [p.y for p in world_pos]
    zs = [p.z for p in world_pos]
    n = len(sel)
    return {
        "success": True,
        "selected_count": n,
        "centroid_world": [round(sum(xs)/n, 4), round(sum(ys)/n, 4), round(sum(zs)/n, 4)],
        "bbox_world": {
            "x": [round(min(xs), 4), round(max(xs), 4)],
            "y": [round(min(ys), 4), round(max(ys), 4)],
            "z": [round(min(zs), 4), round(max(zs), 4)],
        },
    }


def duplicate_object(params):
    name     = params.get("name")
    new_name = params.get("new_name")
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    active = bpy.context.active_object
    if active is None:
        return {"error": "No active object to duplicate"}
    original = active.name
    bpy.ops.object.duplicate(linked=False)
    dup = bpy.context.active_object
    if new_name and dup:
        dup.name = new_name
        if dup.data:
            dup.data.name = new_name
    return {"success": True, "original": original, "duplicate": dup.name if dup else None}


def join_objects(params):
    names = params.get("names", [])
    if len(names) < 2:
        return {"error": "'names' must list at least 2 objects"}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    first = None
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
        obj.select_set(True)
        if first is None:
            first = obj
    bpy.context.view_layer.objects.active = first
    bpy.ops.object.join()
    result = bpy.context.active_object
    return {"success": True, "result_object": result.name if result else None, "joined": names}


def apply_modifiers(params):
    name = params.get("name")
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    else:
        obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if obj.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    mod_names = [m.name for m in obj.modifiers]
    if not mod_names:
        return {"success": True, "applied": [], "object": obj.name}
    applied = []
    for mod_name in mod_names:
        if any(m.name == mod_name for m in obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=mod_name)
            applied.append(mod_name)
    return {"success": True, "applied": applied, "object": obj.name}


def get_blender_status(params):
    import bmesh as _bmesh
    obj = bpy.context.active_object

    status = {
        "mode": obj.mode if obj else "OBJECT",
        "active_object": obj.name if obj else None,
        "active_type": obj.type if obj else None,
        "selected_objects": [o.name for o in bpy.context.selected_objects],
        "last_action": (
            {"id": _history[-1]["id"], "label": _history[-1]["label"], "tool": _history[-1]["tool"]}
            if _history else None
        ),
        "history_depth": len(_history),
    }

    if obj:
        status["location"] = [round(v, 4) for v in obj.location]
        status["dimensions"] = [round(v, 4) for v in obj.dimensions]
        status["rotation_deg"] = [round(math.degrees(v), 2) for v in obj.rotation_euler]
        bb = obj.bound_box
        world_bb = [obj.matrix_world @ mathutils.Vector(c) for c in bb]
        status["world_z_range"] = [
            round(min(v.z for v in world_bb), 4),
            round(max(v.z for v in world_bb), 4),
        ]

    if obj and obj.mode == 'EDIT' and obj.type == 'MESH':
        bm = _bmesh.from_edit_mesh(obj.data)
        sel_verts  = [v for v in bm.verts if v.select]
        sel_edges  = [e for e in bm.edges if e.select]
        sel_faces  = [f for f in bm.faces if f.select]
        status["edit"] = {
            "component_mode": (
                "VERT"  if bpy.context.tool_settings.mesh_select_mode[0] else
                "EDGE"  if bpy.context.tool_settings.mesh_select_mode[1] else
                "FACE"
            ),
            "selected":  {"verts": len(sel_verts),  "edges": len(sel_edges),  "faces": len(sel_faces)},
            "total":     {"verts": len(bm.verts),    "edges": len(bm.edges),   "faces": len(bm.faces)},
        }
        if sel_verts:
            world_sel = [(obj.matrix_world @ v.co) for v in sel_verts]
            status["edit"]["selection_z_range"] = [
                round(min(v.z for v in world_sel), 4),
                round(max(v.z for v in world_sel), 4),
            ]

    return {"success": True, "status": status}


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


# --- Dispatch ---

TOOLS = {
    "get_scene_tree":        lambda p: get_scene_tree(),
    "get_viewport_screenshot": get_viewport_screenshot,
    "get_viewport_collage":  get_viewport_collage,
    "get_history":           get_history,
    "undo_steps":            undo_steps,
    "undo_to":               undo_to,
    "set_viewport_angle":    set_viewport_angle,
    "add_primitive":         add_primitive,
    "select_object":         select_object,
    "scale_object":          scale_object,
    "move_object":           move_object,
    "rotate_object":         rotate_object,
    "snap_to":               snap_to,
    "snap_to_grid":          snap_to_grid,
    "set_mode":              set_mode,
    "delete_object":         delete_object,
    "frame_scene":           frame_scene,
    "zoom_to_selected":      zoom_to_selected,
    "set_camera_position":   set_camera_position,
    "orbit_viewport":        orbit_viewport,
    "bevel":                 bevel,
    "extrude":               extrude,
    "select_all":            select_all,
    "select_by_axis":        select_by_axis,
    "loop_cut":              loop_cut,
    "add_modifier":          add_modifier,
    "move_vertices":         move_vertices,
    "scale_vertices":        scale_vertices,
    "get_object_info":       get_object_info,
    "get_mesh_profile":      get_mesh_profile,
    "get_blender_status":    get_blender_status,
    "rename_object":         rename_object,
    "set_component_mode":    set_component_mode,
    "grow_selection":        grow_selection,
    "select_between":        select_between,
    "get_current_selection": get_current_selection,
    "get_rings":             get_rings,
    "select_ring":           select_ring,
    "taper_end":             taper_end,
    "taper_section":         taper_section,
    "duplicate_object":      duplicate_object,
    "join_objects":          join_objects,
    "apply_modifiers":       apply_modifiers,
}


def execute_command(command):
    tool   = command.get("tool")
    params = command.get("params", {})
    label  = command.get("label", "")
    fn = TOOLS.get(tool)
    if fn is None:
        return {"error": f"Unknown tool: {tool}. Available: {list(TOOLS.keys())}"}
    try:
        result = fn(params)
        if tool not in _NO_LOG_TOOLS and result.get("success"):
            result["op_id"] = _log_operation(tool, params, label)
        if tool not in _NO_STATUS_TOOLS:
            try:
                result["blender_status"] = get_blender_status({}).get("status")
            except Exception:
                pass
        return result
    except Exception as e:
        return {"error": str(e)}


# --- Socket server ---

def handle_client(conn):
    try:
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break

        command = json.loads(data.decode().strip())
        result_event = threading.Event()
        result_box = [None]

        def on_main_thread():
            result_box[0] = execute_command(command)
            result_event.set()
            return None

        _request_queue.put(on_main_thread)
        result_event.wait(timeout=30)

        conn.sendall((json.dumps(result_box[0]) + "\n").encode())
    except Exception as e:
        try:
            conn.sendall((json.dumps({"error": str(e)}) + "\n").encode())
        except Exception:
            pass
    finally:
        conn.close()


def server_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("localhost", PORT))
    sock.listen(5)
    sock.settimeout(1.0)
    while _running:
        try:
            conn, _ = sock.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
        except socket.timeout:
            continue
    sock.close()


def process_queue():
    while not _request_queue.empty():
        try:
            fn = _request_queue.get_nowait()
            fn()
        except queue.Empty:
            break
    return 0.05


# --- UI ---

class BB_OT_StartServer(bpy.types.Operator):
    bl_idname = "bb.start_server"
    bl_label = "Start Server"

    def execute(self, context):
        global _server_thread, _running
        if _running:
            self.report({'INFO'}, "Already running")
            return {'FINISHED'}
        _running = True
        _server_thread = threading.Thread(target=server_loop, daemon=True)
        _server_thread.start()
        bpy.app.timers.register(process_queue, persistent=True)
        self.report({'INFO'}, f"Blender Buttons listening on port {PORT}")
        return {'FINISHED'}


class BB_OT_StopServer(bpy.types.Operator):
    bl_idname = "bb.stop_server"
    bl_label = "Stop Server"

    def execute(self, context):
        global _running
        _running = False
        if bpy.app.timers.is_registered(process_queue):
            bpy.app.timers.unregister(process_queue)
        self.report({'INFO'}, "Server stopped")
        return {'FINISHED'}


class BB_PT_Panel(bpy.types.Panel):
    bl_label = "Blender Buttons"
    bl_idname = "BB_PT_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        layout.operator("bb.start_server", icon='PLAY')
        layout.operator("bb.stop_server", icon='PAUSE')
        layout.label(text=f"Status: {'Running' if _running else 'Stopped'}")
        layout.label(text=f"Port: {PORT}")


classes = [BB_OT_StartServer, BB_OT_StopServer, BB_PT_Panel]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    global _running
    _running = False
    if bpy.app.timers.is_registered(process_queue):
        bpy.app.timers.unregister(process_queue)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

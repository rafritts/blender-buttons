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


# --- Object / group resolution ---

def _resolve_targets(targets):
    """Resolve a target spec into a list of bpy mesh objects.

    targets: str (single object or collection name), list[str], or None (→ active object).
    Collection names expand to all mesh objects inside (recursively).
    Returns (objects, error). On error, objects is None.
    """
    if targets is None:
        obj = bpy.context.active_object
        if obj is None:
            return None, "No active object and no targets specified"
        return [obj], None

    if isinstance(targets, str):
        targets = [targets]

    if not isinstance(targets, list) or not targets:
        return None, "'targets' must be a non-empty string or list of strings"

    objs = []
    seen = set()
    for name in targets:
        obj = bpy.data.objects.get(name)
        coll = bpy.data.collections.get(name)
        if obj is None and coll is None:
            return None, f"Target '{name}' not found (no object or collection by that name)"
        if obj is not None and obj.name not in seen:
            objs.append(obj)
            seen.add(obj.name)
        if coll is not None:
            for o in coll.all_objects:
                if o.type == 'MESH' and o.name not in seen:
                    objs.append(o)
                    seen.add(o.name)
    return objs, None


def _activate(obj):
    """Make obj the sole selected + active object."""
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _apply_scale(obj):
    """Bake object scale into mesh data so obj.scale becomes [1,1,1].
    Required for bevel and other width-based modifiers to behave uniformly."""
    _activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


# --- Placement DSL ---
#
# A placement spec is a dict combining one or more of these constraints. The
# resolver computes the world-space CENTER for a new object whose local bounds
# extend ±(w/2, d/2, h/2) from its origin.
#
# Axis convention: +X right, +Y back (away from front view), +Z up.
# So "front" = -Y, "back" = +Y, "left" = -X, "right" = +X.
#
# Whole-object placements (set all three axes):
#   {"on": "name"}            — rests on top of target, centered XY
#   {"under": "name"}         — rests under target, centered XY
#   {"centered_on": "name"}   — match XYZ centers of target
#   {"between": ["a", "b"]}   — centered on midpoint of two object centers
#   {"at_corner": {"of": "name", "corner": "front_left"|"front_right"|"back_left"|"back_right"}}
#                             — bottom-{corner} of new aligns with bottom-{corner} of target
#
# Adjacency placements (set 1 axis + center the other 2 on target):
#   {"left_of": "name"}       — flush to target's -X side, Y/Z centered on target
#   {"right_of": "name"}      — flush to target's +X side
#   {"in_front_of": "name"}   — flush to target's -Y side
#   {"behind": "name"}        — flush to target's +Y side
#
# Z overrides (always applied last, win conflicts):
#   {"on_floor": True}        — Z_MIN of new = 0
#   {"raise_to": value}       — Z_MIN of new = value
#
# Modifiers:
#   {"gap": 0.02}             — spacing for on/under/left_of/right_of/in_front_of/behind
#                               (positive = farther apart; negative = overlap)

def _resolve_placement(spec, dims):
    """Compute world-space center (cx, cy, cz) for a new object with given dims.
    spec is None or a dict (see vocabulary above). dims is (w, d, h)."""
    w, d, h = dims
    cx, cy, cz = 0.0, 0.0, 0.0

    if not spec:
        return (cx, cy, cz)

    if not isinstance(spec, dict):
        raise ValueError(f"Placement spec must be a dict, got {type(spec).__name__}")

    gap = spec.get("gap", 0.0)

    def bbox(name):
        o = bpy.data.objects.get(name)
        if o is None:
            raise ValueError(f"Placement target '{name}' not found")
        return _world_bbox(o)

    def center(name):
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(name)
        return ((xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2)

    # Whole-object placements
    if "on" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["on"])
        cx = (xmin + xmax) / 2
        cy = (ymin + ymax) / 2
        cz = zmax + h / 2 + gap
    elif "under" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["under"])
        cx = (xmin + xmax) / 2
        cy = (ymin + ymax) / 2
        cz = zmin - h / 2 - gap
    elif "between" in spec:
        names = spec["between"]
        if not (isinstance(names, list) and len(names) == 2):
            raise ValueError("'between' requires a list of exactly 2 object names")
        c1, c2 = center(names[0]), center(names[1])
        cx = (c1[0] + c2[0]) / 2
        cy = (c1[1] + c2[1]) / 2
        cz = (c1[2] + c2[2]) / 2
    elif "centered_on" in spec:
        cx, cy, cz = center(spec["centered_on"])
    elif "at_corner" in spec:
        ac = spec["at_corner"]
        if not isinstance(ac, dict) or "of" not in ac:
            raise ValueError("'at_corner' must be {'of': name, 'corner': 'front_left'|...}")
        corner = ac.get("corner", "front_left")
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(ac["of"])
        parts = corner.lower().split("_")
        if "front" in parts:
            cy = ymin + d / 2
        elif "back" in parts:
            cy = ymax - d / 2
        else:
            cy = (ymin + ymax) / 2
        if "left" in parts:
            cx = xmin + w / 2
        elif "right" in parts:
            cx = xmax - w / 2
        else:
            cx = (xmin + xmax) / 2
        cz = zmin + h / 2

    # Adjacency placements (override the above if present)
    if "left_of" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["left_of"])
        cx = xmin - w / 2 - gap
        cy = (ymin + ymax) / 2
        cz = (zmin + zmax) / 2
    elif "right_of" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["right_of"])
        cx = xmax + w / 2 + gap
        cy = (ymin + ymax) / 2
        cz = (zmin + zmax) / 2
    elif "in_front_of" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["in_front_of"])
        cx = (xmin + xmax) / 2
        cy = ymin - d / 2 - gap
        cz = (zmin + zmax) / 2
    elif "behind" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["behind"])
        cx = (xmin + xmax) / 2
        cy = ymax + d / 2 + gap
        cz = (zmin + zmax) / 2

    # Z overrides (last word)
    if spec.get("on_floor"):
        cz = h / 2
    if "raise_to" in spec:
        cz = spec["raise_to"] + h / 2

    return (cx, cy, cz)


def _describe_placement(obj):
    """Describe an object's position in relational terms — no raw coordinates.
    Walks the scene to find the nearest meaningful anchor (floor, another object's face)."""
    xmin, ymin, zmin, xmax, ymax, zmax = _world_bbox(obj)
    w, d, h = xmax - xmin, ymax - ymin, zmax - zmin

    parts = []
    if abs(zmin) < 1e-4:
        parts.append("standing on floor")
    elif zmin > 0:
        # Look for an object whose top is near this object's bottom
        for o in bpy.context.scene.objects:
            if o == obj or o.type != 'MESH':
                continue
            o_xmin, o_ymin, o_zmin, o_xmax, o_ymax, o_zmax = _world_bbox(o)
            if abs(zmin - o_zmax) < 1e-3 and o_xmin <= (xmin + xmax) / 2 <= o_xmax:
                parts.append(f"resting on '{o.name}'")
                break
        else:
            parts.append(f"floating {round(zmin, 3)}m above floor")

    parts.append(f"size {round(w, 3)}×{round(d, 3)}×{round(h, 3)}m (W×D×H)")
    return "; ".join(parts)


# --- Screenshot overlay (blf-based axis label) ---


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


def _build_primitive(name, ptype, target_dims, on, rotation_deg, extra=None):
    """Shared body for dimensional primitives. Creates the mesh at origin with
    canonical size, resizes to target_dims, applies scale (so obj.scale = [1,1,1]
    and modifiers see uniform scale), resolves placement, moves, and rotates.

    target_dims: (w, d, h) world-space bounding-box dims after resize.
    on: placement spec (None for origin).
    extra: dict of primitive-specific params (vertices, segments, cap_fill, etc.).
    """
    if not name:
        return {"error": "'name' is required — give the object a meaningful name"}
    if bpy.data.objects.get(name) is not None:
        return {"error": f"Object '{name}' already exists — choose a different name or delete the old one first"}

    extra = extra or {}
    rotation_rad = tuple(math.radians(a) for a in (rotation_deg or [0, 0, 0]))

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')

    # Create at origin with unit-ish defaults; we'll resize after.
    if ptype == "BOX":
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    elif ptype == "PLANE":
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, 0, 0))
    elif ptype == "CYLINDER":
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=extra.get("vertices", 32),
            radius=0.5, depth=1.0,
            end_fill_type=extra.get("cap_fill", "NGON").upper(),
            location=(0, 0, 0),
        )
    elif ptype == "SPHERE":
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=extra.get("segments", 32),
            ring_count=extra.get("rings", 16),
            radius=0.5,
            location=(0, 0, 0),
        )
    elif ptype == "CONE":
        # Cone has two radii. We pass both as half-fractions of the wider dim
        # and rely on the resize step to bring it to spec.
        r1 = extra.get("radius1_norm", 0.5)
        r2 = extra.get("radius2_norm", 0.0)
        bpy.ops.mesh.primitive_cone_add(
            vertices=extra.get("vertices", 32),
            radius1=r1, radius2=r2, depth=1.0,
            end_fill_type=extra.get("cap_fill", "NGON").upper(),
            location=(0, 0, 0),
        )
    else:
        return {"error": f"Unknown primitive: {ptype}"}

    obj = bpy.context.active_object
    obj.name = name
    if obj.data:
        obj.data.name = name

    # Resize to target dims. For PLANE, h is irrelevant (single quad).
    w, d, h = target_dims
    if ptype == "PLANE":
        obj.scale = (max(w, 1e-6), max(d, 1e-6), 1.0)
    else:
        obj.scale = (max(w, 1e-6), max(d, 1e-6), max(h, 1e-6))
    bpy.context.view_layer.update()

    # Bake scale so obj.scale = [1,1,1] and bbox dims are correct world dims.
    _activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Resolve placement, then move. The current bbox center is the origin (0,0,0).
    try:
        cx, cy, cz = _resolve_placement(on, target_dims)
    except ValueError as e:
        # Roll back the created object so a bad placement doesn't leave debris.
        bpy.data.objects.remove(obj, do_unlink=True)
        return {"error": str(e)}
    obj.location = (cx, cy, cz)
    obj.rotation_euler = rotation_rad
    bpy.context.view_layer.update()

    xmin, ymin, zmin, xmax, ymax, zmax = _world_bbox(obj)
    return {
        "success": True,
        "object_name": obj.name,
        "dimensions": [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)],
        "world_bounds": {
            "x": [round(xmin, 4), round(xmax, 4)],
            "y": [round(ymin, 4), round(ymax, 4)],
            "z": [round(zmin, 4), round(zmax, 4)],
        },
    }


def add_box(params):
    return _build_primitive(
        name=params.get("name"),
        ptype="BOX",
        target_dims=(params.get("width", 1.0), params.get("depth", 1.0), params.get("height", 1.0)),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
    )


def add_plane(params):
    return _build_primitive(
        name=params.get("name"),
        ptype="PLANE",
        target_dims=(params.get("width", 1.0), params.get("depth", 1.0), 0.0),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
    )


def add_cylinder(params):
    radius = params.get("radius", 0.5)
    return _build_primitive(
        name=params.get("name"),
        ptype="CYLINDER",
        target_dims=(radius * 2, radius * 2, params.get("height", 1.0)),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
        extra={"vertices": params.get("vertices", 32), "cap_fill": params.get("cap_fill", "NGON")},
    )


def add_sphere(params):
    radius = params.get("radius", 0.5)
    return _build_primitive(
        name=params.get("name"),
        ptype="SPHERE",
        target_dims=(radius * 2, radius * 2, radius * 2),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
        extra={"segments": params.get("segments", 32), "rings": params.get("rings", 16)},
    )


def add_cone(params):
    r_bottom = params.get("radius_bottom", 0.5)
    r_top = params.get("radius_top", 0.0)
    height = params.get("height", 1.0)
    r_max = max(r_bottom, r_top, 1e-6)
    # Normalize radii to the unit primitive (max radius = 0.5), then resize.
    return _build_primitive(
        name=params.get("name"),
        ptype="CONE",
        target_dims=(r_max * 2, r_max * 2, height),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
        extra={
            "vertices": params.get("vertices", 32),
            "cap_fill": params.get("cap_fill", "NGON"),
            "radius1_norm": (r_bottom / r_max) * 0.5,
            "radius2_norm": (r_top / r_max) * 0.5,
        },
    )


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


def nudge(params):
    """Move objects by a relative offset in semantic directions.
    right/left → ±X, back/forward → ±Y, up/down → ±Z. Negative values flip direction."""
    targets = params.get("targets")
    objs, err = _resolve_targets(targets)
    if err:
        return {"error": err}

    dx = params.get("right", 0.0) - params.get("left", 0.0)
    dy = params.get("back", 0.0) - params.get("forward", 0.0)
    dz = params.get("up", 0.0) - params.get("down", 0.0)

    for o in objs:
        o.location.x += dx
        o.location.y += dy
        o.location.z += dz
    bpy.context.view_layer.update()
    return {"success": True, "moved": [o.name for o in objs],
            "delta": [round(dx, 5), round(dy, 5), round(dz, 5)]}


def resize(params):
    """Resize objects to absolute world-space dimensions (width × depth × height).
    Each dim is optional; omitted dims preserve current size."""
    targets = params.get("targets")
    objs, err = _resolve_targets(targets)
    if err:
        return {"error": err}

    w = params.get("width")
    d = params.get("depth")
    h = params.get("height")
    if w is None and d is None and h is None:
        return {"error": "resize requires at least one of width, depth, height"}

    results = []
    for o in objs:
        xmin, ymin, zmin, xmax, ymax, zmax = _world_bbox(o)
        cur_w, cur_d, cur_h = xmax - xmin, ymax - ymin, zmax - zmin
        sx = (w / cur_w) if (w is not None and cur_w > 1e-9) else 1.0
        sy = (d / cur_d) if (d is not None and cur_d > 1e-9) else 1.0
        sz = (h / cur_h) if (h is not None and cur_h > 1e-9) else 1.0
        o.scale.x *= sx
        o.scale.y *= sy
        o.scale.z *= sz
        bpy.context.view_layer.update()
        # Bake so future modifiers see uniform scale.
        _activate(o)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        xmin, ymin, zmin, xmax, ymax, zmax = _world_bbox(o)
        results.append({"name": o.name, "dims": [round(xmax - xmin, 4),
                                                  round(ymax - ymin, 4),
                                                  round(zmax - zmin, 4)]})
    return {"success": True, "resized": results}


def apply_transform(params):
    """Bake object transforms into mesh data. After applying scale, obj.scale
    becomes [1,1,1] and modifiers (especially bevel) behave uniformly. Apply
    rotation to clear rotation_euler. Apply location to move the object's
    origin to the world origin (rare; usually undesirable)."""
    targets = params.get("targets")
    objs, err = _resolve_targets(targets)
    if err:
        return {"error": err}
    do_scale = params.get("scale", True)
    do_rotation = params.get("rotation", False)
    do_location = params.get("location", False)

    for o in objs:
        _activate(o)
        bpy.ops.object.transform_apply(
            location=do_location, rotation=do_rotation, scale=do_scale
        )
    return {"success": True,
            "applied_to": [o.name for o in objs],
            "scale": do_scale, "rotation": do_rotation, "location": do_location}


def rotate_object(params):
    """Rotate one or more objects by an angle around an axis."""
    targets = params.get("targets")
    angle = params.get("angle", 0.0)
    axis = params.get("axis", "Z").upper()
    objs, err = _resolve_targets(targets)
    if err:
        return {"error": err}

    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    rad = math.radians(angle)
    for o in objs:
        o.rotation_euler[axis_idx] += rad
    bpy.context.view_layer.update()
    return {"success": True, "rotated": [o.name for o in objs],
            "angle_deg": angle, "axis": axis}


# --- Relational queries (no coordinate leakage) ---

def describe(params):
    """Describe an object in relational terms — what it rests on, what it's beside,
    and its dimensions. No raw world coordinates in the output."""
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}

    xmin, ymin, zmin, xmax, ymax, zmax = _world_bbox(obj)
    w, d, h = xmax - xmin, ymax - ymin, zmax - zmin

    relations = []
    # Floor?
    if abs(zmin) < 1e-3:
        relations.append("standing on floor")

    # Resting on / under another object?
    for o in bpy.context.scene.objects:
        if o == obj or o.type != 'MESH':
            continue
        o_xmin, o_ymin, o_zmin, o_xmax, o_ymax, o_zmax = _world_bbox(o)
        # X/Y overlap test
        xy_overlap = (xmin < o_xmax and xmax > o_xmin and ymin < o_ymax and ymax > o_ymin)
        if xy_overlap and abs(zmin - o_zmax) < 1e-3:
            relations.append(f"resting on '{o.name}'")
        elif xy_overlap and abs(zmax - o_zmin) < 1e-3:
            relations.append(f"directly under '{o.name}'")
        # Side-flush
        z_overlap = (zmin < o_zmax and zmax > o_zmin)
        y_overlap = (ymin < o_ymax and ymax > o_ymin)
        x_overlap = (xmin < o_xmax and xmax > o_xmin)
        if z_overlap and y_overlap:
            if abs(xmax - o_xmin) < 1e-3:
                relations.append(f"flush left of '{o.name}'")
            elif abs(xmin - o_xmax) < 1e-3:
                relations.append(f"flush right of '{o.name}'")
        if z_overlap and x_overlap:
            if abs(ymax - o_ymin) < 1e-3:
                relations.append(f"flush in front of '{o.name}'")
            elif abs(ymin - o_ymax) < 1e-3:
                relations.append(f"flush behind '{o.name}'")

    if not relations:
        relations.append(f"freestanding (origin {round(zmin, 3)}m above floor)")

    dim_str = f"size {round(w, 3)} × {round(d, 3)} × {round(h, 3)} m (W×D×H)"
    sentence = f"{name}: {'; '.join(relations)}; {dim_str}"

    return {
        "success": True,
        "name": name,
        "description": sentence,
        "relations": relations,
        "dimensions": {"width": round(w, 4), "depth": round(d, 4), "height": round(h, 4)},
    }


def distance_between(params):
    """Centre-to-centre distance between two objects. Optionally restricted to one axis."""
    a_name = params.get("a")
    b_name = params.get("b")
    axis = params.get("axis", "ANY").upper()
    a = bpy.data.objects.get(a_name) if a_name else None
    b = bpy.data.objects.get(b_name) if b_name else None
    if a is None or b is None:
        return {"error": f"Both 'a' and 'b' must be existing object names (a={a_name}, b={b_name})"}

    ca = _world_center(a)
    cb = _world_center(b)
    dx, dy, dz = cb[0] - ca[0], cb[1] - ca[1], cb[2] - ca[2]

    if axis == "X":
        dist = abs(dx)
    elif axis == "Y":
        dist = abs(dy)
    elif axis == "Z":
        dist = abs(dz)
    else:
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

    return {"success": True, "a": a_name, "b": b_name, "axis": axis, "distance": round(dist, 5)}


def gap_between(params):
    """Smallest empty distance between two objects' bounding boxes on each axis.
    Negative gap = overlap. Useful for checking 'are these touching?' or 'how far apart?'"""
    a_name = params.get("a")
    b_name = params.get("b")
    a = bpy.data.objects.get(a_name) if a_name else None
    b = bpy.data.objects.get(b_name) if b_name else None
    if a is None or b is None:
        return {"error": f"Both 'a' and 'b' must be existing object names"}

    ax = _world_bbox(a)
    bx = _world_bbox(b)
    gx = max(bx[0] - ax[3], ax[0] - bx[3])
    gy = max(bx[1] - ax[4], ax[1] - bx[4])
    gz = max(bx[2] - ax[5], ax[2] - bx[5])

    touching_axes = [n for n, g in zip("XYZ", (gx, gy, gz)) if abs(g) < 1e-4]
    return {"success": True, "a": a_name, "b": b_name,
            "gap_x": round(gx, 5), "gap_y": round(gy, 5), "gap_z": round(gz, 5),
            "touching_on_axes": touching_axes}


def is_aligned(params):
    """Check if two objects share an aligned face or center on the given side.
    side: TOP|BOTTOM|LEFT|RIGHT|FRONT|BACK|CENTER_X|CENTER_Y|CENTER_Z"""
    a_name = params.get("a")
    b_name = params.get("b")
    side = params.get("side", "TOP").upper()
    tolerance = params.get("tolerance", 1e-3)
    a = bpy.data.objects.get(a_name) if a_name else None
    b = bpy.data.objects.get(b_name) if b_name else None
    if a is None or b is None:
        return {"error": f"Both 'a' and 'b' must be existing object names"}

    a_xmin, a_ymin, a_zmin, a_xmax, a_ymax, a_zmax = _world_bbox(a)
    b_xmin, b_ymin, b_zmin, b_xmax, b_ymax, b_zmax = _world_bbox(b)

    sides = {
        "TOP":      (a_zmax, b_zmax),
        "BOTTOM":   (a_zmin, b_zmin),
        "LEFT":     (a_xmin, b_xmin),
        "RIGHT":    (a_xmax, b_xmax),
        "FRONT":    (a_ymin, b_ymin),
        "BACK":     (a_ymax, b_ymax),
        "CENTER_X": ((a_xmin + a_xmax) / 2, (b_xmin + b_xmax) / 2),
        "CENTER_Y": ((a_ymin + a_ymax) / 2, (b_ymin + b_ymax) / 2),
        "CENTER_Z": ((a_zmin + a_zmax) / 2, (b_zmin + b_zmax) / 2),
    }
    if side not in sides:
        return {"error": f"Invalid side '{side}'. Use {list(sides.keys())}"}
    va, vb = sides[side]
    return {"success": True, "a": a_name, "b": b_name, "side": side,
            "aligned": abs(va - vb) < tolerance, "difference": round(va - vb, 5)}


# --- Relational verbs (operate on named parts; never expose coords) ---

def match_dimension(params):
    """Resize 'target' so its size on the named axis equals 'reference's size on the same axis."""
    target_name = params.get("target")
    reference_name = params.get("reference")
    axis = params.get("axis", "Z").upper()
    target = bpy.data.objects.get(target_name) if target_name else None
    reference = bpy.data.objects.get(reference_name) if reference_name else None
    if target is None or reference is None:
        return {"error": f"Both 'target' and 'reference' must be existing object names"}

    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    t_bb = _world_bbox(target)
    r_bb = _world_bbox(reference)
    t_size = (t_bb[3], t_bb[4], t_bb[5])[axis_idx] - (t_bb[0], t_bb[1], t_bb[2])[axis_idx]
    r_size = (r_bb[3], r_bb[4], r_bb[5])[axis_idx] - (r_bb[0], r_bb[1], r_bb[2])[axis_idx]
    if t_size < 1e-9:
        return {"error": f"Target '{target_name}' has zero extent on {axis}"}
    factor = r_size / t_size
    scale = [1.0, 1.0, 1.0]
    scale[axis_idx] = factor
    target.scale.x *= scale[0]
    target.scale.y *= scale[1]
    target.scale.z *= scale[2]
    bpy.context.view_layer.update()
    _activate(target)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return {"success": True, "target": target_name, "axis": axis,
            "new_size": round(r_size, 5), "factor_applied": round(factor, 5)}


def mirror_across(params):
    """Duplicate parts and mirror the copies across a world axis plane.
    plane: 'X' (mirror across YZ plane through origin), 'Y', or 'Z'.
    Returns names of the new mirrored objects.
    The mirror is via duplicate + flip scale + apply; no constraints, fully independent objects."""
    targets = params.get("targets")
    plane = params.get("plane", "X").upper()
    suffix = params.get("suffix", "_mirror")
    objs, err = _resolve_targets(targets)
    if err:
        return {"error": err}

    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(plane, 0)
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    new_names = []
    for o in objs:
        _activate(o)
        bpy.ops.object.duplicate(linked=False)
        dup = bpy.context.active_object
        dup_name = o.name + suffix
        if bpy.data.objects.get(dup_name) is None:
            dup.name = dup_name
            if dup.data:
                dup.data.name = dup_name
        # Flip the chosen axis: scale = -1, location = -location
        s = list(dup.scale)
        s[axis_idx] *= -1
        dup.scale = s
        loc = list(dup.location)
        loc[axis_idx] *= -1
        dup.location = loc
        bpy.context.view_layer.update()
        # Apply scale so winding/normals are correct
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        new_names.append(dup.name)

    return {"success": True, "mirrored_from": [o.name for o in objs],
            "mirrored_to": new_names, "plane": plane}


def distribute_evenly(params):
    """Position parts so their centers are evenly spaced between two anchor objects' centers.
    The first and last anchor positions are NOT occupied; only the in-between slots get parts.
    e.g. 5 slats between rail_top and rail_bottom on Z → 5 evenly spaced positions strictly
    between the two rail centers."""
    targets = params.get("targets")
    between = params.get("between")
    axis = params.get("axis", "X").upper()
    objs, err = _resolve_targets(targets)
    if err:
        return {"error": err}
    if not (isinstance(between, list) and len(between) == 2):
        return {"error": "'between' must be a list of 2 object names"}
    a = bpy.data.objects.get(between[0])
    b = bpy.data.objects.get(between[1])
    if a is None or b is None:
        return {"error": f"Anchor objects not found: {between}"}

    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 0)
    ca = _world_center(a)[axis_idx]
    cb = _world_center(b)[axis_idx]
    lo, hi = min(ca, cb), max(ca, cb)
    n = len(objs)
    # Evenly spaced strictly between: positions at lo + step*(i+1) where step = (hi-lo)/(n+1)
    step = (hi - lo) / (n + 1)
    placed = []
    for i, o in enumerate(objs):
        target_pos = lo + step * (i + 1)
        cur_center = _world_center(o)[axis_idx]
        delta = target_pos - cur_center
        loc = list(o.location)
        loc[axis_idx] += delta
        o.location = loc
        placed.append({"name": o.name, "axis_pos": round(target_pos, 5)})
    bpy.context.view_layer.update()
    return {"success": True, "axis": axis, "count": n, "spacing": round(step, 5),
            "placed": placed}


def array_at_corners(params):
    """Duplicate a prototype object 4 times, placing each copy at a corner of a target object's
    footprint. Each copy is named with the corner suffix.
    The original prototype is removed unless keep_original=True.
    z_anchor: 'bottom' (default, copies sit on floor if standing_on_floor=True) or 'match' (copies
    align z to target).
    standing_on_floor: if True, copies' z_min = 0 regardless of target z."""
    prototype = params.get("prototype")
    of = params.get("of")
    standing_on_floor = params.get("standing_on_floor", True)
    keep_original = params.get("keep_original", False)
    name_prefix = params.get("name_prefix", prototype)

    proto = bpy.data.objects.get(prototype) if prototype else None
    target = bpy.data.objects.get(of) if of else None
    if proto is None:
        return {"error": f"Prototype '{prototype}' not found"}
    if target is None:
        return {"error": f"Target 'of'={of} not found"}

    t_xmin, t_ymin, t_zmin, t_xmax, t_ymax, t_zmax = _world_bbox(target)
    p_xmin, p_ymin, p_zmin, p_xmax, p_ymax, p_zmax = _world_bbox(proto)
    p_w = p_xmax - p_xmin
    p_d = p_ymax - p_ymin
    p_h = p_zmax - p_zmin

    corners = [
        ("front_left",  t_xmin + p_w / 2, t_ymin + p_d / 2),
        ("front_right", t_xmax - p_w / 2, t_ymin + p_d / 2),
        ("back_left",   t_xmin + p_w / 2, t_ymax - p_d / 2),
        ("back_right",  t_xmax - p_w / 2, t_ymax - p_d / 2),
    ]

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    placed = []
    for corner_name, cx, cy in corners:
        _activate(proto)
        bpy.ops.object.duplicate(linked=False)
        dup = bpy.context.active_object
        new_name = f"{name_prefix}_{corner_name}"
        if bpy.data.objects.get(new_name) is None:
            dup.name = new_name
            if dup.data:
                dup.data.name = new_name
        cz = (p_h / 2) if standing_on_floor else _world_center(proto)[2]
        dup.location = (cx, cy, cz)
        placed.append(dup.name)

    bpy.context.view_layer.update()
    if not keep_original:
        bpy.data.objects.remove(proto, do_unlink=True)

    return {"success": True, "placed": placed, "of": of, "removed_prototype": not keep_original}


def array_along(params):
    """Duplicate a prototype N times, spacing copies evenly between two anchor objects' centers.
    Like distribute_evenly but creates the copies for you. The prototype itself is removed unless
    keep_original=True. The N copies occupy positions strictly between the anchors."""
    prototype = params.get("prototype")
    count = params.get("count", 3)
    between = params.get("between")
    axis = params.get("axis", "X").upper()
    keep_original = params.get("keep_original", False)
    name_prefix = params.get("name_prefix", prototype)

    proto = bpy.data.objects.get(prototype) if prototype else None
    if proto is None:
        return {"error": f"Prototype '{prototype}' not found"}
    if not (isinstance(between, list) and len(between) == 2):
        return {"error": "'between' must be a list of 2 object names"}
    a = bpy.data.objects.get(between[0])
    b = bpy.data.objects.get(between[1])
    if a is None or b is None:
        return {"error": f"Anchor objects not found: {between}"}
    if count < 1:
        return {"error": "count must be >= 1"}

    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 0)
    ca = _world_center(a)[axis_idx]
    cb = _world_center(b)[axis_idx]
    lo, hi = min(ca, cb), max(ca, cb)
    step = (hi - lo) / (count + 1)

    proto_center = _world_center(proto)
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    placed = []
    for i in range(count):
        target_pos = lo + step * (i + 1)
        _activate(proto)
        bpy.ops.object.duplicate(linked=False)
        dup = bpy.context.active_object
        new_name = f"{name_prefix}_{i + 1}"
        if bpy.data.objects.get(new_name) is None:
            dup.name = new_name
            if dup.data:
                dup.data.name = new_name
        loc = list(dup.location)
        cur = _world_center(dup)[axis_idx]
        loc[axis_idx] += target_pos - cur
        dup.location = loc
        placed.append(dup.name)

    bpy.context.view_layer.update()
    if not keep_original:
        bpy.data.objects.remove(proto, do_unlink=True)

    return {"success": True, "axis": axis, "count": count, "spacing": round(step, 5),
            "placed": placed, "removed_prototype": not keep_original}


# --- Groups (Blender collections) ---

def group(params):
    """Create a named collection containing the given parts (and any existing children).
    Operations that accept 'targets' can be given a group name to act on all members."""
    name = params.get("name")
    parts = params.get("parts", [])
    if not name:
        return {"error": "'name' is required"}
    if not isinstance(parts, list) or not parts:
        return {"error": "'parts' must be a non-empty list of object names"}

    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)

    added = []
    for p in parts:
        obj = bpy.data.objects.get(p)
        if obj is None:
            return {"error": f"Object '{p}' not found"}
        # Link to group collection if not already there
        if obj.name not in coll.objects:
            coll.objects.link(obj)
            added.append(p)
        # Unlink from scene root if present (so it lives only in the group)
        if obj.name in bpy.context.scene.collection.objects:
            try:
                bpy.context.scene.collection.objects.unlink(obj)
            except Exception:
                pass
    return {"success": True, "group": name, "members": [o.name for o in coll.objects],
            "newly_added": added}


def parts_in(params):
    """List the parts inside a named group (collection)."""
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    coll = bpy.data.collections.get(name)
    if coll is None:
        return {"error": f"Group '{name}' not found"}
    return {"success": True, "group": name, "parts": [o.name for o in coll.all_objects]}


def ungroup(params):
    """Remove a group (collection) — its objects move back to the scene root, they are NOT deleted."""
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    coll = bpy.data.collections.get(name)
    if coll is None:
        return {"error": f"Group '{name}' not found"}
    members = [o.name for o in coll.all_objects]
    for o in list(coll.objects):
        if o.name not in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.link(o)
        coll.objects.unlink(o)
    bpy.data.collections.remove(coll)
    return {"success": True, "removed_group": name, "members_freed": members}


# --- Bundled finishes ---

def smooth_edges(params):
    """Round off the sharp edges of one or more objects.
    Adds a BEVEL modifier with angle-limit (only sharp edges get beveled, not coplanar ones),
    then shade_smooth + auto_smooth so the rounded edges read as smooth, not faceted.
    width: bevel offset in world units (default 2mm). segments: more = smoother curve.
    angle_limit: edges sharper than this (degrees) get beveled. Default 30°."""
    targets = params.get("targets")
    width = params.get("width", 0.002)
    segments = params.get("segments", 2)
    angle_limit_deg = params.get("angle_limit", 30.0)
    objs, err = _resolve_targets(targets)
    if err:
        return {"error": err}

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    processed = []
    for o in objs:
        if o.type != 'MESH':
            continue
        _activate(o)
        # If object has non-uniform scale, bake it first so the bevel width is consistent.
        if any(abs(s - 1.0) > 1e-4 for s in o.scale):
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        # Remove any existing Smooth_Bevel so calls are idempotent
        for m in list(o.modifiers):
            if m.name == "Smooth_Bevel":
                o.modifiers.remove(m)

        mod = o.modifiers.new(name="Smooth_Bevel", type='BEVEL')
        mod.width = width
        mod.segments = segments
        mod.limit_method = 'ANGLE'
        mod.angle_limit = math.radians(angle_limit_deg)
        mod.miter_outer = 'MITER_ARC'
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.ops.object.shade_smooth()
        # Enable auto-smooth (Blender 4.x: use_auto_smooth lives on mesh)
        if hasattr(o.data, "use_auto_smooth"):
            o.data.use_auto_smooth = True
            o.data.auto_smooth_angle = math.radians(angle_limit_deg)
        processed.append(o.name)

    return {"success": True, "smoothed": processed, "width": width,
            "segments": segments, "angle_limit": angle_limit_deg}


def round_corners(params):
    """Round specific vertical corner edges of an object by a real-world radius.

    target:   object name.
    corners:  list of "front_left" | "front_right" | "back_left" | "back_right".
              Each name identifies a vertical edge at that XY corner of the bbox.
    radius:   bevel offset in meters (the rounding radius). Default 0.02 (2cm).
    segments: number of segments in the round; more = smoother curve. Default 6.

    Works on already-beveled meshes: each "corner" is matched within a tolerance of
    radius/4 in XY, so smooth_edges'd geometry still finds the right edges.
    After beveling, shade_smooth is re-applied so the curve reads as smooth."""
    import bmesh
    target = params.get("target")
    corners = params.get("corners", [])
    radius = params.get("radius", 0.02)
    segments = params.get("segments", 6)

    obj = bpy.data.objects.get(target) if target else None
    if obj is None:
        return {"error": f"Object '{target}' not found"}
    if obj.type != 'MESH':
        return {"error": f"'{target}' is not a mesh"}
    if not corners:
        return {"error": "'corners' must be a non-empty list (front_left|front_right|back_left|back_right)"}

    _activate(obj)
    xmin, ymin, zmin, xmax, ymax, zmax = _world_bbox(obj)

    corner_map = {
        "front_left":  (xmin, ymin),
        "front_right": (xmax, ymin),
        "back_left":   (xmin, ymax),
        "back_right":  (xmax, ymax),
    }
    bad = [c for c in corners if c not in corner_map]
    if bad:
        return {"error": f"Unknown corner(s) {bad}. Valid: {list(corner_map.keys())}"}

    if bpy.context.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')

    bm = bmesh.from_edit_mesh(obj.data)
    mat = obj.matrix_world
    tol = max(radius * 0.5, 1e-3)

    selected = 0
    for edge in bm.edges:
        v0 = mat @ edge.verts[0].co
        v1 = mat @ edge.verts[1].co
        # Vertical edge: same X and Y, differing Z
        if abs(v0.x - v1.x) > 1e-4 or abs(v0.y - v1.y) > 1e-4:
            continue
        if abs(v0.z - v1.z) < 1e-4:
            continue
        ex, ey = v0.x, v0.y
        for cname in corners:
            tx, ty = corner_map[cname]
            if abs(ex - tx) < tol and abs(ey - ty) < tol:
                edge.select = True
                selected += 1
                break

    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)

    if selected == 0:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": f"No vertical corner edges found near {corners}. "
                          f"Object may need loop_cut along Z first if it's a single-segment box."}

    bpy.ops.mesh.bevel(offset=radius, segments=segments, affect='EDGES')
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.shade_smooth()
    if hasattr(obj.data, "use_auto_smooth"):
        obj.data.use_auto_smooth = True
        # 60° works well for rounded-corner geometry alongside flat faces
        obj.data.auto_smooth_angle = math.radians(60)

    _push_undo(f"round_corners {target} {corners} r={radius}")
    return {"success": True, "target": target, "corners": corners,
            "radius": radius, "segments": segments, "edges_beveled": selected}


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
    if mod_type == "BEVEL":
        limit = params.get("limit_method", "ANGLE").upper()
        if hasattr(mod, 'limit_method'):
            mod.limit_method = limit
        if hasattr(mod, 'angle_limit'):
            mod.angle_limit = math.radians(params.get("angle_limit", 30.0))
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
    bpy.context.view_layer.update()
    name = params.get("name") if params else None
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
    else:
        obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object and no 'name' specified"}
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
        "dimensions": [round(max(xs) - min(xs), 4), round(max(ys) - min(ys), 4), round(max(zs) - min(zs), 4)],
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


def select_rings(params):
    """Select the union of vertices belonging to multiple rings along an axis. One call
    replaces the verbose select_ring + ADD + ADD + ... pattern when shaping repeated detail
    (alternating bulge/pinch, etc)."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = params.get("axis", "Z").upper()
    indices = params.get("indices", [])
    action = params.get("action", "SELECT").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    bm, rings = _compute_rings(obj, axis_idx)
    n = len(rings)
    if not rings:
        return {"error": "No rings found"}
    if not indices:
        return {"error": "'indices' must be a non-empty list of ring indices"}

    resolved = []
    target_verts = set()
    for i in indices:
        ri = n + i if i < 0 else i
        if ri < 0 or ri >= n:
            return {"error": f"Ring index {i} out of range [-{n}, {n-1}]"}
        resolved.append(ri)
        for v_idx in rings[ri][1]:
            target_verts.add(v_idx)

    for i, v in enumerate(bm.verts):
        match = i in target_verts
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
        "axis": axis,
        "rings_selected": resolved,
        "ring_count": n,
        "verts_total": len(target_verts),
    }


def scale_rings(params):
    """Scale each named ring around ITS OWN centroid in the two non-axis directions.
    The correct tool for bulge/pinch detail on cylinders or any axis-aligned mesh —
    scale_vertices with pivot=SELECTION collapses everything to one centroid;
    pivot=ORIGIN only works for symmetric primitives centered on origin."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = params.get("axis", "Z").upper()
    indices = params.get("indices", [])
    sx = params.get("x", 1.0)
    sy = params.get("y", 1.0)
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    bm, rings = _compute_rings(obj, axis_idx)
    n = len(rings)
    if not rings:
        return {"error": "No rings found"}
    if not indices:
        return {"error": "'indices' must be a non-empty list of ring indices"}

    other_idxs = [i for i in range(3) if i != axis_idx]
    scaled = []
    affected = 0
    for i in indices:
        ri = n + i if i < 0 else i
        if ri < 0 or ri >= n:
            return {"error": f"Ring index {i} out of range [-{n}, {n-1}]"}
        scaled.append(ri)
        _, vert_indices = rings[ri]
        verts = [bm.verts[vi] for vi in vert_indices]
        centroid = [0.0, 0.0, 0.0]
        for v in verts:
            centroid[0] += v.co.x; centroid[1] += v.co.y; centroid[2] += v.co.z
        centroid = [c / len(verts) for c in centroid]
        scales = {other_idxs[0]: sx, other_idxs[1]: sy}
        for v in verts:
            for ax, sc in scales.items():
                v.co[ax] = centroid[ax] + (v.co[ax] - centroid[ax]) * sc
        affected += len(verts)

    bmesh.update_edit_mesh(obj.data)
    _push_undo(f"scale_rings {axis} {indices} x={sx} y={sy}")
    return {
        "success": True,
        "axis": axis,
        "rings_scaled": scaled,
        "verts_affected": affected,
    }


def taper_end(params):
    """Scale the extreme ring on an axis toward its own centroid in the two non-axis directions.
    scale=0 (default) fully collapses to a point. scale=0.5 leaves the ring at half its original
    spread (partial taper). scale=1 is a no-op."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = params.get("axis", "Z").upper()
    end = params.get("end", "MAX").upper()
    scale = max(0.0, min(1.0, params.get("scale", 0.0)))
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
            v.co[ax] = centroid[ax] + (v.co[ax] - centroid[ax]) * scale
    bmesh.update_edit_mesh(obj.data)
    _push_undo(f"taper_end {axis} {end} scale={scale}")

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
        "scale": scale,
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
    # Force depsgraph evaluation so matrix_world / bound_box reflect any location, rotation,
    # or scale changes from the just-finished tool. Without this, status reads return
    # the pre-mutation state and the appended status block lies.
    bpy.context.view_layer.update()
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
        status["rotation_deg"] = [round(math.degrees(v), 2) for v in obj.rotation_euler]
        # World-space bbox dims (rotation-aware). obj.dimensions is local-bbox × scale and
        # ignores rotation — wrong for any rotated object.
        xmin, ymin, zmin, xmax, ymax, zmax = _world_bbox(obj)
        status["dimensions"] = [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)]
        status["world_bounds"] = {
            "x": [round(xmin, 4), round(xmax, 4)],
            "y": [round(ymin, 4), round(ymax, 4)],
            "z": [round(zmin, 4), round(zmax, 4)],
        }
        status["world_z_range"] = status["world_bounds"]["z"]

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
    # Read-only / viewport
    "get_scene_tree":        lambda p: get_scene_tree(),
    "get_viewport_screenshot": get_viewport_screenshot,
    "get_viewport_collage":  get_viewport_collage,
    "get_history":           get_history,
    "undo_steps":            undo_steps,
    "undo_to":               undo_to,
    "set_viewport_angle":    set_viewport_angle,
    "frame_scene":           frame_scene,
    "zoom_to_selected":      zoom_to_selected,
    "set_camera_position":   set_camera_position,
    "orbit_viewport":        orbit_viewport,
    "get_blender_status":    get_blender_status,
    "get_object_info":       get_object_info,
    "get_mesh_profile":      get_mesh_profile,
    "get_current_selection": get_current_selection,

    # Dimensional primitives (the primary way to create geometry)
    "add_box":               add_box,
    "add_plane":             add_plane,
    "add_cylinder":          add_cylinder,
    "add_sphere":            add_sphere,
    "add_cone":              add_cone,

    # Object basics
    "select_object":         select_object,
    "delete_object":         delete_object,
    "rename_object":         rename_object,
    "duplicate_object":      duplicate_object,
    "join_objects":          join_objects,
    "set_mode":              set_mode,

    # Transforms (relational + semantic)
    "nudge":                 nudge,
    "resize":                resize,
    "rotate_object":         rotate_object,
    "apply_transform":       apply_transform,
    "snap_to":               snap_to,
    "snap_to_grid":          snap_to_grid,

    # Relational queries
    "describe":              describe,
    "distance_between":      distance_between,
    "gap_between":           gap_between,
    "is_aligned":            is_aligned,

    # Relational verbs
    "match_dimension":       match_dimension,
    "mirror_across":         mirror_across,
    "distribute_evenly":     distribute_evenly,
    "array_at_corners":      array_at_corners,
    "array_along":           array_along,

    # Groups
    "group":                 group,
    "parts_in":              parts_in,
    "ungroup":               ungroup,

    # Finishes
    "smooth_edges":          smooth_edges,
    "round_corners":         round_corners,
    "add_modifier":          add_modifier,
    "apply_modifiers":       apply_modifiers,

    # --- Ripcord / edit-mode (prefer the relational verbs above; reach for these
    # only when nothing higher-level fits) ---
    "bevel":                 bevel,
    "extrude":               extrude,
    "loop_cut":              loop_cut,
    "set_component_mode":    set_component_mode,
    "select_all":            select_all,
    "select_by_axis":        select_by_axis,
    "select_between":        select_between,
    "grow_selection":        grow_selection,
    "move_vertices":         move_vertices,
    "scale_vertices":        scale_vertices,
    "get_rings":             get_rings,
    "select_ring":           select_ring,
    "select_rings":          select_rings,
    "scale_rings":           scale_rings,
    "taper_end":             taper_end,
    "taper_section":         taper_section,
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

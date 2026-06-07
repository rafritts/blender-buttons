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
    _capture_viewport(scene, window, screen, area, region, tmp, width, height)

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

    zoom = params.get("zoom", 1.0)
    panel_w = max(160, int(320 * zoom))
    panel_h = max(90,  int(180 * zoom))

    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    r3d = next((s.region_3d for s in area.spaces if s.type == 'VIEW_3D'), None)
    if r3d is None:
        return {"error": "No region_3d found"}

    scene = bpy.context.scene
    old_path   = scene.render.filepath
    old_format = scene.render.image_settings.file_format
    old_res_x  = scene.render.resolution_x
    old_res_y  = scene.render.resolution_y
    old_res_pct = scene.render.resolution_percentage

    scene.render.image_settings.file_format = 'PNG'
    scene.render.resolution_percentage = 100

    # row1: FRONT RIGHT TOP  |  row2: BACK LEFT PERSP
    views = ["FRONT", "RIGHT", "TOP", "BACK", "LEFT", "PERSP"]
    panels = []

    for label in views:
        tmp = os.path.join(tempfile.gettempdir(), f"bb_col_{label.lower()}.png")

        with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
            if label != "PERSP":
                bpy.ops.view3d.view_axis(type=label)
                bpy.ops.view3d.view_all(center=False)
            else:
                bpy.ops.view3d.view_axis(type='FRONT')
                bpy.ops.view3d.view_all(center=False)
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

    row1 = np.concatenate(panels[0:3], axis=1)
    row2 = np.concatenate(panels[3:6], axis=1)
    grid = np.concatenate([row1, row2], axis=0)

    out = os.path.join(tempfile.gettempdir(), "bb_collage.png")
    _write_png(grid, out)

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
    location = params.get("location", [0, 0, 0])

    bpy.ops.object.select_all(action='DESELECT')

    ops = {
        "CUBE":     bpy.ops.mesh.primitive_cube_add,
        "SPHERE":   bpy.ops.mesh.primitive_uv_sphere_add,
        "CYLINDER": bpy.ops.mesh.primitive_cylinder_add,
        "PLANE":    bpy.ops.mesh.primitive_plane_add,
        "CONE":     bpy.ops.mesh.primitive_cone_add,
    }

    if ptype not in ops:
        return {"error": f"Unknown primitive: {ptype}. Valid: {list(ops.keys())}"}

    ops[ptype](location=location)
    obj = bpy.context.active_object
    return {"success": True, "object_name": obj.name if obj else None}


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

"""Edit-mode ripcord: bevel, extrude, loop_cut, component mode, selection ops,
move/scale vertices. Prefer the relational verbs in `relational.py` when possible."""

import bpy

from .state import push_undo


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
    action     = params.get("action", "SELECT").upper()

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
    push_undo(f"loop_cut {axis} x{cuts}")

    return {"success": True, "cuts": cuts, "edges_subdivided": len(edges_to_cut)}


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
    push_undo("move_vertices")
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
    push_undo("scale_vertices")
    return {"success": True, "verts_scaled": len(selected)}


def jitter_vertices(params):
    """Randomly displace selected vertices — the easy path to organic, lumpy geometry.

    amount:    max displacement in meters (default 0.005 = 5mm). Each vertex is offset
               by a uniform random value in [-amount, +amount] along the chosen axis.
    axis:      NORMAL (along each vert's normal — best for organic puffing) |
               X | Y | Z (along world axis) | XYZ (independent random on all 3 axes).
               Default NORMAL.
    seed:      RNG seed for reproducibility. Default 0.
    only_positive: if true, displacement is in [0, amount] (only outward). Default false.

    Use cases:
      - donut tutorial: jitter all the donut's verts along NORMAL for lumpy dough
      - icing drips: jitter the icing's bottom ring along Z (negative) for drippy edges
    """
    import bmesh
    import random as _random
    import mathutils as _mu
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    amount = float(params.get("amount", 0.005))
    axis = (params.get("axis") or "NORMAL").upper()
    seed = int(params.get("seed", 0))
    only_positive = bool(params.get("only_positive", False))

    rng = _random.Random(seed)
    bm = bmesh.from_edit_mesh(obj.data)
    selected = [v for v in bm.verts if v.select]
    if not selected:
        return {"error": "No vertices selected"}

    # Convert world-space amount into local space (account for object scale).
    scale = obj.scale
    inv_scale = _mu.Vector((
        amount / (abs(scale.x) or 1.0),
        amount / (abs(scale.y) or 1.0),
        amount / (abs(scale.z) or 1.0),
    ))

    def _rand():
        return rng.uniform(0.0, 1.0) if only_positive else rng.uniform(-1.0, 1.0)

    if axis == "NORMAL":
        for v in selected:
            n = v.normal
            if n.length == 0:
                continue
            d = _rand()
            v.co += n * (d * amount)
    elif axis in ("X", "Y", "Z"):
        idx = {"X": 0, "Y": 1, "Z": 2}[axis]
        for v in selected:
            d = _rand()
            v.co[idx] += d * inv_scale[idx]
    elif axis == "XYZ":
        for v in selected:
            v.co.x += _rand() * inv_scale.x
            v.co.y += _rand() * inv_scale.y
            v.co.z += _rand() * inv_scale.z
    else:
        return {"error": f"Invalid axis '{axis}'. Use NORMAL | X | Y | Z | XYZ"}

    bmesh.update_edit_mesh(obj.data)
    push_undo(f"jitter_vertices {axis} ±{amount}")
    return {"success": True, "verts_jittered": len(selected),
            "amount": amount, "axis": axis, "seed": seed}


_DELETE_TYPES = {"VERT", "EDGE", "FACE", "ONLY_FACE", "EDGE_FACE"}


def delete_geometry(params):
    """Delete the current selection in edit mode.

    mode: VERT       — delete selected vertices (and the faces/edges touching them)
          EDGE       — delete selected edges
          FACE       — delete selected faces (and the edges/verts only used by them)
          ONLY_FACE  — delete faces only, leave their bounding edges + verts intact (creates a hole)
          EDGE_FACE  — delete edges and faces, leave verts

    Pairs with select_by_axis / select_between to carve away part of a mesh
    (e.g. delete the bottom half of a torus to make an open-bottomed dome).
    """
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    mode = params.get("mode", "VERT").upper()
    if mode not in _DELETE_TYPES:
        return {"error": f"Invalid mode '{mode}'. Use one of {sorted(_DELETE_TYPES)}"}
    bpy.ops.mesh.delete(type=mode)
    push_undo(f"delete_geometry {mode}")
    return {"success": True, "mode": mode}


def separate_selection(params):
    """Separate the current selection into a new object (the 'P → Selection' shortcut).

    new_name: optional name for the new object. If omitted, Blender appends '.001'.

    Returns the new object's name. The original object stays in edit mode; the new
    object is created in object mode and deselected from the edit context.
    """
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    before = set(bpy.data.objects.keys())
    bpy.ops.mesh.separate(type='SELECTED')
    after = set(bpy.data.objects.keys())
    new_names = after - before
    if not new_names:
        return {"error": "Nothing was separated — is anything selected?"}
    new_name = next(iter(new_names))

    requested = params.get("new_name")
    if requested:
        bpy.data.objects[new_name].name = requested
        if bpy.data.objects[requested].data is not None:
            bpy.data.objects[requested].data.name = requested
        new_name = requested

    push_undo(f"separate_selection → {new_name}")
    return {"success": True, "new_object": new_name, "source": obj.name}


TOOLS = {
    "bevel":              bevel,
    "extrude":            extrude,
    "loop_cut":           loop_cut,
    "set_component_mode": set_component_mode,
    "select_all":         select_all,
    "select_by_axis":     select_by_axis,
    "select_between":     select_between,
    "grow_selection":     grow_selection,
    "move_vertices":      move_vertices,
    "scale_vertices":     scale_vertices,
    "delete_geometry":    delete_geometry,
    "separate_selection": separate_selection,
    "jitter_vertices":    jitter_vertices,
}

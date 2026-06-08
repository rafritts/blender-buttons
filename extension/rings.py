"""Ring-based edit-mode operations: get_rings, select_ring(s), scale_rings, taper_end/section."""

import bpy
import mathutils

from .common import nearby_objects
from .state import push_undo


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
    replaces the verbose select_ring + ADD + ADD + ... pattern when shaping repeated detail."""
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
    push_undo(f"scale_rings {axis} {indices} x={sx} y={sy}")
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
    push_undo(f"taper_end {axis} {end} scale={scale}")

    world_centroid = obj.matrix_world @ mathutils.Vector(centroid)
    nearby = nearby_objects(
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
    push_undo(f"taper_section {axis} {from_idx}..{to_idx}")
    return {
        "success": True,
        "axis": axis,
        "from_ring": from_idx,
        "to_ring": to_idx,
        "ring_count": n,
        "rings_scaled": to_idx - from_idx + 1,
        "verts_affected": affected,
    }


TOOLS = {
    "get_rings":     get_rings,
    "select_ring":   select_ring,
    "select_rings":  select_rings,
    "scale_rings":   scale_rings,
    "taper_end":     taper_end,
    "taper_section": taper_section,
}

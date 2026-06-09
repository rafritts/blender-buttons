"""Object-level basics: select, delete, rename, duplicate, join, mode, info, profile, selection readback."""

import math

import bpy
import mathutils

from .common import world_bbox


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


def delete_object(params):
    """Delete an object OR a group. If 'name' resolves to a collection, every
    mesh inside it (recursively, including nested sub-collections) is deleted
    and the empty collections are removed."""
    name = params.get("name")
    if name:
        coll = bpy.data.collections.get(name)
        if coll is not None:
            return _delete_collection(coll)
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object or group '{name}' not found"}
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    active = bpy.context.active_object
    if active is None:
        return {"error": "No active object to delete"}
    deleted = active.name
    bpy.ops.object.delete()
    return {"success": True, "deleted": deleted}


def _delete_collection(coll):
    members = [o.name for o in coll.all_objects]
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for o in coll.all_objects:
        try:
            o.select_set(True)
        except Exception:
            pass
    if any(o.select_get() for o in bpy.context.scene.objects):
        bpy.ops.object.delete()
    sub_colls = []
    def _collect(c):
        for child in c.children:
            _collect(child)
            sub_colls.append(child)
    _collect(coll)
    for c in sub_colls:
        bpy.data.collections.remove(c)
    bpy.data.collections.remove(coll)
    return {"success": True, "deleted_group": coll.name, "deleted_members": members}


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

    merged = None
    merge_threshold = params.get("merge_threshold")
    if merge_threshold is not None and result is not None:
        import bmesh
        threshold = float(merge_threshold)
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(result.data)
        before = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=threshold)
        after = len(bm.verts)
        bmesh.update_edit_mesh(result.data)
        bpy.ops.object.mode_set(mode='OBJECT')
        merged = {"threshold": threshold, "verts_before": before,
                  "verts_after": after, "merged": before - after}

    out = {"success": True, "result_object": result.name if result else None, "joined": names}
    if merged is not None:
        out["merged"] = merged
    return out


def set_mode(params):
    mode = params.get("mode", "OBJECT").upper()
    bpy.ops.object.mode_set(mode=mode)
    return {"success": True, "mode": mode}


def get_object_info(params):
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


TOOLS = {
    "rename_object":         rename_object,
    "select_object":         select_object,
    "delete_object":         delete_object,
    "duplicate_object":      duplicate_object,
    "join_objects":          join_objects,
    "set_mode":              set_mode,
    "get_object_info":       get_object_info,
    "get_mesh_profile":      get_mesh_profile,
    "get_current_selection": get_current_selection,
}

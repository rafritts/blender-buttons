"""Relational verbs that act on named parts: match_dimension, mirror_across,
distribute_evenly, array_at_corners, array_along."""

import bpy

from .common import activate, resolve_targets, world_bbox, world_center


def match_dimension(params):
    """Resize 'target' so its size on the named axis equals 'reference's size on the same axis."""
    target_name = params.get("target")
    reference_name = params.get("reference")
    axis = params.get("axis", "Z").upper()
    target = bpy.data.objects.get(target_name) if target_name else None
    reference = bpy.data.objects.get(reference_name) if reference_name else None
    if target is None or reference is None:
        return {"error": "Both 'target' and 'reference' must be existing object names"}

    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    t_bb = world_bbox(target)
    r_bb = world_bbox(reference)
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
    activate(target)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return {"success": True, "target": target_name, "axis": axis,
            "new_size": round(r_size, 5), "factor_applied": round(factor, 5)}


def mirror_across(params):
    """Duplicate parts and mirror the copies across a world axis plane.
    plane: 'X' (mirror across YZ plane through origin), 'Y', or 'Z'."""
    targets = params.get("targets")
    plane = params.get("plane", "X").upper()
    suffix = params.get("suffix", "_mirror")
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}

    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(plane, 0)
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    new_names = []
    for o in objs:
        activate(o)
        bpy.ops.object.duplicate(linked=False)
        dup = bpy.context.active_object
        dup_name = o.name + suffix
        if bpy.data.objects.get(dup_name) is None:
            dup.name = dup_name
            if dup.data:
                dup.data.name = dup_name
        s = list(dup.scale)
        s[axis_idx] *= -1
        dup.scale = s
        loc = list(dup.location)
        loc[axis_idx] *= -1
        dup.location = loc
        bpy.context.view_layer.update()
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        new_names.append(dup.name)

    return {"success": True, "mirrored_from": [o.name for o in objs],
            "mirrored_to": new_names, "plane": plane}


def distribute_evenly(params):
    """Position parts so their centers are evenly spaced between two anchor objects' centers.
    The first and last anchor positions are NOT occupied; only the in-between slots get parts."""
    targets = params.get("targets")
    between = params.get("between")
    axis = params.get("axis", "X").upper()
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}
    if not (isinstance(between, list) and len(between) == 2):
        return {"error": "'between' must be a list of 2 object names"}
    a = bpy.data.objects.get(between[0])
    b = bpy.data.objects.get(between[1])
    if a is None or b is None:
        return {"error": f"Anchor objects not found: {between}"}

    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 0)
    ca = world_center(a)[axis_idx]
    cb = world_center(b)[axis_idx]
    lo, hi = min(ca, cb), max(ca, cb)
    n = len(objs)
    step = (hi - lo) / (n + 1)
    placed = []
    for i, o in enumerate(objs):
        target_pos = lo + step * (i + 1)
        cur_center = world_center(o)[axis_idx]
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

    t_xmin, t_ymin, t_zmin, t_xmax, t_ymax, t_zmax = world_bbox(target)
    p_xmin, p_ymin, p_zmin, p_xmax, p_ymax, p_zmax = world_bbox(proto)
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
        activate(proto)
        bpy.ops.object.duplicate(linked=False)
        dup = bpy.context.active_object
        new_name = f"{name_prefix}_{corner_name}"
        if bpy.data.objects.get(new_name) is None:
            dup.name = new_name
            if dup.data:
                dup.data.name = new_name
        cz = (p_h / 2) if standing_on_floor else world_center(proto)[2]
        dup.location = (cx, cy, cz)
        placed.append(dup.name)

    bpy.context.view_layer.update()
    if not keep_original:
        bpy.data.objects.remove(proto, do_unlink=True)

    return {"success": True, "placed": placed, "of": of, "removed_prototype": not keep_original}


def array_along(params):
    """Duplicate a prototype N times, spacing copies evenly between two anchor objects' centers."""
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
    ca = world_center(a)[axis_idx]
    cb = world_center(b)[axis_idx]
    lo, hi = min(ca, cb), max(ca, cb)
    step = (hi - lo) / (count + 1)

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    placed = []
    for i in range(count):
        target_pos = lo + step * (i + 1)
        activate(proto)
        bpy.ops.object.duplicate(linked=False)
        dup = bpy.context.active_object
        new_name = f"{name_prefix}_{i + 1}"
        if bpy.data.objects.get(new_name) is None:
            dup.name = new_name
            if dup.data:
                dup.data.name = new_name
        loc = list(dup.location)
        cur = world_center(dup)[axis_idx]
        loc[axis_idx] += target_pos - cur
        dup.location = loc
        placed.append(dup.name)

    bpy.context.view_layer.update()
    if not keep_original:
        bpy.data.objects.remove(proto, do_unlink=True)

    return {"success": True, "axis": axis, "count": count, "spacing": round(step, 5),
            "placed": placed, "removed_prototype": not keep_original}


TOOLS = {
    "match_dimension":    match_dimension,
    "mirror_across":      mirror_across,
    "distribute_evenly":  distribute_evenly,
    "array_at_corners":   array_at_corners,
    "array_along":        array_along,
}

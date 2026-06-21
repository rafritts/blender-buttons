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
    plane: 'X' (mirror across YZ plane through origin), 'Y', or 'Z'.
    replace: optional ["_R", "_L"] — copies of names containing the first string
    get it swapped for the second ('eye_R' → 'eye_L') instead of suffix appending."""
    targets = params.get("targets")
    plane = params.get("plane", "X").upper()
    suffix = params.get("suffix", "_mirror")
    replace = params.get("replace")
    if replace is not None and not (isinstance(replace, (list, tuple)) and len(replace) == 2):
        return {"error": "'replace' must be a 2-item list like [\"_R\", \"_L\"]"}
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
        if replace and replace[0] in o.name:
            dup_name = o.name.replace(replace[0], replace[1])
        else:
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
    linked = bool(params.get("linked", False))  # G54: share the prototype's mesh

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

    shared_mesh = proto.data.name if (linked and proto.data) else None
    placed = []
    for corner_name, cx, cy in corners:
        activate(proto)
        bpy.ops.object.duplicate(linked=linked)
        dup = bpy.context.active_object
        new_name = f"{name_prefix}_{corner_name}"
        if bpy.data.objects.get(new_name) is None:
            dup.name = new_name
            if dup.data and not linked:
                dup.data.name = new_name
        cz = (p_h / 2) if standing_on_floor else world_center(proto)[2]
        dup.location = (cx, cy, cz)
        placed.append(dup.name)

    bpy.context.view_layer.update()
    if not keep_original:
        bpy.data.objects.remove(proto, do_unlink=True)

    return {"success": True, "placed": placed, "of": of, "removed_prototype": not keep_original,
            "linked": linked, "shared_mesh": shared_mesh}


def array_along(params):
    """Duplicate a prototype N times, evenly spaced along the SEGMENT between two anchor
    objects' centers.

    G74: the direction is the true A→B vector in 3D (resolved from the anchors' world
    centres), NOT a single named axis — so anchors that differ on more than one axis, or
    that are coplanar on the axis you'd have guessed, both distribute correctly instead of
    collapsing to spacing 0. Copies INCLUDE both endpoints: copy i sits at A + (B−A)·i/(N−1),
    so step = |B−A|/(N−1) (a single copy lands at the midpoint)."""
    from mathutils import Vector
    prototype = params.get("prototype")
    count = params.get("count", 3)
    between = params.get("between")
    keep_original = params.get("keep_original", False)
    name_prefix = params.get("name_prefix", prototype)
    linked = bool(params.get("linked", False))  # G54: share the prototype's mesh

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

    pa = Vector(world_center(a))
    pb = Vector(world_center(b))
    seg = pb - pa
    length = seg.length

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    shared_mesh = proto.data.name if (linked and proto.data) else None
    placed = []
    for i in range(count):
        t = 0.5 if count == 1 else i / (count - 1)
        target_pt = pa + seg * t
        activate(proto)
        bpy.ops.object.duplicate(linked=linked)
        dup = bpy.context.active_object
        new_name = f"{name_prefix}_{i + 1}"
        if bpy.data.objects.get(new_name) is None:
            dup.name = new_name
            if dup.data and not linked:
                dup.data.name = new_name
        # Move the dup's CENTER onto the target point (full 3D, not one axis).
        dup.location = Vector(dup.location) + (target_pt - Vector(world_center(dup)))
        placed.append(dup.name)

    bpy.context.view_layer.update()
    if not keep_original:
        bpy.data.objects.remove(proto, do_unlink=True)

    step = round(length / (count - 1), 5) if count > 1 else 0.0
    return {"success": True, "axis": "A→B segment", "count": count, "spacing": step,
            "span": round(length, 5), "placed": placed,
            "removed_prototype": not keep_original,
            "linked": linked, "shared_mesh": shared_mesh}


def array_radial(params):
    """Duplicate a prototype in a circle or arc around a center point.

    Blender's native idiom (Array modifier about an empty / dupli-rotate about the
    3D cursor) without leaving the sin/cos to the caller. Covers clock markers,
    bolt circles, spokes, gear teeth, chain links on an arc, petals.

    prototype:        object to duplicate (required).
    count:            number of copies (required, >= 1).
    center:           [x,y,z] world point OR an object name (its bbox centre).
                      Default world origin.
    axis:             X|Y|Z — the axis the ring spins around (the ring lies in the
                      other two axes). Default Z (a ring lying flat in the XY plane).
    start_angle:      degrees of the first copy. Default 0. For a full circle this just
                      ROTATES the whole ring (spacing stays 360/count).
    end_angle:        degrees of the last span edge. Default None = a full turn from the
                      start (start_angle+360), i.e. an evenly-spaced full circle with NO
                      overlapping seam (step=span/count) regardless of start_angle. Pass
                      a value to force an ARC, spread inclusive of both ends
                      (step=span/(count-1)).
    radius:           optional — force every copy onto this distance from centre. If
                      omitted, the prototype's current in-plane distance is preserved.
    align_to_tangent: if True each copy also spins so it faces along the arc (gear
                      teeth, chain links); if False orientation is preserved (upright
                      clock numerals). Default False.
    keep_original:    keep the prototype in place too. Default False (matches array_*).
    name_prefix:      base name for copies (default = prototype name) → <prefix>_1..N.
    """
    import math
    from mathutils import Matrix, Vector

    prototype = params.get("prototype")
    count = params.get("count")
    axis = params.get("axis", "Z").upper()
    start_angle = float(params.get("start_angle", 0.0))
    # G93: default end_angle is a FULL TURN FROM THE START (start+360), not a fixed 360.
    # So any nonzero start_angle still yields an evenly-spaced full ring (step=360/count),
    # just rotated — instead of silently collapsing to a 360−start arc with uneven spacing
    # and a last-copy/first-copy overlap. Pass end_angle explicitly for a deliberate arc.
    _ea = params.get("end_angle")
    end_angle = start_angle + 360.0 if _ea is None else float(_ea)
    radius = params.get("radius")
    align = bool(params.get("align_to_tangent", False))
    keep_original = bool(params.get("keep_original", False))
    name_prefix = params.get("name_prefix") or prototype
    linked = bool(params.get("linked", False))  # G54: share the prototype's mesh

    proto = bpy.data.objects.get(prototype) if prototype else None
    if proto is None:
        return {"error": f"Prototype '{prototype}' not found"}
    if not isinstance(count, int) or count < 1:
        return {"error": "'count' must be an integer >= 1"}
    if axis not in ("X", "Y", "Z"):
        return {"error": "axis must be X, Y, or Z"}

    center_spec = params.get("center", [0.0, 0.0, 0.0])
    if isinstance(center_spec, str):
        c_obj = bpy.data.objects.get(center_spec)
        if c_obj is None:
            return {"error": f"center object '{center_spec}' not found"}
        center = Vector(world_center(c_obj))
    elif isinstance(center_spec, (list, tuple)) and len(center_spec) == 3:
        center = Vector([float(v) for v in center_spec])
    else:
        return {"error": "center must be [x,y,z] or an object name"}

    axis_idx = {"X": 0, "Y": 1, "Z": 2}[axis]
    axis_vec = Vector((0.0, 0.0, 0.0)); axis_vec[axis_idx] = 1.0

    span = end_angle - start_angle
    full_circle = abs(abs(span) - 360.0) < 1e-6
    if count == 1:
        step = 0.0
    elif full_circle:
        step = span / count
    else:
        step = span / (count - 1)

    # Effective starting arm (prototype origin relative to centre), split into the
    # along-axis part (preserved) and the in-plane part (the rotating radius).
    arm = proto.location - center
    along = arm.dot(axis_vec) * axis_vec
    in_plane = arm - along
    if radius is not None:
        r = float(radius)
        if in_plane.length > 1e-9:
            in_plane = in_plane.normalized() * r
        else:  # prototype sits on the axis — pick a default in-plane direction
            seed = Vector((1.0, 0.0, 0.0)) if axis != "X" else Vector((0.0, 1.0, 0.0))
            in_plane = (seed - seed.dot(axis_vec) * axis_vec).normalized() * r
    base_arm = along + in_plane
    r_report = in_plane.length

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    _, rot0, scale0 = proto.matrix_world.decompose()
    base_rot = rot0.to_matrix().to_4x4()
    base_scale = Matrix.Diagonal(scale0.to_4d())

    shared_mesh = proto.data.name if (linked and proto.data) else None
    placed = []
    for i in range(count):
        ang = math.radians(start_angle + step * i)
        R = Matrix.Rotation(ang, 4, axis)
        pos = center + (R.to_3x3() @ base_arm)
        activate(proto)
        bpy.ops.object.duplicate(linked=linked)
        dup = bpy.context.active_object
        if align:
            dup.matrix_world = Matrix.Translation(pos) @ R @ base_rot @ base_scale
        else:
            dup.matrix_world = Matrix.Translation(pos) @ base_rot @ base_scale
        new_name = f"{name_prefix}_{i + 1}"
        if bpy.data.objects.get(new_name) is None:
            dup.name = new_name
            if dup.data and not linked:
                dup.data.name = new_name
        placed.append(dup.name)

    bpy.context.view_layer.update()
    if not keep_original:
        bpy.data.objects.remove(proto, do_unlink=True)

    return {"success": True, "placed": placed, "count": count, "axis": axis,
            "center": [round(v, 5) for v in center],
            "start_angle": start_angle, "end_angle": end_angle,
            "step_deg": round(step, 4), "radius": round(r_report, 5),
            "align_to_tangent": align, "full_circle": full_circle,
            "removed_prototype": not keep_original,
            "linked": linked, "shared_mesh": shared_mesh}


def _pca_plane(pts):
    """Centroid + best-fit plane normal (PCA smallest-variance axis) for a point cloud."""
    import numpy as np
    from mathutils import Vector
    arr = np.array([[p.x, p.y, p.z] for p in pts], dtype=float)
    c = arr.mean(axis=0)
    d = arr - c
    cov = d.T @ d
    _, vecs = np.linalg.eigh(cov)  # ascending eigenvalues; col 0 = smallest variance
    normal = Vector(vecs[:, 0])
    if normal.length < 1e-12:
        normal = Vector((0.0, 0.0, 1.0))
    return Vector(c), normal.normalized()


def _centerline_loop(pts, c, normal, bins=72):
    """Approximate a wire-loop's CENTERLINE as a closed polyline: bucket the verts by
    azimuth around (c, normal) and take each bucket's centroid. Robust to tube thickness
    — for a torus it returns the central circle regardless of cross-section."""
    import math
    from mathutils import Vector
    ref = Vector((1.0, 0.0, 0.0))
    if abs(normal.dot(ref)) > 0.9:
        ref = Vector((0.0, 1.0, 0.0))
    u = (ref - normal * ref.dot(normal)).normalized()
    v = normal.cross(u).normalized()
    buckets = {}
    for p in pts:
        d = p - c
        ang = math.atan2(d.dot(v), d.dot(u))
        k = int(((ang + math.pi) / (2.0 * math.pi)) * bins) % bins
        buckets.setdefault(k, []).append(p)
    loop = []
    for k in sorted(buckets):
        grp = buckets[k]
        cc = Vector((0.0, 0.0, 0.0))
        for p in grp:
            cc += p
        loop.append(cc / len(grp))
    return loop


def _in_plane_dist(p, c, normal):
    d = p - c
    return (d - normal * d.dot(normal)).length


def _net_crossings(loop, c, normal, radius):
    """Signed count of times a closed polyline pierces the spanning disk at (c, normal,
    radius). Net signed value = the linking contribution (an integer); its magnitude >= 1
    ⇒ the curve threads the disk. A poke-in/poke-out clip nets 0 (one + one −)."""
    m = len(loop)
    if m < 3:
        return 0, 0
    signed = 0
    hits = 0
    for i in range(m):
        p0 = loop[i]
        p1 = loop[(i + 1) % m]
        d0 = (p0 - c).dot(normal)
        d1 = (p1 - c).dot(normal)
        if (d0 > 0.0) == (d1 > 0.0):
            continue  # both endpoints same side — no crossing
        denom = d0 - d1
        if abs(denom) < 1e-12:
            continue
        t = d0 / denom
        hit = p0 + (p1 - p0) * t
        if _in_plane_dist(hit, c, normal) <= radius:
            hits += 1
            signed += 1 if d1 > d0 else -1
    return signed, hits


def check_linked(params):
    """G91: are two closed-loop wire shells topologically LINKED (threaded) or merely
    touching? Surface distance reports ~0 for both a bail threaded through a ring AND two
    rings resting outer-face to outer-face — this resolves them with a pierce test:
    extract each loop's centerline, count its SIGNED crossings through the other loop's
    spanning disk. A net |crossings| >= 1 ⇒ linked; a touching pair (or a poke-in/poke-out
    clip) nets 0. Computed both directions for confidence (linking number is symmetric)."""
    from mathutils import Vector
    a_name = params.get("a")
    b_name = params.get("b")
    A = bpy.data.objects.get(a_name) if a_name else None
    B = bpy.data.objects.get(b_name) if b_name else None
    if A is None:
        return {"error": f"object '{a_name}' not found"}
    if B is None:
        return {"error": f"object '{b_name}' not found"}
    if A.type != 'MESH' or B.type != 'MESH':
        return {"error": "both 'a' and 'b' must be mesh objects"}

    def world_verts(o):
        m = o.matrix_world
        vs = [m @ v.co for v in o.data.vertices]
        return vs

    ptsA = world_verts(A)
    ptsB = world_verts(B)
    if len(ptsA) < 3 or len(ptsB) < 3:
        return {"error": "both meshes need >= 3 vertices to read linkage"}

    cA, nA = _pca_plane(ptsA)
    cB, nB = _pca_plane(ptsB)
    rA = sum(_in_plane_dist(p, cA, nA) for p in ptsA) / len(ptsA)
    rB = sum(_in_plane_dist(p, cB, nB) for p in ptsB) / len(ptsB)
    if rA < 1e-9 or rB < 1e-9:
        return {"error": "a mesh is degenerate (no in-plane extent) — not a wire loop"}

    loopA = _centerline_loop(ptsA, cA, nA)
    loopB = _centerline_loop(ptsB, cB, nB)
    # B's centerline through A's disk, and A's centerline through B's disk.
    lk_ab, hits_ab = _net_crossings(loopB, cA, nA, rA)
    lk_ba, hits_ba = _net_crossings(loopA, cB, nB, rB)

    linked_ab = abs(lk_ab) >= 1
    linked_ba = abs(lk_ba) >= 1
    linked = linked_ab or linked_ba
    linking_number = max(abs(lk_ab), abs(lk_ba))
    agree = linked_ab == linked_ba
    return {
        "success": True,
        "a": A.name,
        "b": B.name,
        "linked": linked,
        "linking_number": linking_number,
        "agree": agree,
        "b_through_a": {"net": lk_ab, "hits": hits_ab, "disk_radius": round(rA, 5)},
        "a_through_b": {"net": lk_ba, "hits": hits_ba, "disk_radius": round(rB, 5)},
    }


TOOLS = {
    "match_dimension":    match_dimension,
    "mirror_across":      mirror_across,
    "distribute_evenly":  distribute_evenly,
    "array_at_corners":   array_at_corners,
    "array_along":        array_along,
    "array_radial":       array_radial,
    "check_linked":       check_linked,
}

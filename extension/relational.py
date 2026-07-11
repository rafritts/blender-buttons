"""Relational verbs that act on named parts: match_dimension, distribute_evenly."""

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
    "distribute_evenly":  distribute_evenly,
    "check_linked":       check_linked,
}

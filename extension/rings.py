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
    bm.verts.ensure_lookup_table()  # callers subscript bm.verts[i] by these indices
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
    """Scale the extreme ring on an axis about its own centroid in the two non-axis directions.
    scale=0 (default) fully collapses to a point. scale=0.5 leaves the ring at half its original
    spread (partial taper). scale=1 is a no-op. scale>1 FLARES the ring outward (e.g. 1.5 = a
    trumpet/bell lip) — the upper end is NOT clamped (a former clamp to [0,1] silently turned an
    intended flare into a no-op, gaps.md G56)."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = params.get("axis", "Z").upper()
    end = params.get("end", "MAX").upper()
    scale = max(0.0, float(params.get("scale", 0.0)))
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    bm, rings = _compute_rings(obj, axis_idx)
    if not rings:
        return {"error": "No rings found"}
    ring_idx = len(rings) - 1 if end == "MAX" else 0

    # E8 guard: after smooth_edges/bevel bakes a roundover, a thin sliver ring
    # sits just inside the extreme face. Tapering THAT collapses the 2–6mm bevel
    # lip, not the wall — almost never what's wanted. If the extreme ring is
    # hugging its neighbor (gap < 2% of the axis extent), warn and point at
    # taper_section, which ramps the taper across the full run of rings.
    warnings = []
    if len(rings) >= 3:
        axis_extent = rings[-1][0] - rings[0][0]
        neighbor = rings[-2][0] if end == "MAX" else rings[1][0]
        gap = abs(rings[ring_idx][0] - neighbor)
        if axis_extent > 1e-6 and gap < 0.02 * axis_extent:
            warnings.append(
                f"extreme {axis} ring is only {gap:.4f}m from its neighbor "
                f"({gap / axis_extent * 100:.1f}% of the {axis_extent:.4f}m extent) "
                "— this looks like a bevel sliver, so taper_end will collapse the "
                "rounded lip, not the wall. Use taper_section over the full ring "
                "range to taper the body instead."
            )

    pos, vert_indices = rings[ring_idx]
    verts = [bm.verts[i] for i in vert_indices]
    other_idxs = [i for i in range(3) if i != axis_idx]
    # Scale in world space so rotated objects get a uniform cross-section taper.
    mat = obj.matrix_world
    mat_inv = mat.inverted()
    world_cos = [mat @ v.co for v in verts]
    centroid_w = mathutils.Vector((0.0, 0.0, 0.0))
    for wc in world_cos:
        centroid_w += wc
    centroid_w /= len(world_cos)
    for v, wc in zip(verts, world_cos):
        new_w = wc.copy()
        for ax in other_idxs:
            new_w[ax] = centroid_w[ax] + (wc[ax] - centroid_w[ax]) * scale
        v.co = mat_inv @ new_w
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"taper_end {axis} {end} scale={scale}")

    world_centroid = centroid_w
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
        "warnings": warnings,
    }


_CURVES = {"linear", "ease_in_out", "smoothstep", "ease_in", "ease_out"}


def _curve_eval(t, curve):
    if curve == "smoothstep" or curve == "ease_in_out":
        return t * t * (3.0 - 2.0 * t)
    if curve == "ease_in":
        return t * t
    if curve == "ease_out":
        return 1.0 - (1.0 - t) * (1.0 - t)
    return t  # linear


def taper_section(params):
    """Interpolate scale across a span of rings on the two non-axis directions.

    Scaling is done in WORLD space so rotated objects get an even, axis-aligned
    cross-section taper instead of an oval (fixes the rotated-arm bug).

    curve: linear (default) | smoothstep | ease_in_out | ease_in | ease_out.
    """
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
    curve = (params.get("curve") or "linear").lower()
    if curve not in _CURVES:
        return {"error": f"Invalid curve '{curve}'. Use one of {sorted(_CURVES)}"}
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    bm, rings = _compute_rings(obj, axis_idx)
    n = len(rings)
    if n == 0:
        return {"error": "No rings found"}
    if from_idx < 0: from_idx = n + from_idx
    if to_idx < 0: to_idx = n + to_idx
    if from_idx > to_idx:
        # Honor the caller's from→to ordering (G33): the loop runs ascending, so when
        # from > to we swap the endpoints AND the scale values bound to them, keeping
        # x_start/y_start on the original `from_ring` whichever index it is. Without
        # the value swap the taper silently binds to ascending index and inverts.
        from_idx, to_idx = to_idx, from_idx
        x_start, x_end = x_end, x_start
        y_start, y_end = y_end, y_start
    if from_idx < 0 or to_idx >= n:
        return {"error": f"Ring range [{from_idx}, {to_idx}] out of [0, {n-1}]"}
    other_idxs = [i for i in range(3) if i != axis_idx]
    if len(other_idxs) != 2:
        return {"error": "Internal: expected exactly 2 non-axis directions"}
    span = max(1, to_idx - from_idx)
    mat = obj.matrix_world
    mat_inv = mat.inverted()
    affected = 0
    for ring_i in range(from_idx, to_idx + 1):
        _, vert_indices = rings[ring_i]
        t = (ring_i - from_idx) / span
        tt = _curve_eval(t, curve)
        sx = x_start + tt * (x_end - x_start)
        sy = y_start + tt * (y_end - y_start)
        verts = [bm.verts[i] for i in vert_indices]
        world_cos = [mat @ v.co for v in verts]
        centroid_w = mathutils.Vector((0.0, 0.0, 0.0))
        for wc in world_cos:
            centroid_w += wc
        centroid_w /= len(world_cos)
        scales = {other_idxs[0]: sx, other_idxs[1]: sy}
        for v, wc in zip(verts, world_cos):
            new_w = wc.copy()
            for ax, sc in scales.items():
                new_w[ax] = centroid_w[ax] + (wc[ax] - centroid_w[ax]) * sc
            v.co = mat_inv @ new_w
        affected += len(verts)
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"taper_section {axis} {from_idx}..{to_idx} {curve}")
    return {
        "success": True,
        "axis": axis,
        "from_ring": from_idx,
        "to_ring": to_idx,
        "ring_count": n,
        "rings_scaled": to_idx - from_idx + 1,
        "verts_affected": affected,
    }


def shape_profile(params):
    """G92: set ring radii in ABSOLUTE meters, interpolating between control points.

    The lathe/turning op. taper_section multiplies each ring's CURRENT radius, so tiling
    a profile as touching ranges double-scales the shared seam ring into a pinhole. This
    addresses radius outright — idempotent and seam-safe by construction — and lets you
    say "make ring 7 exactly 12 mm" without remembering a ratio.

    points: list of [ring_index, radius] pairs (or {ring, radius} dicts). Radius is the
            distance from the lathe axis to the surface, in meters. Negative ring indices
            wrap. Rings BETWEEN listed control rings interpolate linearly by world-axis
            position; rings OUTSIDE the lowest..highest control ring are left untouched.

    Each ring is scaled around its own centroid in the two non-axis directions by
    target/current_mean_radius, preserving the cross-section shape (a slightly oval ring
    stays oval, just resized). Done in world space so rotated objects shape evenly.
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = params.get("axis", "Z").upper()
    raw = params.get("points", []) or []
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    bm, rings = _compute_rings(obj, axis_idx)
    n = len(rings)
    if n == 0:
        return {"error": "No rings found"}
    if not raw:
        return {"error": "'points' must be a non-empty list of [ring_index, radius] pairs"}

    cps = []
    for p in raw:
        if isinstance(p, dict):
            ri = p.get("ring", p.get("index"))
            r = p.get("radius", p.get("r"))
        elif isinstance(p, (list, tuple)) and len(p) == 2:
            ri, r = p
        else:
            return {"error": f"bad point {p!r}; want [ring_index, radius] or {{ring, radius}}"}
        if ri is None or r is None:
            return {"error": f"point {p!r} is missing a ring index or radius"}
        ri = int(ri)
        if ri < 0:
            ri = n + ri
        if ri < 0 or ri >= n:
            return {"error": f"ring index {ri} out of range [0, {n-1}] in point {p!r}"}
        cps.append((ri, float(r)))
    cps.sort(key=lambda c: c[0])
    lo_idx, hi_idx = cps[0][0], cps[-1][0]
    # Control points as (world_position, radius), for position-based interpolation.
    ctrl = [(rings[ri][0], rad) for (ri, rad) in cps]

    def target_radius_at(pos):
        if pos <= ctrl[0][0]:
            return ctrl[0][1]
        if pos >= ctrl[-1][0]:
            return ctrl[-1][1]
        for k in range(len(ctrl) - 1):
            p0, r0 = ctrl[k]
            p1, r1 = ctrl[k + 1]
            if p0 <= pos <= p1:
                if p1 - p0 < 1e-12:
                    return r1
                t = (pos - p0) / (p1 - p0)
                return r0 + t * (r1 - r0)
        return ctrl[-1][1]

    mat = obj.matrix_world
    mat_inv = mat.inverted()
    other_idxs = [i for i in range(3) if i != axis_idx]
    set_rings = []
    warnings = []
    affected = 0
    for i in range(lo_idx, hi_idx + 1):
        pos, vert_indices = rings[i]
        verts = [bm.verts[vi] for vi in vert_indices]
        world_cos = [mat @ v.co for v in verts]
        centroid_w = mathutils.Vector((0.0, 0.0, 0.0))
        for wc in world_cos:
            centroid_w += wc
        centroid_w /= len(world_cos)
        cur = 0.0
        for wc in world_cos:
            cur += mathutils.Vector(
                (wc[other_idxs[0]] - centroid_w[other_idxs[0]],
                 wc[other_idxs[1]] - centroid_w[other_idxs[1]], 0.0)).length
        cur /= len(world_cos)
        tgt = target_radius_at(pos)
        if cur < 1e-9:
            warnings.append(
                f"ring {i} is collapsed (radius~0) — can't expand it to {round(tgt, 4)}m; skipped")
            continue
        factor = tgt / cur
        for v, wc in zip(verts, world_cos):
            new_w = wc.copy()
            for ax in other_idxs:
                new_w[ax] = centroid_w[ax] + (wc[ax] - centroid_w[ax]) * factor
            v.co = mat_inv @ new_w
        affected += len(verts)
        set_rings.append({"ring": i, "radius": round(tgt, 5)})
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"shape_profile {axis} {len(cps)}pts")
    return {
        "success": True,
        "axis": axis,
        "ring_count": n,
        "rings_set": set_rings,
        "rings_affected": len(set_rings),
        "verts_affected": affected,
        "warnings": warnings,
    }


def flute(params):
    """G94: corrugate a SURFACE OF REVOLUTION with N evenly-spaced vertical flutes/lobes.

    The "reed a turned surface" primitive — flutes (concave grooves), gadroons/reeding
    (convex lobes), columns all fall out of it. Modulates each vertex's RADIUS (distance
    from the lathe axis) by a cosine of its azimuth, so the count is exact and the pattern
    follows the flare of the profile automatically. No meridional edge-picking, no boolean
    cutter array.

    count:   number of flutes/lobes around the axis (>= 1).
    depth:   radial depth of each feature, meters (> 0).
    profile: 'convex' (lobes bulge OUT — gadroons/reeding) | 'concave' (grooves cut IN —
             flutes). Default convex.
    phase:   rotate the pattern, degrees (default 0).

    Needs meridional resolution to render cleanly: aim for >= ~4 verts per lobe around
    each ring (loop-cut / add enough cylinder sides first). Warns if under-resolved.
    """
    import bmesh
    import math
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = params.get("axis", "Z").upper()
    count = int(params.get("count", 0))
    depth = float(params.get("depth", 0.0))
    profile = (params.get("profile") or "convex").lower()
    phase = math.radians(float(params.get("phase", 0.0)))
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    if count < 1:
        return {"error": "'count' must be >= 1 (number of flutes/lobes)"}
    if depth == 0.0:
        return {"error": "'depth' must be nonzero (radial depth of each flute, m)"}
    if profile not in ("convex", "concave"):
        return {"error": "profile must be 'convex' (lobes out) or 'concave' (grooves in)"}

    bm, rings = _compute_rings(obj, axis_idx)
    warnings = []
    if rings:
        per_ring = max(len(vs) for _, vs in rings)
        if per_ring < count * 4:
            warnings.append(
                f"~{per_ring} verts per ring for {count} flutes (<4 verts/lobe) — the flutes "
                "will look faceted/aliased. Add meridional resolution (more cylinder sides) "
                "before fluting.")

    mat = obj.matrix_world
    mat_inv = mat.inverted()
    other = [i for i in range(3) if i != axis_idx]
    u_i, v_i = other[0], other[1]
    all_verts = list(bm.verts)
    if not all_verts:
        return {"error": "mesh has no vertices"}
    # G96: restrict to the live selection when one exists, so a band can be reeded
    # without touching the rest of a single-lathe body. Compute the rotation center
    # from the operated verts only (bbox center on the cross-plane), so an off-axis
    # selection still corrugates around its own axis rather than the whole-mesh centroid.
    selected = [v for v in all_verts if v.select]
    scoped = bool(selected)
    verts = selected if scoped else all_verts
    world = [mat @ v.co for v in verts]
    if scoped:
        us = [w[u_i] for w in world]
        vs = [w[v_i] for w in world]
        cu = 0.5 * (min(us) + max(us))
        cv = 0.5 * (min(vs) + max(vs))
    else:
        cu = sum(w[u_i] for w in world) / len(world)
        cv = sum(w[v_i] for w in world) / len(world)

    affected = 0
    for v, w in zip(verts, world):
        du = w[u_i] - cu
        dv = w[v_i] - cv
        r = math.hypot(du, dv)
        if r < 1e-9:
            continue  # on the axis — no radial direction to push
        theta = math.atan2(dv, du)
        m = 0.5 * (1.0 + math.cos(count * theta + phase))  # 0..1, peaks at lobe centers
        new_r = r + depth * m if profile == "convex" else r - depth * m
        scale = new_r / r
        new_w = w.copy()
        new_w[u_i] = cu + du * scale
        new_w[v_i] = cv + dv * scale
        v.co = mat_inv @ new_w
        affected += 1

    bm.normal_update()
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"flute {axis} count={count} depth={depth} {profile}")
    return {
        "success": True,
        "axis": axis,
        "count": count,
        "depth": round(depth, 5),
        "profile": profile,
        "verts_affected": affected,
        "scope": "selection" if scoped else "whole_mesh",
        "warnings": warnings,
    }


TOOLS = {
    "get_rings":     get_rings,
    "select_ring":   select_ring,
    "select_rings":  select_rings,
    "scale_rings":   scale_rings,
    "taper_end":     taper_end,
    "taper_section": taper_section,
    "shape_profile": shape_profile,
    "flute":         flute,
}

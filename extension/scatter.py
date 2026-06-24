"""Scatter instances of a source object across a target surface.

The donut-tutorial sprinkles step — distribute many copies of a small mesh
randomly across the surface of another mesh, with optional normal-alignment,
random scale, and random rotation around the normal.

Uses area-weighted face sampling on the target's evaluated (post-modifier) mesh,
so sprinkles land on the visible surface (after subsurf/shrinkwrap), not the
low-poly base.
"""

import math
import random as _random

import bpy
import mathutils

from .common import resolve_targets, world_bbox


def _area_weighted_face_sample(triangles, areas, total_area, rng):
    """Pick a triangle index, weighted by area."""
    pick = rng.uniform(0.0, total_area)
    accum = 0.0
    for i, a in enumerate(areas):
        accum += a
        if accum >= pick:
            return i
    return len(triangles) - 1


def _random_point_in_triangle(p0, p1, p2, rng):
    """Uniform random barycentric point inside the triangle."""
    u = rng.uniform(0.0, 1.0)
    v = rng.uniform(0.0, 1.0)
    if u + v > 1.0:
        u, v = 1.0 - u, 1.0 - v
    w = 1.0 - u - v
    return p0 * w + p1 * u + p2 * v


def _footprint_rect(spec, margin):
    """World XY footprint (xmin, ymin, xmax, ymax) of an object/collection spec,
    expanded by `margin`. Returns (rect | None, err). None rect when spec is empty."""
    if not spec:
        return None, None
    objs, err = resolve_targets(spec)
    if err:
        return None, err
    xs_lo, ys_lo, xs_hi, ys_hi = [], [], [], []
    for o in objs:
        xmin, ymin, _z0, xmax, ymax, _z1 = world_bbox(o)
        xs_lo.append(xmin); ys_lo.append(ymin); xs_hi.append(xmax); ys_hi.append(ymax)
    return (min(xs_lo) - margin, min(ys_lo) - margin,
            max(xs_hi) + margin, max(ys_hi) + margin), None


def scatter_on_surface(params):
    """Scatter copies of one or more sources across the surface of `target`.

    target:        REQUIRED — mesh object to scatter onto. Modifiers are evaluated.
    source:        mesh object to instance. Each copy shares its mesh data (N objects,
                   1 mesh). Use `sources` instead for variety.
    sources:       optional — a list (or comma string) of mesh objects; each instance
                   picks one at random, so the scatter has natural variety instead of N
                   identical clones. Overrides `source` when given.
    count:         number of instances. Default 100. Ignored when `density` is set.
    density:       instances per square meter — the size-independent way to say "this
                   thick". Overrides count (a raw count is meaningless without knowing
                   the surface area). With `within`, density is applied to the masked
                   footprint area.
    name_prefix:   name prefix for the generated objects. Default "<source>_inst".
    scale_min, scale_max: per-instance scale multiplier range. Default 0.8, 1.2.
    align_normal:  if true, each copy's +Z is rotated to point along the target's
                   surface normal at its position. Default true.
    seat:          G136 — lift each copy along the normal so its LOWEST point rests ON
                   the surface instead of burying its origin (the source's own extent
                   sets the lift; no thickness guess). The move for sprinkles/pebbles/
                   leaves that should sit proud. Default false.
    offset:        G136 — explicit signed distance (m) along the surface normal, added on
                   top of any seat lift (+ = proud, − = sunk). Default 0.
    min_distance:  G137 — Poisson-disk spacing: no two instances closer than this (m).
                   Candidates that crowd an already-placed instance are resampled, then
                   dropped (counted in `skipped`) — the believable-density ceiling.
    jitter_tilt:   G137 — max random tilt (deg) off the surface normal, so near-coplanar
                   flat instances CROSS at an angle instead of z-fighting. Default 0.
    up_only:       G104 — only scatter onto UP-FACING faces (normal within max_slope° of
                   +Z), so sprinkles land on top, not on the underside or inner walls.
    max_slope:     cone half-angle in degrees for up_only/normal_dir. Default 45.
    normal_dir:    [x,y,z] — gate to faces near THIS direction instead of +Z (advanced).
    rotate_z:      if true, also apply random rotation around the (already-aligned)
                   Z axis. Default true.
    seed:          RNG seed for reproducibility. Default 0.
    parent_to_target: if true, parent every instance to the target so they move with it.
                      Default true.
    within:        optional object/collection name(s) — a region MASK: instances are
                   kept INSIDE this world XY footprint (the inverse of `avoid`), so
                   density lands where it shows (denser near a path, only in a bed)
                   instead of being sprinkled over the whole surface.
    within_margin: meters to expand the within footprint by. Default 0.
    avoid:         optional object/collection name(s) to keep CLEAR — a hero asset you
                   don't want instances landing inside. Rejection-sampled away.
    avoid_margin:  meters to expand the avoid footprint by. Default 0.

    Returns count of instances created, the source mesh name(s), and the per-instance
    skip count (positions that couldn't satisfy within/avoid).
    """
    target_name = params.get("target")
    if not target_name:
        return {"error": "'target' (the surface to scatter onto) is required"}
    target = bpy.data.objects.get(target_name)
    if target is None or target.type != 'MESH':
        return {"error": f"target '{target_name}' is not a mesh"}

    # G57: one source, or several for variety (each instance picks one at random).
    src_spec = params.get("sources") or params.get("source")
    if isinstance(src_spec, str):
        src_names = [s.strip() for s in src_spec.split(",") if s.strip()]
    elif isinstance(src_spec, (list, tuple)):
        src_names = [str(s).strip() for s in src_spec if str(s).strip()]
    else:
        src_names = []
    if not src_names:
        return {"error": "give a 'source' object (or 'sources' list) to instance"}
    source_objs = []
    for sn in src_names:
        so = bpy.data.objects.get(sn)
        if so is None or so.type != 'MESH':
            return {"error": f"source '{sn}' is not a mesh"}
        source_objs.append(so)
    source_name = src_names[0]

    count = int(params.get("count", 100))
    if count < 1:
        return {"error": "'count' must be >= 1"}
    scale_min = float(params.get("scale_min", 0.8))
    scale_max = float(params.get("scale_max", 1.2))
    align_normal = bool(params.get("align_normal", True))
    rotate_z = bool(params.get("rotate_z", True))
    seed = int(params.get("seed", 0))
    parent_to_target = bool(params.get("parent_to_target", True))
    name_prefix = params.get("name_prefix") or f"{source_name}_inst"
    # G136: seat instances PROUD instead of burying their origin in the surface.
    #   seat   — lift each copy so its LOWEST point rests on the surface (no thickness
    #            guess needed: derived from the source mesh's own extent).
    #   offset — explicit signed nudge along the surface normal, on top of any seat.
    seat = bool(params.get("seat", False))
    offset = float(params.get("offset", 0.0) or 0.0)
    # G137: spacing + anti-z-fight controls for dense scatters.
    #   min_distance — Poisson-disk rejection: no two instances closer than this (m).
    #   jitter_tilt  — random tilt off the normal (deg) so coplanar flats CROSS at an
    #                  angle (a declarable clip) instead of z-fighting as coplanar faces.
    min_distance = float(params.get("min_distance", 0.0) or 0.0)
    jitter_tilt = float(params.get("jitter_tilt", 0.0) or 0.0)

    # G57: a region MASK (`within`, keep inside) and an exclusion zone (`avoid`, keep
    # out) — both world XY footprints, expanded by their margins.
    within_rect, err = _footprint_rect(params.get("within"),
                                       float(params.get("within_margin", 0.0)))
    if err:
        return {"error": f"'within': {err}"}
    avoid_rect, err = _footprint_rect(params.get("avoid"),
                                      float(params.get("avoid_margin", 0.0)))
    if err:
        return {"error": f"'avoid': {err}"}

    # Evaluate target with all modifiers, get a triangulated mesh.
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = target.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    mesh.calc_loop_triangles()

    mat_world = target.matrix_world
    # Build triangle list with world-space vertices + a representative normal per tri.
    triangles = []
    areas = []
    for loop_tri in mesh.loop_triangles:
        v0 = mat_world @ mesh.vertices[loop_tri.vertices[0]].co
        v1 = mat_world @ mesh.vertices[loop_tri.vertices[1]].co
        v2 = mat_world @ mesh.vertices[loop_tri.vertices[2]].co
        # World-space normal via cross-product (rotation-matrix-correct).
        e1 = v1 - v0
        e2 = v2 - v0
        n = e1.cross(e2)
        area = n.length * 0.5
        if area < 1e-12:
            continue
        n.normalize()
        triangles.append((v0, v1, v2, n))
        areas.append(area)

    eval_obj.to_mesh_clear()

    if not triangles:
        return {"error": "Target has no usable surface area"}

    # G163: a BVH over the FULL target surface (before any up_only gating) so we can reject
    # samples that land on an INNER / occluded face — the source of the corrupt instances
    # the donut dogfood hit: copies seated 30–45mm INTO the body on a hidden inner face near
    # the hole, or aligned to an inward-pointing normal (renders dark). The test: cast
    # outward along the sampled face normal — a point on the true outer surface escapes; a
    # buried/back-facing one re-hits the target. Those are dropped (counted), never emitted.
    from mathutils.bvhtree import BVHTree
    _bv, _bf = [], []
    for (_a, _b, _c, _n) in triangles:
        base = len(_bv)
        _bv.extend((_a, _b, _c))
        _bf.append((base, base + 1, base + 2))
    tgt_bvh = BVHTree.FromPolygons(_bv, _bf)

    def _occluded(p, n):
        return tgt_bvh.ray_cast(p + n * 1e-4, n)[0] is not None

    # G104: a normal-gate so "sprinkles on top only" doesn't mean scattering 2× the count
    # and hiding half underneath. up_only keeps faces whose normal sits within max_slope°
    # of +Z (so the icing's underside and inner-hole walls are excluded). A general
    # direction is supported via normal_dir=[x,y,z].
    up_only = bool(params.get("up_only", False))
    nd = params.get("normal_dir")
    if up_only or nd:
        gate_dir = mathutils.Vector(nd).normalized() if nd else mathutils.Vector((0, 0, 1))
        max_slope = float(params.get("max_slope", 45.0))
        cos_lim = math.cos(math.radians(max_slope))
        kept = [(t, a) for t, a in zip(triangles, areas) if t[3].dot(gate_dir) >= cos_lim]
        if not kept:
            return {"error": (f"no faces within {max_slope}° of "
                              f"{'+Z' if not nd else list(nd)} to scatter onto — widen "
                              f"max_slope or drop up_only/normal_dir")}
        triangles = [t for t, _ in kept]
        areas = [a for _, a in kept]

    total_area = sum(areas)
    rng = _random.Random(seed)

    # G57: density (per m²) overrides a raw count — a count is meaningless without the
    # surface size. With a `within` mask, apply it to the masked footprint area so the
    # region fills to the requested density (not the whole surface's).
    density = float(params.get("density", 0.0) or 0.0)
    density_used = density > 0.0
    if density_used:
        if within_rect is not None:
            wx0, wy0, wx1, wy1 = within_rect
            area_for_density = max(1e-6, (wx1 - wx0) * (wy1 - wy0))
        else:
            area_for_density = total_area
        count = max(1, int(round(density * area_for_density)))

    # Cap to avoid runaway pollution.
    if count > 5000:
        extra = (f" (density={density}/m² × {round(total_area, 2)}m²)"
                 if density_used else "")
        return {"error": f"count={count} exceeds 5000 cap (lots of objects = slow "
                         f"viewport){extra}"}

    # G137: Poisson-disk spacing via a coarse spatial hash — a candidate is rejected if
    # any already-placed instance sits within `min_distance`. The grid keeps the
    # neighbour test ~O(1) so even a few-thousand-instance scatter stays fast.
    use_min_dist = min_distance > 0.0
    cell = min_distance if use_min_dist else 1.0
    md2 = min_distance * min_distance
    grid = {}

    def _too_close(p):
        if not use_min_dist:
            return False
        cx, cy, cz = int(p.x // cell), int(p.y // cell), int(p.z // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in grid.get((cx + dx, cy + dy, cz + dz), ()):
                        if (p - q).length_squared < md2:
                            return True
        return False

    def _remember(p):
        if use_min_dist:
            grid.setdefault((int(p.x // cell), int(p.y // cell), int(p.z // cell)),
                            []).append(p.copy())

    def _accept(p):
        # Inside the `within` mask (if any), outside the `avoid` zone (if any), and not
        # crowding an already-placed instance (min_distance).
        if within_rect is not None:
            wx0, wy0, wx1, wy1 = within_rect
            if not (wx0 <= p.x <= wx1 and wy0 <= p.y <= wy1):
                return False
        if avoid_rect is not None:
            ax0, ay0, ax1, ay1 = avoid_rect
            if ax0 <= p.x <= ax1 and ay0 <= p.y <= ay1:
                return False
        if _too_close(p):
            return False
        return True

    need_reject = within_rect is not None or avoid_rect is not None or use_min_dist
    multi_source = len(source_objs) > 1
    # G136: cache each source's vertex coords once so seat can derive its lowest extent.
    src_coords = {o.name: [v.co.copy() for v in o.data.vertices] for o in source_objs}

    created = []
    skipped = 0
    dropped_defective = 0  # G163: samples on an inner/occluded face, rejected not emitted
    colored = 0  # G151: instances that carried a per-object material override
    for i in range(count):
        ti = _area_weighted_face_sample(triangles, areas, total_area, rng)
        v0, v1, v2, normal = triangles[ti]
        pos = _random_point_in_triangle(v0, v1, v2, rng)

        # Reject-sample to satisfy within/avoid/min_distance (cap tries so a target that's
        # mostly masked out — or a min_distance too dense to fit — can't spin forever;
        # the instance is just dropped, which is the right spacing ceiling for G137).
        if need_reject and not _accept(pos):
            placed = False
            for _ in range(30):
                tj = _area_weighted_face_sample(triangles, areas, total_area, rng)
                w0, w1, w2, normal = triangles[tj]
                pos = _random_point_in_triangle(w0, w1, w2, rng)
                if _accept(pos):
                    placed = True
                    break
            if not placed:
                skipped += 1
                continue

        # G163: drop samples on an inner/occluded face (would bury the instance or flip it
        # to render dark). Resampling here would fight a genuinely bad region, so the
        # instance is simply not emitted and the count is reported.
        if _occluded(pos, normal):
            dropped_defective += 1
            continue
        _remember(pos)

        # G57: each instance picks a source for variety; all copies of a given source
        # still share its one mesh datablock.
        chosen_src = (source_objs[rng.randrange(len(source_objs))]
                      if multi_source else source_objs[0])
        src_mesh = chosen_src.data
        s = rng.uniform(scale_min, scale_max)
        inst = bpy.data.objects.new(name=f"{name_prefix}_{i:04d}", object_data=src_mesh)
        bpy.context.scene.collection.objects.link(inst)
        inst.scale = (s, s, s)

        # G151: an instance gets the source's MESH but not its object-level material
        # overrides. Linked-duplicate sources coloured for variety carry their colour on
        # an OBJECT-linked slot (G113), NOT the shared mesh data — so without this copy
        # every instance would render the default mesh colour and the variety is lost.
        carried = False
        for si, sslot in enumerate(chosen_src.material_slots):
            if sslot.link == 'OBJECT' and sslot.material is not None \
                    and si < len(inst.material_slots):
                inst.material_slots[si].link = 'OBJECT'
                inst.material_slots[si].material = sslot.material
                carried = True
        if carried:
            colored += 1

        # Orientation: align to the surface normal, optional spin around it, optional
        # anti-z-fight tilt off it. Build one quaternion so the pieces compose cleanly.
        if align_normal:
            q = normal.to_track_quat('Z', 'Y')
            if rotate_z:
                q = mathutils.Quaternion(normal, rng.uniform(0.0, 2 * math.pi)) @ q
        elif rotate_z:
            q = mathutils.Euler((0.0, 0.0, rng.uniform(0.0, 2 * math.pi))).to_quaternion()
        else:
            q = mathutils.Quaternion()
        if jitter_tilt > 0.0:
            # G137: tilt by a random angle about a random axis PERPENDICULAR to the
            # normal, so near-coplanar flat instances cross instead of z-fighting.
            ref = mathutils.Vector((0, 0, 1)) if abs(normal.z) < 0.9 \
                else mathutils.Vector((1, 0, 0))
            perp = normal.cross(ref).normalized()
            perp = mathutils.Quaternion(normal, rng.uniform(0.0, 2 * math.pi)) @ perp
            q = mathutils.Quaternion(perp, rng.uniform(0.0, math.radians(jitter_tilt))) @ q
        inst.rotation_euler = q.to_euler()

        # G136: seat/offset along the surface normal so a flat part sits PROUD instead of
        # sinking its origin half-under. seat lifts the instance's lowest point (its
        # min extent along the normal, derived from the source's own geometry — no
        # thickness guess) onto the surface; offset is an explicit nudge on top.
        lift = offset
        if seat:
            d = q.inverted() @ normal  # the normal in the instance's LOCAL frame
            min_proj = min((c.dot(d) for c in src_coords[chosen_src.name]), default=0.0)
            lift += -s * min_proj
        inst.location = pos + lift * normal if lift else pos

        if parent_to_target:
            inst.parent = target
            inst.matrix_parent_inverse = target.matrix_world.inverted()

        created.append(inst.name)

    bpy.context.view_layer.update()
    return {
        "success": True,
        "scattered": len(created),
        "skipped": skipped,
        "dropped_defective": dropped_defective or None,  # G163: inner/occluded-face samples
        "skipped_in_avoid": skipped,  # kept for back-compat with older callers
        "target": target_name,
        "source": source_name,
        "sources": [o.name for o in source_objs],
        "source_mesh": source_objs[0].data.name,
        "source_meshes": sorted({o.data.name for o in source_objs}),
        "colored_instances": colored or None,
        "count_placed": count,
        "density": density if density_used else None,
        "seat": seat,
        "offset": offset if offset else None,
        "min_distance": min_distance if use_min_dist else None,
        "jitter_tilt": jitter_tilt if jitter_tilt else None,
        "within": params.get("within") or None,
        "total_area_m2": round(total_area, 4),
        "first_few": created[:5],
        "seed": seed,
    }


TOOLS = {
    "scatter_on_surface": scatter_on_surface,
}

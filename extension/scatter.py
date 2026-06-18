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

    def _accept(p):
        # Inside the `within` mask (if any) AND outside the `avoid` zone (if any).
        if within_rect is not None:
            wx0, wy0, wx1, wy1 = within_rect
            if not (wx0 <= p.x <= wx1 and wy0 <= p.y <= wy1):
                return False
        if avoid_rect is not None:
            ax0, ay0, ax1, ay1 = avoid_rect
            if ax0 <= p.x <= ax1 and ay0 <= p.y <= ay1:
                return False
        return True

    need_reject = within_rect is not None or avoid_rect is not None
    multi_source = len(source_objs) > 1

    z_axis = mathutils.Vector((0, 0, 1))
    created = []
    skipped = 0
    for i in range(count):
        ti = _area_weighted_face_sample(triangles, areas, total_area, rng)
        v0, v1, v2, normal = triangles[ti]
        pos = _random_point_in_triangle(v0, v1, v2, rng)

        # Reject-sample to satisfy within/avoid (cap tries so a target that's mostly
        # masked out can't spin forever — just drop the instance).
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

        # G57: each instance picks a source for variety; all copies of a given source
        # still share its one mesh datablock.
        src_mesh = (source_objs[rng.randrange(len(source_objs))].data
                    if multi_source else source_objs[0].data)
        s = rng.uniform(scale_min, scale_max)
        inst = bpy.data.objects.new(name=f"{name_prefix}_{i:04d}", object_data=src_mesh)
        bpy.context.scene.collection.objects.link(inst)
        inst.location = pos
        inst.scale = (s, s, s)

        if align_normal:
            inst.rotation_euler = normal.to_track_quat('Z', 'Y').to_euler()
            if rotate_z:
                # Compose: align-to-normal first, then random spin around local Z.
                q_align = normal.to_track_quat('Z', 'Y')
                q_spin = mathutils.Quaternion(normal, rng.uniform(0.0, 2 * math.pi))
                inst.rotation_euler = (q_spin @ q_align).to_euler()
        elif rotate_z:
            inst.rotation_euler = (0.0, 0.0, rng.uniform(0.0, 2 * math.pi))

        if parent_to_target:
            inst.parent = target
            inst.matrix_parent_inverse = target.matrix_world.inverted()

        created.append(inst.name)

    bpy.context.view_layer.update()
    return {
        "success": True,
        "scattered": len(created),
        "skipped": skipped,
        "skipped_in_avoid": skipped,  # kept for back-compat with older callers
        "target": target_name,
        "source": source_name,
        "sources": [o.name for o in source_objs],
        "source_mesh": source_objs[0].data.name,
        "source_meshes": sorted({o.data.name for o in source_objs}),
        "count_placed": count,
        "density": density if density_used else None,
        "within": params.get("within") or None,
        "total_area_m2": round(total_area, 4),
        "first_few": created[:5],
        "seed": seed,
    }


TOOLS = {
    "scatter_on_surface": scatter_on_surface,
}

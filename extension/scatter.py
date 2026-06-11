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


def scatter_on_surface(params):
    """Scatter N copies of `source` across the surface of `target`.

    target:        REQUIRED — mesh object to scatter onto. Modifiers are evaluated.
    source:        REQUIRED — mesh object to instance. Each copy shares its mesh data
                   (lightweight — N objects, 1 mesh).
    count:         number of instances. Default 100.
    name_prefix:   name prefix for the generated objects. Default "<source>_inst".
    scale_min, scale_max: per-instance scale multiplier range. Default 0.8, 1.2.
    align_normal:  if true, each copy's +Z is rotated to point along the target's
                   surface normal at its position. Default true.
    rotate_z:      if true, also apply random rotation around the (already-aligned)
                   Z axis. Default true.
    seed:          RNG seed for reproducibility. Default 0.
    parent_to_target: if true, parent every instance to the target so they move with it.
                      Default true.
    avoid:         optional object or collection name to keep clear — a hero asset
                   you don't want rocks landing inside. Instances whose (x, y)
                   fall within its world XY footprint are rejection-sampled away.
    avoid_margin:  meters to expand the avoid footprint by. Default 0.

    Returns count of instances created, the shared source mesh name, and a group
    name (the parent empty if parent_to_target=false, else just the target).
    """
    target_name = params.get("target")
    source_name = params.get("source")
    if not target_name or not source_name:
        return {"error": "'target' and 'source' (object names) are both required"}
    target = bpy.data.objects.get(target_name)
    source = bpy.data.objects.get(source_name)
    if target is None or target.type != 'MESH':
        return {"error": f"target '{target_name}' is not a mesh"}
    if source is None or source.type != 'MESH':
        return {"error": f"source '{source_name}' is not a mesh"}

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

    # Optional exclusion zone: an XY footprint (world bbox of the avoid object/
    # collection, expanded by margin) that instances must not land inside.
    avoid_rect = None
    avoid_spec = params.get("avoid")
    if avoid_spec:
        avoid_objs, err = resolve_targets(avoid_spec)
        if err:
            return {"error": f"'avoid': {err}"}
        margin = float(params.get("avoid_margin", 0.0))
        xs_lo, ys_lo, xs_hi, ys_hi = [], [], [], []
        for ao in avoid_objs:
            xmin, ymin, _zmin, xmax, ymax, _zmax = world_bbox(ao)
            xs_lo.append(xmin); ys_lo.append(ymin); xs_hi.append(xmax); ys_hi.append(ymax)
        avoid_rect = (min(xs_lo) - margin, min(ys_lo) - margin,
                      max(xs_hi) + margin, max(ys_hi) + margin)

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

    # Cap to avoid runaway pollution.
    if count > 5000:
        return {"error": f"count={count} exceeds 5000 cap (lots of objects = slow viewport)"}

    def _in_avoid(p):
        ax0, ay0, ax1, ay1 = avoid_rect
        return ax0 <= p.x <= ax1 and ay0 <= p.y <= ay1

    z_axis = mathutils.Vector((0, 0, 1))
    source_mesh = source.data
    created = []
    skipped = 0
    for i in range(count):
        ti = _area_weighted_face_sample(triangles, areas, total_area, rng)
        v0, v1, v2, normal = triangles[ti]
        pos = _random_point_in_triangle(v0, v1, v2, rng)

        # Reject-sample out of the exclusion zone (cap tries so a target that's
        # mostly covered can't spin forever — just drop the instance).
        if avoid_rect is not None and _in_avoid(pos):
            placed = False
            for _ in range(20):
                tj = _area_weighted_face_sample(triangles, areas, total_area, rng)
                w0, w1, w2, normal = triangles[tj]
                pos = _random_point_in_triangle(w0, w1, w2, rng)
                if not _in_avoid(pos):
                    placed = True
                    break
            if not placed:
                skipped += 1
                continue

        s = rng.uniform(scale_min, scale_max)
        inst = bpy.data.objects.new(name=f"{name_prefix}_{i:04d}", object_data=source_mesh)
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
        "skipped_in_avoid": skipped,
        "target": target_name,
        "source": source_name,
        "source_mesh": source_mesh.name,
        "first_few": created[:5],
        "seed": seed,
    }


TOOLS = {
    "scatter_on_surface": scatter_on_surface,
}

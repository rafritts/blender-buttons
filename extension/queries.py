"""Relational queries — describe/distance/gap/is_aligned. No coordinate leakage in describe."""

import math

import bpy

from .common import (eval_world_bmesh, material_summary, region_words,
                     world_bbox, world_center)


def describe(params):
    """Describe an object in relational terms — what it rests on, what it's beside,
    and its dimensions. No raw world coordinates in the output."""
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}

    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    w, d, h = xmax - xmin, ymax - ymin, zmax - zmin

    relations = []
    if abs(zmin) < 1e-3:
        relations.append("standing on floor")

    for o in bpy.context.scene.objects:
        if o == obj or o.type != 'MESH':
            continue
        o_xmin, o_ymin, o_zmin, o_xmax, o_ymax, o_zmax = world_bbox(o)
        xy_overlap = (xmin < o_xmax and xmax > o_xmin and ymin < o_ymax and ymax > o_ymin)
        if xy_overlap and abs(zmin - o_zmax) < 1e-3:
            relations.append(f"resting on '{o.name}'")
        elif xy_overlap and abs(zmax - o_zmin) < 1e-3:
            relations.append(f"directly under '{o.name}'")
        z_overlap = (zmin < o_zmax and zmax > o_zmin)
        y_overlap = (ymin < o_ymax and ymax > o_ymin)
        x_overlap = (xmin < o_xmax and xmax > o_xmin)
        if z_overlap and y_overlap:
            if abs(xmax - o_xmin) < 1e-3:
                relations.append(f"flush left of '{o.name}'")
            elif abs(xmin - o_xmax) < 1e-3:
                relations.append(f"flush right of '{o.name}'")
        if z_overlap and x_overlap:
            if abs(ymax - o_ymin) < 1e-3:
                relations.append(f"flush in front of '{o.name}'")
            elif abs(ymin - o_ymax) < 1e-3:
                relations.append(f"flush behind '{o.name}'")

    if not relations:
        relations.append(f"freestanding (origin {round(zmin, 3)}m above floor)")

    dim_str = f"size {round(w, 3)} × {round(d, 3)} × {round(h, 3)} m (W×D×H)"

    materials = material_summary(obj)
    mat_strs = []
    for m in materials:
        if not m.get("name"):
            continue
        bits = [m["name"]]
        if "base_color" in m:
            bits.append(f"color={m['base_color'][:3]}")
        elif m.get("base_color_driven"):
            bits.append("color=nodegraph-driven (summary unreliable)")
        if m.get("roughness_driven"):
            bits.append("rough=nodegraph")
        elif "roughness" in m:
            bits.append(f"rough={m['roughness']}")
        if m.get("metallic"):
            bits.append(f"metal={m['metallic']}")
        elif m.get("metallic_driven"):
            bits.append("metal=nodegraph")
        if m.get("emission_strength"):
            bits.append(f"glow={m['emission_strength']}")
        if "toon" in m:
            t = m["toon"]
            bits.append(f"toon(bands={t.get('bands')}"
                        + (", rim" if t.get("rim_color") else "")
                        + (", gradient" if t.get("gradient_top") else "") + ")")
        if "texture" in m:
            tint = m.get("base_color_tint")
            tint_str = f" tint={tint[:3]}" if tint else ""
            bits.append(f"texture({m['texture'].get('asset_id')}@{m['texture'].get('resolution')}{tint_str})")
        elif m.get("base_color_tint"):
            bits.append(f"tint={m['base_color_tint'][:3]}")
        mat_strs.append(" ".join(bits))
    mat_str = f"material: {', '.join(mat_strs)}" if mat_strs else "no material"

    parts = relations + [dim_str, mat_str]

    spline_pts = obj.get("bb_spline_points")
    if spline_pts:
        parts.append(f"spline tube through {spline_pts}")

    sentence = f"{name}: {'; '.join(parts)}"

    result = {
        "success": True,
        "name": name,
        "description": sentence,
        "relations": relations,
        "dimensions": {"width": round(w, 4), "depth": round(d, 4), "height": round(h, 4)},
        "materials": materials,
    }
    if spline_pts:
        result["spline_points"] = spline_pts
    return result


def distance_between(params):
    """Centre-to-centre distance between two objects. Optionally restricted to one axis."""
    a_name = params.get("a")
    b_name = params.get("b")
    axis = params.get("axis", "ANY").upper()
    a = bpy.data.objects.get(a_name) if a_name else None
    b = bpy.data.objects.get(b_name) if b_name else None
    if a is None or b is None:
        return {"error": f"Both 'a' and 'b' must be existing object names (a={a_name}, b={b_name})"}

    ca = world_center(a)
    cb = world_center(b)
    dx, dy, dz = cb[0] - ca[0], cb[1] - ca[1], cb[2] - ca[2]

    if axis == "X":
        dist = abs(dx)
    elif axis == "Y":
        dist = abs(dy)
    elif axis == "Z":
        dist = abs(dz)
    else:
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

    return {"success": True, "a": a_name, "b": b_name, "axis": axis, "distance": round(dist, 5)}


def gap_between(params):
    """Smallest empty distance between two objects' bounding boxes on each axis.
    Negative gap = overlap. Useful for checking 'are these touching?' or 'how far apart?'"""
    a_name = params.get("a")
    b_name = params.get("b")
    a = bpy.data.objects.get(a_name) if a_name else None
    b = bpy.data.objects.get(b_name) if b_name else None
    if a is None or b is None:
        return {"error": "Both 'a' and 'b' must be existing object names"}

    ax = world_bbox(a)
    bx = world_bbox(b)
    gx = max(bx[0] - ax[3], ax[0] - bx[3])
    gy = max(bx[1] - ax[4], ax[1] - bx[4])
    gz = max(bx[2] - ax[5], ax[2] - bx[5])

    touching_axes = [n for n, g in zip("XYZ", (gx, gy, gz)) if abs(g) < 1e-4]
    return {"success": True, "a": a_name, "b": b_name,
            "gap_x": round(gx, 5), "gap_y": round(gy, 5), "gap_z": round(gz, 5),
            "touching_on_axes": touching_axes}


def is_aligned(params):
    """Check if two objects share an aligned face or center on the given side.
    side: TOP|BOTTOM|LEFT|RIGHT|FRONT|BACK|CENTER_X|CENTER_Y|CENTER_Z"""
    a_name = params.get("a")
    b_name = params.get("b")
    side = params.get("side", "TOP").upper()
    tolerance = params.get("tolerance", 1e-3)
    a = bpy.data.objects.get(a_name) if a_name else None
    b = bpy.data.objects.get(b_name) if b_name else None
    if a is None or b is None:
        return {"error": "Both 'a' and 'b' must be existing object names"}

    a_xmin, a_ymin, a_zmin, a_xmax, a_ymax, a_zmax = world_bbox(a)
    b_xmin, b_ymin, b_zmin, b_xmax, b_ymax, b_zmax = world_bbox(b)

    sides = {
        "TOP":      (a_zmax, b_zmax),
        "BOTTOM":   (a_zmin, b_zmin),
        "LEFT":     (a_xmin, b_xmin),
        "RIGHT":    (a_xmax, b_xmax),
        "FRONT":    (a_ymin, b_ymin),
        "BACK":     (a_ymax, b_ymax),
        "CENTER_X": ((a_xmin + a_xmax) / 2, (b_xmin + b_xmax) / 2),
        "CENTER_Y": ((a_ymin + a_ymax) / 2, (b_ymin + b_ymax) / 2),
        "CENTER_Z": ((a_zmin + a_zmax) / 2, (b_zmin + b_zmax) / 2),
    }
    if side not in sides:
        return {"error": f"Invalid side '{side}'. Use {list(sides.keys())}"}
    va, vb = sides[side]
    return {"success": True, "a": a_name, "b": b_name, "side": side,
            "aligned": abs(va - vb) < tolerance, "difference": round(va - vb, 5)}


def _mesh_symmetry(obj, axis_idx, axis, plane, tol):
    """Mesh-level symmetry: mirror every vertex across the plane and measure the
    distance to the nearest surface point of the same mesh. Reports max/mean
    deviation and WHERE the worst asymmetry sits. The first thing human eyes catch
    on character work and the agent's screenshots reliably miss."""
    from mathutils.bvhtree import BVHTree
    bm = eval_world_bmesh(obj)
    if bm is None or not bm.verts:
        if bm:
            bm.free()
        return {"error": f"'{obj.name}' has no usable geometry"}
    bvh = BVHTree.FromBMesh(bm)
    devs = []
    worst_d, worst_p = 0.0, None
    for v in bm.verts:
        m = v.co.copy()
        m[axis_idx] = 2 * plane - m[axis_idx]
        loc, normal, idx, dist = bvh.find_nearest(m)
        if loc is None:
            continue
        devs.append(dist)
        if dist > worst_d:
            worst_d, worst_p = dist, v.co.copy()
    bb = world_bbox(obj)
    bm.free()
    if not devs:
        return {"error": "no vertices to compare"}
    maxd, meand = max(devs), sum(devs) / len(devs)
    is_sym = maxd <= tol
    region = region_words(bb, worst_p) if worst_p is not None else None
    return {
        "success": True, "level": "mesh", "object": obj.name, "axis": axis,
        "plane": plane, "tolerance": tol, "is_symmetric": is_sym,
        "max_deviation_mm": round(maxd * 1000, 2),
        "mean_deviation_mm": round(meand * 1000, 2),
        "worst_region": region,
        "summary": (f"{obj.name}: symmetric across {axis} (max dev {round(maxd * 1000, 2)}mm)"
                    if is_sym else
                    f"{obj.name}: asymmetric across {axis} — max {round(maxd * 1000, 2)}mm "
                    f"at {region}, mean {round(meand * 1000, 2)}mm"),
    }


def check_symmetry(params):
    """Symmetry check across a world-space plane, at two zoom levels.

    Single mesh target → MESH-LEVEL: mirror the geometry and measure per-vertex
    deviation (max/mean + where the worst asymmetry is) — for character/sculpt work.

    Multiple objects / a collection / the whole scene → OBJECT-LEVEL: pair each
    object on the +side with a mirrored counterpart on the −side and report
    unmatched objects — for symmetric assemblies.

    axis:      X|Y|Z — axis the plane is perpendicular to. Default X.
    plane:     world coordinate of the mirror plane on `axis`. Default 0.
    epsilon /
    tolerance: match tolerance (m). Defaults: 0.5mm mesh-level, 10mm object-level.
    targets:   optional — restrict to specific objects/collections.
    """
    axis = params.get("axis", "X").upper()
    plane = float(params.get("plane", 0.0))
    targets = params.get("targets")
    explicit_tol = params.get("epsilon", params.get("tolerance"))

    axis_idx = {"X": 0, "Y": 1, "Z": 2}.get(axis)
    if axis_idx is None:
        return {"error": "axis must be X, Y, or Z"}

    if targets:
        from .common import resolve_targets
        objs, err = resolve_targets(targets)
        if err:
            return {"error": err}
        mesh_objs = [o for o in objs if o.type == 'MESH']
    else:
        mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']

    if len(mesh_objs) == 1:
        tol = float(explicit_tol) if explicit_tol is not None else 0.0005
        return _mesh_symmetry(mesh_objs[0], axis_idx, axis, plane, tol)

    tol = float(explicit_tol) if explicit_tol is not None else 0.01
    pos_side, neg_side, on_plane = [], [], []
    for o in mesh_objs:
        c = world_center(o)
        off = c[axis_idx] - plane
        if abs(off) < tol:
            on_plane.append(o)
        elif off > 0:
            pos_side.append(o)
        else:
            neg_side.append(o)

    from .common import world_bbox as _wb
    def _bbox_dims(o):
        xmin, ymin, zmin, xmax, ymax, zmax = _wb(o)
        return (xmax - xmin, ymax - ymin, zmax - zmin)

    pairs = []
    unmatched_pos = []
    unmatched_neg = list(neg_side)

    for p in pos_side:
        pc = list(world_center(p))
        pc[axis_idx] = 2 * plane - pc[axis_idx]
        pd = _bbox_dims(p)

        best = None
        best_score = float("inf")
        dim_tol = max(tol * 5, max(pd) * 0.05)
        center_tol = max(tol * 5, 0.02)
        for n in unmatched_neg:
            nc = world_center(n)
            d = math.sqrt(sum((pc[i] - nc[i]) ** 2 for i in range(3)))
            if d > center_tol:
                continue
            nd = _bbox_dims(n)
            dim_diff = sum(abs(pd[i] - nd[i]) for i in range(3))
            if dim_diff > dim_tol:
                continue
            score = d + dim_diff
            if score < best_score:
                best = n
                best_score = score

        if best is not None:
            pairs.append({
                "pos": p.name, "neg": best.name,
                "center_diff": round(best_score, 5),
            })
            unmatched_neg.remove(best)
        else:
            unmatched_pos.append(p.name)

    unmatched_neg_names = [o.name for o in unmatched_neg]
    is_symmetric = not unmatched_pos and not unmatched_neg_names

    return {
        "success": True,
        "axis": axis,
        "plane": plane,
        "tolerance": tol,
        "is_symmetric": is_symmetric,
        "pairs": pairs,
        "unmatched_positive_side": unmatched_pos,
        "unmatched_negative_side": unmatched_neg_names,
        "on_plane": [o.name for o in on_plane],
        "summary": (
            f"symmetric across {axis}={plane}" if is_symmetric
            else (f"asymmetric across {axis}={plane}: "
                  f"{len(unmatched_pos)} unmatched on +{axis}, "
                  f"{len(unmatched_neg_names)} unmatched on -{axis}")
        ),
    }


TOOLS = {
    "describe":         describe,
    "distance_between": distance_between,
    "gap_between":      gap_between,
    "is_aligned":       is_aligned,
    "check_symmetry":   check_symmetry,
}

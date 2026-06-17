"""Relational queries — describe/distance/gap/is_aligned. No coordinate leakage in describe."""

import math

import bpy

from .common import (eval_world_bmesh, material_summary, region_words,
                     world_bbox, world_center)


def _base_mesh_world_center(obj):
    """World center of the UNDEFORMED base mesh (obj.data.vertices) — the rest
    reference for measuring pose displacement. obj.bound_box is already modifier-
    aware in 5.1, so the base mesh itself is the honest 'before' for a posed object.
    Falls back to the object origin for objects with no vertex data."""
    me = getattr(obj, "data", None)
    if me is None or not hasattr(me, "vertices") or not len(me.vertices):
        return tuple(obj.matrix_world.translation)
    mw = obj.matrix_world
    xs, ys, zs = [], [], []
    for v in me.vertices:
        w = mw @ v.co
        xs.append(w.x); ys.append(w.y); zs.append(w.z)
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)


def _users_of(obj):
    """Objects that reference obj as a constraint target or a modifier object —
    'what uses this empty/armature/lattice'."""
    users = []
    for o in bpy.context.scene.objects:
        if o == obj:
            continue
        hit = any(getattr(c, "target", None) == obj for c in getattr(o, "constraints", []))
        if not hit:
            hit = any(getattr(m, "object", None) == obj for m in getattr(o, "modifiers", []))
        if hit:
            users.append(o.name)
    return users


def _non_mesh_summary(obj):
    """A relational sentence for a non-mesh type — armatures, empties, lattices —
    instead of the useless 'no material' (gaps.md U6). Returns None for types that
    legitimately carry materials (mesh, curve, font), so they keep the material line."""
    def _trunc(names, n=6):
        return f"{names[:n]}" + (f" +{len(names) - n} more" if len(names) > n else "")

    if obj.type == 'ARMATURE':
        bones = obj.data.bones
        deform = sum(1 for b in bones if b.use_deform)
        roots = sum(1 for b in bones if b.parent is None)
        deformed = [o.name for o in bpy.context.scene.objects
                    if any(m.type == 'ARMATURE' and m.object == obj
                           for m in getattr(o, "modifiers", []))]
        s = f"armature: {len(bones)} bones ({deform} deform), {roots} root(s)"
        if deformed:
            s += f"; deforms {_trunc(deformed)}"
        return s
    if obj.type == 'EMPTY':
        users = _users_of(obj)
        s = f"empty ({obj.empty_display_type.lower()})"
        s += f"; used by {_trunc(users)}" if users else "; not referenced"
        return s
    if obj.type == 'LATTICE':
        deformed = [o.name for o in bpy.context.scene.objects
                    if any(m.type == 'LATTICE' and m.object == obj
                           for m in getattr(o, "modifiers", []))]
        return "lattice" + (f": deforms {_trunc(deformed)}" if deformed else " (deforms nothing)")
    return None


def describe(params):
    """Describe an object in relational terms — what it rests on, what it's beside,
    and its dimensions. No raw world coordinates in the output."""
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}

    posed = bool(params.get("posed"))
    if posed:
        from .common import eval_world_bbox
        xmin, ymin, zmin, xmax, ymax, zmax = eval_world_bbox(obj)
        posed_offset_mm = round(math.dist(
            ((xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2),
            _base_mesh_world_center(obj)) * 1000, 1)
    else:
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
        posed_offset_mm = None
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

    summary = _non_mesh_summary(obj)
    if summary is not None:
        # Empties have no real geometry — the 0×0×0 size line is noise.
        parts = relations + ([summary] if obj.type == 'EMPTY' else [dim_str, summary])
    else:
        parts = relations + [dim_str, mat_str]
    if posed:
        parts.insert(0, f"posed (evaluated geometry; center {posed_offset_mm}mm from rest)")

    from .objects import _particle_systems
    psys = _particle_systems(obj)
    if psys:
        parts.append(f"{len(psys)} particle system(s): "
                     + ", ".join(f"{n}({t.lower()}, {c})" for n, t, c in psys))

    from .common import linked_status
    lib = linked_status(obj)
    if lib:
        parts.append(lib)

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
    if posed:
        result["posed"] = True
        result["posed_center_offset_mm"] = posed_offset_mm
    return result


def _nearest_surface_pair(pa, pb):
    """Min distance from any of pa's sampled verts to pb's surface, with the point
    pair at that minimum. Same BVH path check_contacts uses, so the number reconciles
    with a contacts read (G29). Returns (dist, point_on_a, point_on_b)."""
    best = (float("inf"), None, None)
    for v in pa["verts"]:
        loc, normal, idx, d = pb["bvh"].find_nearest(v)
        if loc is not None and d < best[0]:
            best = (d, v.copy(), loc.copy())
    return best


def distance_between(params):
    """Distance between two objects.

    axis=ANY (default) reports the true nearest-SURFACE distance (BVH) — the same
    measurement check_contacts uses, so it reconciles with a contacts read and the
    bounds in the status block — and labels what it measured. axis=X|Y|Z reports the
    single-axis centre-to-centre projection (G29)."""
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

    if axis in ("X", "Y", "Z"):
        dist = abs({"X": dx, "Y": dy, "Z": dz}[axis])
        return {"success": True, "a": a_name, "b": b_name, "axis": axis,
                "distance": round(dist, 5), "measured": "centre-to-centre"}

    # ANY → genuine nearest-surface distance (BVH), with the point pair so the operator
    # can check it against the bounds the status block reports.
    from .introspect import _prepare
    pa, pb = _prepare(a), _prepare(b)
    if pa is not None and pb is not None:
        d1, a1, b1 = _nearest_surface_pair(pa, pb)
        d2, b2, a2 = _nearest_surface_pair(pb, pa)
        if d1 <= d2:
            dist, pt_a, pt_b = d1, a1, b1
        else:
            dist, pt_a, pt_b = d2, a2, b2
        return {"success": True, "a": a_name, "b": b_name, "axis": "ANY",
                "distance": round(dist, 5), "measured": "nearest surface (BVH)",
                "between": [[round(c, 4) for c in pt_a], [round(c, 4) for c in pt_b]]}
    # Either object has no usable mesh geometry (e.g. an empty) — fall back to centroid.
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    return {"success": True, "a": a_name, "b": b_name, "axis": "ANY",
            "distance": round(dist, 5), "measured": "centre-to-centre (no mesh geometry)"}


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


def aim_surface(params):
    """Cast a normalized bbox-face aim onto the surface — the constructive-side
    analog of `feel structure` → handles (gaps.md G1 / SPEC-06). Turns a framing the
    agent CAN reason about (a face of the local bbox + two 0..1 coords) into the world
    point + surface normal the coordinate-hungry verbs (sculpt/select/add) need, and
    hands the coordinate back so the agent learns it instead of inventing it.

    face: which local bbox face to cast FROM, as a signed axis — -Y +Y -X +X -Z +Z.
          '-Y' = origin on the −Y face, ray travels +Y INTO the volume.
    u, v: 0..1 position on that face over the OTHER two local axes (ascending index,
          X<Y<Z). face=-Y → u:X, v:Z. face=-Z → u:X, v:Y. 0=min, 0.5=centre, 1=max.
    Casts onto the EVALUATED surface (subsurf/modifiers included)."""
    from mathutils import Vector
    name = params.get("target")
    obj = bpy.data.objects.get(name) if name else bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": f"target '{name}' not a mesh"}
    face = str(params.get("face", "-Y")).strip().upper()
    if len(face) != 2 or face[0] not in "+-" or face[1] not in "XYZ":
        return {"error": f"face '{face}' invalid — use one of -Y +Y -X +X -Z +Z"}
    u = float(params.get("u", 0.5))
    v = float(params.get("v", 0.5))
    sign = -1.0 if face[0] == "-" else 1.0
    axis = {"X": 0, "Y": 1, "Z": 2}[face[1]]
    other = [i for i in (0, 1, 2) if i != axis]   # ascending → other[0]=u, other[1]=v

    bb = [Vector(c) for c in obj.bound_box]        # 8 corners, LOCAL space
    mn = Vector((min(c.x for c in bb), min(c.y for c in bb), min(c.z for c in bb)))
    mx = Vector((max(c.x for c in bb), max(c.y for c in bb), max(c.z for c in bb)))
    span = mx - mn
    margin = max(float(params.get("margin", 0.0)) or 0.0, 1e-4)

    # face plane along `axis`: -X/-Y/-Z face sits at mn[axis], +face at mx[axis].
    face_pos = mn[axis] if sign < 0 else mx[axis]
    ray_dir_axis = 1.0 if sign < 0 else -1.0       # into the volume
    origin = Vector((0.0, 0.0, 0.0))
    origin[axis] = face_pos - ray_dir_axis * margin   # start just OUTSIDE the face
    origin[other[0]] = mn[other[0]] + u * span[other[0]]
    origin[other[1]] = mn[other[1]] + v * span[other[1]]
    direction = Vector((0.0, 0.0, 0.0))
    direction[axis] = ray_dir_axis
    distance = float(span[axis]) + 2 * margin

    hit, loc_local, nrm_local, idx = obj.ray_cast(origin, direction, distance=distance)
    if not hit:
        return {"note": f"ray missed — no surface behind face={face} u={u} v={v} "
                        f"(try other u/v, or the opposite face)", "hit": False}
    mw = obj.matrix_world
    loc_w = mw @ loc_local
    nrm_w = (mw.to_3x3() @ nrm_local).normalized()
    bbox = world_bbox(obj)
    return {
        "success": True, "hit": True,
        "point": [round(c, 5) for c in loc_w],
        "normal": [round(c, 4) for c in nrm_w],
        "region": region_words(bbox, loc_w),
        "cast_axis": face,
        "push_out": f"move +normal to pull OUT, -normal to push IN",
    }


TOOLS = {
    "describe":         describe,
    "distance_between": distance_between,
    "gap_between":      gap_between,
    "is_aligned":       is_aligned,
    "check_symmetry":   check_symmetry,
    "aim_surface":      aim_surface,
}

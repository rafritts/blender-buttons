"""Edit-mode ripcord: bevel, extrude, loop_cut, component mode, selection ops,
move/scale vertices. Prefer the relational verbs in `relational.py` when possible."""

import math

import bpy
from mathutils import Quaternion, Vector

from .state import push_undo


# ───────────────────────── local-frame direction vocabulary (F1) ─────────────
# Shared by the vertex-moving verbs (extrude / move_vertices / proportional_move)
# and sculpt_grab. All distances are METERS in WORLD space. The words:
#   out / inward            — along the selection's area-weighted average normal
#                             (recomputed fresh each call, so no bbox-unit drift)
#   up/down/left/right/      — the nudge words: world ±Z / ±X / ±Y
#     forward/back
# 'in' is a Python keyword, so the inward word is spelled `inward` at the API.

_DIR_WORDS = ("out", "inward", "up", "down", "left", "right", "forward", "back")

# Below this ratio (|Σnormals| / Σweights) the selection's normals substantially
# cancel — a closed ring / sphere band / full loop — and 'out' has no meaningful
# direction. Refuse rather than move along a garbage average.
_NORMAL_DEGENERATE = 0.2


def _has_dir_words(params):
    return any(abs(float(params.get(w, 0.0) or 0.0)) > 0 for w in _DIR_WORDS)


def _avg_normal_world(bm, obj):
    """Area-weighted average WORLD normal of the current selection.

    Returns (unit_vec | None, ratio) where ratio = |Σ| / Σweights in [0, 1].
    A low ratio means the normals cancel (closed band) — the caller refuses.
    Prefers selected faces (area-weighted); falls back to selected vert normals
    when no whole face is selected (a bare rim/edge loop)."""
    nmat = obj.matrix_world.to_3x3()
    acc = Vector((0.0, 0.0, 0.0))
    total = 0.0
    sel_faces = [f for f in bm.faces if f.select]
    if sel_faces:
        for f in sel_faces:
            wn = nmat @ f.normal
            if wn.length == 0:
                continue
            w = f.calc_area()
            acc += wn.normalized() * w
            total += w
    else:
        for v in bm.verts:
            if not v.select:
                continue
            wn = nmat @ v.normal
            if wn.length == 0:
                continue
            acc += wn.normalized()
            total += 1.0
    if total == 0 or acc.length == 0:
        return None, 0.0
    return acc.normalized(), acc.length / total


def _describe_dir(n):
    """Name a world unit vector in scene-semantic words so the agent can
    cross-check its mental model — e.g. 'forward, 15° above level'."""
    n = n.normalized()
    elev = math.degrees(math.asin(max(-1.0, min(1.0, n.z))))
    if math.hypot(n.x, n.y) < 1e-4:
        return "straight up" if n.z >= 0 else "straight down"
    if abs(n.x) >= abs(n.y):
        word = "right" if n.x > 0 else "left"
    else:
        word = "back" if n.y > 0 else "forward"
    if abs(elev) < 5:
        return f"{word}, level"
    return f"{word}, {round(abs(elev))}° {'above' if elev > 0 else 'below'} level"


def _resolve_world_delta(bm, obj, params):
    """Resolve the F1 direction words into a world-space translation (meters).

    Returns (Vector, frame_str | None, err_dict | None). `frame_str` is set only
    when out/inward is used (the normal direction the agent can't see)."""
    vec = Vector((0.0, 0.0, 0.0))
    vec.x += float(params.get("right", 0.0) or 0.0) - float(params.get("left", 0.0) or 0.0)
    vec.y += float(params.get("back", 0.0) or 0.0) - float(params.get("forward", 0.0) or 0.0)
    vec.z += float(params.get("up", 0.0) or 0.0) - float(params.get("down", 0.0) or 0.0)
    frame = None
    nrm_amt = float(params.get("out", 0.0) or 0.0) - float(params.get("inward", 0.0) or 0.0)
    if nrm_amt != 0.0:
        bm.normal_update()
        n, ratio = _avg_normal_world(bm, obj)
        if n is None or ratio < _NORMAL_DEGENERATE:
            return None, None, {"error":
                "selection normals cancel (closed ring / band / full loop) — 'out'/'inward' "
                "has no well-defined direction here. For a radial puff use inflate_selection; "
                "otherwise move along a world direction (up/down/left/right/forward/back)."}
        vec = vec + n * nrm_amt
        frame = "out ≈ " + _describe_dir(n)
    return vec, frame, None


def _flush_vert_selection(bm):
    """Make a per-vertex selection authoritative across the edge/face domains
    (gaps.md X3). A selector that writes vert flags must not leave a stale prior
    edge/face selection live: in EDGE/FACE component mode, `select_flush_mode`
    re-derives verts FROM those stale higher elements and clobbers the verts just
    set — which is how a 24-vert band left all 6554 edges + 3268 faces selected and
    the next region-extrude cloned the whole mesh. Clear the higher domains, then
    flush UP so an edge/face is selected iff ALL its verts are — exactly the
    just-chosen verts drive what the next verb acts on. Flushes up to the current
    component mode (doesn't force VERT).

    The sequence matters: capture the wanted verts FIRST, then clear every domain,
    then re-set the verts, then `select_flush(True)` to promote. Clearing can't come
    after the selector's own flag-setting, because `edge.select = False` flushes
    DOWN and would deselect the very verts we want — capturing first sidesteps that.
    `select_flush(True)` then lights edges/faces fully enclosed by the verts and is
    what survives `update_edit_mesh`'s re-flush in EDGE/FACE component mode."""
    want = [v for v in bm.verts if v.select]
    for f in bm.faces:
        f.select = False
    for e in bm.edges:
        e.select = False
    for v in bm.verts:
        v.select = False
    for v in want:
        v.select = True
    bm.select_flush(True)


def bevel(params):
    width    = params.get("width")
    factor   = params.get("factor", 0.05)
    segments = params.get("segments", 1)
    affect   = params.get("affect", "EDGES").upper()
    obj = bpy.context.active_object
    dims = obj.dimensions if obj and obj.type == 'MESH' else None
    if width is not None and float(width) > 0:
        # F3: width is a world-space offset in METERS (documented-primary).
        offset = float(width)
    elif dims:
        min_dim = min(d for d in [dims.x, dims.y, dims.z] if d > 0) if any(d > 0 for d in [dims.x, dims.y, dims.z]) else 1.0
        offset = factor * min_dim
    else:
        offset = factor
    bpy.ops.mesh.bevel(offset=offset, segments=segments, affect=affect)
    return {"success": True, "offset_world": round(offset, 5)}


def extrude(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "No active mesh object"}
    if obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    until_contact = (params.get("until_contact") or "").strip()
    until_length = float(params.get("until_length", 0.0) or 0.0)
    has_dir = _has_dir_words(params)

    # F1/F2 path: meter-based direction words and/or a closed-loop termination.
    if has_dir or until_contact or until_length > 0:
        bm = bmesh.from_edit_mesh(obj.data)
        # When a termination is given the magnitude is supplied by it, so default
        # the direction to `out` if the caller named none.
        dir_params = params if has_dir else {"out": 1.0}
        wv, frame, err = _resolve_world_delta(bm, obj, dir_params)
        if err:
            return err
        if wv.length == 0:
            return {"error": "No direction given (e.g. out=, up=, until_length=…)"}

        if until_contact or until_length > 0:
            unit = wv.normalized()
            if until_contact:
                dist, hit_err = _contact_distance(bm, obj, unit, until_contact)
                if hit_err:
                    return hit_err
                term = f"contact with '{until_contact}'"
            else:
                dist = until_length
                term = f"length {until_length}m"
            translate = unit * dist
        else:
            translate = wv
            term = None

        bpy.ops.mesh.extrude_region_move(
            TRANSFORM_OT_translate={"value": tuple(translate), "orient_type": "GLOBAL"})
        result = {"success": True,
                  "translation_world": [round(c, 4) for c in translate]}
        if frame:
            result["frame"] = frame
        if term:
            result["terminated_at"] = term
            result["distance_world"] = round(translate.length, 4)
        return result

    # Legacy fraction-of-bbox path (kept for old tests/transcripts).
    fx = params.get("x", 0.0)
    fy = params.get("y", 0.0)
    fz = params.get("z", 0.0)
    dims = obj.dimensions
    x = fx * dims.x
    y = fy * dims.y
    z = fz * dims.z
    bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": (x, y, z)})
    return {"success": True, "translation_world": [round(x, 4), round(y, 4), round(z, 4)]}


def _contact_distance(bm, obj, unit, target_name):
    """First-contact distance (meters) along `unit` from the selected geometry to
    the named object's evaluated surface. Returns (dist, None) or (None, err)."""
    from .common import object_bvh
    target = bpy.data.objects.get(target_name)
    if target is None:
        return None, {"error": f"until_contact: object '{target_name}' not found"}
    if target.name == obj.name:
        return None, {"error": "until_contact: target must be a different object"}
    bvh = object_bvh(target)
    if bvh is None:
        return None, {"error": f"until_contact: '{target_name}' has no evaluable mesh"}
    mat = obj.matrix_world
    sel = [v for v in bm.verts if v.select]
    if not sel:
        return None, {"error": "No geometry selected to extrude"}
    eps = 1e-5
    best = None
    for v in sel:
        origin = (mat @ v.co) + unit * eps
        hit = bvh.ray_cast(origin, unit)
        if hit and hit[0] is not None:
            d = hit[3] + eps
            if d > eps and (best is None or d < best):
                best = d
    if best is None:
        return None, {"error": f"until_contact: no surface of '{target_name}' lies "
                               "along the extrude direction"}
    return best, None


# ───────────────────────── sweep the selection along a curve (G1) ────────────
# extrude_along_curve: the classic SWEEP — extrude the current edit-mode face
# selection along a curve in ONE call (spline_tube sweeps a circle into a NEW
# object; this aims the same idea at the in-mesh selection). Reuses the F1 frame:
# the curve describes the SHAPE of the path, re-rooted so its start sits at the
# selection's centroid with its initial tangent aligned to the selection's `out`
# normal. Frames are carried by PARALLEL TRANSPORT (minimal twist), never Frenet
# (which flips 180° at inflections and candy-wraps the mesh).


def _order_curve_chain(verts, edges):
    """Order an evaluated curve's polyline verts into a single walk. `verts` is a
    list of world Vectors, `edges` a list of (i, j) index pairs. Walks from an
    open endpoint (degree-1); falls back to index order if the graph is cyclic or
    disconnected. Returns the ordered list of Vectors for the chain containing the
    start endpoint."""
    adj = {i: [] for i in range(len(verts))}
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    ends = [i for i, nb in adj.items() if len(nb) == 1]
    if not ends:
        return list(verts)  # cyclic / no clear endpoint — trust index order
    start = ends[0]
    order = [start]
    prev, cur = -1, start
    while True:
        nxt = [x for x in adj[cur] if x != prev]
        if not nxt or nxt[0] == start:
            break
        prev, cur = cur, nxt[0]
        order.append(cur)
    return [verts[i] for i in order]


def _resample_polyline(pts, n):
    """Resample a dense world-space polyline into n+1 ARC-LENGTH-EQUIDISTANT
    points (one extrude step per segment). Returns (points, total_length)."""
    cum = [0.0]
    for i in range(len(pts) - 1):
        cum.append(cum[-1] + (pts[i + 1] - pts[i]).length)
    total = cum[-1]
    if total == 0:
        return None, 0.0
    out = [pts[0].copy()]
    j = 0
    for k in range(1, n):
        d = total * k / n
        while j < len(cum) - 2 and cum[j + 1] < d:
            j += 1
        seg = cum[j + 1] - cum[j]
        t = 0.0 if seg == 0 else (d - cum[j]) / seg
        out.append(pts[j].lerp(pts[j + 1], t))
    out.append(pts[-1].copy())
    return out, total


def _sweep_path(curve_obj, n, centroid, out):
    """Build the n+1 world-space path points for the sweep. Samples the curve's
    evaluated shape, resamples to arc-length-equidistant, then re-roots it so the
    start sits at `centroid` with its initial tangent rotated onto `out` (the F1
    frame). Returns (points, total_length, err)."""
    deps = bpy.context.evaluated_depsgraph_get()
    ce = curve_obj.evaluated_get(deps)
    me = ce.to_mesh()
    try:
        if len(me.polygons) > 0:
            return None, 0.0, {"error":
                f"curve '{curve_obj.name}' has thickness (a bevel/tube surface) — pass a "
                "pure PATH curve (add_curve with bevel_depth=0). The sweep needs the "
                "centerline, not a solid."}
        cmat = curve_obj.matrix_world
        world = [cmat @ v.co.copy() for v in me.vertices]
        edges = [(e.vertices[0], e.vertices[1]) for e in me.edges]
    finally:
        ce.to_mesh_clear()
    if len(world) < 2:
        return None, 0.0, {"error": f"curve '{curve_obj.name}' has no usable path "
                                    "(need at least 2 evaluated points)"}
    ordered = _order_curve_chain(world, edges)
    resampled, total = _resample_polyline(ordered, n)
    if resampled is None:
        return None, 0.0, {"error": f"curve '{curve_obj.name}' has zero length"}
    init_tan = (resampled[1] - resampled[0])
    if init_tan.length == 0:
        return None, 0.0, {"error": "curve start is degenerate (first two points coincide)"}
    rc = init_tan.normalized().rotation_difference(out)
    p0 = resampled[0]
    path = [centroid + (rc @ (p - p0)) for p in resampled]
    return path, total, None


def extrude_along_curve(params):
    """Sweep the current edit-mode FACE selection along a curve in one call (G1)."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "No active mesh object"}
    if obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with a face selected"}

    curve_name = (params.get("curve") or "").strip()
    if not curve_name:
        return {"error": "'curve' (an existing curve object's name) is required"}
    curve_obj = bpy.data.objects.get(curve_name)
    if curve_obj is None:
        return {"error": f"curve '{curve_name}' not found"}
    if curve_obj.type != 'CURVE':
        return {"error": f"'{curve_name}' is a {curve_obj.type.lower()}, not a curve "
                         "(author the path with add_curve)"}

    segments = max(1, min(int(params.get("segments", 8)), 256))
    taper = float(params.get("taper", 1.0))
    if taper <= 0:
        return {"error": "'taper' must be > 0 (1.0 = no taper, 0.3 = tip at 30%)"}

    bm = bmesh.from_edit_mesh(obj.data)
    bm.normal_update()
    cap_faces = [f for f in bm.faces if f.select]
    if not cap_faces:
        return {"error": "select at least one FACE to sweep (extrude_along_curve sweeps "
                         "a face region into a tube — like a horn cap)"}

    # F1 frame: the curve's start aligns to the selection's area-weighted 'out'.
    out, ratio = _avg_normal_world(bm, obj)
    if out is None or ratio < _NORMAL_DEGENERATE:
        return {"error":
            "selection normals cancel (closed ring / band / full loop) — there's no "
            "well-defined 'out' to align the curve's start to. Sweep an open cap "
            "(a single face or a contiguous face patch that points somewhere)."}

    mat = obj.matrix_world
    inv = mat.inverted()
    cap_verts = list({v for f in cap_faces for v in f.verts})
    centroid = Vector((0.0, 0.0, 0.0))
    for v in cap_verts:
        centroid += mat @ v.co
    centroid /= len(cap_verts)

    # Per-vert profile offset, split into the along-normal (depth) and in-plane
    # (cross-section) parts — taper scales only the in-plane part (F3 in_plane).
    profile = {}
    profile_radius = 0.0
    for v in cap_verts:
        o = (mat @ v.co) - centroid
        nc = out * o.dot(out)
        ip = o - nc
        profile[v] = (nc, ip)
        profile_radius = max(profile_radius, ip.length)

    path, total, err = _sweep_path(curve_obj, segments, centroid, out)
    if err:
        return err

    # Self-intersection guard (same spirit as F1's degeneracy guard): where the
    # path's bend radius drops below the profile radius, the inner wall folds
    # through itself. Estimate bend radius per interior sample as ds/dθ.
    min_bend = float("inf")
    for i in range(1, segments):
        d1 = path[i] - path[i - 1]
        d2 = path[i + 1] - path[i]
        if d1.length == 0 or d2.length == 0:
            continue
        phi = d1.angle(d2, 0.0)
        if phi < 1e-4:
            continue
        ds = (d1.length + d2.length) * 0.5
        min_bend = min(min_bend, ds / phi)
    if profile_radius > 0 and min_bend < profile_radius:
        return {"error":
            f"sweep would self-intersect: tightest bend radius {round(min_bend, 4)}m is "
            f"smaller than the profile radius {round(profile_radius, 4)}m, so the inner "
            "wall folds through itself. Use a gentler curve, more spacing, or scale the "
            "selection down (scale_vertices in_plane=) before sweeping."}

    # Sweep: one extrude_face_region per sample, repositioning each new cap vert
    # into the parallel-transported, taper-scaled frame at that sample.
    current = dict(profile)            # live cap vert -> (normal_comp, in_plane)
    cur_faces = cap_faces
    prev_tan = out
    q = Quaternion()                   # accumulated parallel-transport rotation
    steps = 0
    for i in range(1, segments + 1):
        seg = path[i] - path[i - 1]
        seg_tan = seg.normalized() if seg.length > 0 else prev_tan
        q = prev_tan.rotation_difference(seg_tan) @ q
        prev_tan = seg_tan
        rot = q.to_matrix()
        s = 1.0 + (taper - 1.0) * (i / segments)

        ret = bmesh.ops.extrude_face_region(bm, geom=cur_faces)
        new_verts = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
        new_set = set(new_verts)
        top_faces = [g for g in ret["geom"]
                     if isinstance(g, bmesh.types.BMFace) and all(fv in new_set for fv in g.verts)]
        old_set = set(current.keys())
        old_to_new = {}
        for nv in new_verts:
            for e in nv.link_edges:
                ov = e.other_vert(nv)
                if ov in old_set:
                    old_to_new[ov] = nv
                    break

        nxt = {}
        for ov, (nc, ip) in current.items():
            nv = old_to_new.get(ov)
            if nv is None:
                continue
            nv.co = inv @ (path[i] + (rot @ (nc + ip * s)))
            nxt[nv] = (nc, ip)
        current = nxt
        cur_faces = top_faces
        steps += 1

    # Leave the final cap selected so the sweep can be continued / capped.
    for f in bm.faces:
        f.select = False
    for e in bm.edges:
        e.select = False
    for v in bm.verts:
        v.select = False
    for v in current:
        v.select = True
    bm.select_flush(True)

    bmesh.update_edit_mesh(obj.data)
    push_undo(f"extrude_along_curve {curve_name} x{segments}")
    return {
        "success": True,
        "steps": steps,
        "path_length": round(total, 4),
        "frame": "out ≈ " + _describe_dir(out),
        "profile_radius": round(profile_radius, 4),
        "min_bend_radius": (round(min_bend, 4) if min_bend != float("inf") else None),
        "taper": taper,
    }


def select_all(params):
    action = params.get("action", "SELECT").upper()
    bpy.ops.mesh.select_all(action=action)
    return {"success": True}


def select_by_axis(params):
    import bmesh
    axis       = params.get("axis", "Z").upper()
    factor     = params.get("factor", 0.5)
    comparison = params.get("comparison", "GREATER").upper()
    action     = params.get("action", "SELECT").upper()
    extend     = bool(params.get("extend", False))

    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with an active object"}

    bm = bmesh.from_edit_mesh(obj.data)
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)

    world_vals = [(obj.matrix_world @ v.co)[axis_idx] for v in bm.verts]
    v_min, v_max = min(world_vals), max(world_vals)
    threshold = v_min + factor * (v_max - v_min)

    count = 0
    for vert in bm.verts:
        val = (obj.matrix_world @ vert.co)[axis_idx]
        matches = (val > threshold) if comparison == "GREATER" else (val < threshold)
        if action == "DESELECT":
            if matches:
                vert.select = False
        elif extend:
            # additive: turn matching verts ON, never clear the prior selection —
            # so two by_axis calls can union two regions (e.g. both sleeves).
            if matches:
                vert.select = True
        else:
            vert.select = matches
        if vert.select:
            count += 1

    _flush_vert_selection(bm)
    bmesh.update_edit_mesh(obj.data)
    return {"success": True, "threshold_world": round(threshold, 4),
            "selected_count": count}


def select_between(params):
    import bmesh
    axis       = params.get("axis", "Z").upper()
    lo         = params.get("lo", 0.0)
    hi         = params.get("hi", 1.0)
    action     = params.get("action", "SELECT").upper()
    extend     = bool(params.get("extend", False))
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with an active object"}
    bm = bmesh.from_edit_mesh(obj.data)
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    world_vals = [(obj.matrix_world @ v.co)[axis_idx] for v in bm.verts]
    v_min, v_max = min(world_vals), max(world_vals)
    lo_thresh = v_min + lo * (v_max - v_min)
    hi_thresh = v_min + hi * (v_max - v_min)
    count = 0
    for vert in bm.verts:
        val = (obj.matrix_world @ vert.co)[axis_idx]
        in_range = lo_thresh <= val <= hi_thresh
        if action == "DESELECT":
            if in_range:
                vert.select = False
        elif extend:
            if in_range:
                vert.select = True
        else:
            vert.select = in_range
        if vert.select:
            count += 1
    _flush_vert_selection(bm)
    bmesh.update_edit_mesh(obj.data)
    return {
        "success": True,
        "lo_world": round(lo_thresh, 4),
        "hi_world": round(hi_thresh, 4),
        "selected_count": count,
    }


def loop_cut(params):
    import bmesh
    import mathutils
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    cuts     = params.get("cuts", 1)
    axis     = params.get("axis", "Z").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)

    bm = bmesh.from_edit_mesh(obj.data)
    mat = obj.matrix_world

    # Z2/X7: honor the current selection — cut only edges whose BOTH ends are
    # selected, so a support loop can be added to ONE limb without ribbing the whole
    # mesh. Whole-mesh is the fallback ONLY when nothing is selected (the case the
    # target= auto-switch produces, since it deselects on entry).
    selected = {v.index for v in bm.verts if v.select}
    scoped = len(selected) > 0
    bm.verts.ensure_lookup_table()

    def along_axis(e):
        return abs(((mat @ e.verts[1].co) - (mat @ e.verts[0].co))
                   .normalized()[axis_idx]) > 0.7

    edges_to_cut = [
        e for e in bm.edges
        if along_axis(e)
        and (not scoped or (e.verts[0].index in selected and e.verts[1].index in selected))
    ]

    if not edges_to_cut:
        where = "within the selection " if scoped else ""
        return {"error": f"No edges {where}run along the {axis} axis. "
                         + ("Try a different axis, or widen the selection."
                            if scoped else f"Try a different axis.")}

    geom = bmesh.ops.subdivide_edges(bm, edges=edges_to_cut, cuts=cuts, use_grid_fill=True)
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"loop_cut {axis} x{cuts}")

    # Report in scene vocabulary, NOT a coordinate dump (X7): how many loops, where
    # they landed (region word + axis span), and whether the cut was scoped.
    new_verts = [g for g in geom["geom_inner"] if isinstance(g, bmesh.types.BMVert)]
    loop_keys = sorted(set(round((mat @ v.co)[axis_idx], 4) for v in new_verts))
    loops = len(loop_keys)
    span = [loop_keys[0], loop_keys[-1]] if loop_keys else None
    centroid = mathutils.Vector((0.0, 0.0, 0.0))
    for v in new_verts:
        centroid += mat @ v.co
    if new_verts:
        centroid /= len(new_verts)
    from .common import world_bbox, region_words
    region = region_words(world_bbox(obj), centroid) if new_verts else "center"
    return {"success": True, "cuts": cuts, "edges_subdivided": len(edges_to_cut),
            "loops": loops, "axis": axis, "span_world": span, "region": region,
            "scoped_to_selection": scoped}


def set_component_mode(params):
    mode = params.get("mode", "VERT").upper()
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    mode_map = {
        'VERT': (True, False, False),
        'EDGE': (False, True, False),
        'FACE': (False, False, True),
    }
    if mode not in mode_map:
        return {"error": f"Invalid mode '{mode}'. Use VERT, EDGE, or FACE"}
    bpy.context.tool_settings.mesh_select_mode = mode_map[mode]
    return {"success": True, "component_mode": mode}


def grow_selection(params):
    direction = params.get("direction", "GROW").upper()
    steps = params.get("steps", 1)
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    op = bpy.ops.mesh.select_more if direction == "GROW" else bpy.ops.mesh.select_less
    for _ in range(max(1, steps)):
        op()
    return {"success": True, "direction": direction, "steps": steps}


def move_vertices(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    bm = bmesh.from_edit_mesh(obj.data)
    selected = [v for v in bm.verts if v.select]
    if not selected:
        return {"error": "No vertices selected"}

    frame = None
    if _has_dir_words(params):
        # F1: meter-based RIGID translation — every selected vert moves by the same
        # world delta along the resolved direction (distinct from inflate_selection,
        # which moves each vert along its OWN normal).
        wv, frame, err = _resolve_world_delta(bm, obj, params)
        if err:
            return err
        local = obj.matrix_world.inverted().to_3x3() @ wv
        world_delta = [round(c, 5) for c in wv]
    else:
        # Legacy fraction-of-bbox path.
        fx = params.get("x", 0.0)
        fy = params.get("y", 0.0)
        fz = params.get("z", 0.0)
        dims = obj.dimensions
        scale = obj.scale
        local = Vector((fx * dims.x / (abs(scale.x) or 1.0),
                        fy * dims.y / (abs(scale.y) or 1.0),
                        fz * dims.z / (abs(scale.z) or 1.0)))
        world_delta = [round(fx * dims.x, 5), round(fy * dims.y, 5), round(fz * dims.z, 5)]

    for v in selected:
        v.co += local
    bmesh.update_edit_mesh(obj.data)
    push_undo("move_vertices")
    result = {"success": True, "verts_moved": len(selected), "delta_world": world_delta}
    if frame:
        result["frame"] = frame
    return result


def scale_vertices(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    in_plane = params.get("in_plane")
    pivot = params.get("pivot", "SELECTION")  # SELECTION | ORIGIN
    bm = bmesh.from_edit_mesh(obj.data)
    selected = [v for v in bm.verts if v.select]
    if not selected:
        return {"error": "No vertices selected"}

    if in_plane is not None:
        # F3: uniform scale IN the selection's tangent plane (perpendicular to the
        # average normal). World-axis multipliers are meaningless on a tilted patch;
        # this dilates/contracts the patch within its own surface, leaving the
        # normal (depth) component untouched — widen a collar, shrink an iris.
        f = float(in_plane)
        n, ratio = _avg_normal_world(bm, obj)
        if n is None or ratio < _NORMAL_DEGENERATE:
            return {"error":
                "selection normals cancel — no well-defined tangent plane for in_plane "
                "scaling. Use per-axis x/y/z multipliers, or scale_rings for a closed loop."}
        n_local = (obj.matrix_world.inverted().to_3x3() @ n)
        if n_local.length == 0:
            return {"error": "degenerate normal in local space"}
        n_local.normalize()
        c = Vector((sum(v.co.x for v in selected) / len(selected),
                    sum(v.co.y for v in selected) / len(selected),
                    sum(v.co.z for v in selected) / len(selected)))
        for v in selected:
            offset = v.co - c
            normal_comp = n_local * offset.dot(n_local)
            tangent = offset - normal_comp
            v.co = c + normal_comp + tangent * f
        bmesh.update_edit_mesh(obj.data)
        push_undo(f"scale_vertices in_plane={f}")
        return {"success": True, "verts_scaled": len(selected),
                "frame": "in-plane ⟂ " + _describe_dir(n)}

    sx = params.get("x", 1.0)
    sy = params.get("y", 1.0)
    sz = params.get("z", 1.0)
    if pivot == "SELECTION":
        cx = sum(v.co.x for v in selected) / len(selected)
        cy = sum(v.co.y for v in selected) / len(selected)
        cz = sum(v.co.z for v in selected) / len(selected)
    else:
        cx = cy = cz = 0.0
    for v in selected:
        v.co.x = cx + (v.co.x - cx) * sx
        v.co.y = cy + (v.co.y - cy) * sy
        v.co.z = cz + (v.co.z - cz) * sz
    bmesh.update_edit_mesh(obj.data)
    push_undo("scale_vertices")
    return {"success": True, "verts_scaled": len(selected)}


_FALLOFFS = {"SMOOTH", "LINEAR", "SPHERE", "SHARP", "ROOT", "CONSTANT"}


def proportional_move(params):
    """Move selected verts with a falloff — drags nearby verts along with the pull.

    This is the donut-tutorial proportional-editing equivalent: each selected vert
    acts as a "handle" that pulls every vert within `radius` along with the
    translation, weighted by distance. Selected verts move the full amount; verts
    at exactly the radius edge don't move at all.

    x, y, z: translation as a fraction of the object's dimensions (same units as
             move_vertices).
    radius:  falloff radius in meters. Default 0.01 (1cm).
    falloff: SMOOTH (default — smoothstep, soft round shape) | LINEAR | SPHERE |
             SHARP (sharp at edge) | ROOT | CONSTANT (no falloff — full move within radius).

    Use case: icing drips. Select a sparse set of boundary verts, then
    proportional_move(z=-0.5, radius=0.005, falloff=SMOOTH) — each pulled vert
    drags its neighbors down with it, making round bulbous drips instead of
    triangular spikes.
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    radius = float(params.get("radius", 0.01))
    if radius <= 0:
        return {"error": "'radius' must be > 0"}
    falloff = (params.get("falloff") or "SMOOTH").upper()
    if falloff not in _FALLOFFS:
        return {"error": f"Invalid falloff '{falloff}'. Use {sorted(_FALLOFFS)}"}

    scale = obj.scale
    sx = abs(scale.x) or 1.0
    sy = abs(scale.y) or 1.0
    sz = abs(scale.z) or 1.0

    frame = None
    if _has_dir_words(params):
        # F1: meter-based direction words. _bm is built below for the handles, but
        # the average normal only depends on the current selection — build a read
        # handle now.
        _bm0 = bmesh.from_edit_mesh(obj.data)
        wv, frame, err = _resolve_world_delta(_bm0, obj, params)
        if err:
            return err
        local = obj.matrix_world.inverted().to_3x3() @ wv
        dx, dy, dz = local.x, local.y, local.z
        delta_world = [round(c, 5) for c in wv]
    else:
        fx = float(params.get("x", 0.0))
        fy = float(params.get("y", 0.0))
        fz = float(params.get("z", 0.0))
        dims = obj.dimensions
        # Local-space deltas (mirrors move_vertices).
        dx = fx * dims.x / sx
        dy = fy * dims.y / sy
        dz = fz * dims.z / sz
        delta_world = [round(fx * dims.x, 5), round(fy * dims.y, 5), round(fz * dims.z, 5)]
    # Radius is in world meters; convert to local space (approx — pick the
    # smallest scale so we err on the side of a larger local radius).
    inv_scale_min = 1.0 / min(sx, sy, sz)
    radius_local = radius * inv_scale_min
    r2 = radius_local * radius_local

    bm = bmesh.from_edit_mesh(obj.data)
    handles = [v for v in bm.verts if v.select]
    if not handles:
        return {"error": "No vertices selected"}
    handle_cos = [v.co.copy() for v in handles]

    affected = 0
    for v in bm.verts:
        # Find nearest handle — squared distance keeps the hot loop sqrt-free.
        best2 = r2
        for h in handle_cos:
            d2 = (v.co - h).length_squared
            if d2 < best2:
                best2 = d2
        if best2 >= r2:
            continue
        d = best2 ** 0.5
        t = d / radius_local  # 0 at handle, 1 at radius edge
        if falloff == "SMOOTH":
            w = 1.0 - t * t * (3.0 - 2.0 * t)
        elif falloff == "LINEAR":
            w = 1.0 - t
        elif falloff == "SPHERE":
            inner = 1.0 - t * t
            w = inner ** 0.5 if inner > 0 else 0.0
        elif falloff == "SHARP":
            w = (1.0 - t) ** 2
        elif falloff == "ROOT":
            w = 1.0 - t ** 0.5
        else:  # CONSTANT
            w = 1.0
        v.co.x += dx * w
        v.co.y += dy * w
        v.co.z += dz * w
        affected += 1

    bmesh.update_edit_mesh(obj.data)
    push_undo(f"proportional_move r={radius} {falloff}")
    result = {
        "success": True,
        "handles": len(handles),
        "affected": affected,
        "radius": radius,
        "falloff": falloff,
        "delta_world": delta_world,
    }
    if frame:
        result["frame"] = frame
    return result


def random_select(params):
    """Randomly thin out the current selection.

    Keeps a `fraction` of the currently-selected verts; deselects the rest.
    Use to turn a uniform ring/loop into a sparse pattern — e.g., the
    "pick random verts on the icing boundary to pull down as drips" step.

    fraction: 0.0–1.0. Fraction of selected verts to keep. Default 0.2.
    seed:     RNG seed for reproducibility. Default 0.
    """
    import bmesh
    import random as _random
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    fraction = float(params.get("fraction", 0.2))
    if not 0.0 < fraction <= 1.0:
        return {"error": "'fraction' must be in (0, 1]"}
    seed = int(params.get("seed", 0))
    rng = _random.Random(seed)

    bm = bmesh.from_edit_mesh(obj.data)
    selected = [v for v in bm.verts if v.select]
    if not selected:
        return {"error": "No vertices selected"}
    keep_count = max(1, int(round(len(selected) * fraction)))
    keep = set(rng.sample(range(len(selected)), keep_count))
    for i, v in enumerate(selected):
        if i not in keep:
            v.select = False
    _flush_vert_selection(bm)
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"random_select {fraction}")
    return {"success": True, "kept": keep_count, "from": len(selected), "seed": seed}


def jitter_vertices(params):
    """Randomly displace selected vertices — the easy path to organic, lumpy geometry.

    amount:    max displacement in meters (default 0.005 = 5mm). Each vertex is offset
               by a uniform random value in [-amount, +amount] along the chosen axis.
    axis:      NORMAL (along each vert's normal — best for organic puffing) |
               X | Y | Z (along world axis) | XYZ (independent random on all 3 axes).
               Default NORMAL.
    seed:      RNG seed for reproducibility. Default 0.
    only_positive: if true, displacement is in [0, amount] (only outward). Default false.

    Use cases:
      - donut tutorial: jitter all the donut's verts along NORMAL for lumpy dough
      - icing drips: jitter the icing's bottom ring along Z (negative) for drippy edges
    """
    import bmesh
    import random as _random
    import mathutils as _mu
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    amount = float(params.get("amount", 0.005))
    axis = (params.get("axis") or "NORMAL").upper()
    seed = int(params.get("seed", 0))
    only_positive = bool(params.get("only_positive", False))

    rng = _random.Random(seed)
    bm = bmesh.from_edit_mesh(obj.data)
    selected = [v for v in bm.verts if v.select]
    if not selected:
        return {"error": "No vertices selected"}

    # Convert world-space amount into local space (account for object scale).
    scale = obj.scale
    inv_scale = _mu.Vector((
        amount / (abs(scale.x) or 1.0),
        amount / (abs(scale.y) or 1.0),
        amount / (abs(scale.z) or 1.0),
    ))

    def _rand():
        return rng.uniform(0.0, 1.0) if only_positive else rng.uniform(-1.0, 1.0)

    if axis == "NORMAL":
        for v in selected:
            n = v.normal
            if n.length == 0:
                continue
            d = _rand()
            v.co += n * (d * amount)
    elif axis in ("X", "Y", "Z"):
        idx = {"X": 0, "Y": 1, "Z": 2}[axis]
        for v in selected:
            d = _rand()
            v.co[idx] += d * inv_scale[idx]
    elif axis == "XYZ":
        for v in selected:
            v.co.x += _rand() * inv_scale.x
            v.co.y += _rand() * inv_scale.y
            v.co.z += _rand() * inv_scale.z
    else:
        return {"error": f"Invalid axis '{axis}'. Use NORMAL | X | Y | Z | XYZ"}

    bmesh.update_edit_mesh(obj.data)
    push_undo(f"jitter_vertices {axis} ±{amount}")
    return {"success": True, "verts_jittered": len(selected),
            "amount": amount, "axis": axis, "seed": seed}


def inflate_selection(params):
    """Push selected verts along their normals by a fixed amount — the sculpt 'Inflate' brush as a one-shot.

    amount: meters to move along each vert's normal. Positive = outward (puff up),
            negative = inward (deflate). Default 0.003 (3mm).

    Use case: bulbous drip tips. After pulling drip-tip verts down with
    proportional_move, select just the tip verts and inflate_selection(amount=0.003)
    to bulge them outward into proper teardrop bulbs instead of pointy tongues.
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    amount = float(params.get("amount", 0.003))

    scale = obj.scale
    sx = abs(scale.x) or 1.0
    sy = abs(scale.y) or 1.0
    sz = abs(scale.z) or 1.0

    bm = bmesh.from_edit_mesh(obj.data)
    selected = [v for v in bm.verts if v.select]
    if not selected:
        return {"error": "No vertices selected"}
    moved = 0
    for v in selected:
        n = v.normal
        if n.length == 0:
            continue
        v.co.x += n.x * amount / sx
        v.co.y += n.y * amount / sy
        v.co.z += n.z * amount / sz
        moved += 1
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"inflate_selection {amount}")
    return {"success": True, "verts_inflated": moved, "amount": amount}


_DELETE_TYPES = {"VERT", "EDGE", "FACE", "ONLY_FACE", "EDGE_FACE"}


def delete_geometry(params):
    """Delete the current selection in edit mode.

    mode: VERT       — delete selected vertices (and the faces/edges touching them)
          EDGE       — delete selected edges
          FACE       — delete selected faces (and the edges/verts only used by them)
          ONLY_FACE  — delete faces only, leave their bounding edges + verts intact (creates a hole)
          EDGE_FACE  — delete edges and faces, leave verts

    Pairs with select_by_axis / select_between to carve away part of a mesh
    (e.g. delete the bottom half of a torus to make an open-bottomed dome).
    """
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    mode = params.get("mode", "VERT").upper()
    if mode not in _DELETE_TYPES:
        return {"error": f"Invalid mode '{mode}'. Use one of {sorted(_DELETE_TYPES)}"}
    bpy.ops.mesh.delete(type=mode)
    push_undo(f"delete_geometry {mode}")
    return {"success": True, "mode": mode}


def separate_selection(params):
    """Separate the current selection into a new object (the 'P → Selection' shortcut).

    new_name: optional name for the new object. If omitted, Blender appends '.001'.

    Returns the new object's name. The original object stays in edit mode; the new
    object is created in object mode and deselected from the edit context.
    """
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    before = set(bpy.data.objects.keys())
    bpy.ops.mesh.separate(type='SELECTED')
    after = set(bpy.data.objects.keys())
    new_names = after - before
    if not new_names:
        return {"error": "Nothing was separated — is anything selected?"}
    new_name = next(iter(new_names))

    requested = params.get("new_name")
    if requested:
        bpy.data.objects[new_name].name = requested
        if bpy.data.objects[requested].data is not None:
            bpy.data.objects[requested].data.name = requested
        new_name = requested

    push_undo(f"separate_selection → {new_name}")
    return {"success": True, "new_object": new_name, "source": obj.name}


def mark_sharp(params):
    """Mark selected edges as sharp (or clear). SubSurf + auto-smooth then preserves
    these as crisp creases instead of melting them into rounded blobs.

    clear: if true, unmark instead of mark. Default false.
    Operates on the currently selected edges. Switch to edge mode first.
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    clear = bool(params.get("clear", False))
    bm = bmesh.from_edit_mesh(obj.data)
    sel = [e for e in bm.edges if e.select]
    if not sel:
        return {"error": "No edges selected"}
    for e in sel:
        e.smooth = bool(clear)  # smooth=False == sharp
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"mark_sharp clear={clear}")
    return {"success": True, "edges_marked": len(sel), "clear": clear}


def set_edge_crease(params):
    """Set the SubSurf edge-crease weight on selected edges. 0 = no crease (default smoothing),
    1 = perfectly sharp under SubSurf. Use on hand/foot boxes after SubSurf to keep silhouette.

    weight: 0..1. Default 1.0.
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    weight = float(params.get("weight", 1.0))
    weight = max(0.0, min(1.0, weight))
    bm = bmesh.from_edit_mesh(obj.data)
    # Blender 4.0+/5.1 store edge crease as the generic float attribute "crease_edge"
    # (the legacy bm.edges.layers.crease accessor was removed). Verify/create the
    # layer BEFORE collecting edge refs — adding a layer reallocates and invalidates
    # any held BMEdge.
    cl = bm.edges.layers.float
    crease_layer = cl.get("crease_edge") or cl.new("crease_edge")
    sel = [e for e in bm.edges if e.select]
    if not sel:
        return {"error": "No edges selected"}
    for e in sel:
        e[crease_layer] = weight
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"set_edge_crease {weight}")
    return {"success": True, "edges_creased": len(sel), "weight": weight}


def merge_by_distance(params):
    """Weld coincident vertices in edit mode. After join_objects this fuses the seams
    between formerly-separate meshes so SubSurf treats the result as one continuous skin.

    threshold:    welding distance in meters (default 0.001 = 1mm).
    selected_only: if true, only merge currently selected verts. Default false (whole mesh).
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    threshold = float(params.get("threshold", 0.001))
    selected_only = bool(params.get("selected_only", False))
    bm = bmesh.from_edit_mesh(obj.data)
    verts = [v for v in bm.verts if v.select] if selected_only else list(bm.verts)
    if not verts:
        return {"error": "No vertices to merge"}
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=verts, dist=threshold)
    after = len(bm.verts)
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"merge_by_distance {threshold}")
    return {"success": True, "threshold": threshold, "verts_before": before,
            "verts_after": after, "merged": before - after}


def select_in_sphere(params):
    """Select vertices inside a world-space sphere — for localized region editing on joined meshes.

    center: [x, y, z] world coords (required).
    radius: meters (required).
    action: SELECT (replace) | ADD | DESELECT. Default SELECT.

    Pair with proportional_move or inflate_selection to bulge/sculpt that region.
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    center = params.get("center")
    if not (isinstance(center, list) and len(center) == 3):
        return {"error": "'center' must be a [x, y, z] list"}
    radius = float(params.get("radius", 0.1))
    if radius <= 0:
        return {"error": "'radius' must be > 0"}
    action = (params.get("action") or "SELECT").upper()
    # Unify on the `extend` flag used by by_axis/between: extend=True unions with
    # the current selection (reuses the existing additive ADD path).
    if bool(params.get("extend", False)) and action == "SELECT":
        action = "ADD"
    cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
    r2 = radius * radius
    bm = bmesh.from_edit_mesh(obj.data)
    mat = obj.matrix_world
    count = 0
    for v in bm.verts:
        wv = mat @ v.co
        d2 = (wv.x - cx) ** 2 + (wv.y - cy) ** 2 + (wv.z - cz) ** 2
        inside = d2 <= r2
        if action == "DESELECT":
            if inside:
                v.select = False
                count += 1
        elif action == "ADD":
            if inside:
                v.select = True
                count += 1
        else:
            v.select = inside
            if inside:
                count += 1
    _flush_vert_selection(bm)
    bmesh.update_edit_mesh(obj.data)
    return {"success": True, "selected": count, "center": [cx, cy, cz], "radius": radius,
            "action": action}


def select_boundary(params):
    """Select the OPEN-BOUNDARY edges of a mesh — the edges of a hole/rim (X3B).

    An open boundary edge borders exactly one face. This is the only way to grab a
    mesh rim: a tilted collar/sleeve/armhole loop can't be isolated by axis bands
    (a band always drags in adjacent faces). With a rim selected, set_edge_crease /
    mark_sharp can finally be AIMED at it — which is what fixes cut boundaries
    curling under SubSurf (Y2), and what rim insets / sleeve hems need.

    Switches to EDGE component mode (a boundary IS an edge set).

    from_selection: if True (default) and verts are already selected, restrict to
                    boundary edges touching that selection — grow a rim from a seed
                    region. With nothing selected, selects EVERY open boundary on the
                    mesh.
    action: SELECT (replace) | ADD | DESELECT. Default SELECT.
    """
    import bmesh
    import mathutils
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    action = (params.get("action") or "SELECT").upper()
    if action not in ("SELECT", "ADD", "DESELECT"):
        return {"error": f"Invalid action '{action}'. Use SELECT | ADD | DESELECT"}
    from_selection = bool(params.get("from_selection", True))

    bm = bmesh.from_edit_mesh(obj.data)
    seed = {v.index for v in bm.verts if v.select} if from_selection else set()
    boundary = [e for e in bm.edges if len(e.link_faces) == 1]
    if not boundary:
        return {"error": "No open boundary found — the mesh is closed/watertight "
                         "(every edge borders 2+ faces). Nothing to select."}
    if seed:
        boundary = [e for e in boundary
                    if e.verts[0].index in seed or e.verts[1].index in seed]
        if not boundary:
            return {"error": "No open boundary edges touch the current selection. "
                             "Deselect (select_all DESELECT) to grab all rims, or "
                             "seed nearer the hole."}

    # A boundary is an edge set — switch to EDGE component mode so the selection is
    # usable by set_edge_crease / mark_sharp.
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    if action == "SELECT":
        for f in bm.faces:
            f.select = False
        for e in bm.edges:
            e.select = False
        for v in bm.verts:
            v.select = False
    target = set(boundary)
    for e in bm.edges:
        if e in target:
            e.select = (action != "DESELECT")
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)

    mat = obj.matrix_world
    centroid = mathutils.Vector((0.0, 0.0, 0.0))
    for e in boundary:
        centroid += mat @ ((e.verts[0].co + e.verts[1].co) * 0.5)
    centroid /= len(boundary)
    from .common import world_bbox, region_words
    region = region_words(world_bbox(obj), centroid)
    push_undo(f"select_boundary {action}")
    return {"success": True, "action": action, "boundary_edges": len(boundary),
            "from_seed": bool(seed), "region": region}


def assign_weight(params):
    """Assign a vertex-group weight to the CURRENT edit-mode selection (Z1).

    The deform-side sibling of select_by_axis / select_in_sphere: select the verts
    (by axis band, sphere, ring…), then bind just those to a named group at a chosen
    weight. The general primitive the all-or-nothing binders lacked — weight_to_bone
    rigid-binds the WHOLE mesh to one bone, auto_weight heat-solves the WHOLE mesh;
    neither can say "these verts → this group, blended N%". A group named after a
    bone is read by an Armature modifier as that bone's influence; an arbitrary group
    is read by a MeshDeform / mask modifier's vertex_group slot — so this stays a
    general weight verb, not a bespoke 'bind the shoulder' tool.

    group:  vertex-group name (created on the mesh if absent). Required.
    weight: 0..1 weight to write. Default 1.0.
    mode:   REPLACE (set selected verts to `weight`) | ADD (add `weight`, clamped to
            1) | SUBTRACT (subtract `weight`, clamped to 0). Default REPLACE. Other
            groups are left untouched — assign partial weights to two groups to blend
            a bridge between two differently-driven meshes.
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    group = params.get("group")
    if not group:
        return {"error": "'group' (vertex-group / bone name) is required"}
    weight = float(params.get("weight", 1.0))
    weight = max(0.0, min(1.0, weight))
    mode = (params.get("mode") or "REPLACE").upper()
    if mode not in ("REPLACE", "ADD", "SUBTRACT"):
        return {"error": f"Invalid mode '{mode}'. Use REPLACE | ADD | SUBTRACT"}

    vg = obj.vertex_groups.get(group)
    created = vg is None
    if vg is None:
        vg = obj.vertex_groups.new(name=group)

    bm = bmesh.from_edit_mesh(obj.data)
    # Verify the deform layer BEFORE collecting vert refs — verify() can create the
    # layer and reallocate, invalidating any held BMVert ("BMesh data … removed").
    deform = bm.verts.layers.deform.verify()
    selected = [v for v in bm.verts if v.select]
    if not selected:
        return {"error": "No vertices selected"}
    gi = vg.index
    for v in selected:
        cur = v[deform].get(gi, 0.0)
        if mode == "REPLACE":
            new = weight
        elif mode == "ADD":
            new = min(1.0, cur + weight)
        else:  # SUBTRACT
            new = max(0.0, cur - weight)
        v[deform][gi] = new
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"assign_weight {group} {mode} {weight}")
    return {"success": True, "group": group, "group_created": created, "mode": mode,
            "weight": weight, "verts_assigned": len(selected)}


def split_by_part(params):
    """Split the active mesh into separate objects, one per connected component (P → By Loose Parts).

    After join_objects you lose per-part addressability; this restores it.
    Returns the names of the resulting objects.
    """
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    before = set(bpy.data.objects.keys())
    bpy.ops.mesh.separate(type='LOOSE')
    after = set(bpy.data.objects.keys())
    new_names = sorted(after - before)
    push_undo("split_by_part")
    return {"success": True, "source": obj.name, "new_objects": new_names,
            "part_count": len(new_names) + 1}


def select_limb(params):
    """Feature-anchored limb select (SPEC-06): select a whole protrusion — sleeve,
    limb, finger, spout — by its CAP REGION, anchored to the mesh's own topology, so
    a sleeve comes off at the armhole with no coordinate ever typed. Consumes the
    handles from topology.find_protrusions and selects the limb's verts OUT TO (not
    including) its base ring; delete them and the base ring is left as a clean
    opening. `which` filters by cap-region substring (e.g. 'top-left'); empty =
    every protrusion. extend unions onto the current selection."""
    import bmesh
    from . import topology
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    if obj.type != 'MESH':
        return {"error": f"'{obj.name}' is not a mesh"}
    which = (params.get("which") or "").strip().lower()
    extend = bool(params.get("extend", False))

    abm = topology._topology_bmesh(obj, "cage")
    try:
        bbox = topology._bbox(abm)
        prots, _ap = topology.find_protrusions(abm, bbox)
    finally:
        abm.free()
    if not prots:
        return {"error": "No protrusions found — needs an open-shell tube "
                         "(run feel structure to see the regime)."}
    chosen = prots if not which else [p for p in prots if which in p["cap_region"]]
    if not chosen:
        avail = ", ".join(p["cap_region"] for p in prots)
        return {"error": f"No protrusion cap matches '{which}'. Available: {avail}"}

    member = set()
    for p in chosen:
        member.update(p["member_ids"])

    bpy.context.tool_settings.mesh_select_mode = (True, False, False)  # VERT
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    if not extend:
        for v in bm.verts:
            v.select = False
    nverts = len(bm.verts)
    for i in member:
        if 0 <= i < nverts:
            bm.verts[i].select = True
    _flush_vert_selection(bm)
    bmesh.update_edit_mesh(obj.data)
    count = sum(1 for v in bm.verts if v.select)
    caps = [p["cap_region"] for p in chosen]
    return {"success": True, "selected_count": count, "limbs": caps,
            "base_regions": [p["base_region"] for p in chosen],
            "note": f"selected limb(s) capped @ {', '.join(caps)}; delete to "
                    f"remove — the base ring stays as a clean opening"}


TOOLS = {
    "select_limb":        select_limb,
    "bevel":              bevel,
    "extrude":            extrude,
    "extrude_along_curve": extrude_along_curve,
    "loop_cut":           loop_cut,
    "set_component_mode": set_component_mode,
    "select_all":         select_all,
    "select_by_axis":     select_by_axis,
    "select_between":     select_between,
    "grow_selection":     grow_selection,
    "move_vertices":      move_vertices,
    "scale_vertices":     scale_vertices,
    "delete_geometry":    delete_geometry,
    "separate_selection": separate_selection,
    "jitter_vertices":    jitter_vertices,
    "random_select":      random_select,
    "proportional_move":  proportional_move,
    "inflate_selection":  inflate_selection,
    "mark_sharp":         mark_sharp,
    "set_edge_crease":    set_edge_crease,
    "merge_by_distance":  merge_by_distance,
    "select_in_sphere":   select_in_sphere,
    "split_by_part":      split_by_part,
    "assign_weight":      assign_weight,
    "select_boundary":    select_boundary,
}

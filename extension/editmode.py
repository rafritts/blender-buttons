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
        elif action == "INTERSECT":
            # G44: keep only verts BOTH already selected AND matching — turn OFF
            # non-matches, leave matches as-is (result = prior selection ∩ criterion).
            if not matches:
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
        elif action == "INTERSECT":
            # G44: prior selection ∩ band — drop verts outside the band, keep the rest.
            if not in_range:
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


def subdivide_selection(params):
    """Locally subdivide the SELECTED region — add sculptable resolution exactly where
    you select, with no global edge loops (unlike loop_cut) and no shape-key block
    (unlike apply-Subsurf / dyntopo). The 'add resolution here' affordance for a coarse
    patch (e.g. a 5-face breast region) before sculpting it.

    cuts:   new cuts per edge (1 = quarter the faces, 2 = ninth, …).
    smooth: 0 = flat (keeps the cage shape; just denser) … ~1 = round the new verts
            toward the Catmull-Clark limit surface. Use a touch of smooth to pre-curve
            a region you're about to push out.

    Subdivides every edge of the selected faces/edges. Where the patch meets unselected
    faces the boundary fans into triangles (the normal Subdivide behavior) — fine for
    sculpt clay; run a retopo pass later for deformation-grade flow."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    cuts = max(1, int(params.get("cuts", 1)))
    smooth = float(params.get("smooth", 0.0))
    bm = bmesh.from_edit_mesh(obj.data)
    edges = {e for e in bm.edges if e.select}
    edges |= {e for f in bm.faces if f.select for e in f.edges}
    edges = list(edges)
    if not edges:
        return {"error": "nothing selected — select verts/edges/faces to subdivide first"}
    before = len(bm.verts)
    bmesh.ops.subdivide_edges(bm, edges=edges, cuts=cuts, use_grid_fill=True,
                              smooth=smooth)
    bmesh.update_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    after = len(bm.verts)
    push_undo(f"subdivide_selection x{cuts}")
    return {"success": True, "cuts": cuts, "smooth": round(smooth, 3),
            "edges_subdivided": len(edges), "verts_added": after - before,
            "verts_total": after, "faces_total": len(bm.faces)}


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


def flood_to_crease(params):
    """G43 — region-coherent selection. Flood OUT from the current selection (the seed)
    across the surface, halting at a CREASE (an edge whose dihedral angle ≥ `angle`) or a
    mesh boundary, so a feature fills to its own natural edge — the under-breast crease,
    the deltoid seam, a hard-surface panel — instead of a guessed coordinate box that
    over/under-shoots (the band-bleeds-into-the-midriff failure).

    angle: crease threshold in degrees (default 25). Lower = stops at subtler creases
           (organic forms); higher = only hard edges halt it (the flood spreads further).
    max_verts: safety cap (default 20000). If the flood hits it, the region did NOT
           close — reported so it's not mistaken for a captured feature.

    Reads + writes the live selection; needs a seed selected first. Pairs with
    feel op=verify to confirm the flood actually bounded the feature."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with a seed selection to flood from"}
    thr = math.radians(float(params.get("angle", 25.0)))
    max_verts = int(params.get("max_verts", 20000))
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    seed = [v for v in bm.verts if v.select]
    if not seed:
        return {"note": "nothing selected — select a seed vert/patch inside the feature first",
                "selected": 0}

    visited = {v.index for v in seed}
    frontier = list(seed)
    capped = False
    while frontier:
        v = frontier.pop()
        for e in v.link_edges:
            # A crease (or a mesh boundary) is a wall the flood does not cross.
            if len(e.link_faces) == 2:
                try:
                    ang = e.calc_face_angle(0.0)
                except (ValueError, RuntimeError):
                    ang = 0.0
            else:
                ang = math.pi   # open boundary edge — hard stop
            if ang >= thr:
                continue
            o = e.other_vert(v)
            if o.index not in visited:
                if len(visited) >= max_verts:
                    capped = True
                    break
                visited.add(o.index)
                o.select = True
                frontier.append(o)
        if capped:
            break

    _flush_vert_selection(bm)
    bmesh.update_edit_mesh(obj.data)
    out = {"success": True, "seed_verts": len(seed), "selected": len(visited),
           "angle_deg": round(math.degrees(thr), 1), "capped": capped}
    if capped:
        out["note"] = (f"hit the {max_verts}-vert cap — the region did NOT close at a "
                       f"crease; lower `angle` so a subtler crease halts the flood, or "
                       f"the feature has no enclosing crease at this threshold")
    return out


def verify_selection(params):
    """G48 — capture verification. A plausible centroid certifies WHERE the selection
    sits, not WHAT it bounded; a sloppy band lands its centroid on the feature anyway,
    so a single read is *unfalsified, not verified*. This PERTURBS the selection (grow
    + shrink by `steps` rings) and reports how far the centroid and extent move:

      • stable under both        ⇒ the feature is CAPTURED (boundary sits at its edge);
      • big jump on GROW         ⇒ CLIPPING — the feature continues past the boundary
                                   (the clipped thumb, the short buttock line);
      • extent barely drops on SHRINK ⇒ SLACK — the border verts swept in a neighbour
                                   (the tricep on the shoulder).

    Also surfaces the bounds aspect (world W×D×H) + dominant axis, so a wrong-FORM
    selection (a taller-than-wide 'collarbone') reads as obviously off without a
    viewport. Restores the original selection before returning."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with a selection to verify"}
    steps = max(1, int(params.get("steps", 1)))
    mw = obj.matrix_world

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    sel0 = [v.index for v in bm.verts if v.select]
    n0 = len(sel0)
    if n0 < 4:
        return {"note": f"select a region first — verify reads the live selection "
                        f"(need >=4 verts, found {n0})", "selected": n0}

    def measure():
        b = bmesh.from_edit_mesh(obj.data)
        cos = [mw @ v.co for v in b.verts if v.select]
        n = len(cos)
        c = Vector((sum(p.x for p in cos) / n, sum(p.y for p in cos) / n,
                    sum(p.z for p in cos) / n))
        xs = [p.x for p in cos]; ys = [p.y for p in cos]; zs = [p.z for p in cos]
        ext = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        return c, ext, n

    def restore():
        b = bmesh.from_edit_mesh(obj.data)
        b.verts.ensure_lookup_table()
        for v in b.verts:
            v.select = False
        for i in sel0:
            b.verts[i].select = True
        _flush_vert_selection(b)
        bmesh.update_edit_mesh(obj.data)

    c0, ext0, _ = measure()
    diag0 = math.sqrt(ext0[0] ** 2 + ext0[1] ** 2 + ext0[2] ** 2) or 1e-6

    for _ in range(steps):
        bpy.ops.mesh.select_more()
    cg, extg, ng = measure()
    grow_shift = (cg - c0).length
    diag_g = math.sqrt(extg[0] ** 2 + extg[1] ** 2 + extg[2] ** 2)
    grow_ext_pct = (diag_g - diag0) / diag0 * 100.0

    restore()
    for _ in range(steps):
        bpy.ops.mesh.select_less()
    cs, exts, ns = measure()
    shrink_shift = (cs - c0).length
    diag_s = math.sqrt(exts[0] ** 2 + exts[1] ** 2 + exts[2] ** 2)
    shrink_ext_pct = (diag_s - diag0) / diag0 * 100.0
    restore()

    # Verdict heuristic — drift relative to the selection's own size. A captured
    # feature barely moves its centroid when the boundary wiggles; a clipped one drags
    # toward the un-captured mass on growth; a slack one loses little extent on shrink.
    grow_rel = grow_shift / diag0
    flags = []
    if grow_rel > 0.10:
        flags.append("clipping? centroid jumped on GROW — the feature likely continues "
                     "past the boundary (under-capture)")
    if abs(shrink_ext_pct) < 8.0 and ns > 4:
        flags.append("slack? extent barely shrank — border verts may be redundant "
                     "(over-capture sweeping in a neighbour)")
    if not flags:
        flags.append("stable under perturbation — the boundary sits near the feature's edge")

    dims = {"W_x_cm": round(ext0[0] * 100, 2), "D_y_cm": round(ext0[1] * 100, 2),
            "H_z_cm": round(ext0[2] * 100, 2)}
    dom = max((("X", ext0[0]), ("Y", ext0[1]), ("Z", ext0[2])), key=lambda t: t[1])[0]

    return {
        "success": True,
        "selected": n0,
        "steps": steps,
        "grow": {"verts": ng, "centroid_shift_cm": round(grow_shift * 100, 2),
                 "extent_change_pct": round(grow_ext_pct, 1)},
        "shrink": {"verts": ns, "centroid_shift_cm": round(shrink_shift * 100, 2),
                   "extent_change_pct": round(shrink_ext_pct, 1)},
        "bounds": dims,
        "longest_axis": dom,
        "verdict": flags,
    }


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
        # G72: explicit x/y/z are RAW WORLD METERS — matching the schema's "(m)" and the
        # named directions above. (The pre-F1 fraction-of-bbox behaviour was the bug: it
        # silently scaled the move by the object's bbox extent.) Convert the world delta
        # to local space so a rotated object still travels the right WORLD distance.
        wv = Vector((params.get("x", 0.0), params.get("y", 0.0), params.get("z", 0.0)))
        local = obj.matrix_world.inverted().to_3x3() @ wv
        world_delta = [round(c, 5) for c in wv]

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


def snap_loop(params):
    """transform op=snap_loop — seat the selected boundary loop onto a target opening
    (gaps.md G17, the ACTION half of feel op=assembly's measurement). Translates the
    live selection's centroid onto a named target handle's point; optionally scales the
    loop about that centroid so its rim matches the target's (rim→rim) and rotates its
    plane parallel to the target's. The "fit one opening onto another" primitive —
    necks→collars, sleeves→armholes, any tube→any opening — and the natural precursor
    to `edit op=bridge` (fit, then weld).

    Source = the current edit-mode selection (so you select the loop yourself — no
    deselect-on-entry). Target = a named boundary handle (mint with feel op=assembly).

      handle:       target boundary handle to seat onto (required).
      fit_scale:    scale the loop about its centroid so its mean radius matches the
                    target's (default True). False keeps the loop's own size — a pure
                    align (e.g. a slim neck sinking into a wider head hole).
      fit_rotation: rotate the loop so its plane is parallel to the target's, by the
                    SHORTER turn so two near-coplanar rims don't flip 180° (default
                    False)."""
    import bmesh
    from . import handles as H

    target_name = (params.get("handle") or "").strip()
    if not target_name:
        return {"error": "transform op=snap_loop needs handle=<target opening> "
                         "(mint boundary handles with feel op=assembly)"}
    fit_scale = bool(params.get("fit_scale", True))
    fit_rotation = bool(params.get("fit_rotation", False))

    obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with the source loop selected "
                         "(snap_loop seats the live selection onto the target)"}

    # target opening — world-space loop from its vgroup
    empty = H._find_handle(target_name)
    if empty is None:
        return {"error": f"target handle '{target_name}' not found "
                         f"(run feel op=assembly to mint boundary handles)"}
    owner = bpy.data.objects.get(empty.get("bb_owner", ""))
    tcos, _tn = H._vgroup_geo(owner, empty.get("bb_vgroup", ""))
    if not tcos:
        return {"error": f"target handle '{target_name}' is orphaned (vgroup gone/empty)"}
    t_centroid = H._centroid(tcos)
    t_radius = sum((c - t_centroid).length for c in tcos) / len(tcos)

    # source loop — the live selection, world space
    bm = bmesh.from_edit_mesh(obj.data)
    sel = [v for v in bm.verts if v.select]
    if not sel:
        return {"error": "No vertices selected — select the source boundary loop first"}
    mw = obj.matrix_world
    scos = [mw @ v.co for v in sel]
    s_centroid = H._centroid(scos)
    s_radius = sum((c - s_centroid).length for c in scos) / len(scos)

    scale = (t_radius / s_radius) if (fit_scale and s_radius > 1e-9) else 1.0

    rot = None
    if fit_rotation:
        s_n = H._newell_normal(scos, s_centroid, None)
        t_n = H._newell_normal(tcos, t_centroid, None)
        if s_n.dot(t_n) < 0:            # nearer orientation — no 180° surprise
            t_n = -t_n
        rot = s_n.rotation_difference(t_n)

    miw = mw.inverted()
    for v, p in zip(sel, scos):
        rel = p - s_centroid
        if rot is not None:
            rel = rot @ rel
        v.co = miw @ (t_centroid + rel * scale)
    bmesh.update_edit_mesh(obj.data)
    # G17 undo fix: snap_loop is NOT an EDIT_MODE_TOOLS auto-switch op (it consumes
    # the live selection, which the auto-target path would deselect), so without this
    # it would run AND push its undo step while still in EDIT mode — and an in-edit
    # post-edit checkpoint has no clean object-mode anchor to undo back to (the moved
    # verts stayed put after `history undo`). Commit the edit by returning to OBJECT
    # mode here, so the dispatch's push_undo_step lands an object-mode checkpoint like
    # every other edit verb (see extension/server.py: "each step is an object-mode
    # checkpoint"). Re-enter edit mode yourself to keep shaping.
    bpy.ops.object.mode_set(mode='OBJECT')

    move = t_centroid - s_centroid
    return {
        "success": True, "verts": len(sel), "handle": target_name,
        "moved_cm": round(move.length * 100, 2),
        "delta_world": [round(c, 5) for c in move],
        "scaled": round(scale, 4) if fit_scale else None,
        "rotated": bool(rot is not None),
        "source_diam_cm": round(s_radius * 2 * 100, 2),
        "target_diam_cm": round(t_radius * 2 * 100, 2),
    }


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

    Topology-aware shaping (gaps.md G60):
    connected: when true, falloff is measured as GEODESIC distance along edges from
               the selection — not straight-line. Verts on a different shell (or a
               topological detour) are unreachable, so a big move stops dragging
               whatever merely sits near in space. Default false (Euclidean, original).
    freeze:    a handle name whose verts are held RIGID — never moved, and (in
               connected mode) treated as walls the falloff can't flow through. The
               way to say "shape the connector, hold the cylinder still."

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
    connected = bool(params.get("connected", False))

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
    bm.verts.ensure_lookup_table()
    handles = [v for v in bm.verts if v.select]
    if not handles:
        return {"error": "No vertices selected"}

    # G60 — freeze a named handle's verts rigid. Resolve its vgroup via the bmesh
    # deform layer (an edit-mode-safe read; obj.data.vertices is stale here).
    freeze_name = (params.get("freeze") or "").strip()
    frozen = set()
    if freeze_name:
        from . import handles as H
        ent = H._find_handle(freeze_name)
        if ent is None:
            return {"error": f"freeze handle '{freeze_name}' not found "
                             f"(mint with feel op=assembly / structure)"}
        vg = obj.vertex_groups.get(ent.get("bb_vgroup", ""))
        if vg is None:
            return {"error": f"freeze handle '{freeze_name}' has no live vgroup — re-mint it"}
        gi = vg.index
        dl = bm.verts.layers.deform.active
        if dl is not None:
            frozen = {v.index for v in bm.verts if gi in v[dl]}
        if not frozen:
            return {"error": f"freeze handle '{freeze_name}' resolved to 0 verts — re-mint it"}

    def _weight(t):
        if falloff == "SMOOTH":
            return 1.0 - t * t * (3.0 - 2.0 * t)
        if falloff == "LINEAR":
            return 1.0 - t
        if falloff == "SPHERE":
            inner = 1.0 - t * t
            return inner ** 0.5 if inner > 0 else 0.0
        if falloff == "SHARP":
            return (1.0 - t) ** 2
        if falloff == "ROOT":
            return 1.0 - t ** 0.5
        return 1.0  # CONSTANT

    # dist[vi] = distance (Euclidean-nearest-handle, or geodesic along edges) within
    # radius. Frozen verts are excluded as movers; in connected mode they're also
    # walls the flood can't cross.
    dist = {}
    if connected:
        import heapq
        heap = []
        for h in handles:
            if h.index in frozen:
                continue
            dist[h.index] = 0.0
            heap.append((0.0, h.index))
        heapq.heapify(heap)
        while heap:
            d, vi = heapq.heappop(heap)
            if d > dist.get(vi, r2):  # stale heap entry
                continue
            if d >= radius_local:
                continue
            v = bm.verts[vi]
            for e in v.link_edges:
                w = e.other_vert(v)
                if w.index in frozen:
                    continue
                nd = d + e.calc_length()
                if nd < dist.get(w.index, radius_local):
                    dist[w.index] = nd
                    heapq.heappush(heap, (nd, w.index))
    else:
        handle_cos = [v.co.copy() for v in handles]
        for v in bm.verts:
            if v.index in frozen:
                continue
            best2 = r2
            for h in handle_cos:
                d2 = (v.co - h).length_squared
                if d2 < best2:
                    best2 = d2
            if best2 < r2:
                dist[v.index] = best2 ** 0.5

    affected = 0
    for vi, d in dist.items():
        t = d / radius_local  # 0 at handle, 1 at radius edge
        w = _weight(t)
        v = bm.verts[vi]
        v.co.x += dx * w
        v.co.y += dy * w
        v.co.z += dz * w
        affected += 1

    bmesh.update_edit_mesh(obj.data)
    push_undo(f"proportional_move r={radius} {falloff}"
              + (" connected" if connected else "")
              + (f" freeze={freeze_name}" if freeze_name else ""))
    result = {
        "success": True,
        "connected": connected,
        "frozen": len(frozen),
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
        # No narrowed selection → jitter the WHOLE mesh (matches this op's own
        # "jitter all the donut's verts" use case). One predictable contract: pass
        # target=, get the whole mesh unless you've selected a subset (G28).
        for v in bm.verts:
            v.select = True
        selected = list(bm.verts)
        if not selected:
            return {"error": f"'{obj.name}' has no vertices to jitter"}

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


def bridge_handles(params):
    """edit op=bridge — weld two open boundary loops into a continuous skin (SPEC-07
    Phase 5, the consumer half of gaps.md G10). Consumes two named boundary handles,
    selects their rims, and runs bridge_edge_loops — the single most fundamental
    "close the gap between two open loops" move, which the edit surface lacked.

    SAME-OBJECT only. `edit` acts on one mesh; both loops must live on the same owner.
    Two parts on separate objects → `object op=join` them first, then bridge the loops
    on the joined mesh. Keyed/rigged meshes are refused: bridging adds faces, which
    corrupts a shape-key block or a deform bind (the honest G10 limit).

    a, b: the two boundary handles to weld (order-independent — bridging is symmetric).

    Curvature dials (gaps.md G58 — pass-through to Bridge Edge Loops). Default `cuts=0`
    is the original straight single-ring weld; raise `cuts` to subdivide the span so it
    can bow:
      cuts          int   intermediate loops across the span (0 = straight strut)
      smoothness    float tangent bow of the interpolated cuts (native default 1.0)
      interpolation str   LINEAR | PATH | SURFACE — how the cuts follow the rims
      profile       float profile_factor: bulge the cross-section out (0 = none)
      twist         int   twist_offset: rotate vert-to-vert mapping when the two rims
                          face different ways (kills the spiral); units = verts."""
    import bmesh
    from . import handles as H
    a = (params.get("a") or "").strip()
    b = (params.get("b") or "").strip()
    if not a or not b:
        return {"error": "edit op=bridge needs a=<handle> and b=<handle> (two boundary handles)"}
    if a == b:
        return {"error": "a and b are the same handle — bridge needs two distinct loops"}

    ea, eb = H._find_handle(a), H._find_handle(b)
    if ea is None:
        return {"error": f"handle '{a}' not found (run feel op=assembly to mint boundary handles)"}
    if eb is None:
        return {"error": f"handle '{b}' not found (run feel op=assembly to mint boundary handles)"}

    owner_a, owner_b = ea.get("bb_owner", ""), eb.get("bb_owner", "")
    if owner_a != owner_b:
        return {"error":
            f"cross-object bridge: '{a}' is on '{owner_a}', '{b}' is on '{owner_b}'. "
            f"edit is single-object — join them first "
            f"(`object op=join names={owner_a},{owner_b}`), then bridge the loops on "
            f"the joined mesh."}

    obj = bpy.data.objects.get(owner_a)
    if obj is None or obj.type != 'MESH':
        return {"error": f"owner '{owner_a}' is gone or not a mesh"}
    if obj.data.shape_keys is not None:
        return {"error":
            f"'{obj.name}' has shape keys — bridging changes topology and would corrupt "
            f"the keys. Keyed/rigged welds are out of scope."}

    idx_a = H._vgroup_vertset(obj, ea.get("bb_vgroup", ""))
    idx_b = H._vgroup_vertset(obj, eb.get("bb_vgroup", ""))
    if not idx_a or not idx_b:
        return {"error": "a handle's vgroup is empty/gone — re-mint with feel op=assembly"}

    # Own the edit-mode entry: the owner is derived from the handles, not a user
    # `target=`, so this doesn't route through the EDIT_MODE_TOOLS path.
    if bpy.context.active_object is not None and bpy.context.active_object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    want = idx_a | idx_b
    for f in bm.faces:
        f.select = False
    for e in bm.edges:
        e.select = False
    for v in bm.verts:
        v.select = False
    sel_edges = 0
    for e in bm.edges:
        if (len(e.link_faces) == 1
                and e.verts[0].index in want and e.verts[1].index in want):
            e.select = True
            e.verts[0].select = True
            e.verts[1].select = True
            sel_edges += 1
    bmesh.update_edit_mesh(obj.data)
    if sel_edges == 0:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error":
            f"no open boundary edges on those handles — '{a}'/'{b}' may not be open "
            f"loops (bridge needs two rims of one-face edges)"}

    cuts = max(0, min(int(params.get("cuts", 0) or 0), 1000))
    smoothness = max(0.0, min(float(params.get("smoothness", 1.0) or 1.0), 1000.0))
    profile = float(params.get("profile", 0.0) or 0.0)
    twist = int(params.get("twist", 0) or 0)
    interp = str(params.get("interpolation", "PATH") or "PATH").strip().upper()
    if interp not in ("LINEAR", "PATH", "SURFACE"):
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error":
            f"interpolation '{interp}' invalid — use LINEAR, PATH, or SURFACE"}

    faces_before = len(bm.faces)
    try:
        bpy.ops.mesh.bridge_edge_loops(
            number_cuts=cuts, interpolation=interp, smoothness=smoothness,
            profile_shape_factor=profile, twist_offset=twist)
    except (RuntimeError, TypeError) as ex:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": f"bridge_edge_loops failed: {ex}"}

    bm = bmesh.from_edit_mesh(obj.data)
    faces_after = len(bm.faces)
    bpy.ops.object.mode_set(mode='OBJECT')
    push_undo(f"bridge {a} ↔ {b}")
    return {"success": True, "owner": obj.name, "a": a, "b": b,
            "edges_bridged": sel_edges, "faces_created": faces_after - faces_before,
            "faces_total": faces_after,
            "bridge": {"cuts": cuts, "smoothness": smoothness,
                       "interpolation": interp, "profile": profile, "twist": twist}}


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
        elif action == "INTERSECT":
            # G44: prior selection ∩ sphere — drop verts outside the sphere.
            if not inside:
                v.select = False
            elif v.select:
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


# ───────────────────────── surface-tangential moves (G49) ───────────────────
# The movers above (proportional_move/inflate/jitter) all push verts THROUGH space
# in a fixed direction. These two move verts ALONG the surface instead: relax
# redistributes spacing, slide drags a selection over the form — both by snapping
# every moved vert back onto a BVH snapshot of the surface taken BEFORE the move.
# That reprojection is what turns a space-move into a surface-move: the shape is
# preserved (verts can only land on the original surface), only their layout changes.

def _surface_bvh(bm):
    """A BVHTree snapshot of the bmesh's current geometry (local space). The tree
    copies geometry at build time, so mutating bm afterward leaves it untouched —
    exactly what reprojection needs (snap to where the surface WAS before the move)."""
    from mathutils.bvhtree import BVHTree
    return BVHTree.FromBMesh(bm)


def _reproject(verts, tree):
    """Snap each vert onto the nearest point of `tree` (the pre-move surface).
    Returns the number actually moved onto the surface."""
    n = 0
    for v in verts:
        loc, _nrm, _idx, _dist = tree.find_nearest(v.co)
        if loc is not None:
            v.co = loc
            n += 1
    return n


def relax_selection(params):
    """G49 — RELAX: even out vertex spacing over the existing form without changing
    its shape. Laplacian-smooths the selected verts (each drifts toward the average of
    its neighbours), then reprojects every one onto a BVH snapshot of the pre-relax
    surface so the form is preserved and only the layout improves. The fix for stretched
    / bunched quads at a feature — the redistribute half of the retopo toolkit.

    iterations: smoothing passes (default 5). factor: 0..1 step per pass (default 0.5).
    reproject:  snap back onto the original surface each pass (default True). False =
                a plain Laplacian smooth that also relaxes the shape (shrinks bulges)."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    iterations = max(1, int(params.get("iterations", 5)))
    factor = float(params.get("factor", 0.5))
    reproject = params.get("reproject", True)

    bm = bmesh.from_edit_mesh(obj.data)
    sel = [v for v in bm.verts if v.select]
    if not sel:
        return {"error": "No vertices selected"}
    before = [v.co.copy() for v in sel]
    tree = _surface_bvh(bm) if reproject else None
    for _ in range(iterations):
        bmesh.ops.smooth_vert(bm, verts=sel, factor=factor,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
        if tree is not None:
            _reproject(sel, tree)
    bm.normal_update()
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"relax_selection x{iterations}")
    mw = obj.matrix_world
    drift = sum(((mw @ v.co) - (mw @ b)).length for v, b in zip(sel, before)) / len(sel)
    return {"success": True, "verts_relaxed": len(sel), "iterations": iterations,
            "factor": factor, "reprojected": bool(reproject),
            "avg_drift_cm": round(drift * 100, 3)}


def slide_selection(params):
    """G49 — SLIDE: drag the selected verts ALONG the surface in a direction, instead of
    THROUGH space. Moves them by the usual metre direction words, then reprojects onto a
    BVH snapshot of the pre-slide surface — so the net motion is the tangential component
    (the verts travel over the form; the form's shape is unchanged). Relocate a pole or a
    loop to a feature's high point without denting the mesh.

    Direction words (METERS, composable): out/inward (selection normal),
    up/down/left/right/forward/back (world axes). The displacement should be small
    relative to the surface's curvature — a slide is a nudge, looped if you need more."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    if not _has_dir_words(params):
        return {"error": "slide needs a direction — out/inward or up/down/left/right/"
                         "forward/back (meters)"}
    bm = bmesh.from_edit_mesh(obj.data)
    sel = [v for v in bm.verts if v.select]
    if not sel:
        return {"error": "No vertices selected"}
    wv, frame, err = _resolve_world_delta(bm, obj, params)
    if err:
        return err
    local = obj.matrix_world.inverted().to_3x3() @ wv
    before = [v.co.copy() for v in sel]
    tree = _surface_bvh(bm)
    for v in sel:
        v.co += local
    _reproject(sel, tree)
    bm.normal_update()
    bmesh.update_edit_mesh(obj.data)
    push_undo("slide_selection")
    mw = obj.matrix_world
    drift = sum(((mw @ v.co) - (mw @ b)).length for v, b in zip(sel, before)) / len(sel)
    result = {"success": True, "verts_slid": len(sel),
              "requested_world": [round(c, 5) for c in wv],
              "avg_slide_cm": round(drift * 100, 3)}
    if frame:
        result["frame"] = frame
    return result


# ───────────────────────── face authoring / retopo primitives (G50) ──────────

def poke_faces(params):
    """G50 — POKE: fan each selected face out from a new centre vertex. The centre vert
    has valence = the face's side count, so poking a quad mints a 4-pole, an n-gon an
    n-pole — the way to AUTHOR a radial centre where the surface wants one (e.g. under a
    nipple/dome) and there isn't a pole already. offset: push the new centre along the
    face normal (m, default 0 = flat)."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    offset = float(params.get("offset", 0.0))
    bm = bmesh.from_edit_mesh(obj.data)
    faces = [f for f in bm.faces if f.select]
    if not faces:
        return {"error": "No faces selected (switch to FACE mode / select faces to poke)"}
    n_faces = len(faces)
    # The new centre's valence = the face's side count — capture it now, because the
    # poke op REMOVES the original faces (dereferencing faces[0] after would raise).
    sides = len(faces[0].verts)
    res = bmesh.ops.poke(bm, faces=faces, offset=offset)
    new_verts = res.get("verts", [])
    for v in bm.verts:
        v.select = False
    for v in new_verts:
        v.select = True
    bm.select_flush(True)
    bmesh.update_edit_mesh(obj.data)
    push_undo("poke_faces")
    return {"success": True, "faces_poked": n_faces,
            "poles_created": len(new_verts), "offset": offset,
            "note": f"new centre vert(s) left selected — a poked {sides}-gon mints a "
                    f"{sides}-pole"}


def inset_faces(params):
    """G50 — INSET: shrink a copy of the selected faces inward, ringing them with a new
    band of faces (the classic 'I' inset). Adds an edge loop around a region so a feature
    can be defined/tightened. thickness: inset distance (m). depth: push the inset in/out
    along the normal (m). individual: inset each face on its own vs. the region as a whole."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    thickness = float(params.get("thickness", 0.01))
    depth = float(params.get("depth", 0.0))
    individual = bool(params.get("individual", False))
    bm = bmesh.from_edit_mesh(obj.data)
    faces = [f for f in bm.faces if f.select]
    if not faces:
        return {"error": "No faces selected (switch to FACE mode / select faces to inset)"}
    if individual:
        res = bmesh.ops.inset_individual(bm, faces=faces, thickness=thickness, depth=depth)
    else:
        res = bmesh.ops.inset_region(bm, faces=faces, thickness=thickness, depth=depth,
                                     use_boundary=True, use_even_offset=True)
    new_faces = res.get("faces", [])
    bm.normal_update()
    bmesh.update_edit_mesh(obj.data)
    push_undo("inset_faces")
    return {"success": True, "faces_inset": len(faces), "ring_faces": len(new_faces),
            "thickness": thickness, "depth": depth,
            "mode": "individual" if individual else "region"}


def grid_fill(params):
    """G50 — GRID FILL: fill a selected closed edge loop with a regular quad grid (the
    Face menu 'Grid Fill'). Lays clean four-sided flow across a hole/region instead of a
    fan — the patch primitive for repairing or re-flowing topology. Be in edit mode with
    a single closed boundary loop selected (even vert count). span/offset tune the grid."""
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    span = int(params.get("span", 0))
    offset = int(params.get("offset", 0))
    import bmesh
    bm = bmesh.from_edit_mesh(obj.data)
    faces_before = len(bm.faces)
    try:
        if span > 0:
            bpy.ops.mesh.fill_grid(span=span, offset=offset)
        else:
            bpy.ops.mesh.fill_grid(offset=offset)
    except RuntimeError as e:
        return {"error": f"grid_fill failed: {e}. Needs ONE closed edge loop with an "
                         f"even vertex count selected."}
    bm = bmesh.from_edit_mesh(obj.data)
    added = len(bm.faces) - faces_before
    if added <= 0:
        return {"error": "grid_fill added nothing — the selection isn't a fillable grid. "
                         "Select ONE closed edge loop with an EVEN vertex count (Blender "
                         "splits it into four sides); an odd or branching loop can't be "
                         "gridded. Use edit op=bridge for two separate loops."}
    return {"success": True, "faces_added": added, "faces_total": len(bm.faces)}


TOOLS = {
    "relax_selection":    relax_selection,
    "slide_selection":    slide_selection,
    "poke_faces":         poke_faces,
    "inset_faces":        inset_faces,
    "grid_fill":          grid_fill,
    "select_limb":        select_limb,
    "bevel":              bevel,
    "extrude":            extrude,
    "extrude_along_curve": extrude_along_curve,
    "loop_cut":           loop_cut,
    "subdivide_selection": subdivide_selection,
    "set_component_mode": set_component_mode,
    "select_all":         select_all,
    "select_by_axis":     select_by_axis,
    "select_between":     select_between,
    "grow_selection":     grow_selection,
    "verify_selection":   verify_selection,
    "flood_to_crease":    flood_to_crease,
    "move_vertices":      move_vertices,
    "scale_vertices":     scale_vertices,
    "snap_loop":          snap_loop,
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
    "bridge_handles":     bridge_handles,
}

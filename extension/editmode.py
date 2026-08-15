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


def _restrict_to_selected_faces(bm):
    """G85: after `extrude_region_move`, Blender leaves the source ring's verts/edges
    selected ALONGSIDE the new cap face — so the status block's sel_bounds / vert count
    over-report the selection (a 32-vert cap reads as 64 verts spanning the outer radius).
    `inset` doesn't suffer this because its bmesh-op leaves only the inner face selected.
    Re-derive the selection from the selected FACES alone, so the next read describes
    exactly the extruded face. No-op when nothing is fully face-selected (vert/edge
    extrude), so it never disturbs those selections."""
    faces = [f for f in bm.faces if f.select]
    if not faces:
        return
    for v in bm.verts:
        v.select = False
    for e in bm.edges:
        e.select = False
    for f in bm.faces:
        f.select = False
    for f in faces:
        f.select_set(True)  # selects the face plus its own verts + edges
    bm.select_flush_mode()


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
    # G132: bevel offset is applied in the object's LOCAL space, so an unapplied object
    # scale silently magnifies it — a 2mm width pulls 6mm on a 3× object, pinching a thin
    # wall far more than its named width. Report the TRUE world offset and warn.
    result = {"success": True, "offset_local": round(offset, 5)}
    if obj is not None:
        from .common import scale_unit_note
        eff, note = scale_unit_note(obj, offset, what="bevel width")
        if note:
            result["offset_world"] = eff
            result.setdefault("notes", []).append(note)
        else:
            result["offset_world"] = round(offset, 5)
    return result


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
        _restrict_to_selected_faces(bmesh.from_edit_mesh(obj.data))  # G85
        bmesh.update_edit_mesh(obj.data)
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
    _restrict_to_selected_faces(bmesh.from_edit_mesh(obj.data))  # G85
    bmesh.update_edit_mesh(obj.data)
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
# selection along a curve in ONE call (a swept-tube curve sweeps a circle into a NEW
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
    import bmesh
    action = params.get("action", "SELECT").upper()
    bpy.ops.mesh.select_all(action=action)
    out = {"success": True, "action": action}
    obj = bpy.context.active_object
    if obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(obj.data)
        out["selected_count"] = sum(1 for v in bm.verts if v.select)
    return out


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
    world_lo   = params.get("world_lo", None)
    world_hi   = params.get("world_hi", None)
    eps        = float(params.get("eps", 1e-5))
    action     = params.get("action", "SELECT").upper()
    extend     = bool(params.get("extend", False))
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with an active object"}
    bm = bmesh.from_edit_mesh(obj.data)
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    world_vals = [(obj.matrix_world @ v.co)[axis_idx] for v in bm.verts]
    v_min, v_max = min(world_vals), max(world_vals)
    # G184: a band can address a FIXED world location (world_lo/world_hi) that doesn't
    # drift as the bbox grows mid-build, OR the legacy 0..1 fraction of the LIVE bbox
    # extent (lo/hi). A world coord wins PER BOUND when given, and each side falls back
    # to its fraction independently — so `world_lo` paired with a fractional `hi` is valid.
    # `eps` (default 0.01mm) widens both bounds so a vert row landing exactly on the bound
    # isn't clipped by threshold-arithmetic rounding (the boundary-inclusivity surprise the
    # gap names). It's a float-jitter absorber, not a tolerance band — kept well below any
    # realistic vert spacing so it never pulls in a neighbouring row; raise it explicitly
    # when you DO want a millimetre-scale catch.
    lo_thresh = float(world_lo) if world_lo is not None else v_min + lo * (v_max - v_min)
    hi_thresh = float(world_hi) if world_hi is not None else v_min + hi * (v_max - v_min)
    lo_cmp, hi_cmp = lo_thresh - eps, hi_thresh + eps
    count = 0
    for vert in bm.verts:
        val = (obj.matrix_world @ vert.co)[axis_idx]
        in_range = lo_cmp <= val <= hi_cmp
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
        "world_addressed": (world_lo is not None) or (world_hi is not None),
        "selected_count": count,
    }


def list_components(params):
    """G185 — enumerate the verts in the CURRENT selection with stable labels (their mesh
    vertex index) and valence, so the agent can then address them by index (select
    op=by_index) instead of binary-searching coordinate bands. The "list what's here, let
    me pick by name" primitive: narrow with a band first, then list, then refine.

    Coordinate-starved by default (SPEC-21 §6.2): positions come as Δs from the selection's
    centroid — enough to see the arrangement and pick — and raw world XYZ sits behind
    world_xyz=True, the debug escape hatch off the default path.

    Labels are mesh vertex indices — stable across selection/read calls, but a topology op
    (loop_cut / extrude / delete / merge) renumbers verts, so re-list after any such edit."""
    import bmesh
    from mathutils import Vector
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with an active object"}
    cap = int(params.get("max_verts", 60) or 60)
    world_xyz = bool(params.get("world_xyz"))
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    mw = obj.matrix_world
    sel = [v for v in bm.verts if v.select]
    sel.sort(key=lambda v: v.index)
    ctr = Vector((0.0, 0.0, 0.0))
    if sel and not world_xyz:
        for v in sel:
            ctr += mw @ v.co
        ctr /= len(sel)
    items = []
    for v in sel[:cap]:
        co = (mw @ v.co) - ctr
        items.append({"i": v.index,
                      "co": [round(co.x, 4), round(co.y, 4), round(co.z, 4)],
                      "valence": len(v.link_edges)})
    return {"success": True, "total": len(sel), "shown": len(items),
            "capped": len(sel) > cap,
            "frame": "world" if world_xyz else "centroid", "verts": items}


def select_by_index(params):
    """G185 — select verts by their mesh vertex index (the labels from list_components):
    'select v3, v7' instead of a coordinate slab. action SELECT|DESELECT|INTERSECT, extend
    to union onto the current selection."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with an active object"}
    raw = params.get("indices") or []
    try:
        want = {int(i) for i in raw}
    except (TypeError, ValueError):
        return {"error": "indices must be a list of integer vertex indices"}
    if not want:
        return {"error": "select op=by_index needs indices=[...] — vertex indices from "
                         "select op=list"}
    action = params.get("action", "SELECT").upper()
    extend = bool(params.get("extend", False))
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    n = len(bm.verts)
    bad = sorted(i for i in want if i < 0 or i >= n)
    if bad:
        return {"error": f"vertex index out of range (mesh has {n} verts): {bad[:10]}"}
    count = 0
    for v in bm.verts:
        hit = v.index in want
        if action == "DESELECT":
            if hit:
                v.select = False
        elif action == "INTERSECT":
            if not hit:
                v.select = False
        elif extend:
            if hit:
                v.select = True
        else:
            v.select = hit
        if v.select:
            count += 1
    _flush_vert_selection(bm)
    bmesh.update_edit_mesh(obj.data)
    return {"success": True, "requested": len(want), "selected_count": count}


def select_by_vgroup(params):
    """Select the verts belonging to a named vertex group (or every group whose name
    matches a substring) — the named-handle selector for IMPORTED assets. VRoid/Mixamo/
    rigged characters ship semantic vertex groups (skirt sway panels, garment parts,
    bone weights); this addresses them by NAME instead of box-selecting a shell out of a
    fused mesh by hand.

    name:       substring, case-insensitive. Empty = DISCOVERY: return every vgroup name
                on the mesh (the 'grep' — list, don't select).
    min_weight: a vert counts as in the group only if its weight there exceeds this
                (default 0.0 = any non-zero weight). Raise it to shed faint seam bleed.
    action:     SELECT (default) | DESELECT.
    extend:     SELECT only — union onto the current selection instead of replacing.

    Multiple matching groups are UNIONED (so name='skirt' grabs all three skirt layers
    in one call). Reports which group names matched."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "active object is not a mesh"}
    name       = (params.get("name") or "").strip()
    action     = params.get("action", "SELECT").upper()
    extend     = bool(params.get("extend", False))
    min_weight = float(params.get("min_weight", 0.0))
    groups = list(obj.vertex_groups)

    if not name:
        return {"success": True, "groups": [vg.name for vg in groups],
                "group_count": len(groups)}

    needle = name.lower()
    matched = [vg for vg in groups if needle in vg.name.lower()]
    if not matched:
        return {"error": f"no vertex group matching '{name}'. "
                         f"Available ({len(groups)}): {[vg.name for vg in groups]}"}
    if obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    bm = bmesh.from_edit_mesh(obj.data)
    deform = bm.verts.layers.deform.verify()
    gidx = {vg.index for vg in matched}
    count = 0
    for v in bm.verts:
        dv = v[deform]
        hit = any(gi in dv and dv[gi] > min_weight for gi in gidx)
        if hit:
            v.select = (action != "DESELECT")
        elif action == "SELECT" and not extend:
            v.select = False
        if v.select:
            count += 1
    _flush_vert_selection(bm)
    bmesh.update_edit_mesh(obj.data)
    return {"success": True,
            "matched_groups": [vg.name for vg in matched],
            "selected": count, "min_weight": min_weight}


def select_by_material(params):
    """Select faces by MATERIAL SLOT — the named-handle selector for imported garments
    that SHARE bone weights with the body. A jacket/coat torso rides the same spine/chest
    bones as the skin underneath, so no vertex group isolates it — but its material slot
    does. VRoid/VRM meshes give every garment its own material (Tops, Bottoms, Shoes,
    Hair, ...), so the material is the garment's real name.

    name:   substring, case-insensitive, matched against material names. Empty = DISCOVERY:
            list every material slot with index, name, and face count (the 'grep').
    action: SELECT (default) | DESELECT.
    extend: SELECT only — union onto the current selection instead of replacing.

    Multiple matching slots are UNIONED (so name='Tops' grabs every Tops cloth layer).
    Reports which materials matched."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "active object is not a mesh"}
    name   = (params.get("name") or "").strip()
    action = params.get("action", "SELECT").upper()
    extend = bool(params.get("extend", False))
    slots  = [(i, (s.material.name if s.material else "<empty>"))
              for i, s in enumerate(obj.material_slots)]

    if obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    bm = bmesh.from_edit_mesh(obj.data)

    if not name:
        counts = {}
        for f in bm.faces:
            counts[f.material_index] = counts.get(f.material_index, 0) + 1
        return {"success": True,
                "slots": [{"slot": i, "material": nm, "faces": counts.get(i, 0)}
                          for i, nm in slots],
                "slot_count": len(slots)}

    needle = name.lower()
    matched = [(i, nm) for i, nm in slots if needle in nm.lower()]
    if not matched:
        return {"error": f"no material matching '{name}'. "
                         f"Available ({len(slots)}): {[nm for _, nm in slots]}"}
    midx = {i for i, _ in matched}

    if action == "SELECT" and not extend:
        for v in bm.verts:
            v.select = False
        for e in bm.edges:
            e.select = False
        for f in bm.faces:
            f.select = False

    sel_faces = 0
    for f in bm.faces:
        if f.material_index in midx:
            f.select_set(action != "DESELECT")
            if f.select:
                sel_faces += 1
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    nverts = sum(1 for v in bm.verts if v.select)
    return {"success": True,
            "matched_materials": [nm for _, nm in matched],
            "matched_slots": sorted(midx),
            "selected_faces": sel_faces, "selected_verts": nverts}


def loop_cut(params):
    import bmesh
    import mathutils
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    cuts     = params.get("cuts", 1)
    axis     = params.get("axis", "Z").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    # G183: explicit ring SEED — the world coord on `axis` of the cross-section to ring.
    # Without it, every along-axis edge is subdivided (cuts evenly-spaced rings across the
    # whole span); with it, only edges that STRADDLE the plane axis=at are cut, so the loop
    # lands on the cross-section you aimed at instead of whatever ring the walker stumbles
    # into once the topology forks.
    at = params.get("at", None)
    if at is not None:
        at = float(at)

    bm = bmesh.from_edit_mesh(obj.data)
    mat = obj.matrix_world

    # Native Ctrl+R ignores the selection — so do we, by DEFAULT: a loop_cut rings the
    # whole mesh. This matches the human mental model and kills the chaining trap where each
    # cut left only the new loop selected and silently scoped the NEXT cut to that sliver
    # (gridding a cube needed a manual reselect-all between every cut). only_selected=True
    # opts back INTO scoping — cut only edges whose BOTH ends are selected, to rib ONE
    # limb/region without ribbing the whole mesh (Z2/X7).
    scoped = bool(params.get("only_selected", False))
    selected = {v.index for v in bm.verts if v.select} if scoped else set()
    bm.verts.ensure_lookup_table()

    def along_axis(e):
        return abs(((mat @ e.verts[1].co) - (mat @ e.verts[0].co))
                   .normalized()[axis_idx]) > 0.7

    def straddles(e):
        a = (mat @ e.verts[0].co)[axis_idx]
        b = (mat @ e.verts[1].co)[axis_idx]
        return min(a, b) <= at <= max(a, b)

    edges_to_cut = [
        e for e in bm.edges
        if along_axis(e)
        and (at is None or straddles(e))
        and (not scoped or (e.verts[0].index in selected and e.verts[1].index in selected))
    ]

    if not edges_to_cut:
        where = "within the selection " if scoped else ""
        seed = f" crossing {axis}={round(at, 4)}" if at is not None else ""
        return {"error": f"No edges {where}run along the {axis} axis{seed}. "
                         + ("Try a different axis/seed, or widen the selection."
                            if scoped else "Try a different axis or seed (at=).")}

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

    # G183: stub-loop / under-span detection. A real loop RINGS the whole cross-section,
    # so its extent in the two perpendicular axes should match the mesh's there; a stub
    # (the walker stopped at a pole on forked topology) rings only a sliver. Measure the
    # new ring's perpendicular extent against the mesh's and report the COVERAGE, warning
    # when it spans far less than the cross-section — so a stub reads as the failure it is,
    # not a silent success. Suppressed when scoped to a selection (a small ring is then the
    # intent), and skipped for multi-loop cuts where the new verts span several rings.
    perp = [i for i in (0, 1, 2) if i != axis_idx]
    coverage = None
    warning = None
    if new_verts and loops <= 1:
        def extent(vs, i):
            vals = [(mat @ v.co)[i] for v in vs]
            return max(vals) - min(vals)
        ratios = []
        for i in perp:
            mesh_e = extent(bm.verts, i)
            if mesh_e > 1e-6:
                ratios.append(extent(new_verts, i) / mesh_e)
        if ratios:
            coverage = round(min(ratios), 3)
            if not scoped and coverage < 0.5:
                warning = (f"stub loop: the cut rings only {int(coverage * 100)}% of the "
                           f"mesh's cross-section on {axis} — the loop walker likely hit a "
                           f"pole on forked topology and stopped short of a spanning ring. "
                           f"Aim it with at=<{axis} coord>, or select the ring first.")

    out = {"success": True, "cuts": cuts, "edges_subdivided": len(edges_to_cut),
           "loops": loops, "axis": axis, "span_world": span, "region": region,
           "scoped_to_selection": scoped, "seed_at": at, "coverage": coverage}
    if warning:
        out["warning"] = warning
    return out


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
    """G219 — expansion answers with before → after, and on Δ=0 says WHY. 'GROW xN'
    with no counts made a correct no-op (a saturated island), a real malfunction,
    and a wrong-store fantasy read identically — and cost a committed misdiagnosis."""
    import bmesh
    direction = params.get("direction", "GROW").upper()
    steps = params.get("steps", 1)
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    bm = bmesh.from_edit_mesh(obj.data)
    before = sum(1 for v in bm.verts if v.select)
    op = bpy.ops.mesh.select_more if direction == "GROW" else bpy.ops.mesh.select_less
    for _ in range(max(1, steps)):
        op()
    bm = bmesh.from_edit_mesh(obj.data)
    after = sum(1 for v in bm.verts if v.select)
    out = {"success": True, "direction": direction, "steps": steps,
           "before": before, "after": after}
    if after == before:
        from .perception import expansion_noop_reason
        out["why_unchanged"] = expansion_noop_reason(bm, direction)
    return out


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
    elif len(visited) == len(seed):
        # G219 — a flood that added nothing must say why: either the seed is a whole
        # island (nothing to cross to) or every way out is a crease/boundary wall.
        from .perception import expansion_noop_reason
        why = expansion_noop_reason(bm, "GROW")
        if "saturated" not in why and "whole mesh" not in why and "nothing is" not in why:
            why = (f"every edge out of the seed is a crease ≥{round(math.degrees(thr), 1)}° "
                   f"or a mesh boundary — the seed already fills its crease-bounded region")
        out["why_unchanged"] = why
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


def _face_project_snap(moving_obj, moved_verts, target_name):
    """Native Snapping (Face + Project) as a headless drag-snap: after the grab, drop each
    moved vert onto the nearest point of `target_name`'s surface. A BVHTree of the target's
    evaluated mesh (world space) is the projection surface; verts are round-tripped through
    the moving object's matrix. Returns (snapped_count, err|None)."""
    from mathutils.bvhtree import BVHTree
    tgt = bpy.data.objects.get(target_name)
    if tgt is None:
        return 0, f"snap_target '{target_name}' not found"
    if getattr(tgt, "type", None) != 'MESH':
        return 0, f"snap_target '{target_name}' is not a mesh"
    import bmesh
    dg = bpy.context.evaluated_depsgraph_get()
    tbm = bmesh.new()
    tbm.from_object(tgt, dg)
    tbm.transform(tgt.matrix_world)
    tree = BVHTree.FromBMesh(tbm)
    m = moving_obj.matrix_world
    minv = m.inverted()
    n = 0
    for v in moved_verts:
        loc, _nrm, _idx, _dist = tree.find_nearest(m @ v.co)
        if loc is not None:
            v.co = minv @ loc
            n += 1
    tbm.free()
    return n, None


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
    # SPEC-22 Phase 4: native Snapping (Face + Project) as a flag — after the grab, drop
    # the moved verts onto a target surface (drape verts onto another mesh's face).
    snap_to = (params.get("snap_to") or "").lower()
    snapped = None
    if snap_to == "face_project":
        target_name = params.get("snap_target") or ""
        if not target_name:
            return {"error": "snap_to='face_project' needs snap_target=<mesh to project onto>"}
        snapped, err = _face_project_snap(obj, selected, target_name)
        if err:
            return {"error": err}
    # G87: re-derive edge/face selection from the vert flags before the editmesh→mesh
    # sync, so the live selection survives the OBJECT↔EDIT round-trip a following edit
    # op triggers (without this flush, moved verts could re-enter with a stale/empty
    # selection, silently no-op'ing the next op). Matches every select_* op's flush.
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    push_undo("move_vertices")
    result = {"success": True, "verts_moved": len(selected), "delta_world": world_delta}
    if frame:
        result["frame"] = frame
    if snapped is not None:
        result["snapped_to_face"] = snapped
    return result


def _selected_islands(selected):
    """Partition selected verts into connected components, where connectivity is an
    edge with BOTH endpoints selected (G186). An isolated selected vert — no selected
    neighbour across an edge — is its own singleton island. So four separate inset
    faces split into four islands, while a contiguous patch stays one."""
    sel = set(selected)
    seen = set()
    islands = []
    for start in selected:
        if start in seen:
            continue
        seen.add(start)
        stack = [start]
        comp = []
        while stack:
            v = stack.pop()
            comp.append(v)
            for e in v.link_edges:
                o = e.other_vert(v)
                if o in sel and o not in seen:
                    seen.add(o)
                    stack.append(o)
        islands.append(comp)
    return islands


def scale_vertices(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    in_plane = params.get("in_plane")
    pivot = params.get("pivot", "SELECTION")  # SELECTION | INDIVIDUAL | ORIGIN
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
        bm.select_flush_mode()  # G87: keep the selection live across the edit-mode round-trip
        bmesh.update_edit_mesh(obj.data)
        push_undo(f"scale_vertices in_plane={f}")
        return {"success": True, "verts_scaled": len(selected),
                "frame": "in-plane ⟂ " + _describe_dir(n)}

    sx = params.get("x", 1.0)
    sy = params.get("y", 1.0)
    sz = params.get("z", 1.0)
    if (pivot or "").upper() == "INDIVIDUAL":
        # G186: scale each connected ISLAND about its OWN centroid — Blender's
        # Individual Origins pivot. "Even out these N inset faces, make each square"
        # means S about each face's own centre; the shared SELECTION pivot instead
        # drifts every feature toward the common centre. Pairs with select by_index.
        islands = _selected_islands(selected)
        for isl in islands:
            cx = sum(v.co.x for v in isl) / len(isl)
            cy = sum(v.co.y for v in isl) / len(isl)
            cz = sum(v.co.z for v in isl) / len(isl)
            for v in isl:
                v.co.x = cx + (v.co.x - cx) * sx
                v.co.y = cy + (v.co.y - cy) * sy
                v.co.z = cz + (v.co.z - cz) * sz
        bm.select_flush_mode()  # G87: keep the selection live across the round-trip
        bmesh.update_edit_mesh(obj.data)
        push_undo("scale_vertices individual")
        return {"success": True, "verts_scaled": len(selected),
                "islands": len(islands)}
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
    bm.select_flush_mode()  # G87: keep the selection live across the edit-mode round-trip
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


def proportional_scale(params):
    """G216 — proportional SCALE with falloff: shrink/grow the selection toward its own
    centroid, dragging nearby verts along by the same falloff machinery as
    proportional_move. A drip GATHERS — the surface narrows toward the hanging tip — and
    that is a soft scale, not a translate. Expressible on a coarse mesh with no sculpt
    density.

    factor:  scale multiplier at the handle verts (t=0). 0.6 = pull in to 60%, 1.4 = swell.
             Verts at the radius edge (t=1) keep factor 1.0 (unchanged); between, the
             per-vert factor lerps 1→`factor` by the falloff weight.
    radius:  falloff radius in meters (default 0.01).
    falloff: SMOOTH (default) | LINEAR | SPHERE | SHARP | ROOT | CONSTANT.
    connected: geodesic (along-edges) falloff — won't gather a disconnected shell (G60).
    freeze:  a handle whose verts are held rigid (and wall off a geodesic flood).
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    factor = float(params.get("factor", 1.0))
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
    inv_scale_min = 1.0 / min(sx, sy, sz)
    radius_local = radius * inv_scale_min

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    handles = [v for v in bm.verts if v.select]
    if not handles:
        return {"error": "No vertices selected"}

    # Pivot: the selection's centroid (local space) — verts scale toward/away from it.
    pivot = Vector((sum(v.co.x for v in handles) / len(handles),
                    sum(v.co.y for v in handles) / len(handles),
                    sum(v.co.z for v in handles) / len(handles)))

    # G60 — freeze a named handle's verts rigid (also walls a geodesic flood).
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

    r2 = radius_local * radius_local
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
            if d > dist.get(vi, radius_local):
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
        t = d / radius_local
        w = _weight(t)
        s = 1.0 + (factor - 1.0) * w         # per-vert scale, lerped by falloff
        v = bm.verts[vi]
        v.co = pivot + (v.co - pivot) * s
        affected += 1

    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"proportional_scale f={factor} r={radius} {falloff}"
              + (" connected" if connected else "")
              + (f" freeze={freeze_name}" if freeze_name else ""))
    return {"success": True, "factor": factor, "connected": connected,
            "frozen": len(frozen), "handles": len(handles), "affected": affected,
            "radius": radius, "falloff": falloff}


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


def pick_element(params):
    """G221 — the yolo click. Select ONE arbitrary element within a scope, without
    caring which one: the human's cheapest selection primitive ("click a face on the
    finger, hold Ctrl+Numpad+"). Its essence is PERMISSION TO NOT CARE which element
    it lands on — dead-reckoning a seed from coordinate listings is pure waste.

    kind:   FACE (default) | VERT | EDGE — what one element to pick.
    within: scope, a vertex-group / minted-handle name substring (case-insensitive;
            handles' backing vgroups match too). Empty = the CURRENT selection if one
            exists (pick inside what you just narrowed), else the whole mesh.
    seed:   RNG seed — the same seed picks the same element, so transcripts replay.

    Replaces the selection with exactly that element (component mode switched to
    `kind`), ready for grow/flood to expand from. Reports the element starved of
    coordinates: position words + area/length/valence, never world XYZ."""
    import bmesh
    import random as _random
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode with an active object"}
    kind = (params.get("kind") or "FACE").upper()
    if kind not in ("FACE", "VERT", "EDGE"):
        return {"error": f"pick: kind must be FACE | VERT | EDGE (got '{kind}')"}
    seed = int(params.get("seed", 0) or 0)
    within = (params.get("within") or "").strip()

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    scope = None            # None = whole mesh; else a vert-index set
    if within:
        needle = within.lower()
        matched = [vg for vg in obj.vertex_groups if needle in vg.name.lower()]
        if not matched:
            return {"error": f"pick: no vertex group / handle matching '{within}'. "
                             f"Available ({len(obj.vertex_groups)}): "
                             f"{[vg.name for vg in obj.vertex_groups]}"}
        deform = bm.verts.layers.deform.verify()
        gidx = {vg.index for vg in matched}
        scope = {v.index for v in bm.verts
                 if any(gi in v[deform] and v[deform][gi] > 0.0 for gi in gidx)}
        scope_desc = "group(s) " + ", ".join(vg.name for vg in matched)
        if not scope:
            return {"error": f"pick: {scope_desc} contain no verts on this mesh"}
    else:
        cur = {v.index for v in bm.verts if v.select}
        if cur:
            scope = cur
            scope_desc = f"the current selection ({len(cur)} verts)"
        else:
            scope_desc = "the whole mesh"

    if kind == "FACE":
        cands = bm.faces if scope is None else \
            [f for f in bm.faces if all(v.index in scope for v in f.verts)]
    elif kind == "EDGE":
        cands = bm.edges if scope is None else \
            [e for e in bm.edges if all(v.index in scope for v in e.verts)]
    else:
        cands = bm.verts if scope is None else \
            [v for v in bm.verts if v.index in scope]
    cands = sorted(cands, key=lambda el: el.index)
    if not cands:
        return {"error": f"pick: no whole {kind.lower()} lies within {scope_desc} — "
                         f"a sparse scope may contain no full face/edge; try kind=VERT"}
    choice = cands[_random.Random(seed).randrange(len(cands))]

    # Replace the selection with exactly this element, in its component mode.
    bpy.context.tool_settings.mesh_select_mode = {
        'VERT': (True, False, False), 'EDGE': (False, True, False),
        'FACE': (False, False, True)}[kind]
    for f in bm.faces:
        f.select = False
    for e in bm.edges:
        e.select = False
    for v in bm.verts:
        v.select = False
    verts = [choice] if kind == "VERT" else list(choice.verts)
    for v in verts:
        v.select = True
    bm.select_flush(True)
    bmesh.update_edit_mesh(obj.data)

    # Coordinate-starved facts (SPEC-21 §6.2): position words + a scalar, no XYZ.
    from .common import region_words
    mw = obj.matrix_world
    cos = [mw @ v.co for v in verts]
    centroid = sum(cos, Vector((0, 0, 0))) / len(cos)
    inf = float("inf")
    b = [inf, inf, inf, -inf, -inf, -inf]
    for v in bm.verts:
        co = mw @ v.co
        b[0] = min(b[0], co.x); b[1] = min(b[1], co.y); b[2] = min(b[2], co.z)
        b[3] = max(b[3], co.x); b[4] = max(b[4], co.y); b[5] = max(b[5], co.z)
    out = {"success": True, "kind": kind, "picked_index": choice.index,
           "candidates": len(cands), "seed": seed, "scope": scope_desc,
           "at": region_words((b[0], b[1], b[2], b[3], b[4], b[5]), centroid)}
    if kind == "FACE":
        area = 0.0
        for i in range(1, len(cos) - 1):
            area += ((cos[i] - cos[0]).cross(cos[i + 1] - cos[0])).length / 2.0
        out["area_mm2"] = round(area * 1e6, 2)
    elif kind == "EDGE":
        out["length_mm"] = round((cos[1] - cos[0]).length * 1000, 2)
    else:
        out["valence"] = len(choice.link_edges)
    push_undo(f"pick {kind.lower()} #{choice.index}")
    return out


def jitter_vertices(params):
    """Mesh ▸ Transform ▸ Randomize — wrap native `transform.vertex_random`.

    SPEC-22 §5.1: native name ⇒ native semantics. Displaces selected verts in 3D
    (amount / uniform / normal / seed). There is no axis restriction — that was
    the old hand-rolled jitter (bugs.md B9).

    amount:  max offset in meters (maps to native `offset`; default 0.005).
    uniform: 0 = fully random, 1 = more even (native default 0).
    normal:  0 = world 3D, 1 = align the offset along each vert normal (native 0).
    seed:    random seed (native default 0).

    G28: no narrowed selection → randomize the whole mesh (pass target=).
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    amount = float(params.get("amount", 0.005))
    uniform = float(params.get("uniform", 0.0))
    normal = float(params.get("normal", 0.0))
    seed = int(params.get("seed", 0))

    bm = bmesh.from_edit_mesh(obj.data)
    selected = [v for v in bm.verts if v.select]
    if not selected:
        # No narrowed selection → randomize the WHOLE mesh (G28).
        for v in bm.verts:
            v.select = True
        selected = list(bm.verts)
        if not selected:
            return {"error": f"'{obj.name}' has no vertices to randomize"}
        bmesh.update_edit_mesh(obj.data)

    try:
        bpy.ops.transform.vertex_random(
            offset=amount, uniform=uniform, normal=normal, seed=seed,
            wait_for_input=False)
    except RuntimeError as e:
        return {"error": f"vertex_random failed: {e}"}

    push_undo(f"randomize offset={amount} uniform={uniform} normal={normal} seed={seed}")
    return {"success": True, "verts_randomized": len(selected),
            "verts_jittered": len(selected),
            "amount": amount, "uniform": uniform, "normal": normal, "seed": seed}


def inflate_selection(params):
    """Alt+S · Mesh ▸ Transform ▸ Shrink/Fatten — push the selected verts along their
    OWN per-vert normals by `amount` (positive = fatten/out, negative = shrink/in).

    SPEC-22 Phase 4: this now wraps the native `transform.shrink_fatten` operator
    directly (drivable headless in 5.1.2), so it inherits native semantics — including
    Offset Even (`even`, native "Offset Even": correct the offset by the vertex-normal
    angle so a non-planar patch keeps even wall thickness). The prior hand-rolled push
    (fixed normal × inverse object scale, no Offset Even) diverged from native on curved
    regions; native defaults win.
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    amount = float(params.get("amount", 0.003))
    even = bool(params.get("even", False))  # native "Offset Even" default is OFF

    bm = bmesh.from_edit_mesh(obj.data)
    selected = [v for v in bm.verts if v.select]
    if not selected:
        return {"error": "No vertices selected"}
    try:
        bpy.ops.transform.shrink_fatten(value=amount, use_even_offset=even)
    except RuntimeError as e:
        return {"error": f"shrink_fatten failed: {e}"}
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"shrink_fatten {amount} even={even}")
    return {"success": True, "verts_inflated": len(selected), "amount": amount,
            "even": even}


def spin(params):
    """Native Spin (bpy.ops.mesh.spin) — revolve the selected PROFILE around a world axis
    through the object's origin: the surface-of-revolution author (SPEC-21 §4 exposes it
    natively; a goblet is a profile polyline spun 360° about Z).

    axis:  world axis to revolve AROUND — X | Y | Z (the axis line passes through the
           object's origin).
    angle: degrees of revolution (default 360 = a full turn).
    steps: cross-sections around the revolution (default 24).

    A full 360° revolve closes the seam (5.x spin shares the start ring; a residual
    merge-by-distance at 1e-5 m is kept as a safety net) and recalcs normals outward,
    so the result is watertight where the profile allows it. Topology change → refused
    on a shape-keyed mesh (it would corrupt the keys)."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    if obj.data.shape_keys is not None:
        return {"error": f"'{obj.name}' has shape keys — spin changes topology, which "
                         f"corrupts every key. Clear the keys first (pose "
                         f"op=shape_key_delete key=ALL) or spin a key-free copy."}
    axis_name = (params.get("axis") or "Z").upper()
    if axis_name not in ("X", "Y", "Z"):
        return {"error": f"axis must be X, Y or Z (got '{axis_name}')"}
    angle = float(params.get("angle") or 360.0)
    steps = max(2, int(params.get("steps") or 24))

    bm = bmesh.from_edit_mesh(obj.data)
    n_sel = sum(1 for v in bm.verts if v.select)
    if n_sel == 0:
        return {"error": "No vertices selected — select the profile to revolve first "
                         "(the open polyline/edge run that traces the silhouette)"}
    verts_before = len(bm.verts)

    # mesh.spin takes GLOBAL center/axis; the axis line runs through the object's origin.
    center = obj.matrix_world.translation
    axis_vec = Vector((0.0, 0.0, 0.0))
    setattr(axis_vec, axis_name.lower(), 1.0)
    full_turn = abs(abs(angle) - 360.0) < 1e-6
    bpy.ops.mesh.spin(steps=steps, dupli=False, angle=math.radians(angle),
                      center=center, axis=axis_vec)

    welded = 0
    if full_turn:
        # the start and end profile rings coincide — weld the seam, then face outward
        bpy.ops.mesh.select_all(action='SELECT')
        bm = bmesh.from_edit_mesh(obj.data)
        before_weld = len(bm.verts)
        bpy.ops.mesh.remove_doubles(threshold=1e-5)
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bm = bmesh.from_edit_mesh(obj.data)
        welded = before_weld - len(bm.verts)

    bm = bmesh.from_edit_mesh(obj.data)
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"spin {axis_name} {angle}° ×{steps}")
    return {"success": True, "profile_verts": n_sel, "steps": steps,
            "angle": angle, "axis": axis_name,
            "verts_before": verts_before, "verts_after": len(bm.verts),
            "faces_after": len(bm.faces), "seam_welded": welded,
            "full_turn": full_turn}


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


def symmetrize(params):
    """Make the active mesh bilaterally symmetric across an axis plane through its origin —
    the Mesh ▸ Symmetrize op (G205). One half is mirrored onto the other and welded at the
    seam, so a one-sided single-mesh edit (a pulled cheekbone, an asymmetric brow) is
    reflected TRUE in a single call, and a mesh that drifted off-symmetric is re-trued.
    This is how single-mesh organic shaping stays bilateral: shape one side freely with any
    vertex/sculpt op, then symmetrize — no need for a per-op mirror flag or a half-mesh
    MIRROR modifier. axis X|Y|Z (X = the usual left-right face plane); keep '+'|'-' picks
    which half is the SOURCE that gets copied across."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = str(params.get("axis", "X")).upper()
    if axis not in ("X", "Y", "Z"):
        return {"error": f"axis must be X|Y|Z, got {axis!r}"}
    keep = str(params.get("keep", "+")).strip()
    sign = "NEGATIVE" if keep.startswith("-") else "POSITIVE"
    direction = f"{sign}_{axis}"
    threshold = float(params.get("threshold", 1e-4))
    before = len(bmesh.from_edit_mesh(obj.data).verts)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.symmetrize(direction=direction, threshold=threshold)
    after = len(bmesh.from_edit_mesh(obj.data).verts)
    push_undo(f"symmetrize {direction}")
    return {"success": True, "direction": direction, "axis": axis,
            "kept": f"{sign.lower()} {axis}", "verts_before": before, "verts_after": after}


def recalc_normals(params):
    """Recalculate face normals consistently — the Mesh ▸ Normals ▸ Recalculate Outside
    fix (Shift-N), exposed as a primitive so a flipped-normal mesh (a boolean result whose
    shell inverted, an imported mesh with bad winding) is repaired IN PLACE instead of
    forcing a full undo+rebuild. G176 / pairs with G175.

    inside: recalc normals to face OUTWARD (False, default) or INWARD (True).
    flip:   additionally flip every face normal AFTER the recalc (Mesh ▸ Normals ▸ Flip) —
            use to invert a known-good shell, or to get the opposite of consistent-outside.

    WHOLE-MESH by default — "Recalculate Outside" almost always means fix the entire
    shell (e.g. after a boolean), so it ignores any leftover selection from a prior op and
    selects all first. only_selected=True scopes to the current selection — recalc/flip just
    ONE shell of a multi-part mesh. Reports the face count and the resulting outward/inward
    sense."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    inside = bool(params.get("inside", False))
    flip   = bool(params.get("flip", False))
    only_selected = bool(params.get("only_selected", False))
    bm = bmesh.from_edit_mesh(obj.data)
    whole = not only_selected
    if whole:
        bpy.ops.mesh.select_all(action='SELECT')
        bm = bmesh.from_edit_mesh(obj.data)
    faces = sum(1 for f in bm.faces if f.select)
    if not faces:
        return {"error": "No faces to recalculate"
                         + (" (only_selected=True but nothing is selected)" if only_selected else "")}
    bpy.ops.mesh.normals_make_consistent(inside=inside)
    if flip:
        bpy.ops.mesh.flip_normals()
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"recalc_normals inside={inside} flip={flip}")
    return {"success": True, "faces": faces, "inside": inside, "flip": flip,
            "outward": (not inside) ^ flip, "whole_mesh": whole}


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
    boundary_edges = [e for e in bm.edges if e.select and len(e.link_faces) == 1]
    # G190: weld the two rims with the LOW-LEVEL bmesh bridge on exactly these boundary
    # edges, instead of bpy.ops.mesh.bridge_edge_loops. The operator's SINGLE/PAIRS
    # auto-detect misfires when both loops sit on the SAME shell — it fans self-crossing
    # faces and leaves both rims open (χ=0, 3 boundary loops, non-manifold). bmesh.ops.
    # bridge_loops pairs the two rims into a manifold tube, consuming both boundaries
    # (genus +1) — the canonical two-hole handle. bmesh.ops.bridge_loops takes ONLY
    # `edges` (the operator's use_pairs/twist/… kwargs don't exist on the bmesh op); it
    # auto-pairs the two rims by proximity, which is what we want for coaxial holes.
    try:
        res = bmesh.ops.bridge_loops(bm, edges=boundary_edges)
    except (RuntimeError, TypeError, ValueError) as ex:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": f"bridge failed: {ex}"}
    new_faces = res.get("faces", [])
    new_edges = res.get("edges", [])
    # cuts subdivide the rungs so the tube can bow; smoothness eases the interpolation.
    if cuts > 0 and new_edges:
        bmesh.ops.subdivide_edges(bm, edges=new_edges, cuts=cuts,
                                  smooth=smoothness, use_smooth_even=True)
    # the new band inherits arbitrary winding — recompute outward so it's not inside-out.
    if new_faces:
        bmesh.ops.recalc_face_normals(bm, faces=[f for f in new_faces if f.is_valid])
    bm.normal_update()
    bmesh.update_edit_mesh(obj.data)

    bm = bmesh.from_edit_mesh(obj.data)
    faces_after = len(bm.faces)
    # honest verdict: did the weld consume both rims into a manifold tunnel?
    remaining_open = sum(1 for e in bm.edges
                         if e.verts[0].index in want and e.verts[1].index in want
                         and len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bpy.ops.object.mode_set(mode='OBJECT')
    push_undo(f"bridge {a} ↔ {b}")
    out = {"success": True, "owner": obj.name, "a": a, "b": b,
           "edges_bridged": sel_edges, "faces_created": faces_after - faces_before,
           "faces_total": faces_after,
           "bridge": {"cuts": cuts, "smoothness": smoothness}}
    if remaining_open or nonmanifold:
        out["warnings"] = [
            f"weld left {remaining_open} rim edge(s) open / {nonmanifold} non-manifold "
            f"edge(s) — the two rims may have very different vertex counts or not sit "
            f"across from each other; match their counts / check they're coaxial."]
    return out


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


def select_by_radius(params):
    """Select verts in a radial BAND around a point or an axis line (G132/G122).

    The cylindrical/banded sibling of select_in_sphere. Two things it adds:
      • an INNER radius — so this is a band (a hollow tube/shell), not a solid ball:
        'the wall between r=0.030 and r=0.036' is one call, which retires the
        in-place wall-thinning cutter-cylinder hack and the concentric-loop dance.
      • a CYLINDER shape — perpendicular distance from an AXIS LINE, not a point, so
        a full-height vessel wall selects regardless of Z.

    center / center_object / center_selection: where to measure from (world). Exactly
        one resolves the center point; for CYLINDER the axis passes through it.
          center=[x,y,z]            an explicit world point (also how handle= arrives)
          center_object='Mug'       that object's bbox centre
          center_selection=True     the current selection's bbox centre (no handle to
                                    mint first — solves G122's chicken-and-egg)
    shape:  CYLINDER (dist from the axis line) | SPHERE (dist from the point). Default CYLINDER.
    axis:   X|Y|Z cylinder axis (ignored for SPHERE). Default Z.
    radius_inner / radius_outer: the band. select iff radius_inner <= dist <= radius_outer.
        radius_inner=0 = a solid disk/ball (then it's select_in_sphere with a free axis).
    action / extend: as the other selectors (SELECT|ADD|DESELECT|INTERSECT).
    """
    import bmesh
    from mathutils import Vector
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    shape = (params.get("shape") or "CYLINDER").upper()
    if shape not in ("CYLINDER", "SPHERE"):
        return {"error": "shape must be CYLINDER or SPHERE"}
    axis = (params.get("axis") or "Z").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    r_in = float(params.get("radius_inner", 0.0) or 0.0)
    r_out = params.get("radius_outer", params.get("radius"))
    if r_out is None:
        return {"error": "radius_outer (the band's outer radius, m) is required"}
    r_out = float(r_out)
    if r_out <= 0:
        return {"error": "radius_outer must be > 0"}
    if r_in < 0 or r_in >= r_out:
        return {"error": f"radius_inner ({r_in}) must be >= 0 and < radius_outer ({r_out})"}
    action = (params.get("action") or "SELECT").upper()
    if bool(params.get("extend", False)) and action == "SELECT":
        action = "ADD"

    bm = bmesh.from_edit_mesh(obj.data)
    mw = obj.matrix_world

    center = params.get("center")
    if center is None and params.get("center_selection"):
        sel = [mw @ v.co for v in bm.verts if v.select]
        if not sel:
            return {"error": "center_selection=True but nothing is selected to centre on"}
        center = [(min(p[i] for p in sel) + max(p[i] for p in sel)) / 2 for i in range(3)]
    if center is None and params.get("center_object"):
        co = bpy.data.objects.get(params["center_object"])
        if co is None:
            return {"error": f"center_object '{params['center_object']}' not found"}
        bb = [co.matrix_world @ Vector(c) for c in co.bound_box]
        center = [(min(p[i] for p in bb) + max(p[i] for p in bb)) / 2 for i in range(3)]
    if center is None:
        # Default: the edited object's OWN axis (its bbox centre) — the common
        # "thin this vessel's wall" case needs only the radii, no centre spec.
        bb = [mw @ Vector(c) for c in obj.bound_box]
        center = [(min(p[i] for p in bb) + max(p[i] for p in bb)) / 2 for i in range(3)]
    if not (isinstance(center, (list, tuple)) and len(center) == 3):
        return {"error": "need a centre: center=[x,y,z], center_object=, "
                         "center_selection=True, or handle="}
    cx, cy, cz = float(center[0]), float(center[1]), float(center[2])

    # Band bounds are usually MEASURED radii (an agent feels r=0.05, then bands [0, 0.05]
    # to grab that shell). A surface sitting exactly on the band edge scatters across it by
    # float noise (~1e-9 m), silently dropping a fifth of the ring. Pad the band by a
    # sub-micron epsilon so "outer = the radius I measured" reliably includes that surface.
    eps = max(1e-6, r_out * 1e-4)
    lo = max(0.0, r_in - eps)
    hi = r_out + eps
    r_in2, r_out2 = lo * lo, hi * hi
    count = 0
    for v in bm.verts:
        wv = mw @ v.co
        if shape == "SPHERE":
            d2 = (wv.x - cx) ** 2 + (wv.y - cy) ** 2 + (wv.z - cz) ** 2
        else:
            dv = [wv.x - cx, wv.y - cy, wv.z - cz]
            dv[axis_idx] = 0.0
            d2 = dv[0] ** 2 + dv[1] ** 2 + dv[2] ** 2
        inside = r_in2 <= d2 <= r_out2
        if action == "DESELECT":
            if inside:
                v.select = False
                count += 1
        elif action == "ADD":
            if inside:
                v.select = True
                count += 1
        elif action == "INTERSECT":
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
    return {"success": True, "selected": count, "shape": shape,
            "axis": (axis if shape == "CYLINDER" else None),
            "radius_inner": round(r_in, 5), "radius_outer": round(r_out, 5),
            "center": [round(cx, 5), round(cy, 5), round(cz, 5)], "action": action}


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
    weight. The general primitive the all-or-nothing binders lacked — auto_weight
    heat-solves the WHOLE mesh; it can't say "these verts → this group, blended N%". A group named after a
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


# ───────────────────────── SPEC-22 Phase 4: native-basis completion ──────────
# Every handler below resolves to a single native Blender operator (or, where that
# operator is modal/context-dependent headless, a faithful bmesh equivalent of that
# ONE operator — house precedent, SPEC-22 §5 rule 3). Native name, native defaults.

def duplicate_selection(params):
    """Shift+D · Mesh ▸ Duplicate — copy the selected geometry IN-MESH. The copy is
    left selected and (native default) unmoved; pass direction words to grab it away
    in the same call (Shift+D then move). bmesh.ops.duplicate = the Duplicate operator."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    bm = bmesh.from_edit_mesh(obj.data)
    geom = ([v for v in bm.verts if v.select] + [e for e in bm.edges if e.select]
            + [f for f in bm.faces if f.select])
    if not any(isinstance(g, bmesh.types.BMVert) for g in geom):
        return {"error": "No geometry selected to duplicate"}
    verts_before = len(bm.verts)
    # Resolve the grab delta from the ORIGINAL selection (its 'out' normal) before we
    # reselect onto the copy.
    local = None
    frame = None
    world_delta = [0.0, 0.0, 0.0]
    if _has_dir_words(params):
        wv, frame, err = _resolve_world_delta(bm, obj, params)
        if err:
            return err
        local = obj.matrix_world.inverted().to_3x3() @ wv
        world_delta = [round(c, 5) for c in wv]
    elif any(abs(float(params.get(k, 0.0) or 0.0)) > 0 for k in ("x", "y", "z")):
        wv = Vector((params.get("x", 0.0), params.get("y", 0.0), params.get("z", 0.0)))
        local = obj.matrix_world.inverted().to_3x3() @ wv
        world_delta = [round(c, 5) for c in wv]
    res = bmesh.ops.duplicate(bm, geom=geom)
    new_geom = res.get("geom", [])
    new_verts = [g for g in new_geom if isinstance(g, bmesh.types.BMVert)]
    if local is not None:
        for v in new_verts:
            v.co += local
    for v in bm.verts:
        v.select = False
    for e in bm.edges:
        e.select = False
    for f in bm.faces:
        f.select = False
    for g in new_geom:
        g.select = True
    bm.select_flush(True)
    bmesh.update_edit_mesh(obj.data)
    push_undo("duplicate_selection")
    out = {"success": True, "verts_duplicated": len(new_verts),
           "verts_before": verts_before, "verts_after": len(bm.verts),
           "delta_world": world_delta}
    if frame:
        out["frame"] = frame
    return out


def rotate_selection(params):
    """R · Mesh ▸ Transform ▸ Rotate — rotate the selection about its own median
    (native pivot default) around a world axis. transform.rotate, drivable headless."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = (params.get("axis") or "Z").upper()
    if axis not in ("X", "Y", "Z"):
        return {"error": f"axis must be X, Y or Z (got '{axis}')"}
    angle = float(params.get("angle") or 0.0)
    bm = bmesh.from_edit_mesh(obj.data)
    sel = [v for v in bm.verts if v.select]
    if not sel:
        return {"error": "No vertices selected"}
    cen_local = sum((v.co for v in sel), Vector()) / len(sel)
    cen_world = obj.matrix_world @ cen_local
    bpy.ops.transform.rotate(value=math.radians(angle), orient_axis=axis,
                             orient_type='GLOBAL', center_override=cen_world)
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"rotate_selection {axis} {angle}°")
    return {"success": True, "axis": axis, "angle": angle, "verts_rotated": len(sel)}


_MERGE_AT = {"CENTER", "CURSOR", "COLLAPSE", "FIRST", "LAST"}


def merge_at(params):
    """M · Mesh ▸ Merge — weld the selected verts to one point: CENTER (their median),
    CURSOR (the 3D cursor), FIRST / LAST (the first/last selected), or COLLAPSE (each
    connected island to its own centre). mesh.merge — the M-menu targets (By Distance
    is the separate remove_doubles path)."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    at = (params.get("at") or "CENTER").upper()
    if at not in _MERGE_AT:
        return {"error": f"at must be one of {sorted(_MERGE_AT)} (or DISTANCE for "
                         f"merge-by-distance), got '{at}'"}
    bm = bmesh.from_edit_mesh(obj.data)
    before = len(bm.verts)
    if sum(1 for v in bm.verts if v.select) < 2:
        return {"error": "Select at least 2 vertices to merge"}
    try:
        bpy.ops.mesh.merge(type=at)
    except RuntimeError as e:
        return {"error": f"merge at {at} failed: {e}"}
    bm = bmesh.from_edit_mesh(obj.data)
    after = len(bm.verts)
    push_undo(f"merge_at {at}")
    return {"success": True, "at": at, "verts_before": before, "verts_after": after,
            "merged": before - after}


def make_edge_face(params):
    """F · Vertex ▸ New Edge/Face from Vertices — the "F closes it" reflex:
    2 selected verts → a new edge, 3–4 (or a boundary chain) → a new face.
    mesh.edge_face_add."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    bm = bmesh.from_edit_mesh(obj.data)
    n_sel = sum(1 for v in bm.verts if v.select)
    if n_sel < 2:
        return {"error": "Select 2 verts (→ edge) or 3+ verts / a boundary loop (→ face)"}
    e_before, f_before = len(bm.edges), len(bm.faces)
    try:
        bpy.ops.mesh.edge_face_add()
    except RuntimeError as e:
        return {"error": f"edge_face_add failed: {e}"}
    bm = bmesh.from_edit_mesh(obj.data)
    push_undo("make_edge_face")
    return {"success": True, "edges_added": len(bm.edges) - e_before,
            "faces_added": len(bm.faces) - f_before}


_DISSOLVE = {"VERT": "dissolve_verts", "EDGE": "dissolve_edges", "FACE": "dissolve_faces"}


def dissolve(params):
    """Ctrl+X · Mesh ▸ Dissolve — remove the selected elements but KEEP the surrounding
    surface (merges the neighbours into a larger face), distinct from Delete which makes
    a hole. mode VERT|EDGE|FACE → mesh.dissolve_verts/edges/faces."""
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    mode = (params.get("mode") or "VERT").upper()
    op_name = _DISSOLVE.get(mode)
    if op_name is None:
        return {"error": f"mode must be VERT|EDGE|FACE, got '{mode}'"}
    import bmesh
    bm = bmesh.from_edit_mesh(obj.data)
    vb, fb = len(bm.verts), len(bm.faces)
    if not any(v.select for v in bm.verts):
        return {"error": "Nothing selected to dissolve"}
    try:
        getattr(bpy.ops.mesh, op_name)()
    except RuntimeError as e:
        return {"error": f"{op_name} failed: {e}"}
    bm = bmesh.from_edit_mesh(obj.data)
    push_undo(f"dissolve {mode}")
    return {"success": True, "mode": mode, "verts_before": vb, "verts_after": len(bm.verts),
            "faces_before": fb, "faces_after": len(bm.faces)}


def hide_geometry(params):
    """H (Shift+H = unselected) · Mesh ▸ Show/Hide ▸ Hide — hide the selected elements
    in edit mode so they're out of the way of the next op. mesh.hide."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    unselected = bool(params.get("unselected", False))
    try:
        bpy.ops.mesh.hide(unselected=unselected)
    except RuntimeError as e:
        return {"error": f"hide failed: {e}"}
    bm = bmesh.from_edit_mesh(obj.data)
    hidden = sum(1 for v in bm.verts if v.hide)
    push_undo(f"hide_geometry unselected={unselected}")
    return {"success": True, "unselected": unselected, "hidden_verts": hidden}


def reveal_geometry(params):
    """Alt+H · Mesh ▸ Show/Hide ▸ Reveal — unhide everything hidden in edit mode.
    mesh.reveal (select=True re-selects what it reveals, the native default)."""
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    select = bool(params.get("select", True))
    try:
        bpy.ops.mesh.reveal(select=select)
    except RuntimeError as e:
        return {"error": f"reveal failed: {e}"}
    push_undo("reveal_geometry")
    return {"success": True, "select": select}


def rip_selection(params):
    """V · Vertex ▸ Rip — tear the mesh open along the selected edge(s)/vert chain,
    splitting the shared verts so the two sides part; pass direction words to pull the
    torn side away in the same call. transform.rip_move is modal (crashes headless), so
    this reproduces its ONE operator with bmesh.ops.split_edges + the grab tail."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    bm = bmesh.from_edit_mesh(obj.data)
    sel_edges = [e for e in bm.edges if e.select]
    if not sel_edges:
        selv = set(v for v in bm.verts if v.select)
        sel_edges = [e for e in bm.edges if e.verts[0] in selv and e.verts[1] in selv]
    if not sel_edges:
        return {"error": "Select an edge, an edge chain, or two adjacent verts to rip"}
    before_set = set(bm.verts)
    verts_before = len(bm.verts)
    bmesh.ops.split_edges(bm, edges=sel_edges)
    bm.verts.ensure_lookup_table()
    new_verts = [v for v in bm.verts if v not in before_set]
    world_delta = [0.0, 0.0, 0.0]
    frame = None
    if _has_dir_words(params):
        wv, frame, err = _resolve_world_delta(bm, obj, params)
        if err:
            return err
        local = obj.matrix_world.inverted().to_3x3() @ wv
        world_delta = [round(c, 5) for c in wv]
        for v in new_verts:
            v.co += local
    elif any(abs(float(params.get(k, 0.0) or 0.0)) > 0 for k in ("x", "y", "z")):
        wv = Vector((params.get("x", 0.0), params.get("y", 0.0), params.get("z", 0.0)))
        local = obj.matrix_world.inverted().to_3x3() @ wv
        world_delta = [round(c, 5) for c in wv]
        for v in new_verts:
            v.co += local
    for v in bm.verts:
        v.select = False
    for v in new_verts:
        v.select = True
    bm.select_flush(True)
    bmesh.update_edit_mesh(obj.data)
    push_undo("rip_selection")
    out = {"success": True, "verts_ripped": len(new_verts),
           "verts_before": verts_before, "verts_after": len(bm.verts),
           "delta_world": world_delta}
    if frame:
        out["frame"] = frame
    return out


def split_selection(params):
    """Y · Mesh ▸ Split ▸ Selection — disconnect the selected geometry from the rest of
    the mesh (it stays in the same object as a loose island). mesh.split."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    bm = bmesh.from_edit_mesh(obj.data)
    if not any(v.select for v in bm.verts):
        return {"error": "Nothing selected to split"}
    vb = len(bm.verts)
    try:
        bpy.ops.mesh.split()
    except RuntimeError as e:
        return {"error": f"split failed: {e}"}
    bm = bmesh.from_edit_mesh(obj.data)
    push_undo("split_selection")
    return {"success": True, "verts_before": vb, "verts_after": len(bm.verts)}


def smooth_vertices(params):
    """Vertex ▸ Smooth Vertices — relax the selected verts toward the average of their
    neighbours (native Laplacian-free smooth). mesh.vertices_smooth (factor, repeat)."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    factor = float(params.get("factor", 0.5))
    repeat = max(1, int(params.get("repeat", 1)))
    bm = bmesh.from_edit_mesh(obj.data)
    n_sel = sum(1 for v in bm.verts if v.select)
    if n_sel == 0:
        return {"error": "No vertices selected to smooth"}
    try:
        bpy.ops.mesh.vertices_smooth(factor=factor, repeat=repeat)
    except RuntimeError as e:
        return {"error": f"vertices_smooth failed: {e}"}
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"smooth_vertices ×{repeat}")
    return {"success": True, "verts_smoothed": n_sel, "factor": factor, "repeat": repeat}


def bisect(params):
    """Mesh ▸ Bisect — cut the selected geometry with an infinite plane through
    `axis`=offset; optionally fill the cut and/or clear one side. mesh.bisect."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = (params.get("axis") or "Z").upper()
    if axis not in ("X", "Y", "Z"):
        return {"error": f"axis must be X, Y or Z (got '{axis}')"}
    offset = float(params.get("offset", 0.0))
    use_fill = bool(params.get("use_fill", False))
    clear_inner = bool(params.get("clear_inner", False))
    clear_outer = bool(params.get("clear_outer", False))
    bm = bmesh.from_edit_mesh(obj.data)
    if not any(v.select for v in bm.verts):
        bpy.ops.mesh.select_all(action='SELECT')
    plane_no = Vector((0.0, 0.0, 0.0))
    setattr(plane_no, axis.lower(), 1.0)
    plane_co = plane_no * offset
    vb = len(bmesh.from_edit_mesh(obj.data).verts)
    try:
        bpy.ops.mesh.bisect(plane_co=plane_co, plane_no=plane_no, use_fill=use_fill,
                            clear_inner=clear_inner, clear_outer=clear_outer)
    except RuntimeError as e:
        return {"error": f"bisect failed: {e}"}
    bm = bmesh.from_edit_mesh(obj.data)
    push_undo(f"bisect {axis}={offset}")
    return {"success": True, "axis": axis, "offset": offset, "use_fill": use_fill,
            "clear_inner": clear_inner, "clear_outer": clear_outer,
            "verts_before": vb, "verts_after": len(bm.verts)}


def shear_selection(params):
    """Shift+Ctrl+Alt+S · Mesh ▸ Transform ▸ Shear — slant the selection: displace each
    vert along `axis` in proportion to its coordinate along `along`, about the selection
    median. transform.shear fails poll headless, so this is its ONE operator as a bmesh
    shear matrix (native semantics: a pure shear in the axis/along plane)."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    axis = (params.get("axis") or "X").upper()
    along = (params.get("along") or "Z").upper()
    if axis not in ("X", "Y", "Z") or along not in ("X", "Y", "Z"):
        return {"error": "axis and along must each be X, Y or Z"}
    if axis == along:
        return {"error": "axis (shear direction) and along (gradient) must differ"}
    amount = float(params.get("amount", 0.0))
    ai = {"X": 0, "Y": 1, "Z": 2}[axis]
    gi = {"X": 0, "Y": 1, "Z": 2}[along]
    bm = bmesh.from_edit_mesh(obj.data)
    sel = [v for v in bm.verts if v.select]
    if not sel:
        return {"error": "No vertices selected"}
    cen = sum((v.co for v in sel), Vector()) / len(sel)
    for v in sel:
        v.co[ai] += amount * (v.co[gi] - cen[gi])
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"shear_selection {axis} along {along} {amount}")
    return {"success": True, "axis": axis, "along": along, "amount": amount,
            "verts_sheared": len(sel)}


def to_sphere(params):
    """Shift+Alt+S · Mesh ▸ Transform ▸ To Sphere — blend the selection toward a sphere
    about its median. factor 0..1 (1 = fully spherical). transform.tosphere."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    factor = max(0.0, min(1.0, float(params.get("factor", 1.0))))
    bm = bmesh.from_edit_mesh(obj.data)
    if not any(v.select for v in bm.verts):
        return {"error": "No vertices selected"}
    try:
        bpy.ops.transform.tosphere(value=factor)
    except RuntimeError as e:
        return {"error": f"to_sphere failed: {e}"}
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"to_sphere {factor}")
    return {"success": True, "factor": factor}


def triangulate(params):
    """Ctrl+T · Face ▸ Triangulate Faces — convert the selected faces to triangles.
    mesh.quads_convert_to_tris."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    bm = bmesh.from_edit_mesh(obj.data)
    if not any(f.select for f in bm.faces):
        bpy.ops.mesh.select_all(action='SELECT')
    fb = len(bmesh.from_edit_mesh(obj.data).faces)
    try:
        bpy.ops.mesh.quads_convert_to_tris()
    except RuntimeError as e:
        return {"error": f"triangulate failed: {e}"}
    bm = bmesh.from_edit_mesh(obj.data)
    push_undo("triangulate")
    return {"success": True, "faces_before": fb, "faces_after": len(bm.faces)}


def tris_to_quads(params):
    """Alt+J · Face ▸ Tris to Quads — merge adjacent triangles back into quads where the
    shared edge is below the angle limits. mesh.tris_convert_to_quads (face_threshold,
    shape_threshold in degrees)."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    face_thr = math.radians(float(params.get("face_threshold", 40.0)))
    shape_thr = math.radians(float(params.get("shape_threshold", 40.0)))
    bm = bmesh.from_edit_mesh(obj.data)
    if not any(f.select for f in bm.faces):
        bpy.ops.mesh.select_all(action='SELECT')
    fb = len(bmesh.from_edit_mesh(obj.data).faces)
    try:
        bpy.ops.mesh.tris_convert_to_quads(face_threshold=face_thr, shape_threshold=shape_thr)
    except RuntimeError as e:
        return {"error": f"tris_to_quads failed: {e}"}
    bm = bmesh.from_edit_mesh(obj.data)
    push_undo("tris_to_quads")
    return {"success": True, "faces_before": fb, "faces_after": len(bm.faces)}


def fill(params):
    """Alt+F · Face ▸ Fill — fill the selected edge boundary with triangles (an n-gon
    region gets a triangle fan). mesh.fill (use_beauty on by default = native)."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    use_beauty = bool(params.get("use_beauty", True))
    bm = bmesh.from_edit_mesh(obj.data)
    fb = len(bm.faces)
    try:
        bpy.ops.mesh.fill(use_beauty=use_beauty)
    except RuntimeError as e:
        return {"error": f"fill failed: {e}. Select a closed edge boundary to fill."}
    bm = bmesh.from_edit_mesh(obj.data)
    added = len(bm.faces) - fb
    if added <= 0:
        return {"error": "fill added nothing — select a closed edge boundary (an open "
                         "loop of edges around a hole)."}
    push_undo("fill")
    return {"success": True, "faces_added": added, "faces_total": len(bm.faces)}


def beautify(params):
    """Shift+Alt+F · Face ▸ Beautify Faces — re-flip the shared edges of the selected
    triangles toward a more balanced (Delaunay-ish) triangulation. mesh.beautify_fill."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    angle = math.radians(float(params.get("angle_limit", 180.0)))
    bm = bmesh.from_edit_mesh(obj.data)
    if not any(f.select for f in bm.faces):
        return {"error": "No faces selected to beautify"}
    try:
        bpy.ops.mesh.beautify_fill(angle_limit=angle)
    except RuntimeError as e:
        return {"error": f"beautify failed: {e}. Select triangles to rebalance."}
    bmesh.update_edit_mesh(obj.data)
    push_undo("beautify")
    return {"success": True}


def connect_verts(params):
    """J · Vertex ▸ Connect Vertices — cut a new edge between the selected verts across
    the faces they share (splits a quad in two). mesh.vert_connect."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    bm = bmesh.from_edit_mesh(obj.data)
    if sum(1 for v in bm.verts if v.select) < 2:
        return {"error": "Select at least 2 verts on a shared face to connect"}
    eb = len(bm.edges)
    try:
        bpy.ops.mesh.vert_connect()
    except RuntimeError as e:
        return {"error": f"connect failed: {e}"}
    bm = bmesh.from_edit_mesh(obj.data)
    added = len(bm.edges) - eb
    if added <= 0:
        return {"error": "connect made no cut — the selected verts must share a face "
                         "(and not already be joined by an edge)."}
    push_undo("connect_verts")
    return {"success": True, "edges_added": added}


def slide(params):
    """Vertex Slide (Shift+V) / Edge Slide (GG) · Vertex/Edge ▸ Slide — move the
    selected verts ALONG their neighbouring edges by `factor` (-1..1; sign picks which
    rail), staying on the existing topology (no reprojection). transform.vert_slide /
    edge_slide are modal (crash headless), so this reproduces that ONE operator's core:
    a topological along-edge slide. mode VERT|EDGE selects which selection it reads."""
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    factor = float(params.get("factor", 0.5))
    if not -1.0 <= factor <= 1.0:
        return {"error": "factor must be in -1..1 (fraction of the rail edge)"}
    bm = bmesh.from_edit_mesh(obj.data)
    sel_verts = set(v for v in bm.verts if v.select)
    if not sel_verts:
        return {"error": "Nothing selected to slide"}
    moved = 0
    for v in sel_verts:
        rails = [e for e in v.link_edges if e.other_vert(v) not in sel_verts]
        if not rails:
            continue
        rails.sort(key=lambda e: (e.other_vert(v).co - v.co).x, reverse=(factor >= 0))
        other = rails[0].other_vert(v)
        v.co += (other.co - v.co) * abs(factor)
        moved += 1
    if moved == 0:
        return {"error": "no rail to slide along — the selection has no adjacent "
                         "unselected vert to slide toward (select fewer / an interior loop)."}
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"slide {factor}")
    return {"success": True, "verts_slid": moved, "factor": factor}


TOOLS = {
    "poke_faces":         poke_faces,
    "inset_faces":        inset_faces,
    "grid_fill":          grid_fill,
    "select_limb":        select_limb,
    "bevel":              bevel,
    "extrude":            extrude,
    "spin":               spin,
    "extrude_along_curve": extrude_along_curve,
    "loop_cut":           loop_cut,
    "subdivide_selection": subdivide_selection,
    "set_component_mode": set_component_mode,
    "select_all":         select_all,
    "select_by_axis":     select_by_axis,
    "select_between":     select_between,
    "list_components":    list_components,
    "select_by_index":    select_by_index,
    "select_by_vgroup":   select_by_vgroup,
    "select_by_material": select_by_material,
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
    "pick_element":       pick_element,
    "proportional_move":  proportional_move,
    "proportional_scale": proportional_scale,
    "inflate_selection":  inflate_selection,
    "mark_sharp":         mark_sharp,
    "set_edge_crease":    set_edge_crease,
    "merge_by_distance":  merge_by_distance,
    "symmetrize":         symmetrize,
    "recalc_normals":     recalc_normals,
    "select_in_sphere":   select_in_sphere,
    "select_by_radius":   select_by_radius,
    "split_by_part":      split_by_part,
    "assign_weight":      assign_weight,
    "select_boundary":    select_boundary,
    "bridge_handles":     bridge_handles,
    # SPEC-22 Phase 4 — native-basis completion
    "duplicate_selection": duplicate_selection,
    "rotate_selection":   rotate_selection,
    "merge_at":           merge_at,
    "make_edge_face":     make_edge_face,
    "dissolve":           dissolve,
    "hide_geometry":      hide_geometry,
    "reveal_geometry":    reveal_geometry,
    "rip_selection":      rip_selection,
    "split_selection":    split_selection,
    "smooth_vertices":    smooth_vertices,
    "bisect":             bisect,
    "shear_selection":    shear_selection,
    "to_sphere":          to_sphere,
    "triangulate":        triangulate,
    "tris_to_quads":      tris_to_quads,
    "fill":               fill,
    "beautify":           beautify,
    "connect_verts":      connect_verts,
    "slide":              slide,
}

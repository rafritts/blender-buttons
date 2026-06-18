"""get_topology — the topology sense (SPEC-04).

One read-only verb, many METHODS, over ONE mesh. Returns NAMED, GRABBABLE
landmarks + summaries (openings, branches, regions, poles, symmetry, thickness),
never a raw vertex dump. This is the concrete tool that realizes SPEC-02's
"object / element view" — the structural sense `describe` (enclosure altitude)
does not provide.

v1 methods (numpy + bmesh + native BVH/KDTree, zero extra deps):
  components  genus  boundaries  poles  symmetry  frame  sections  curvature  features  thickness
v2 methods (need scipy — heat-method geodesics / spectral cut):
  geodesic  skeleton  segments
"""

import math

import bmesh
import mathutils
import numpy as np

from .common import region_words

_DEFAULT_METHODS = ["components", "genus", "boundaries", "sections", "poles", "symmetry", "frame"]
_V2_METHODS = {"geodesic", "skeleton", "segments"}
_AXES = ("X", "Y", "Z")


# ─────────────────────────── mesh access ───────────────────────────

def _topology_bmesh(obj, base):
    """A world-space bmesh of obj for analysis.

    base='cage' (default) reads the BASE control mesh — no modifiers — which is
    what you want for topology: the subsurf/particle-evaluated mesh explodes the
    vert count and buries structure (Spring's pullover = subsurf + 800 hair
    strands). base='evaluated' reads the modifier result when that's the question.
    Caller owns the bmesh and must .free() it.
    """
    import bpy
    # G42: in EDIT mode the live selection (and any unflushed geometry) lives in the
    # edit bmesh, NOT in obj.data — `from_mesh(obj.data)` would read the STALE snapshot
    # from the last mode exit (region_form reported a 12-vert core while 150 were live-
    # selected). Flush the edit-mode data back to obj.data so every method below reads
    # the selection the operator is actually pointing at.
    if obj.mode == 'EDIT':
        obj.update_from_editmode()
    bm = bmesh.new()
    if base == "evaluated":
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        me = obj_eval.to_mesh()
        bm.from_mesh(me)
        obj_eval.to_mesh_clear()
    else:
        bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return bm


def _bbox(bm):
    """6-tuple world bbox of the bmesh, for region_words."""
    co = np.array([list(v.co) for v in bm.verts]) if bm.verts else np.zeros((1, 3))
    mn, mx = co.min(0), co.max(0)
    return (mn[0], mn[1], mn[2], mx[0], mx[1], mx[2])


def _boundary_loops(bm):
    """Walk open-boundary edges (one linked face) into ordered vert-index loops.
    Robust for manifold boundaries; non-manifold boundary verts may split a loop —
    acceptable for v1 (reported counts stay honest)."""
    bedges = [e for e in bm.edges if len(e.link_faces) == 1]
    visited = set()
    loops = []
    for start in bedges:
        if start.index in visited:
            continue
        loop_v = []
        e, v = start, start.verts[0]
        while e is not None and e.index not in visited:
            visited.add(e.index)
            loop_v.append(v.index)
            nv = e.other_vert(v)
            ne = None
            for cand in nv.link_edges:
                if len(cand.link_faces) == 1 and cand.index not in visited:
                    ne = cand
                    break
            v, e = nv, ne
        loops.append(loop_v)
    return loops


# ─────────────────────────── methods ───────────────────────────

def _m_components(bm, lod, bbox):
    """Separate shells (islands) — the 'scarf vs its stitches' / fused-vs-not test."""
    seen = set()
    comps = []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, members = [v], []
        seen.add(v.index)
        while stack:
            cur = stack.pop()
            members.append(cur)
            for e in cur.link_edges:
                o = e.other_vert(cur)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
        comps.append(members)
    comps.sort(key=len, reverse=True)
    out = []
    for i, mem in enumerate(comps):
        co = np.array([list(v.co) for v in mem])
        size = co.max(0) - co.min(0)
        out.append({"index": i, "verts": len(mem),
                    "size_m": [round(float(x), 4) for x in size]})
    res = {"count": len(comps)}
    cap = 10 if lod == "low" else len(out)
    res["components"] = out[:cap]
    if len(out) > cap:
        res["omitted"] = len(out) - cap
    return res


def _m_genus(bm, lod, bbox):
    """Euler characteristic → topological type. For an orientable surface with b
    boundary loops, χ = V−E+F = 2 − 2g − b, so g = (2 − χ − b)/2. Reports the whole
    mesh; a multi-shell mesh is summarized as 'see components'."""
    V, E, F = len(bm.verts), len(bm.edges), len(bm.faces)
    chi = V - E + F
    b = len(_boundary_loops(bm))
    genus = (2 - chi - b) / 2.0
    closed = (b == 0)
    return {"euler_characteristic": chi, "boundary_loops": b,
            "genus": round(genus, 2) if genus == int(genus) else round(genus, 3),
            "closed": closed,
            "reading": (f"closed genus-{int(genus)} surface" if closed and genus == int(genus)
                        else f"open shell, {b} hole(s)" if not closed
                        else "multi-shell — see components")}


def _m_boundaries(bm, lod, bbox):
    """The openings: every open hole, sized + located. The cut/graft anchors."""
    loops = sorted(_boundary_loops(bm), key=len, reverse=True)
    out = []
    for i, lv in enumerate(loops):
        co = [bm.verts[idx].co for idx in lv]
        per = sum((co[k] - co[(k + 1) % len(co)]).length for k in range(len(co)))
        centroid = mathutils.Vector((0, 0, 0))
        for c in co:
            centroid += c
        centroid /= len(co)
        entry = {"index": i, "verts": len(lv),
                 "circumference_cm": round(per * 100, 1),
                 "region": region_words(bbox, centroid)}
        if lod != "low":
            entry["path_vert_ids"] = lv
        out.append(entry)
    return {"count": len(out), "boundaries": out}


def _m_poles(bm, lod, bbox):
    """Valence ≠ 4 verts (quad-flow breaks). Boundary verts excluded (naturally
    non-4). Poles near a cut line make a cut messy — surface them."""
    by_val = {}
    poles = []
    for v in bm.verts:
        if not v.link_edges:
            continue
        if any(len(e.link_faces) == 1 for e in v.link_edges):
            continue
        val = len(v.link_edges)
        if val != 4:
            by_val[val] = by_val.get(val, 0) + 1
            poles.append((v, val))
    res = {"count": len(poles),
           "by_valence": {str(k): by_val[k] for k in sorted(by_val)}}
    if lod != "low":
        res["poles"] = [{"valence": val, "vert_id": v.index,
                         "region": region_words(bbox, v.co)}
                        for v, val in poles[:200]]
    return res


def _m_symmetry(bm, lod, bbox):
    """Mirror error across each world axis plane (through the centroid), via a
    KDTree nearest-mirror test. The bilateral plane of a character is the axis
    with near-zero error."""
    from mathutils.kdtree import KDTree
    n = len(bm.verts)
    if n < 2:
        return {"error": "too few verts"}
    co = [v.co.copy() for v in bm.verts]
    centroid = mathutils.Vector((0, 0, 0))
    for c in co:
        centroid += c
    centroid /= n
    kd = KDTree(n)
    for i, c in enumerate(co):
        kd.insert(c, i)
    kd.balance()
    per_axis = {}
    best, best_err = None, None
    for ai, ax in enumerate(_AXES):
        errs = np.empty(n)
        for i, c in enumerate(co):
            m = c.copy()
            m[ai] = 2 * centroid[ai] - m[ai]
            _, _, d = kd.find(m)
            errs[i] = d
        mean_mm = float(errs.mean()) * 1000
        per_axis[ax] = {"mean_error_mm": round(mean_mm, 3),
                        "max_error_mm": round(float(errs.max()) * 1000, 3),
                        "symmetric": mean_mm < 1.0}
        if best_err is None or mean_mm < best_err:
            best, best_err = ax, mean_mm
    return {"per_axis": per_axis, "best_plane": best,
            "best_mean_error_mm": round(best_err, 3)}


def _m_region_form(bm, lod, bbox):
    """Read the FORM of the current selection — the scalars an axis-aligned bbox
    CANNOT show: how far the patch bulges, whether its slope is convex or concave,
    and whether it has a left/right mirror twin. Closes the sculpt feedback loop so
    form is judgeable between strokes without a screenshot (gaps.md G2).

    Reads v.select — the last edit-mode selection, retained on the base mesh. Read it
    in OBJECT mode (or right after a select op) so the selection is synced. Needs >=4
    selected verts."""
    from mathutils.kdtree import KDTree
    sel = [v for v in bm.verts if v.select]
    n = len(sel)
    if n < 4:
        return {"note": f"select a region first — this lens reads the current "
                        f"selection (need >=4 verts, found {n})", "selected": n}
    co = np.array([list(v.co) for v in sel])           # world space
    c = co.mean(0)
    # best-fit plane through the patch: normal = smallest-variance eigenvector
    evals, evecs = np.linalg.eigh(np.cov((co - c).T))
    normal = evecs[:, int(np.argmin(evals))]
    # orient OUTWARD = away from the whole-mesh centre, so +proj = bulging out
    mesh_c = np.array([(bbox[0] + bbox[3]) / 2, (bbox[1] + bbox[4]) / 2,
                       (bbox[2] + bbox[5]) / 2])
    if float(np.dot(normal, c - mesh_c)) < 0:
        normal = -normal
    d = (co - c) @ normal                              # signed dist from plane (m)
    inplane = (co - c) - np.outer(d, normal)
    r = np.linalg.norm(inplane, axis=1)                # in-plane radius per vert
    span_cm = round(float(r.max()) * 2 * 100, 2)       # ~patch diameter
    # convex/concave: inner third (by radius) vs outer third, signed along normal
    order = np.argsort(r)
    k = max(1, n // 3)
    center_vs_rim_mm = round(float(d[order[:k]].mean() - d[order[-k:]].mean()) * 1000, 2)
    if abs(center_vs_rim_mm) < 0.5:
        verdict = "flat"
    elif center_vs_rim_mm > 0:
        verdict = "convex (centre bulges out past the rim)"
    else:
        verdict = "concave (centre dips in behind the rim)"
    # L/R symmetry: mirror each selected vert across the X plane (through mesh centre)
    # and measure nearest vert in the WHOLE mesh — finds a mirror twin region if any.
    allco = [v.co.copy() for v in bm.verts]
    kd = KDTree(len(allco))
    for i, cc in enumerate(allco):
        kd.insert(cc, i)
    kd.balance()
    errs = np.empty(n)
    px = float(mesh_c[0])
    for i in range(n):
        m = mathutils.Vector(co[i]); m[0] = 2 * px - m[0]
        _, _, dist = kd.find(m)
        errs[i] = dist
    out = {
        "selected": n,
        "region": region_words(bbox, mathutils.Vector(c)),
        "span_cm": span_cm,
        "projection_out_cm": round(float(d.max()) * 100, 2),
        "projection_in_cm": round(float(d.min()) * 100, 2),
        "curvature_verdict": verdict,
        "center_vs_rim_mm": center_vs_rim_mm,
        "lr_mirror_mean_mm": round(float(errs.mean()) * 1000, 3),
        "lr_mirror_max_mm": round(float(errs.max()) * 1000, 3),
    }
    # G48 prong 3 — static trust caveat: a tiny patch gives a noisy verdict, and a very
    # wide one averages distinct features together (the navel funnel read shallow). Flag
    # the value's reliability rather than silently returning a confident number.
    if n < 12:
        out["caveat"] = (f"only {n} verts — verdict is noisy; grow the selection or run "
                         f"feel op=verify to test capture")
    elif span_cm > 12.0:
        out["caveat"] = (f"~{span_cm}cm patch is broad — distinct features may be "
                         f"averaging together; tighten the selection if reading one feature")
    return out


def _m_protrusion(bm, lod, bbox):
    """ABSOLUTE protrusion of the SELECTION above its surrounding surface (gaps.md
    G41). region_form fits its plane to the patch ITSELF, so it's invariant to
    self-similar growth and can't answer "did this get bigger / how far does it stick
    out?". This fits the base plane to the NEIGHBOURHOOD ring (the unselected verts
    bordering the selection) — the local surface the patch rises from — and measures
    the selection's rise above it, in cm. An absolute ruler that moves when the form
    grows: snapshot before, read after, diff. Complements region_form (relative shape)
    the way a ruler complements a curvature gauge.

    Reads v.select (world-space bmesh). Needs >=4 selected verts and a border ring."""
    sel = [v for v in bm.verts if v.select]
    n = len(sel)
    if n < 4:
        return {"note": f"select a region first — this reads the current selection "
                        f"(need >=4 verts, found {n})", "selected": n}
    sel_idx = {v.index for v in sel}
    ring = {}
    for v in sel:
        for e in v.link_edges:
            o = e.other_vert(v)
            if o.index not in sel_idx:
                ring[o.index] = o
    if len(ring) < 3:
        return {"note": "selection has no surrounding ring (whole-shell or boundary "
                        "selection?) — absolute protrusion needs unselected neighbours "
                        "to fit the base plane against", "selected": n, "ring_verts": len(ring)}
    rco = np.array([list(v.co) for v in ring.values()])
    base_c = rco.mean(0)
    evals, evecs = np.linalg.eigh(np.cov((rco - base_c).T))
    normal = evecs[:, int(np.argmin(evals))]
    mesh_c = np.array([(bbox[0] + bbox[3]) / 2, (bbox[1] + bbox[4]) / 2,
                       (bbox[2] + bbox[5]) / 2])
    if float(np.dot(normal, base_c - mesh_c)) < 0:
        normal = -normal
    sco = np.array([list(v.co) for v in sel])
    d = (sco - base_c) @ normal                 # signed dist from the base plane (m)
    apex = sco[int(np.argmax(d))]
    out = {
        "selected": n,
        "ring_verts": len(ring),
        "region": region_words(bbox, mathutils.Vector(base_c)),
        "max_protrusion_cm": round(float(d.max()) * 100, 2),
        "mean_protrusion_cm": round(float(d.mean()) * 100, 2),
        "base_recess_cm": round(float(d.min()) * 100, 2),
        "apex_world": [round(float(x), 4) for x in apex],
        "base_normal": [round(float(x), 3) for x in normal],
    }
    # G48 prong 3 — a base plane fit to too few ring verts is unreliable; flag it
    # instead of returning a confident protrusion off a noisy plane.
    if len(ring) < 8:
        out["caveat"] = (f"base plane fit to only {len(ring)} ring verts — protrusion "
                         f"is unreliable; widen the selection so it has a fuller border")
    return out


def _m_frame(bm, lod, bbox):
    """Intrinsic principal axes (PCA) + extents — so analysis never assumes
    world-up. The pose-independent frame of the shape."""
    co = np.array([list(v.co) for v in bm.verts])
    if len(co) < 3:
        return {"error": "too few verts"}
    c = co.mean(0)
    cov = np.cov((co - c).T)
    evals, evecs = np.linalg.eigh(cov)
    order = np.argsort(evals)[::-1]
    evecs = evecs[:, order]
    proj = (co - c) @ evecs
    extents = proj.max(0) - proj.min(0)
    axes = []
    for k in range(3):
        vec = evecs[:, k]
        axes.append({"extent_m": round(float(extents[k]), 4),
                     "direction": [round(float(x), 3) for x in vec],
                     "aligns_world": _AXES[int(np.argmax(np.abs(vec)))]})
    return {"principal_axes": axes}


def _corner_angle(f, v):
    verts = list(f.verts)
    i = verts.index(v)
    a, b, c = verts[i - 1].co, verts[i].co, verts[(i + 1) % len(verts)].co
    e1, e2 = (a - b), (c - b)
    if e1.length < 1e-12 or e2.length < 1e-12:
        return 0.0
    return math.acos(max(-1.0, min(1.0, e1.normalized().dot(e2.normalized()))))


def _m_curvature(bm, lod, bbox):
    """Per-vertex curvature, summarized. Gaussian via angle defect (flat / elliptic
    / saddle); mean-curvature SIGN via neighbor-centroid vs normal (convex bump vs
    concave dip). Fuzzy by nature — reported as a distribution + located extremes,
    tagged as a guess. The mesh-independent (Laplacian) version is v2."""
    flat = elliptic_convex = elliptic_concave = saddle = 0
    extremes = []
    for v in bm.verts:
        if not v.link_faces:
            continue
        if any(len(e.link_faces) == 1 for e in v.link_edges):
            continue
        ang = sum(_corner_angle(f, v) for f in v.link_faces)
        defect = 2 * math.pi - ang
        # mean-curvature sign: where do the neighbours sit relative to the surface normal?
        nbrs = [e.other_vert(v).co for e in v.link_edges]
        nc = mathutils.Vector((0, 0, 0))
        for p in nbrs:
            nc += p
        nc /= len(nbrs)
        convex = (nc - v.co).dot(v.normal) < 0
        if abs(defect) < 0.05:
            flat += 1
        elif defect > 0:
            if convex:
                elliptic_convex += 1
            else:
                elliptic_concave += 1
        else:
            saddle += 1
        extremes.append((abs(defect), v, convex))
    total = flat + elliptic_convex + elliptic_concave + saddle
    if total == 0:
        return {"error": "no interior verts to measure"}
    extremes.sort(key=lambda t: t[0], reverse=True)
    res = {"interior_verts": total, "tagged": "fuzzy — curvature is a guess (v2 = exact)",
           "distribution_pct": {
               "flat": round(100 * flat / total, 1),
               "convex": round(100 * elliptic_convex / total, 1),
               "concave": round(100 * elliptic_concave / total, 1),
               "saddle": round(100 * saddle / total, 1)}}
    if lod != "low":
        res["high_curvature"] = [
            {"vert_id": v.index, "region": region_words(bbox, v.co),
             "kind": "convex" if cx else "concave"}
            for _, v, cx in extremes[:50]]
    return res


def _m_features(bm, lod, bbox):
    """Hard edges by dihedral angle — the MACHINE sense (an AK/car is defined by
    its sharp edges, where organic methods say nothing). Sharp edges grouped into
    connected chains (a part's hard rim)."""
    thr = math.radians(float(30.0))
    sharp = []
    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        try:
            ang = e.calc_face_angle(0.0)
        except (ValueError, RuntimeError):
            continue
        if ang >= thr:
            sharp.append(e)
    # union-find over sharp edges sharing a vert → chain count
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    vert_to_edge = {}
    for e in sharp:
        for v in e.verts:
            if v.index in vert_to_edge:
                union(e.index, vert_to_edge[v.index])
            vert_to_edge[v.index] = e.index
        find(e.index)
    chains = len({find(e.index) for e in sharp}) if sharp else 0
    return {"threshold_deg": 30.0, "sharp_edges": len(sharp), "chains": chains}


def _m_thickness(bm, lod, bbox):
    """Local wall/part diameter via inward BVH ray-cast (the SDF cue for part
    segmentation). v1 = single inward ray per sampled face; true SDF averages a
    cone — flagged in the spec. Open shells yield few hits → reported honestly."""
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromBMesh(bm)
    faces = bm.faces
    if not faces:
        return {"error": "no faces"}
    step = max(1, len(faces) // 400)
    vals = []
    for idx in range(0, len(faces), step):
        f = faces[idx]
        n = f.normal
        if n.length < 1e-9:
            continue
        origin = f.calc_center_median() - n * 1e-5
        hit = tree.ray_cast(origin, -n)
        if hit[0] is not None and hit[3] > 1e-6:
            vals.append(hit[3])
    if not vals:
        return {"samples": 0, "note": "no inward hits — likely an open/single-sided surface"}
    arr = np.array(vals)
    return {"samples": len(vals),
            "min_mm": round(float(arr.min()) * 1000, 2),
            "median_mm": round(float(np.median(arr)) * 1000, 2),
            "max_mm": round(float(arr.max()) * 1000, 2)}


def _plane_contours(bm, t, t0):
    """Intersect the surface with the plane {axis·x = t0} and return its contour
    curves. t is the per-vertex axis coordinate (index-aligned). Each crossed face
    contributes a segment between its two crossing edges; segments are chained into
    connected components. A component where every node has valence 2 is a CLOSED
    contour (fabric fully wraps here); a component with valence-1 ends is an OPEN
    arc (only partial coverage). No contour at all = a VOID at this station."""
    side = t >= t0
    edge_pt = {}

    def get_pt(e):
        p = edge_pt.get(e.index)
        if p is not None:
            return p
        a, b = e.verts
        ta, tb = t[a.index], t[b.index]
        denom = tb - ta
        s = 0.5 if abs(denom) < 1e-12 else (t0 - ta) / denom
        p = a.co.lerp(b.co, min(1.0, max(0.0, s)))
        edge_pt[e.index] = p
        return p

    adj = {}
    seg_len = {}

    def add_seg(i, j, p, q):
        key = (i, j) if i < j else (j, i)
        if key in seg_len:
            return
        seg_len[key] = (p - q).length
        adj.setdefault(i, []).append(j)
        adj.setdefault(j, []).append(i)

    for f in bm.faces:
        ce = [l.edge for l in f.loops
              if side[l.edge.verts[0].index] != side[l.edge.verts[1].index]]
        if len(ce) < 2:
            continue
        pts = [get_pt(e) for e in ce]
        for m in range(0, len(ce) - 1, 2):
            add_seg(ce[m].index, ce[m + 1].index, pts[m], pts[m + 1])

    contours, seen = [], set()
    for node in list(adj):
        if node in seen:
            continue
        comp, stack = [], [node]
        seen.add(node)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nb in adj[cur]:
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        compset = set(comp)
        closed = len(comp) >= 3 and all(len(adj[n]) == 2 for n in comp)
        length = sum(L for (i, j), L in seg_len.items()
                     if i in compset and j in compset)
        cpt = mathutils.Vector((0, 0, 0))
        for n in comp:
            cpt += edge_pt[n]
        cpt /= len(comp)
        contours.append({"closed": closed, "length_cm": round(length * 100, 1),
                         "centroid": cpt})
    return contours


def _longest_zero_run(counts):
    """(start_index, length) of the longest run of empty stations — the biggest void."""
    best_start = best_len = cur_start = cur = 0
    for i, c in enumerate(counts):
        if c == 0:
            if cur == 0:
                cur_start = i
            cur += 1
            if cur > best_len:
                best_len, best_start = cur, cur_start
        else:
            cur = 0
    return best_start, best_len


_STATIONS = {"low": 24, "medium": 48, "high": 96}


def _m_sections(bm, lod, bbox):
    """Cross-section sweep along the intrinsic principal axes — the COVERAGE sense.
    Topology can't tell a full sweater from a hollow collar-with-sleeves (they're
    homeomorphic); this can. Marching a plane down each axis, it reports per station
    how many contours exist, their length, and whether they're CLOSED (wraps fully)
    or OPEN (partial). Empty stations = a VOID — material that isn't there. Catches
    coverage gaps, partial wraps, and branch splits (contour count 1→2) in one pass.
    Pose-robust: sweeps PCA axes, never world-up."""
    co = np.array([list(v.co) for v in bm.verts])
    if len(co) < 4 or not bm.faces:
        return {"error": "too few verts/faces"}
    centroid = co.mean(0)
    evals, evecs = np.linalg.eigh(np.cov((co - centroid).T))
    evecs = evecs[:, np.argsort(evals)[::-1]]
    n = _STATIONS.get(lod, 24)
    cen = mathutils.Vector([float(x) for x in centroid])
    axes_out = []
    for k in range(3):
        vec = evecs[:, k]
        t = (co - centroid) @ vec
        tmin, tmax = float(t.min()), float(t.max())
        span = tmax - tmin
        if span < 1e-9:
            continue
        vmv = mathutils.Vector([float(x) for x in vec])
        counts, detail = [], []
        closed_total = contour_total = 0
        open_regions = {}  # where the open (C-shaped) arcs cluster — the coverage gaps
        for s in range(n):
            t0 = tmin + (s + 0.5) / n * span
            contours = _plane_contours(bm, t, t0)
            counts.append(len(contours))
            contour_total += len(contours)
            for c in contours:
                if c["closed"]:
                    closed_total += 1
                else:
                    r = region_words(bbox, c["centroid"])
                    open_regions[r] = open_regions.get(r, 0) + 1
            if lod == "high":
                detail.append({"pos_cm": round(t0 * 100, 1),
                               "contours": [{"length_cm": c["length_cm"],
                                             "closed": c["closed"],
                                             "region": region_words(bbox, c["centroid"])}
                                            for c in contours]})
        open_total = contour_total - closed_total
        occupied = sum(1 for c in counts if c > 0)
        gstart, glen = _longest_zero_run(counts)
        gap = None
        if glen:
            tc = tmin + (gstart + glen / 2.0) / n * span
            gap = {"span_cm": round(glen / n * span * 100, 1), "stations": glen,
                   "region": region_words(bbox, cen + vmv * tc)}
        top_open = sorted(open_regions.items(), key=lambda kv: kv[1], reverse=True)[:3]
        axis_out = {
            "axis": _AXES[int(np.argmax(np.abs(vec)))],
            "direction": [round(float(x), 3) for x in vec],
            "extent_cm": round(span * 100, 1),
            "stations": n,
            "occupied_pct": round(100 * occupied / n, 1),
            "max_contours": max(counts) if counts else 0,
            "open_pct": round(100 * open_total / contour_total, 1) if contour_total else 0.0,
            "closed_pct": round(100 * closed_total / contour_total, 1) if contour_total else 0.0,
            "open_regions": [{"region": r, "count": c} for r, c in top_open],
            "largest_gap": gap,
        }
        if lod == "medium":
            axis_out["profile"] = counts
        elif lod == "high":
            axis_out["sections"] = detail
        axes_out.append(axis_out)
    return {"axes": axes_out}


# ──────────────────── structure (SPEC-07: the skeleton lens) ────────────────────
#
# The compact, role-HONEST read. Every other method either floods (sections) or
# lies by omission (boundaries says "4 holes" — can't tell a cuff from an armhole).
# This one runs a fingertip inward from each opening and classifies it:
#   PROTRUSION cap — a tube (sleeve/limb/finger/spout) that holds a girth then
#                    necks UP into a much larger body. The opening is a cuff; the
#                    neck is the armhole = the natural cut line.
#   FLUSH aperture — opens straight into the body (neck hole, hem). No tube.
# It spends its tokens on the protrusions, because that's where a cut goes and
# exactly where a census is silent. Zero extra deps (bmesh + numpy).

def _loop_perimeter(co):
    """True circumference of an ORDERED vert-coord loop (metres)."""
    n = len(co)
    return sum((co[k] - co[(k + 1) % n]).length for k in range(n))


def _ring_layers(bm, seed_ids, max_rings=400):
    """BFS vertex layers outward from a seed set (a boundary loop). layer[0] = the
    seed; layer[k] = verts at edge-distance k. This IS the fingertip running inward
    from the opening; each layer is a cross-ring whose girth we then read."""
    visited = set(seed_ids)
    cur = [bm.verts[i] for i in seed_ids]
    layers = [cur]
    while cur and len(layers) < max_rings:
        nxt = []
        for v in cur:
            for e in v.link_edges:
                o = e.other_vert(v)
                if o.index not in visited:
                    visited.add(o.index)
                    nxt.append(o)
        if not nxt:
            break
        layers.append(nxt)
        cur = nxt
    return layers


def _ring_girth(verts):
    """Girth proxy of an UNORDERED vert ring: treat it as a circle about its own
    centroid, girth = 2π·mean_radius. Tessellation-independent and monotone-faithful
    along a tube — all the step-up test needs. Returns (girth_m, centroid_np)."""
    co = np.array([list(v.co) for v in verts], dtype=float)
    c = co.mean(0)
    return float(2 * math.pi * np.linalg.norm(co - c, axis=1).mean()), c


def _find_protrusion_base(girths):
    """Walking inward from an opening, decide PROTRUSION vs FLUSH from the girth
    profile. The discriminator is a FLAT RUN: a real protrusion is a TUBE, so its
    girth holds roughly constant for a stretch (the tube wall) and only THEN ramps up
    into the body. A flush opening on a CURVED body — an armhole, a neckline — has no
    flat run: girth climbs straight off the rim, ring after ring. Requiring the flat
    run is what stops the re-anchoring spiral (cut a sleeve → the fresh armhole is a
    rising rim, NOT a flat tube → not re-flagged → no endless inward re-cutting).

    Returns (base_index, body_girth) where base_index is the LAST ring of the flat
    tube (the cut line), or None for a flush opening.
    """
    n = len(girths)
    if n < 5:
        return None
    body = max(girths)
    BAND = 0.15        # a 'flat' run stays within ±15% (max ≤ 1.15·min of the run)
    MIN_RUN = 4        # ... for at least this many rings — a real tube wall
    CAP_FRAC = 0.6     # the tube must be meaningfully narrower than the body it joins
    i = 0
    while i < n:
        j, lo, hi = i, girths[i], girths[i]
        while j + 1 < n:
            nlo, nhi = min(lo, girths[j + 1]), max(hi, girths[j + 1])
            if nhi <= (1 + BAND) * nlo:        # run stays flat
                lo, hi, j = nlo, nhi, j + 1
            else:
                break
        level = 0.5 * (lo + hi)
        if (j - i + 1) >= MIN_RUN and level < CAP_FRAC * body and j < n - 1:
            return j, body                     # cut at the end of the flat tube wall
        i = j + 1
    return None


def find_protrusions(bm, bbox):
    """Shared protrusion analysis — the engine behind BOTH the perception lens and
    the action (select_limb). Returns (protrusions, apertures). Each protrusion
    carries grabbable HANDLES so the cut can be anchored to topology, never a
    coordinate:
      cap_ids       — the cuff/opening loop (vert indices, obj.data-aligned)
      base_ring_ids — the cut loop (the armhole): the ring where the tube meets body
      member_ids    — the limb's verts OUT to (not incl.) the base ring: the set to
                      delete to remove the limb, leaving base_ring as a clean opening
    plus metrics (diameter, extent, girths, regions, girth profile).
    """
    loops = sorted(_boundary_loops(bm), key=len, reverse=True)
    protrusions, apertures = [], []
    for lv in loops:
        if len(lv) < 3:
            continue
        co = [bm.verts[i].co for i in lv]
        circ = _loop_perimeter(co)
        centroid = mathutils.Vector((0, 0, 0))
        for c in co:
            centroid += c
        centroid /= len(co)
        layers = _ring_layers(bm, lv)
        rings = [_ring_girth(L) for L in layers]
        prof = [round(g * 100, 1) for g, _ in rings]
        found = _find_protrusion_base([g for g, _ in rings])
        if found is None:
            apertures.append({"circumference_cm": round(circ * 100, 1),
                              "region": region_words(bbox, centroid),
                              "verts": len(lv), "girth_profile_cm": prof[:30]})
        else:
            base_idx, body = found
            base_g, base_c = rings[base_idx]
            base_v = mathutils.Vector(tuple(base_c))
            member = set()
            for L in layers[:base_idx]:          # cap..base-1: the limb, sans cut ring
                for v in L:
                    member.add(v.index)
            protrusions.append({
                "cap_circumference_cm": round(circ * 100, 1),
                "diameter_cm": round(circ / math.pi * 100, 1),
                "extent_cm": round((base_v - centroid).length * 100, 1),
                "base_girth_cm": round(base_g * 100, 1),
                "cap_region": region_words(bbox, centroid),
                "base_region": region_words(bbox, base_v),
                "base_point": [round(float(x), 4) for x in base_c],
                "cap_ids": lv,
                "base_ring_ids": [v.index for v in layers[base_idx]],
                "member_ids": sorted(member),
                "girth_profile_cm": prof[:30],
            })
    return protrusions, apertures


def _lens_protrusion(bm, lod, bbox):
    """The PROTRUSION lens (open-shell regime). Tubes capped by an open loop that
    neck into a larger body — sleeves, limbs, fingers, spouts — become protrusions
    with their cut line; everything else is a flush aperture. Gated by the
    dispatcher: only fired when the mesh actually has open boundary loops. Today it
    seeds on open loops; generalizing the seed to curve-skeleton leaves is what
    extends it to CLOSED limbs (a character's arm ends in a hand, not a hole).
    Presentation only — strips the heavy id handles at low lod; `find_protrusions`
    holds them for select_limb."""
    protrusions, apertures = find_protrusions(bm, bbox)
    pres_p, pres_a = [], []
    for p in protrusions:
        e = {k: p[k] for k in ("cap_circumference_cm", "diameter_cm", "extent_cm",
                               "base_girth_cm", "cap_region", "base_region")}
        if lod != "low":
            e["base_point"] = p["base_point"]
            e["cap_path_vert_ids"] = p["cap_ids"]
            e["base_ring_ids"] = p["base_ring_ids"]
            e["girth_profile_cm"] = p["girth_profile_cm"]
        pres_p.append(e)
    for a in apertures:
        e = {"circumference_cm": a["circumference_cm"], "region": a["region"]}
        if lod != "low":
            e["girth_profile_cm"] = a["girth_profile_cm"]
        pres_a.append(e)
    return {"n_protrusions": len(pres_p), "n_apertures": len(pres_a),
            "protrusions": pres_p, "apertures": pres_a}


def _count_shells(bm):
    """Cheap connected-component (shell) count — a triage predicate, O(V+E)."""
    seen, n = set(), 0
    for v in bm.verts:
        if v.index in seen:
            continue
        n += 1
        stack = [v]
        seen.add(v.index)
        while stack:
            cur = stack.pop()
            for e in cur.link_edges:
                o = e.other_vert(cur)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
    return n


def _m_structure(bm, lod, bbox):
    """The DISPATCHER (SPEC-07). Touch a mesh → cheap triage (open holes? watertight?
    through-holes? how many shells?) → fire the lens(es) that fit, and NAME any
    regime we detect but have no lens for yet. Never a silent 0+0: an unhandled
    regime says so out loud. Lenses are non-exclusive — a mesh can match several.
    The predicates are all near-free (boundary count, shell count, Euler χ), so the
    triage rides on every touch and only the matching heavy lens actually runs.

    Lens registry today:
      open boundary loops → protrusion lens (sleeves/limbs/spouts) — BUILT
      watertight, χ < 2   → through-hole / handle regime (genus lens) — TBD
      watertight, χ = 2   → closed solid: symmetry/primitive regime (gear) — TBD
      > 1 shell           → assembly (flagged; per-shell lensing) — TBD
    """
    loops = _boundary_loops(bm)
    nbound = len(loops)
    shells = _count_shells(bm)
    euler = len(bm.verts) - len(bm.edges) + len(bm.faces)
    watertight = nbound == 0

    out = {"triage": {"shells": shells, "open_loops": nbound,
                      "watertight": watertight, "euler": euler},
           "regimes": [], "lenses_run": [], "unhandled": []}

    if nbound > 0:
        out["regimes"].append("open-shell")
        out["lenses_run"].append("protrusion")
        out["protrusion"] = _lens_protrusion(bm, lod, bbox)
    if watertight and euler < 2:
        out["regimes"].append("solid-with-through-holes")
        out["unhandled"].append("through-hole/handle lens (genus regime) — not built yet")
    if watertight and euler == 2:
        out["regimes"].append("closed-solid")
        out["unhandled"].append("symmetry/primitive lens (gear, prop, blob) — not built yet")
    if shells > 1:
        out["unhandled"].append(f"{shells} separate shells — per-shell lensing not built "
                                f"(protrusion lens reads them pooled)")
    return out


_METHODS = {
    "components": _m_components,
    "structure": _m_structure,
    "genus": _m_genus,
    "boundaries": _m_boundaries,
    "poles": _m_poles,
    "symmetry": _m_symmetry,
    "frame": _m_frame,
    "sections": _m_sections,
    "curvature": _m_curvature,
    "region_form": _m_region_form,
    "protrusion": _m_protrusion,
    "features": _m_features,
    "thickness": _m_thickness,
}


# ─────────────────────────── dispatcher ───────────────────────────

def get_topology(params):
    import bpy
    name = params.get("target") or params.get("name")
    obj = bpy.data.objects.get(name) if name else bpy.context.active_object
    if obj is None:
        return {"error": "no target object (pass target= or select one)"}
    if obj.type != 'MESH':
        return {"error": f"'{obj.name}' is not a mesh (type {obj.type})"}

    methods = params.get("method") or list(_DEFAULT_METHODS)
    if isinstance(methods, str):
        methods = [methods]
    lod = (params.get("lod") or "low").lower()
    base = (params.get("base") or "cage").lower()
    if base not in ("cage", "evaluated"):
        return {"error": f"base must be 'cage' or 'evaluated', got '{base}'"}

    bm = _topology_bmesh(obj, base)
    try:
        bbox = _bbox(bm)
        report = {}
        for m in methods:
            if m in _V2_METHODS:
                report[m] = {"error": "not implemented in v1 (needs scipy — v2)"}
            elif m in _METHODS:
                try:
                    report[m] = _METHODS[m](bm, lod, bbox)
                except Exception as e:
                    report[m] = {"error": f"{type(e).__name__}: {e}"}
            else:
                valid = ", ".join(sorted(_METHODS))
                v2 = ", ".join(sorted(_V2_METHODS))
                report[m] = {"error": f"unknown method '{m}'. valid: {valid} "
                                      f"(v2, needs scipy: {v2})"}
        result = {
            "success": True,
            "object": obj.name,
            "base": base,
            "lod": lod,
            "counts": {"verts": len(bm.verts), "edges": len(bm.edges),
                       "faces": len(bm.faces)},
            "topology": report,
        }
    finally:
        bm.free()
    return result


# ── G45: before/after region diff ─────────────────────────────────────────────
# Session store (cleared on addon reload) mapping a baseline name → the verts it
# captured + their form metrics. A region diff is inherently a within-session
# before/after, so a module dict is the right lifetime — no datablock needed.
_REGION_BASELINES = {}


def _region_snapshot(obj, indices, base="cage"):
    """Compute the selection-scoped form bundle over an explicit vert-index set, by
    setting select flags on a THROWAWAY world bmesh (never touches the live mesh).
    Returns (metrics_dict, present_count)."""
    bm = _topology_bmesh(obj, base)
    idxset = set(int(i) for i in indices)
    present = 0
    cos = []
    for v in bm.verts:
        hit = v.index in idxset
        v.select = hit
        if hit:
            present += 1
            cos.append(v.co.copy())
    if present < 4:
        bm.free()
        return None, present
    bbox = _bbox(bm)
    rf = _m_region_form(bm, "low", bbox)
    pr = _m_protrusion(bm, "low", bbox)
    bm.free()
    c = mathutils.Vector((sum(p.x for p in cos), sum(p.y for p in cos),
                          sum(p.z for p in cos))) / present
    metrics = {"centroid": [round(x, 5) for x in c], "verts": present}
    for k in ("span_cm", "projection_out_cm", "projection_in_cm", "center_vs_rim_mm",
              "curvature_verdict", "lr_mirror_mean_mm"):
        if k in rf:
            metrics[k] = rf[k]
    if "max_protrusion_cm" in pr:
        metrics["max_protrusion_cm"] = pr["max_protrusion_cm"]
    return metrics, present


def region_baseline(params):
    """G45 — capture the live selection's form (span/projection/curvature/symmetry/
    centroid) + its vert indices as a NAMED baseline, to diff after an edit. The
    'before' half of a local, temporal verification."""
    import bpy
    name = (params.get("name") or "").strip()
    if not name:
        return {"error": "region baseline needs name=<label>"}
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "active object is not a mesh"}
    base = params.get("base", "cage")
    bm = _topology_bmesh(obj, base)
    indices = [v.index for v in bm.verts if v.select]
    bm.free()
    if len(indices) < 4:
        return {"note": f"select a region first (need >=4 verts, found {len(indices)})",
                "selected": len(indices)}
    metrics, _ = _region_snapshot(obj, indices, base)
    _REGION_BASELINES[name] = {"owner": obj.name, "indices": indices,
                               "base": base, "metrics": metrics}
    return {"success": True, "name": name, "owner": obj.name,
            "verts": len(indices), "metrics": metrics}


def region_diff(params):
    """G45 — re-read a named baseline's SAME verts now and report the signed change per
    metric. The 'after' half: a local edit checked locally and temporally, so 'it grew
    2cm and stayed symmetric' is one read, not a hand-diff of two global snapshots."""
    import bpy
    name = (params.get("name") or "").strip()
    b = _REGION_BASELINES.get(name)
    if b is None:
        return {"error": f"no region baseline named '{name}' — capture one first with "
                         f"feel op=baseline name={name} (this session only)"}
    obj = bpy.data.objects.get(b["owner"])
    if obj is None or obj.type != 'MESH':
        return {"error": f"baseline owner '{b['owner']}' is gone"}
    after, present = _region_snapshot(obj, b["indices"], b.get("base", "cage"))
    if after is None:
        return {"error": f"baseline '{name}' verts are gone ({present} of "
                         f"{len(b['indices'])} remain) — the edit changed topology; re-baseline"}
    before = b["metrics"]
    delta = {}
    for k in ("span_cm", "projection_out_cm", "projection_in_cm", "center_vs_rim_mm",
              "lr_mirror_mean_mm", "max_protrusion_cm"):
        if k in before and k in after:
            delta[k] = round(after[k] - before[k], 3)
    bc, ac = before.get("centroid"), after.get("centroid")
    if bc and ac:
        delta["centroid_shift_cm"] = round(math.sqrt(sum((a - b2) ** 2
                                          for a, b2 in zip(ac, bc))) * 100, 2)
    return {"success": True, "name": name, "owner": obj.name,
            "before": before, "after": after, "delta": delta}


TOOLS = {
    "get_topology":   get_topology,
    "region_baseline": region_baseline,
    "region_diff":    region_diff,
}

"""get_topology — the topology sense (SPEC-04).

One read-only verb, many METHODS, over ONE mesh. Returns NAMED, GRABBABLE
landmarks + summaries (openings, branches, regions, poles, symmetry, thickness),
never a raw vertex dump. This is the concrete tool that realizes SPEC-02's
"object / element view" — the structural sense `describe` (enclosure altitude)
does not provide.

v1 methods (numpy + bmesh + native BVH/KDTree, zero extra deps):
  components  genus  boundaries  poles  symmetry  frame  curvature  features  thickness
v2 methods (need scipy — heat-method geodesics / spectral cut):
  geodesic  skeleton  segments
"""

import math

import bmesh
import mathutils
import numpy as np

from .common import region_words

_DEFAULT_METHODS = ["components", "genus", "boundaries", "poles", "symmetry", "frame"]
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


_METHODS = {
    "components": _m_components,
    "genus": _m_genus,
    "boundaries": _m_boundaries,
    "poles": _m_poles,
    "symmetry": _m_symmetry,
    "frame": _m_frame,
    "curvature": _m_curvature,
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
                report[m] = {"error": f"unknown method '{m}'"}
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


TOOLS = {
    "get_topology": get_topology,
}

"""compose — SPEC-19 Phase 3: the algebraic merge the bridge/connect family can't do.

`edit op=graft a=<A> b=<B> mode=smin blend=<k>` converts two parts to signed-distance
fields, smooth-min unions them (the fillet radius is the ONE legible number `k`), and
marching-tetrahedra meshes the result — the filleted union that replaces the "merge monster"
with arithmetic (supersedes gaps.md G153). `edit op=stitch a=<A> b=<B>` welds two surface
patches that share a boundary into one watertight quilt (matched sampling + boundary weld),
the C0 seam the discrete connectors leave cracked.

No scipy/skimage in Blender, so the SDF→mesh is a self-contained marching TETRAHEDRA (a tiny,
unambiguous case table that is always watertight/manifold — the Freudenthal 6-tet cube split).
"""

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .state import push_undo


# ───────────────────────────── signed distance fields ─────────────────────────────

def _world_bmesh(obj):
    """An evaluated, world-space bmesh copy of obj (modifiers applied)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(obj.matrix_world)
    bm.normal_update()
    ev.to_mesh_clear()
    return bm


def _open_edges(bm):
    return sum(1 for e in bm.edges if len(e.link_faces) != 2)


def _sdf_grid(bvh, pts):
    """Signed distance from each world point to the mesh: sign by the nearest face normal
    (>0 outside, <0 inside) — reliable for a CLOSED mesh."""
    out = np.empty(len(pts), dtype=float)
    for i in range(len(pts)):
        p = Vector((float(pts[i, 0]), float(pts[i, 1]), float(pts[i, 2])))
        loc, nrm, _idx, dist = bvh.find_nearest(p)
        if loc is None:
            out[i] = 1e9
        else:
            out[i] = dist if (p - loc).dot(nrm) >= 0.0 else -dist
    return out


def _smin(a, b, k):
    """Polynomial smooth minimum (iquilezles): a soft union whose blend width is k."""
    if k <= 1e-9:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return a * h + b * (1.0 - h) - k * h * (1.0 - h)


# ───────────────────────────── marching tetrahedra ─────────────────────────────

_CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
         (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
_TETS = [(0, 5, 1, 6), (0, 1, 2, 6), (0, 2, 3, 6),
         (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6)]


def _marching_tets(G, xs, ys, zs):
    """Iso=0 surface of a scalar grid G via marching tetrahedra. Returns (verts, tris),
    watertight + manifold by construction. Only sign-straddling cells are processed."""
    n0, n1, n2 = G.shape
    verts = []
    vcache = {}
    tris = []

    def vid(p):
        key = (round(p[0], 6), round(p[1], 6), round(p[2], 6))
        vi = vcache.get(key)
        if vi is None:
            vi = len(verts); vcache[key] = vi; verts.append((p[0], p[1], p[2]))
        return vi

    for i in range(n0 - 1):
        for j in range(n1 - 1):
            for k in range(n2 - 1):
                blk = G[i:i + 2, j:j + 2, k:k + 2]
                if blk.min() > 0.0 or blk.max() < 0.0:
                    continue
                cp = [(xs[i + c[0]], ys[j + c[1]], zs[k + c[2]]) for c in _CUBE]
                cval = [G[i + c[0], j + c[1], k + c[2]] for c in _CUBE]
                for tet in _TETS:
                    cv = [cval[t] for t in tet]
                    pp = [cp[t] for t in tet]
                    inside = [m for m in range(4) if cv[m] < 0.0]
                    outside = [m for m in range(4) if cv[m] >= 0.0]

                    def X(a, b):
                        va, vb = cv[a], cv[b]
                        t = va / (va - vb) if (va - vb) != 0.0 else 0.5
                        pa, pb = pp[a], pp[b]
                        return vid((pa[0] + t * (pb[0] - pa[0]),
                                    pa[1] + t * (pb[1] - pa[1]),
                                    pa[2] + t * (pb[2] - pa[2])))
                    if len(inside) == 1:
                        a = inside[0]
                        tris.append((X(a, outside[0]), X(a, outside[1]), X(a, outside[2])))
                    elif len(inside) == 3:
                        c = outside[0]
                        tris.append((X(inside[0], c), X(inside[1], c), X(inside[2], c)))
                    elif len(inside) == 2:
                        a, b = inside; c, d = outside
                        p_ac, p_ad, p_bd, p_bc = X(a, c), X(a, d), X(b, d), X(b, c)
                        tris.append((p_ac, p_ad, p_bd))
                        tris.append((p_ac, p_bd, p_bc))
    return verts, tris


# ───────────────────────────── the graft op ─────────────────────────────

def graft(params):
    a_name = (params.get("a", "") or "").strip()
    b_name = (params.get("b", "") or "").strip()
    mode = (params.get("mode", "smin") or "smin").lower()
    blend = float(params.get("blend", 0.0) or 0.0)
    res = int(params.get("resolution", 0) or 0) or 48
    out_name = (params.get("name", "") or "").strip() or "graft"
    keep = bool(params.get("keep", False))
    if mode != "smin":
        return {"error": f"graft mode must be 'smin' (got {mode!r}); smin = SDF smooth-min union"}
    A = bpy.data.objects.get(a_name)
    B = bpy.data.objects.get(b_name)
    if A is None or A.type != 'MESH' or B is None or B.type != 'MESH':
        return {"error": "graft needs two mesh objects (a= and b=)"}
    if bpy.data.objects.get(out_name) is not None:
        return {"error": f"object '{out_name}' already exists"}
    res = max(12, min(res, 96))

    bmA, bmB = _world_bmesh(A), _world_bmesh(B)
    warnings = []
    if _open_edges(bmA) or _open_edges(bmB):
        warnings.append("a source mesh is not closed — SDF sign may be unreliable at the seam")
    bvhA, bvhB = BVHTree.FromBMesh(bmA), BVHTree.FromBMesh(bmB)

    # combined bbox + a margin so the blended fillet has room to bulge outward
    allco = np.array([list(v.co) for v in bmA.verts] + [list(v.co) for v in bmB.verts])
    lo, hi = allco.min(0), allco.max(0)
    margin = max(blend * 1.5, (hi - lo).max() / res * 2.0)
    lo -= margin; hi += margin
    xs = np.linspace(lo[0], hi[0], res)
    ys = np.linspace(lo[1], hi[1], res)
    zs = np.linspace(lo[2], hi[2], res)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    pts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    G = _smin(_sdf_grid(bvhA, pts), _sdf_grid(bvhB, pts), blend).reshape(res, res, res)
    bmA.free(); bmB.free()

    verts, tris = _marching_tets(G, xs, ys, zs)
    if not verts:
        return {"error": "graft produced no surface — parts may not overlap (raise blend= or "
                         "move them closer) or resolution is too coarse"}

    me = bpy.data.meshes.new(out_name)
    me.from_pydata(verts, [], tris)
    me.update()
    obj = bpy.data.objects.new(out_name, me)
    bpy.context.scene.collection.objects.link(obj)

    nb = bmesh.new(); nb.from_mesh(me)
    open_seam = _open_edges(nb); nb.free()

    removed = []
    if not keep:
        for o in (A, B):
            removed.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    push_undo(f"graft {a_name}+{b_name} smin k={blend}")
    return {"success": True, "object": out_name, "verts": len(verts), "faces": len(tris),
            "blend": round(blend, 5), "resolution": res, "watertight": open_seam == 0,
            "removed": removed, "warnings": warnings}


# ───────────────────────────── the stitch op ─────────────────────────────

def _world_boundary_pts(obj):
    """World-space copy of obj's mesh + its open-boundary vertex coords."""
    me = obj.data.copy()
    me.transform(obj.matrix_world)
    bm = bmesh.new(); bm.from_mesh(me)
    pts = np.array([list(v.co) for v in bm.verts
                    if any(len(e.link_faces) < 2 for e in v.link_edges)], dtype=float)
    n_bound = sum(1 for e in bm.edges if len(e.link_faces) < 2)
    bm.free(); bpy.data.meshes.remove(me)
    return pts, n_bound


def _append_world(bm, obj):
    me = obj.data.copy()
    me.transform(obj.matrix_world)
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)


def stitch(params):
    a_name = (params.get("a", "") or "").strip()
    b_name = (params.get("b", "") or "").strip()
    out_name = (params.get("name", "") or "").strip() or "stitch"
    keep = bool(params.get("keep", False))
    A = bpy.data.objects.get(a_name)
    B = bpy.data.objects.get(b_name)
    if A is None or A.type != 'MESH' or B is None or B.type != 'MESH':
        return {"error": "stitch needs two mesh patches (a= and b=)"}
    if bpy.data.objects.get(out_name) is not None:
        return {"error": f"object '{out_name}' already exists"}

    pa, nba = _world_boundary_pts(A)
    pb, nbb = _world_boundary_pts(B)
    if len(pa) == 0 or len(pb) == 0:
        return {"error": "a patch has no open boundary to stitch (already closed)"}
    # closest gap between the two boundaries = the seam separation
    dists = np.sqrt(((pa[:, None, :] - pb[None, :, :]) ** 2).sum(-1))
    gap = float(dists.min())
    diagA = float(np.linalg.norm(pa.max(0) - pa.min(0)))
    diagB = float(np.linalg.norm(pb.max(0) - pb.min(0)))
    if gap > 0.15 * min(diagA, diagB):           # a shared seam is ~coincident, not patch-sized
        return {"error": f"patches don't share a boundary (closest gap {gap*1000:.1f}mm) — "
                         f"align them so the seam coincides + match the sampling first (§2)"}
    weld = max(gap * 2.5, 1e-5)

    bm = bmesh.new()
    _append_world(bm, A)
    _append_world(bm, B)
    v_before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
    v_after = len(bm.verts)
    seam_open = sum(1 for e in bm.edges if len(e.link_faces) < 2)
    me = bpy.data.meshes.new(out_name)
    bm.to_mesh(me); bm.free()
    me.update()
    obj = bpy.data.objects.new(out_name, me)
    bpy.context.scene.collection.objects.link(obj)

    removed = []
    if not keep:
        for o in (A, B):
            removed.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    push_undo(f"stitch {a_name}+{b_name}")
    welded = v_before - v_after
    return {"success": True, "object": out_name, "verts": v_after,
            "seam_verts": welded, "seam_gap_mm": round(gap * 1000.0, 4),
            "seam_closed": seam_open < (nba + nbb), "removed": removed, "warnings": []}


TOOLS = {
    "graft": graft,
    "stitch": stitch,
}

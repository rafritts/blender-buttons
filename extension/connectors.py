"""connectors — geometry-bound parametric connectors (SPEC-10 Phases 2–3).

`edit op=connect a=<handleA> b=<handleB>` welds two open rims with a swept,
tapered, tangent-continuous tube — the primitive the two-cylinder "connect with
an organic curve" dogfood proved missing (gaps.md G59/G60/G61/G65).

What it does that no existing verb could:
  • G59 — anchors the curve to the two openings: each endpoint sits on the rim and
    the curve LEAVES each pipe along that opening's outward normal (G1 continuity at
    the seam). No hand-typed control points; `tension` is the one legible "how much
    arc" scalar.
  • G61 — sweeps a HOLLOW cross-section that matches each rim's vertex count 1:1 and
    tapers radius/shape between them, on a PARALLEL-TRANSPORTED (minimum-twist) frame
    so it never creases, then welds both ends into one watertight manifold.
  • G60 — lays the ring of geometry ALONG the centreline with cross-sections kept
    perpendicular to the tangent (a swept path, not a displacement bulge).
  • G65 — emits the centreline quality reads (length, min bend radius, per-seam
    tangent-vs-normal angle, sweep feasibility) in the status block.

v1 scope: rims must have EQUAL vertex counts (1:1 weld); unequal counts are refused
with a pointer to re-ring. Both owners must be meshes. The editable-parameter tier
(re-evaluate against live handles) and the multi-strand tier are SPEC-10 Phases 4–5,
not built here.
"""

import math

import bmesh
import bpy
from mathutils import Vector

from . import handles as H
from .common import world_center
from .state import push_undo


# ── rim reading ───────────────────────────────────────────────────────────────

def _ordered_loop(owner, vgname):
    """Walk a boundary handle's vert-set into an ORDERED world-space loop.

    Returns (positions, indices, error). `positions` is the cyclic list of world
    Vectors, `indices` the matching owner-vert indices. Errors when the set has no
    open-boundary edges (a closed cap) or doesn't form one clean cycle."""
    if owner is None or owner.type != 'MESH':
        return None, None, "owner is gone or not a mesh"
    vset = H._vgroup_vertset(owner, vgname)
    if not vset:
        return None, None, "handle is orphaned (vgroup gone/empty)"

    bm = bmesh.new()
    bm.from_mesh(owner.data)
    bm.verts.ensure_lookup_table()
    adj = {i: [] for i in vset}
    co = {}
    nedges = 0
    mw = owner.matrix_world
    for e in bm.edges:
        if len(e.link_faces) != 1:
            continue
        i, j = e.verts[0].index, e.verts[1].index
        if i in vset and j in vset:
            adj[i].append(j)
            adj[j].append(i)
            nedges += 1
    for i in vset:
        co[i] = mw @ bm.verts[i].co.copy()
    bm.free()

    if nedges == 0:
        return None, None, ("sits on a CLOSED cap — no open rim to weld into "
                            "(uncap it first: delete the cap face)")
    if any(len(adj[i]) != 2 for i in vset):
        return None, None, ("boundary isn't a single clean loop (a vert has !=2 "
                            "boundary neighbours — the rim branches or is doubled)")

    start = next(iter(vset))
    order = [start]
    prev, cur = None, start
    while True:
        nbrs = [x for x in adj[cur] if x != prev]
        if not nbrs:
            break
        nxt = nbrs[0]
        if nxt == start:
            break
        order.append(nxt)
        prev, cur = cur, nxt
        if len(order) > len(vset):
            break
    if len(order) != len(vset):
        return None, None, (f"boundary isn't a single cycle "
                            f"({len(order)} of {len(vset)} verts walked)")
    return [co[i] for i in order], order, None


# ── centreline ────────────────────────────────────────────────────────────────

def _bezier(p0, p1, p2, p3, t):
    u = 1.0 - t
    return (p0 * (u * u * u) + p1 * (3 * u * u * t)
            + p2 * (3 * u * t * t) + p3 * (t * t * t))


_STYLE_TENSION = {"arc": 0.55, "s_curve": 0.55, "slack": 0.9, "direct": 0.0}


# ── the verb ──────────────────────────────────────────────────────────────────

def connect_handles(params):
    """edit op=connect — weld two open boundary rims with a swept tangent-continuous
    tube (SPEC-10). See module docstring. Consumes two boundary handles (mint with
    feel op=assembly), not coordinates.

    a, b:     the two boundary handles to connect (order-independent for the weld;
              the curve is symmetric).
    style:    arc (default) | s_curve | direct | slack. arc/s_curve/slack leave each
              opening along its OUTWARD NORMAL (G1 continuity); the shape that emerges
              is a single arc when the openings face each other and an S when they face
              the same way. direct relaxes continuity toward the straight chord.
    tension:  0..1 — control-handle length as a fraction of the gap ("how much it
              bows"). -1 (default) = the style's default.
    sections: length resolution (rings along the span). Default 12.
    profile:  match (default — sweep each rim's own cross-section, tapering between) |
              round (force a clean circle of the matched radius mid-span).
    weld:     fuse both ends into the owning shell(s) → one watertight manifold
              (default True). False leaves the connector as a separate mesh object.
    name:     name for the connector object (default 'connector'). When weld=True the
              result keeps owner a's name; this only shows on weld=False.
    """
    a_name = (params.get("a") or "").strip()
    b_name = (params.get("b") or "").strip()
    if not a_name or not b_name:
        return {"error": "edit op=connect needs a=<handle> and b=<handle> "
                         "(mint boundary handles with feel op=assembly)"}
    if a_name == b_name:
        return {"error": "a and b are the same handle — connect needs two distinct rims"}

    ea, eb = H._find_handle(a_name), H._find_handle(b_name)
    if ea is None:
        return {"error": f"handle '{a_name}' not found (run feel op=assembly to mint rims)"}
    if eb is None:
        return {"error": f"handle '{b_name}' not found (run feel op=assembly to mint rims)"}

    owner_a = bpy.data.objects.get(ea.get("bb_owner", ""))
    owner_b = bpy.data.objects.get(eb.get("bb_owner", ""))
    if owner_a is None or owner_a.type != 'MESH':
        return {"error": f"'{a_name}' owner is gone or not a mesh"}
    if owner_b is None or owner_b.type != 'MESH':
        return {"error": f"'{b_name}' owner is gone or not a mesh"}
    for o in (owner_a, owner_b):
        if o.data.shape_keys is not None:
            return {"error": f"'{o.name}' has shape keys — connect changes topology and "
                             f"would corrupt the keys. Keyed/rigged meshes are out of scope."}

    # Own the mode: rim reads + object creation/join all need OBJECT mode.
    if bpy.context.active_object is not None and bpy.context.active_object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')

    loopA, _idxA, errA = _ordered_loop(owner_a, ea.get("bb_vgroup", ""))
    if errA:
        return {"error": f"handle '{a_name}': {errA}"}
    loopB, _idxB, errB = _ordered_loop(owner_b, eb.get("bb_vgroup", ""))
    if errB:
        return {"error": f"handle '{b_name}': {errB}"}

    nA, nB = len(loopA), len(loopB)
    if nA != nB:
        return {"error":
            f"rims have different vertex counts ({nA} vs {nB}) — connect needs 1:1 "
            f"weldable rims. Re-ring one opening to match (edit op=loop_cut / a remesh "
            f"to equalise the loop), then retry."}
    n = nA

    cA = H._centroid(loopA)
    cB = H._centroid(loopB)
    nA_out = H._newell_normal(loopA, cA, Vector(world_center(owner_a)))
    nB_out = H._newell_normal(loopB, cB, Vector(world_center(owner_b)))
    rA = sum((c - cA).length for c in loopA) / n
    rB = sum((c - cB).length for c in loopB) / n

    gap = (cB - cA).length
    if gap < 1e-6:
        return {"error": "the two rim centres coincide — nothing to span"}

    style = (params.get("style") or "arc").strip().lower()
    if style not in _STYLE_TENSION:
        return {"error": f"style '{style}' invalid — use arc | s_curve | direct | slack"}
    tension = params.get("tension", -1.0)
    tension = float(tension if tension is not None else -1.0)
    if tension < 0:
        tension = _STYLE_TENSION[style]
    tension = max(0.0, min(tension, 2.0))
    sections = max(2, min(int(params.get("sections", 12) or 12), 256))
    profile = (params.get("profile") or "match").strip().lower()
    if profile not in ("match", "round"):
        return {"error": f"profile '{profile}' invalid — use match | round"}
    weld = bool(params.get("weld", True))
    cname = (params.get("name") or "connector").strip() or "connector"

    # Bézier control points: leave A along nA_out, arrive at B along -nB_out (so it
    # leaves B along nB_out) — G1 continuity at both seams. tension sets handle length.
    hlen = tension * gap
    P0, P3 = cA, cB
    P1 = cA + nA_out * hlen
    P2 = cB + nB_out * hlen
    path = [_bezier(P0, P1, P2, P3, k / sections) for k in range(sections + 1)]

    # Parallel-transport a frame from A. t0 = initial tangent; u0 seeded from rim A's
    # first vert so the start frame lines up with the rim we're welding to.
    seg0 = path[1] - path[0]
    t0 = seg0.normalized() if seg0.length > 1e-9 else nA_out
    u0 = (loopA[0] - cA)
    u0 = (u0 - t0 * u0.dot(t0))
    u0 = u0.normalized() if u0.length > 1e-9 else t0.orthogonal().normalized()
    v0 = t0.cross(u0).normalized()
    u0 = v0.cross(t0).normalized()

    frames = [(u0, v0)]
    u, v, prev_t = u0, v0, t0
    for k in range(1, sections + 1):
        seg = path[k] - path[k - 1]
        t_k = seg.normalized() if seg.length > 1e-9 else prev_t
        q = prev_t.rotation_difference(t_k)
        u = (q @ u).normalized()
        v = (q @ v).normalized()
        prev_t = t_k
        frames.append((u, v))
    uB, vB = frames[sections]

    # A-profile in the start frame (the rim's own cross-section shape).
    oA = [((c - cA).dot(u0), (c - cA).dot(v0)) for c in loopA]
    # B-profile in the end frame.
    oB = [((c - cB).dot(uB), (c - cB).dot(vB)) for c in loopB]

    # Correspondence (twist + winding): seat A's transported end ring onto B's actual
    # rim by the cyclic shift + direction that minimises the total seam gap. This is
    # the automatic twist that kills the spiral — no hand-tuned twist offset.
    scaleEnd = (rB / rA) if rA > 1e-9 else 1.0
    fr = [path[sections] + uB * (oA[i][0] * scaleEnd) + vB * (oA[i][1] * scaleEnd)
          for i in range(n)]
    best = None
    for d in (1, -1):
        for s in range(n):
            cost = 0.0
            for i in range(n):
                j = (d * i + s) % n
                cost += (fr[i] - loopB[j]).length_squared
            if best is None or cost < best[0]:
                best = (cost, d, s)
    _c, bd, bs = best
    perm = [(bd * i + bs) % n for i in range(n)]
    oBc = [oB[perm[i]] for i in range(n)]

    if profile == "round":
        # Force a clean circle of the matched radius at each column angle (regularises
        # a wobbly rim mid-span; the end rings still weld to the actual rims).
        oA = [(rA * math.cos(math.atan2(ay, ax)), rA * math.sin(math.atan2(ay, ax)))
              for (ax, ay) in oA]
        oBc = [(rB * math.cos(math.atan2(ay, ax)), rB * math.sin(math.atan2(ay, ax)))
               for (ax, ay) in oBc]

    # Build the rings. End rings are the ACTUAL rim verts (exact weld); interior rings
    # blend A→B profile under the transported frame (loft + sweep in one).
    rings = []
    for k in range(sections + 1):
        if k == 0:
            rings.append(list(loopA))
            continue
        if k == sections:
            rings.append([loopB[perm[i]] for i in range(n)])
            continue
        f = k / sections
        u_k, v_k = frames[k]
        ring = []
        for i in range(n):
            ax, ay = oA[i]
            bx, by = oBc[i]
            px = ax + (bx - ax) * f
            py = ay + (by - ay) * f
            ring.append(path[k] + u_k * px + v_k * py)
        rings.append(ring)

    # Quality reads (G65). Centreline metrics + per-seam tangent-vs-normal angle.
    length = sum((path[k + 1] - path[k]).length for k in range(sections))
    max_k = 0.0
    tight_at = 0.0
    cum = 0.0
    for i in range(1, sections):
        a3, b3, c3 = path[i - 1], path[i], path[i + 1]
        ab, bc, ca = (b3 - a3).length, (c3 - b3).length, (a3 - c3).length
        cross = (b3 - a3).cross(c3 - b3)
        denom = ab * bc * ca
        cum += ab
        if denom > 1e-12 and cross.length > 1e-12:
            kk = 4.0 * (cross.length / 2.0) / denom
            if kk > max_k:
                max_k = kk
                tight_at = cum / length if length > 0 else 0.0
    min_bend = (1.0 / max_k) if max_k > 1e-9 else None

    def _ang(x, y):
        d = max(-1.0, min(1.0, x.normalized().dot(y.normalized())))
        return round(math.degrees(math.acos(d)), 1)

    # Seam continuity from the ANALYTIC Bézier endpoint tangents (exact by
    # construction), not the discretised first-segment chord — so arc/slack report ~0°
    # (continuity is built in) and direct reports its real chord-vs-normal deviation.
    launchA = (P1 - P0)
    launchA = launchA if launchA.length > 1e-9 else (cB - cA)
    launchB = (P2 - P3)
    launchB = launchB if launchB.length > 1e-9 else (cA - cB)
    seam_a = _ang(launchA, nA_out)                     # leave-A tangent vs A normal
    seam_b = _ang(launchB, nB_out)                     # leave-B tangent vs B normal
    rim_r = min(rA, rB)
    feasible = (min_bend is None) or (min_bend > rim_r)

    # Materialise the tube as a fresh mesh object (world coords == local; join folds it
    # into the owner's local space, preserving the world-coincident seam verts).
    bm = bmesh.new()
    vmap = []
    for ring in rings:
        vmap.append([bm.verts.new(p) for p in ring])
    for k in range(sections):
        for i in range(n):
            j = (i + 1) % n
            try:
                bm.faces.new((vmap[k][i], vmap[k][j], vmap[k + 1][j], vmap[k + 1][i]))
            except ValueError:
                pass   # duplicate face guard
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(cname)
    bm.to_mesh(me)
    bm.free()
    conn = bpy.data.objects.new(cname, me)
    bpy.context.scene.collection.objects.link(conn)
    conn.select_set(True)
    bpy.context.view_layer.objects.active = conn
    bpy.ops.object.shade_smooth()
    conn_name = conn.name

    out = {
        "success": True, "a": a_name, "b": b_name, "style": style,
        "tension": round(tension, 3), "sections": sections, "profile": profile,
        "sides": n,
        "length_cm": round(length * 100, 2),
        "min_bend_radius_cm": round(min_bend * 100, 2) if min_bend else None,
        "tightest_at": round(tight_at, 2),
        "diam_a_cm": round(rA * 2 * 100, 2), "diam_b_cm": round(rB * 2 * 100, 2),
        "taper": round(scaleEnd, 3),
        "seam_angle_a_deg": seam_a, "seam_angle_b_deg": seam_b,
        "twist_offset": bs, "winding": "same" if bd == 1 else "reversed",
        "sweep_feasible": feasible,
    }
    if not feasible:
        out["warning"] = (f"tightest bend radius {round(min_bend * 100, 2)}cm < rim "
                          f"radius {round(rim_r * 100, 2)}cm — the inner wall may fold "
                          f"through itself. Lower tension or use style=slack.")

    if not weld:
        push_undo(f"connect {a_name} ↔ {b_name} (unwelded)")
        out["connector"] = conn_name
        out["welded"] = False
        return out

    # Weld: join owner(s) + connector, fuse the world-coincident seam verts.
    owners = [owner_a] if owner_a.name == owner_b.name else [owner_a, owner_b]
    bpy.ops.object.select_all(action='DESELECT')
    for o in owners:
        o.select_set(True)
    conn.select_set(True)
    keep = owner_a
    bpy.context.view_layer.objects.active = keep
    consumed = {o.name for o in owners if o.name != keep.name} | {conn_name}
    bpy.ops.object.join()
    result = bpy.context.active_object

    bpy.ops.object.mode_set(mode='EDIT')
    rbm = bmesh.from_edit_mesh(result.data)
    before = len(rbm.verts)
    bmesh.ops.remove_doubles(rbm, verts=list(rbm.verts), dist=1e-4)
    bmesh.update_edit_mesh(result.data)
    rbm = bmesh.from_edit_mesh(result.data)
    after = len(rbm.verts)
    bpy.ops.object.mode_set(mode='OBJECT')

    # G63 — re-home handles whose owner was consumed by the join.
    rehomed = []
    coll = bpy.data.collections.get(H.HANDLES_COLLECTION)
    if coll:
        for h in coll.objects:
            if h.get("bb_handle") and h.get("bb_owner") in consumed:
                h["bb_owner"] = result.name
                rehomed.append(h.name)

    push_undo(f"connect {a_name} ↔ {b_name}")
    out["welded"] = True
    out["result_object"] = result.name
    out["seam_merged"] = before - after
    if rehomed:
        out["rehomed_handles"] = rehomed
    return out


TOOLS = {
    "connect_handles": connect_handles,
}

"""connectors — geometry-bound parametric connectors (SPEC-10).

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

SPEC-10 Phase 4 (editability): a weld=False connector stores its recipe (the two
handles + style/tension/sections/profile) as custom props. `buttons-connector-macro op=reshape
name=<connector>` re-evaluates that recipe against the LIVE handles — deform a pipe
and the connector follows — with an optional `tension` override for "more / less
arc". A welded connector is a COMMIT (the rims are fused into the shell, so there is
nothing live to re-evaluate); reshape it by re-running connect.

Vertex-count match: the exact weld needs both rims at the same vertex count.
`buttons-connector-macro op=resample a=<handle> count=N` resamples a boundary rim to N verts (an
arc-length transition collar), so a 16-vs-32 mismatch is equalised in one call and
connect stays a clean 1:1 weld. Both owners must be meshes (keyed/rigged refused).
The multi-strand expressive tier is SPEC-10 Phase 5, not built here.
"""

import math
import random

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


# ── shared rim resolution (connect + strands both consume this) ───────────────

def _resolve_rim_pair(a_name, b_name):
    """Resolve two boundary handles LIVE into their ordered world rims + geometry.

    Returns (info, None) or (None, error_str). `info` carries loopA/loopB (the ordered
    world loops), cA/cB (centroids), nA_out/nB_out (outward opening normals), rA/rB
    (mean radii), gap, and owner_a/owner_b. Shared by `_compute_connector` (a 1:1
    weld) and `_compute_strands` (N distributed tubes); the equal-vertex-count
    requirement is connect's alone and is NOT enforced here. Owns the mode switch to
    OBJECT (rim reads need it)."""
    ea, eb = H._find_handle(a_name), H._find_handle(b_name)
    if ea is None:
        return None, f"handle '{a_name}' not found (run feel op=assembly to mint rims)"
    if eb is None:
        return None, f"handle '{b_name}' not found (run feel op=assembly to mint rims)"

    owner_a = bpy.data.objects.get(ea.get("bb_owner", ""))
    owner_b = bpy.data.objects.get(eb.get("bb_owner", ""))
    if owner_a is None or owner_a.type != 'MESH':
        return None, f"'{a_name}' owner is gone or not a mesh"
    if owner_b is None or owner_b.type != 'MESH':
        return None, f"'{b_name}' owner is gone or not a mesh"
    for o in (owner_a, owner_b):
        if o.data.shape_keys is not None:
            return None, (f"'{o.name}' has shape keys — this changes topology and would "
                          f"corrupt the keys. Keyed/rigged meshes are out of scope.")

    if bpy.context.active_object is not None and bpy.context.active_object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')

    loopA, _idxA, errA = _ordered_loop(owner_a, ea.get("bb_vgroup", ""))
    if errA:
        return None, f"handle '{a_name}': {errA}"
    loopB, _idxB, errB = _ordered_loop(owner_b, eb.get("bb_vgroup", ""))
    if errB:
        return None, f"handle '{b_name}': {errB}"

    cA = H._centroid(loopA)
    cB = H._centroid(loopB)
    nA_out = H._newell_normal(loopA, cA, Vector(world_center(owner_a)))
    nB_out = H._newell_normal(loopB, cB, Vector(world_center(owner_b)))
    rA = sum((c - cA).length for c in loopA) / len(loopA)
    rB = sum((c - cB).length for c in loopB) / len(loopB)
    gap = (cB - cA).length
    if gap < 1e-6:
        return None, "the two rim centres coincide — nothing to span"

    return {
        "loopA": loopA, "loopB": loopB, "cA": cA, "cB": cB,
        "nA_out": nA_out, "nB_out": nB_out, "rA": rA, "rB": rB, "gap": gap,
        "owner_a": owner_a, "owner_b": owner_b,
    }, None


# ── the swept-connector engine (shared by connect + reshape) ──────────────────

def _compute_connector(a_name, b_name, style, tension, sections, profile):
    """Resolve both handles LIVE and build the connector rings + G65 quality reads.

    Returns (data, None) on success or (None, error_str). `data` carries `rings`
    (the ring-of-rings to materialise), `n` (sides), and every public read field
    plus the private `min_bend`/`rim_r`. Both `connect_handles` (create) and
    `reshape_connector` (re-evaluate) call this — the geometry lives in one place so
    a reshape re-reads the handles' current positions and the tube follows."""
    info, err = _resolve_rim_pair(a_name, b_name)
    if err:
        return None, err
    loopA, loopB = info["loopA"], info["loopB"]

    nA, nB = len(loopA), len(loopB)
    if nA != nB:
        coarser = a_name if nA < nB else b_name
        return None, (
            f"rims have different vertex counts ({nA} vs {nB}) — connect needs 1:1 "
            f"weldable rims. Equalise them first: buttons-connector-macro op=resample a={coarser} "
            f"count={max(nA, nB)} (resamples the coarser rim up to match), then retry.")
    n = nA

    if style not in _STYLE_TENSION:
        return None, f"style '{style}' invalid — use arc | s_curve | direct | slack"
    if profile not in ("match", "round"):
        return None, f"profile '{profile}' invalid — use match | round"
    tension = max(0.0, min(float(tension), 2.0))
    sections = max(2, min(int(sections), 256))

    cA, cB = info["cA"], info["cB"]
    nA_out, nB_out = info["nA_out"], info["nB_out"]
    rA, rB = info["rA"], info["rB"]
    gap = info["gap"]

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

    data = {
        "rings": rings, "n": n,
        "style": style, "tension": tension, "sections": sections, "profile": profile,
        "length_cm": round(length * 100, 2),
        "min_bend_radius_cm": round(min_bend * 100, 2) if min_bend else None,
        "tightest_at": round(tight_at, 2),
        "diam_a_cm": round(rA * 2 * 100, 2), "diam_b_cm": round(rB * 2 * 100, 2),
        "taper": round(scaleEnd, 3),
        "seam_angle_a_deg": seam_a, "seam_angle_b_deg": seam_b,
        "twist_offset": bs, "winding": "same" if bd == 1 else "reversed",
        "sweep_feasible": feasible,
        "min_bend": min_bend, "rim_r": rim_r,
    }
    return data, None


def _rings_to_bmesh(rings, n, matrix=None):
    """Materialise the ring-of-rings into a smooth-shaded bmesh tube. `rings` are
    WORLD points; pass `matrix` (an inverse world transform) to bake them into a
    moved object's local space."""
    bm = bmesh.new()
    vmap = []
    for ring in rings:
        pts = [matrix @ p for p in ring] if matrix is not None else ring
        vmap.append([bm.verts.new(p) for p in pts])
    for k in range(len(rings) - 1):
        for i in range(n):
            j = (i + 1) % n
            try:
                f = bm.faces.new((vmap[k][i], vmap[k][j], vmap[k + 1][j], vmap[k + 1][i]))
                f.smooth = True
            except ValueError:
                pass   # duplicate face guard
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


_READ_KEYS = ("style", "tension", "sections", "profile",
              "length_cm", "min_bend_radius_cm", "tightest_at",
              "diam_a_cm", "diam_b_cm", "taper",
              "seam_angle_a_deg", "seam_angle_b_deg",
              "twist_offset", "winding", "sweep_feasible")


def _public_reads(data):
    """The status fields connect/reshape both surface — selected from `data`."""
    out = {k: data[k] for k in _READ_KEYS}
    out["tension"] = round(data["tension"], 3)
    out["sides"] = data["n"]
    if not data["sweep_feasible"]:
        out["warning"] = (f"tightest bend radius {data['min_bend_radius_cm']}cm < rim "
                          f"radius {round(data['rim_r'] * 100, 2)}cm — the inner wall may "
                          f"fold through itself. Lower tension or use style=slack.")
    return out


# ── the strand engine (SPEC-10 Phase 5 — expressive multi-strand tier) ────────

def _strand_rings(aPt, nA_out, bPt, nB_out, tension, sections, sides, radius, jvec):
    """One strand: a thin `sides`-gon tube from aPt to bPt that LEAVES along nA_out and
    ARRIVES along nB_out (G1, same construction as the single connector), optionally
    bowed by a per-strand `jvec` displacement under a sin² envelope. Returns
    (rings, length, min_bend_radius)."""
    gap = (bPt - aPt).length
    hlen = tension * gap
    P0, P1, P2, P3 = aPt, aPt + nA_out * hlen, bPt + nB_out * hlen, bPt
    path = []
    for k in range(sections + 1):
        t = k / sections
        p = _bezier(P0, P1, P2, P3, t)
        if jvec is not None:
            # sin²(πt) is 0 with zero slope at t=0,1 → endpoints AND launch tangents
            # (the normals) are preserved; the bow lives entirely in the midspan.
            p = p + jvec * (math.sin(math.pi * t) ** 2)
        path.append(p)

    # Parallel-transport a frame down the centreline (min-twist; seed arbitrary — a
    # thin circular tube has no preferred roll).
    seg0 = path[1] - path[0]
    t0 = seg0.normalized() if seg0.length > 1e-9 else nA_out
    u0 = t0.orthogonal().normalized()
    v0 = t0.cross(u0).normalized()
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

    angs = [2.0 * math.pi * s / sides for s in range(sides)]
    rings = []
    for k in range(sections + 1):
        uk, vk = frames[k]
        rings.append([path[k] + (uk * math.cos(a) + vk * math.sin(a)) * radius
                      for a in angs])

    length = sum((path[k + 1] - path[k]).length for k in range(sections))
    max_k = 0.0
    for i in range(1, sections):
        a3, b3, c3 = path[i - 1], path[i], path[i + 1]
        ab, bc, ca = (b3 - a3).length, (c3 - b3).length, (a3 - c3).length
        cross = (b3 - a3).cross(c3 - b3)
        denom = ab * bc * ca
        if denom > 1e-12 and cross.length > 1e-12:
            kk = 4.0 * (cross.length / 2.0) / denom
            if kk > max_k:
                max_k = kk
    min_bend = (1.0 / max_k) if max_k > 1e-9 else None
    return rings, length, min_bend


def _compute_strands(a_name, b_name, count, style, tension, sections,
                     sides, radius, jitter, seed):
    """Build N thin tubes distributed around the two rims — the expressive tier.

    Resolves both handles LIVE (so strands follow a deformed pipe on reshape), samples
    `count` anchor points around each rim by arc length, pairs them by the cyclic
    shift+winding that minimises total strand length (so the bundle fans, never
    crosses), and sweeps each as a `_strand_rings` tube with a seeded coherent jitter.
    Returns (data, None) or (None, error_str)."""
    info, err = _resolve_rim_pair(a_name, b_name)
    if err:
        return None, err
    if style not in _STYLE_TENSION:
        return None, f"style '{style}' invalid — use arc | s_curve | direct | slack"
    count = max(2, min(int(count), 256))
    sides = max(3, min(int(sides), 64))
    sections = max(2, min(int(sections), 256))
    tension = max(0.0, min(float(tension), 2.0))
    jitter = max(0.0, min(float(jitter), 1.0))

    loopA, loopB = info["loopA"], info["loopB"]
    nA_out, nB_out = info["nA_out"], info["nB_out"]
    rA, rB = info["rA"], info["rB"]
    gap = info["gap"]

    ptsA = _resample_polyline_closed(loopA, count)
    ptsB = _resample_polyline_closed(loopB, count)

    best = None
    for d in (1, -1):
        for s in range(count):
            cost = 0.0
            for i in range(count):
                cost += (ptsA[i] - ptsB[(d * i + s) % count]).length_squared
            if best is None or cost < best[0]:
                best = (cost, d, s)
    _c, bd, bs = best
    perm = [(bd * i + bs) % count for i in range(count)]

    # Auto strand radius: pack the tubes around the rim without heavy overlap. Adjacent
    # strand centres sit ~2π·rim_r/count apart; keep each tube under ~0.35 of that.
    rim_r = min(rA, rB)
    if radius is None or radius < 0:
        spacing = (2.0 * math.pi * rim_r) / count
        radius = max(min(0.35 * spacing, 0.45 * rim_r), 0.001)
    else:
        radius = max(float(radius), 1e-4)

    rng = random.Random(int(seed))
    strands, lengths, min_bend = [], [], None
    for i in range(count):
        jvec = None
        if jitter > 1e-9:
            rv = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
            if rv.length > 1e-9:
                jvec = rv.normalized() * (jitter * gap * 0.5)
        rings_i, len_i, bend_i = _strand_rings(
            ptsA[i], nA_out, ptsB[perm[i]], nB_out,
            tension, sections, sides, radius, jvec)
        strands.append(rings_i)
        lengths.append(len_i)
        if bend_i is not None and (min_bend is None or bend_i < min_bend):
            min_bend = bend_i

    feasible = (min_bend is None) or (min_bend > radius)
    data = {
        "strands": strands, "n_strands": count, "sides": sides,
        "style": style, "tension": round(tension, 3), "sections": sections,
        "jitter": round(jitter, 3), "seed": int(seed),
        "strand_radius_cm": round(radius * 100, 2),
        "avg_length_cm": round((sum(lengths) / len(lengths)) * 100, 2),
        "min_bend_radius_cm": round(min_bend * 100, 2) if min_bend else None,
        "diam_a_cm": round(rA * 2 * 100, 2), "diam_b_cm": round(rB * 2 * 100, 2),
        "winding": "same" if bd == 1 else "reversed",
        "sweep_feasible": feasible, "radius": radius,
    }
    return data, None


def _strands_to_bmesh(strands, sides, matrix=None):
    """Materialise N strands (each a list of `sides`-vert rings) into ONE bmesh of
    smooth, end-capped tubes. WORLD points; pass `matrix` (an inverse world transform)
    to bake into a moved object's local space."""
    bm = bmesh.new()
    for rings in strands:
        vmap = []
        for ring in rings:
            pts = [matrix @ p for p in ring] if matrix is not None else ring
            vmap.append([bm.verts.new(p) for p in pts])
        for k in range(len(rings) - 1):
            for i in range(sides):
                j = (i + 1) % sides
                try:
                    f = bm.faces.new((vmap[k][i], vmap[k][j],
                                      vmap[k + 1][j], vmap[k + 1][i]))
                    f.smooth = True
                except ValueError:
                    pass   # duplicate face guard
        for cap in (vmap[0], vmap[-1]):   # close each strand into a solid tube
            try:
                bm.faces.new(cap)
            except ValueError:
                pass
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


_STRAND_READ_KEYS = ("style", "tension", "sections", "n_strands", "sides", "jitter",
                     "seed", "strand_radius_cm", "avg_length_cm", "min_bend_radius_cm",
                     "diam_a_cm", "diam_b_cm", "winding", "sweep_feasible")


def _public_strand_reads(data):
    """The status fields strands/reshape both surface — selected from `data`."""
    out = {k: data[k] for k in _STRAND_READ_KEYS}
    if not data["sweep_feasible"]:
        out["warning"] = (
            f"tightest strand bend radius {data['min_bend_radius_cm']}cm < strand radius "
            f"{data['strand_radius_cm']}cm — a strand may fold through itself. Lower "
            f"tension/jitter or use style=slack.")
    return out


# ── op=strands (SPEC-10 Phase 5) ──────────────────────────────────────────────

def make_strands(params):
    """buttons-connector-macro op=strands — generate N thin tubes between two rims (SPEC-10 Phase 5).

    The expressive tier: "a sequence of crazy curves" as cheap relational generation,
    not K hand-placed Béziers. Distributes `count` strands around the two openings,
    each leaving along the opening's normal (G1, like the single connector), with a
    seeded coherent `jitter` bowing each one differently → variety from a count + a
    seed. Emitted as ONE editable mesh object (capped tubes); stores its recipe, so
    buttons-connector-macro op=reshape re-bakes the whole bundle against the LIVE handles.

    a, b:     the two boundary handles to span (mint with feel op=assembly).
    count:    number of strands (>=2).
    style:    arc (default) | s_curve | direct | slack — same gesture vocabulary as
              connect (arc/s_curve/slack leave each rim along its normal).
    tension:  0..1 how much each strand bows; -1 (default) = the style's default.
    sections: rings along each strand. Default 24.
    sides:    cross-section verts per strand (thin tube). Default 8.
    jitter:   0..1 coherent midspan waywardness — 0 = a clean parallel fan, higher =
              each strand bows its own way (endpoints + launch normals stay fixed).
    seed:     RNG seed — same seed reproduces the same bundle.
    radius:   strand tube radius (m); -1 (default) = auto-pack to the rim + count.
    name:     name for the strands object (default 'strands').
    """
    a_name = (params.get("a") or "").strip()
    b_name = (params.get("b") or "").strip()
    if not a_name or not b_name:
        return {"error": "buttons-connector-macro op=strands needs a=<handle> and b=<handle> "
                         "(mint boundary handles with feel op=assembly)"}
    if a_name == b_name:
        return {"error": "a and b are the same handle — strands needs two distinct rims"}
    count = int(params.get("count", 0) or 0)
    if count < 2:
        return {"error": "count must be >=2 (the number of strands to generate)"}

    style = (params.get("style") or "arc").strip().lower()
    tension = params.get("tension", -1.0)
    tension = float(tension if tension is not None else -1.0)
    if tension < 0:
        tension = _STYLE_TENSION.get(style, 0.55)
    sections = int(params.get("sections", 24) or 24)
    sides = int(params.get("sides", 8) or 8)
    jitter = float(params.get("jitter", 0.0) or 0.0)
    seed = int(params.get("seed", 0) or 0)
    radius = params.get("radius", -1.0)
    radius = float(radius if radius is not None else -1.0)
    cname = (params.get("name") or "strands").strip() or "strands"

    data, err = _compute_strands(a_name, b_name, count, style, tension, sections,
                                 sides, radius, jitter, seed)
    if err:
        return {"error": err}

    bm = _strands_to_bmesh(data["strands"], data["sides"])
    me = bpy.data.meshes.new(cname)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(cname, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    oname = obj.name

    # Recipe → buttons-connector-macro op=reshape re-evaluates the bundle against the live handles.
    obj["bb_strands"] = True
    obj["bb_conn_a"] = a_name
    obj["bb_conn_b"] = b_name
    obj["bb_conn_style"] = data["style"]
    obj["bb_conn_tension"] = data["tension"]
    obj["bb_conn_sections"] = data["sections"]
    obj["bb_strand_count"] = data["n_strands"]
    obj["bb_strand_sides"] = data["sides"]
    obj["bb_strand_jitter"] = data["jitter"]
    obj["bb_strand_seed"] = data["seed"]
    obj["bb_strand_radius"] = data["radius"]

    push_undo(f"strands {a_name} ↔ {b_name} ×{count}")
    out = {"success": True, "a": a_name, "b": b_name, "object": oname}
    out.update(_public_strand_reads(data))
    return out


# ── op=connect ─────────────────────────────────────────────────────────────────

def connect_handles(params):
    """edit op=connect — weld two open boundary rims with a swept tangent-continuous
    tube (SPEC-10). See module docstring. Consumes two boundary handles (mint with
    feel op=assembly), not coordinates.

    a, b:     the two boundary handles to connect (order-independent for the weld).
    style:    arc (default) | s_curve | direct | slack. arc/s_curve/slack leave each
              opening along its OUTWARD NORMAL (G1 continuity); direct relaxes toward
              the straight chord.
    tension:  0..1 — control-handle length as a fraction of the gap ("how much it
              bows"). -1 (default) = the style's default.
    sections: length resolution (rings along the span). Default 12.
    profile:  match (default — sweep each rim's own cross-section, tapering between) |
              round (force a clean circle of the matched radius mid-span).
    weld:     fuse both ends into the owning shell(s) → one watertight manifold
              (default True). False leaves the connector as a separate, EDITABLE mesh
              object (stores its recipe → buttons-connector-macro op=reshape).
    name:     name for the connector object (default 'connector'; shows on weld=False).
    """
    a_name = (params.get("a") or "").strip()
    b_name = (params.get("b") or "").strip()
    if not a_name or not b_name:
        return {"error": "edit op=connect needs a=<handle> and b=<handle> "
                         "(mint boundary handles with feel op=assembly)"}
    if a_name == b_name:
        return {"error": "a and b are the same handle — connect needs two distinct rims"}

    style = (params.get("style") or "arc").strip().lower()
    tension = params.get("tension", -1.0)
    tension = float(tension if tension is not None else -1.0)
    if tension < 0:
        tension = _STYLE_TENSION.get(style, 0.55)
    sections = int(params.get("sections", 12) or 12)
    profile = (params.get("profile") or "match").strip().lower()
    weld = bool(params.get("weld", True))
    cname = (params.get("name") or "connector").strip() or "connector"

    data, err = _compute_connector(a_name, b_name, style, tension, sections, profile)
    if err:
        return {"error": err}

    n = data["n"]
    bm = _rings_to_bmesh(data["rings"], n)
    me = bpy.data.meshes.new(cname)
    bm.to_mesh(me)
    bm.free()
    conn = bpy.data.objects.new(cname, me)
    bpy.context.scene.collection.objects.link(conn)
    conn.select_set(True)
    bpy.context.view_layer.objects.active = conn
    conn_name = conn.name

    out = {"success": True, "a": a_name, "b": b_name}
    out.update(_public_reads(data))

    if not weld:
        # SPEC-10 Phase 4 — store the recipe so the connector is re-evaluable against
        # the live handles (buttons-connector-macro op=reshape).
        conn["bb_connector"] = True
        conn["bb_conn_a"] = a_name
        conn["bb_conn_b"] = b_name
        conn["bb_conn_style"] = data["style"]
        conn["bb_conn_tension"] = data["tension"]
        conn["bb_conn_sections"] = data["sections"]
        conn["bb_conn_profile"] = data["profile"]
        push_undo(f"connect {a_name} ↔ {b_name} (unwelded)")
        out["connector"] = conn_name
        out["welded"] = False
        return out

    # Weld: join owner(s) + connector, fuse the world-coincident seam verts.
    ea, eb = H._find_handle(a_name), H._find_handle(b_name)
    owner_a = bpy.data.objects.get(ea.get("bb_owner", ""))
    owner_b = bpy.data.objects.get(eb.get("bb_owner", ""))
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


# ── op=reshape (SPEC-10 Phase 4) ──────────────────────────────────────────────

def reshape_connector(params):
    """buttons-connector-macro op=reshape — re-evaluate an UNWELDED connector against its live handles.

    The connector stored its recipe at create time (the two handles + style/tension/
    sections/profile). reshape re-reads the handles' CURRENT positions and re-bakes
    the tube in place, so deforming/moving a pipe drags the connector with it. The one
    editable knob is `tension` (more / less arc); -1 keeps the stored value.

    Welded connectors are committed (the rims are fused into the shell) and carry no
    recipe — re-run edit op=connect to reshape them.

    name:    the connector object to re-evaluate.
    tension: 0..1 override ("more / less arc"); -1 (default) keeps the stored value.
    """
    name = (params.get("name") or "").strip()
    if not name:
        return {"error": "buttons-connector-macro op=reshape needs name=<connector> (an unwelded connector)"}
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"object '{name}' not found"}
    if obj.get("bb_strands"):
        return _reshape_strands(obj, params)
    if not obj.get("bb_connector"):
        return {"error": f"'{name}' is not an editable connector. Welded connectors are "
                         f"committed (the rims are fused) — re-run edit op=connect to "
                         f"reshape. Only weld=False connectors store an editable recipe."}

    a = obj.get("bb_conn_a", "")
    b = obj.get("bb_conn_b", "")
    if not a or not b:
        return {"error": f"'{name}' has an incomplete recipe (missing handle binding) — "
                         f"re-create it with edit op=connect"}
    style = obj.get("bb_conn_style", "arc")
    sections = int(obj.get("bb_conn_sections", 12) or 12)
    profile = obj.get("bb_conn_profile", "match")

    t = params.get("tension", -1.0)
    t = float(t if t is not None else -1.0)
    tension = t if t >= 0 else float(obj.get("bb_conn_tension",
                                             _STYLE_TENSION.get(style, 0.55)))

    if bpy.context.active_object is not None and bpy.context.active_object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')

    data, err = _compute_connector(a, b, style, tension, sections, profile)
    if err:
        return {"error": f"reshape '{name}': {err}"}

    bm = _rings_to_bmesh(data["rings"], data["n"], matrix=obj.matrix_world.inverted())
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    obj["bb_conn_tension"] = data["tension"]

    push_undo(f"reshape {name}")
    out = {"success": True, "reshaped": True, "name": name, "a": a, "b": b}
    out.update(_public_reads(data))
    return out


def _reshape_strands(obj, params):
    """buttons-connector-macro op=reshape on a strands object — re-bake the whole bundle against its live
    handles (same recipe-replay contract as the single connector). The stored seed keeps
    the bundle identical apart from the handles' motion; `tension` overrides the bow."""
    a = obj.get("bb_conn_a", "")
    b = obj.get("bb_conn_b", "")
    if not a or not b:
        return {"error": f"'{obj.name}' has an incomplete strands recipe (missing handle "
                         f"binding) — re-create it with buttons-connector-macro op=strands"}
    style = obj.get("bb_conn_style", "arc")
    sections = int(obj.get("bb_conn_sections", 24) or 24)
    count = int(obj.get("bb_strand_count", 6) or 6)
    sides = int(obj.get("bb_strand_sides", 8) or 8)
    jitter = float(obj.get("bb_strand_jitter", 0.0) or 0.0)
    seed = int(obj.get("bb_strand_seed", 0) or 0)
    radius = float(obj.get("bb_strand_radius", -1.0))   # concrete value stored at create

    t = params.get("tension", -1.0)
    t = float(t if t is not None else -1.0)
    tension = t if t >= 0 else float(obj.get("bb_conn_tension",
                                             _STYLE_TENSION.get(style, 0.55)))

    if bpy.context.active_object is not None and bpy.context.active_object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')

    data, err = _compute_strands(a, b, count, style, tension, sections,
                                 sides, radius, jitter, seed)
    if err:
        return {"error": f"reshape '{obj.name}': {err}"}

    bm = _strands_to_bmesh(data["strands"], data["sides"],
                           matrix=obj.matrix_world.inverted())
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    obj["bb_conn_tension"] = data["tension"]

    push_undo(f"reshape {obj.name}")
    out = {"success": True, "reshaped": True, "kind": "strands",
           "name": obj.name, "a": a, "b": b}
    out.update(_public_strand_reads(data))
    return out


# ── op=resample — equalise a rim's vertex count (lifts the connect 1:1 limit) ──

def _resample_polyline_closed(pts, count):
    """Arc-length-equidistant resample of a CLOSED polyline to `count` points. The
    first sample lands on pts[0] (keeps the new rim's winding aligned to the old)."""
    m = len(pts)
    seg = [(pts[(i + 1) % m] - pts[i]).length for i in range(m)]
    total = sum(seg)
    if total < 1e-9:
        return [pts[i % m].copy() for i in range(count)]
    cum = [0.0]
    for s in seg:
        cum.append(cum[-1] + s)            # cum[m] == total
    out = []
    for k in range(count):
        target = (k / count) * total
        i = 0
        while i < m and cum[i + 1] <= target:
            i += 1
        if i >= m:
            i = m - 1
        seglen = seg[i] if seg[i] > 1e-12 else 1.0
        f = (target - cum[i]) / seglen
        out.append(pts[i].lerp(pts[(i + 1) % m], f))
    return out


def resample_loop(params):
    """buttons-connector-macro op=resample — resample a boundary rim to a target vertex count.

    Builds a short arc-length transition collar from the rim out to a fresh `count`-
    vert loop and re-homes the handle onto it, so two rims that didn't match (e.g.
    16 vs 32) can be equalised in one call and edit op=connect stays a clean 1:1 weld.
    The handle is re-baselined (its vert count changes), so it reads clean afterward.

    a:      the boundary handle whose rim to resample (mint with feel op=assembly).
    count:  target vertex count (>=3).
    depth:  collar length along the rim's outward normal (m); -1 = auto (~5% of the
            rim radius). The collar extends the opening by this much; the new rim
            keeps the opening's diameter.
    """
    hname = (params.get("a") or params.get("handle") or "").strip()
    if not hname:
        return {"error": "buttons-connector-macro op=resample needs a=<boundary handle> and count=N"}
    count = int(params.get("count", 0) or 0)
    if count < 3:
        return {"error": "count must be >=3 (the target vertex count for the rim)"}

    e = H._find_handle(hname)
    if e is None:
        return {"error": f"handle '{hname}' not found (run feel op=assembly to mint rims)"}
    owner = bpy.data.objects.get(e.get("bb_owner", ""))
    if owner is None or owner.type != 'MESH':
        return {"error": f"'{hname}' owner is gone or not a mesh"}
    if owner.data.shape_keys is not None:
        return {"error": f"'{owner.name}' has shape keys — resample changes topology and "
                         f"would corrupt the keys. Keyed/rigged meshes are out of scope."}

    if bpy.context.active_object is not None and bpy.context.active_object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')

    vgname = e.get("bb_vgroup", "")
    loop, idx, err = _ordered_loop(owner, vgname)
    if err:
        return {"error": f"handle '{hname}': {err}"}
    m = len(loop)
    if count == m:
        return {"success": True, "handle": hname, "owner": owner.name,
                "from_count": m, "to_count": m, "noop": True}

    cen = H._centroid(loop)
    nrm = H._newell_normal(loop, cen, Vector(world_center(owner)))
    rim_r = sum((c - cen).length for c in loop) / m

    depth = params.get("depth", -1.0)
    depth = float(depth if depth is not None else -1.0)
    if depth < 0:
        depth = max(0.05 * rim_r, 0.005)

    new_world = [p + nrm * depth for p in _resample_polyline_closed(loop, count)]

    mw = owner.matrix_world
    mwi = mw.inverted()
    bm = bmesh.new()
    bm.from_mesh(owner.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    # The old rim's open-boundary edges (one adjacent face) along the walked cycle.
    needed = {frozenset((idx[a], idx[(a + 1) % m])) for a in range(m)}
    old_edges = [ed for ed in bm.edges
                 if len(ed.link_faces) == 1
                 and frozenset((ed.verts[0].index, ed.verts[1].index)) in needed]

    new_verts = [bm.verts.new(mwi @ p) for p in new_world]
    new_edges = [bm.edges.new((new_verts[a], new_verts[(a + 1) % count]))
                 for a in range(count)]

    bridged = bmesh.ops.bridge_loops(bm, edges=old_edges + new_edges)
    for f in bridged.get("faces", []):
        f.smooth = True
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.index_update()
    new_idx = [v.index for v in new_verts]
    new_local = [v.co.copy() for v in new_verts]
    bm.to_mesh(owner.data)
    bm.free()
    owner.data.update()

    # Re-home the handle onto the new rim (the old verts are now interior).
    g = owner.vertex_groups.get(vgname)
    if g is not None:
        g.remove(list(idx))
        g.add(new_idx, 1.0, 'REPLACE')

    # Re-baseline: the vert count changed, so a stale snapshot would read orphaned.
    new_world_cos = [mw @ c for c in new_local]
    new_cen = H._centroid(new_world_cos)
    new_nrm = H._newell_normal(new_world_cos, new_cen, Vector(world_center(owner)))
    H._snapshot_provenance(e, new_cen, new_nrm, new_world_cos, count, hname)
    if not e.get("bb_vertex_parent"):
        e.location = new_cen
    e.rotation_euler = new_nrm.to_track_quat('Z', 'Y').to_euler()

    push_undo(f"resample {hname} {m}→{count}")
    return {"success": True, "handle": hname, "owner": owner.name,
            "from_count": m, "to_count": count,
            "depth_cm": round(depth * 100, 2), "rim_diam_cm": round(rim_r * 2 * 100, 2)}


TOOLS = {
    "connect_handles": connect_handles,
    "reshape_connector": reshape_connector,
    "resample_loop": resample_loop,
    "make_strands": make_strands,
}

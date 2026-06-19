"""
Rung 5 — test the CORRESPONDENCE SOLVER itself, on known geometry.

Rung 0 proved triangulation works when the correspondence is HANDED to it.
This rung removes that gift: build a known head-like quad grid, project it to
front/side, throw the correspondence away (shuffle node ids, MERGE nodes that
collapse on top of each other in a view — exactly what image extraction yields),
and see whether a solver can re-pair front<->side vertices well enough to
reconstruct the real depth (nose poking out, sockets receding).

Why this is the make-or-break test for the whole idea:
  - The pipeline rests on matching vertices across views. If that can't be done
    from graph + geometry alone, no amount of clean detection saves us.
  - It also exposes a STRUCTURAL limit: a symmetric head seen front + ONE side
    folds left onto right in the side view. We measure what that costs and what
    it takes to fix (a symmetry-breaking 3/4 view), so we know which images to
    generate BEFORE generating them.

Solver (front + one side), per height-row (rows share Z, which both views see):
  - front gives each vertex its X and the row's symmetry center -> rank by
    distance-from-center (0 = centerline, outward).
  - side gives the row's depth values; sort frontmost-first -> rank.
  - pair by rank. This is the convex-face assumption: frontmost = centerline.
    Left/right twins get the same Y (correct — they ARE the same depth).
Then 3D = (X from front, Y from side-by-rank, Z shared). Compare to truth.

No image files involved — this is the algorithm in a vacuum.
"""

import numpy as np

R, C = 27, 21                       # grid rows (height) x cols (left-right)
W, HGT, DMAX = 1.0, 2.0, 0.7        # half-width, height, base forward depth


def make_head(cheekbones=False):
    """Known quad-grid 'head' patch. Returns truth verts (N,3) and grid edges."""
    u = np.linspace(-1, 1, C)       # left .. right
    v = np.linspace(0, 1, R)        # bottom .. top
    V = np.zeros((R, C, 3))
    for i in range(R):
        for j in range(C):
            uu, vv = u[j], v[i]
            x = W * uu
            z = HGT * vv
            # convex base bulge, tapered top & bottom
            y = DMAX * np.sqrt(max(0.0, 1 - uu * uu)) * (0.55 + 0.45 * np.sin(np.pi * vv))
            # nose: forward spike on the centerline, mid-height
            y += 0.45 * np.exp(-(uu / 0.12) ** 2) * np.exp(-((vv - 0.45) / 0.09) ** 2)
            # eye sockets: paired recesses off-centerline, just above nose
            y -= 0.18 * np.exp(-((abs(uu) - 0.34) / 0.10) ** 2) * np.exp(-((vv - 0.60) / 0.07) ** 2)
            if cheekbones:
                # cheekbones: paired forward bulges OFF the centerline -> the
                # frontmost point of the row is no longer the centre. This is
                # the convex assumption's killer.
                y += 0.30 * np.exp(-((abs(uu) - 0.45) / 0.11) ** 2) * np.exp(-((vv - 0.42) / 0.10) ** 2)
            V[i, j] = (x, y, z)
    edges = []
    for i in range(R):
        for j in range(C):
            if j + 1 < C:
                edges.append((i * C + j, i * C + j + 1))
            if i + 1 < R:
                edges.append((i * C + j, (i + 1) * C + j))
    return V.reshape(-1, 3), edges


def view_graph(V3, axes, seed, merge_eps=0.012, _theta=None):
    """Project to a 2D view, shuffle node ids, and MERGE nodes that land within
    merge_eps (simulating image extraction: coincident dots become one node).
    axes=(a,b) picks world axes; _theta (radians) instead gives a 3/4 view
    rotated about the vertical (x'=X cos-Y sin, vertical=Z).
    Returns: nodes2d, truth->node map (for scoring only)."""
    if _theta is not None:
        xp = V3[:, 0] * np.cos(_theta) - V3[:, 1] * np.sin(_theta)
        P = np.column_stack([xp, V3[:, 2]])
    else:
        P = V3[:, list(axes)]
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(P))
    nodes, truth2node = [], np.full(len(P), -1)
    for orig in order:
        p = P[orig]
        hit = next((k for k, q in enumerate(nodes) if np.hypot(*(p - q)) < merge_eps), None)
        if hit is None:
            hit = len(nodes)
            nodes.append(p)
        truth2node[orig] = hit
    return np.array(nodes), truth2node


def rows_by_z(P, n_rows):
    """Cluster a view's nodes into height-rows by Z (the shared axis). Returns
    list of node-index arrays, ordered bottom->top."""
    z = P[:, 1]
    edges = np.linspace(z.min() - 1e-6, z.max() + 1e-6, n_rows + 1)
    rows = []
    for k in range(n_rows):
        idx = np.where((z >= edges[k]) & (z < edges[k + 1]))[0]
        if len(idx):
            rows.append(idx)
    return rows


def reconstruct_front_side(front, side):
    """Pair front<->side per row by rank-from-center (front) / frontmost (side).
    Returns reconstructed (N,3) aligned to FRONT node order."""
    fr = rows_by_z(front, R)
    sr = rows_by_z(side, R)
    fr.sort(key=lambda ix: front[ix, 1].mean())
    sr.sort(key=lambda ix: side[ix, 1].mean())
    out = np.full((len(front), 3), np.nan)
    for fidx, sidx in zip(fr, sr):
        xc = np.median(front[fidx, 0])                 # row symmetry centre (front)
        rank_f = np.argsort(np.abs(front[fidx, 0] - xc))   # 0=centre outward
        depth_sorted = np.sort(side[sidx, 0])[::-1]        # frontmost first
        for r, fi in enumerate(fidx[rank_f]):
            ring = (r + 1) // 2     # ring 0 = centre (1 node); each ring out = a twin pair
            y = depth_sorted[min(ring, len(depth_sorted) - 1)]
            out[fi] = (front[fi, 0], y, front[fi, 1])
    return out


def pair_front_q34(front, q34):
    """Match front<->q34 vertices by height-row then left->right order. This is
    ANGLE-FREE: it needs no theta, because both views order the same way in X.
    Returns list of (front_idx, q34_idx) pairs."""
    fr = rows_by_z(front, R)
    qr = rows_by_z(q34, R)
    fr.sort(key=lambda ix: front[ix, 1].mean())
    qr.sort(key=lambda ix: q34[ix, 1].mean())
    pairs = []
    for fidx, qidx in zip(fr, qr):
        if len(fidx) != len(qidx):
            continue                                  # row count mismatch -> skip
        fo = fidx[np.argsort(front[fidx, 0])]
        qo = qidx[np.argsort(q34[qidx, 0])]
        pairs.extend(zip(fo.tolist(), qo.tolist()))
    return pairs


def reconstruct_front_q34(front, q34, theta, pairs=None):
    """Front + a 3/4 view rotated by theta. With per-vertex pairs known, solve:
        x' = X*cos(theta) - Y*sin(theta)  ->  Y = (X*cos(theta) - x') / sin(theta)
    """
    if pairs is None:
        pairs = pair_front_q34(front, q34)
    ct, st = np.cos(theta), np.sin(theta)
    out = np.full((len(front), 3), np.nan)
    for fi, qi in pairs:
        X = front[fi, 0]
        out[fi] = (X, (X * ct - q34[qi, 0]) / st, front[fi, 1])
    return out


def estimate_theta(front, q34, side, pairs):
    """Recover the unknown 3/4 angle from the data using the CENTERLINE, the one
    thing the side view reports reliably (frontmost-per-row = facial profile).
    For a centerline vertex:  x' = X*cos(t) - Y*sin(t), with X~0 and Y from the
    side profile. Stack rows -> least-squares for (cos t, sin t)."""
    f2q = dict(pairs)
    fr = rows_by_z(front, R); fr.sort(key=lambda ix: front[ix, 1].mean())
    sr = rows_by_z(side, R);  sr.sort(key=lambda ix: side[ix, 1].mean())
    X, Yc, xp = [], [], []
    for fidx, sidx in zip(fr, sr):
        xc = np.median(front[fidx, 0])
        fi = fidx[np.argmin(np.abs(front[fidx, 0] - xc))]   # centerline front node
        if fi not in f2q:
            continue
        X.append(front[fi, 0]); Yc.append(side[sidx, 0].max()); xp.append(q34[f2q[fi], 0])
    X, Yc, xp = np.array(X), np.array(Yc), np.array(xp)
    # 1-D search: centerline obeys x' = X cos(t) - Yc sin(t). (X~0 constrains
    # only sin(t), so a 2-param fit degenerates; search t directly.)
    ts = np.radians(np.arange(10, 61, 0.5))
    res = [(np.sum((X * np.cos(t) - Yc * np.sin(t) - xp) ** 2), t) for t in ts]
    return np.degrees(min(res)[1])


def score(name, Vtrue, front, truth2front, recon):
    """Map reconstruction (front-node order) back to truth verts and measure."""
    err = []
    for orig in range(len(Vtrue)):
        fn = truth2front[orig]
        if not np.isnan(recon[fn, 1]):
            err.append(abs(recon[fn, 1] - Vtrue[orig, 1]))
    err = np.array(err)
    depth_span = Vtrue[:, 1].max() - Vtrue[:, 1].min()
    print(f"  {name:18s}  depth-RMS {err.std():.4f}  mean|dY| {err.mean():.4f}"
          f"  worst {err.max():.4f}   (span {depth_span:.3f}, "
          f"= {100*err.mean()/depth_span:.1f}% mean)")
    return err.mean() / depth_span


def run(cheekbones):
    label = "WITH cheekbones (non-convex rows)" if cheekbones else "convex face"
    print("=" * 70)
    print(f"RUNG 5: correspondence solver — {label}")
    print("=" * 70)
    Vtrue, _ = make_head(cheekbones)

    fnodes, t2f = view_graph(Vtrue, (0, 2), seed=1)   # front (X,Z)
    snodes, _ = view_graph(Vtrue, (1, 2), seed=2)     # side  (Y,Z)
    print(f"  truth verts {len(Vtrue)}   front nodes {len(fnodes)}   "
          f"side nodes {len(snodes)}  (side collapse "
          f"{100*(1-len(snodes)/len(Vtrue)):.0f}% — left/right fold)")

    recon = reconstruct_front_side(fnodes, snodes)
    score("front+side", Vtrue, fnodes, t2f, recon)

    theta = np.radians(35)
    qnodes, t2q = view_graph(Vtrue, None, seed=3, _theta=theta)  # 3/4 view
    print(f"  3/4 view ({np.degrees(theta):.0f} deg): {len(qnodes)} nodes "
          f"(collapse {100*(1-len(qnodes)/len(Vtrue)):.0f}% — symmetry broken)")
    recon_q = reconstruct_front_q34(fnodes, qnodes, theta)
    score("front+3/4", Vtrue, fnodes, t2f, recon_q)

    if not cheekbones:   # how wrong can the ASSUMED angle be? (Grok won't hit 35 exactly)
        for off in (-10, -5, 5, 10):
            rq = reconstruct_front_q34(fnodes, qnodes, theta + np.radians(off))
            score(f"front+3/4 {off:+d}deg", Vtrue, fnodes, t2f, rq)
        pairs = pair_front_q34(fnodes, qnodes)
        est = estimate_theta(fnodes, qnodes, snodes, pairs)   # recover angle from data
        rq = reconstruct_front_q34(fnodes, qnodes, np.radians(est), pairs)
        print(f"  -- angle recovered from data (true 35): {est:.1f} deg --")
        score("front+side+3/4", Vtrue, fnodes, t2f, rq)
    print("=" * 70)


if __name__ == "__main__":
    run(cheekbones=False)
    run(cheekbones=True)

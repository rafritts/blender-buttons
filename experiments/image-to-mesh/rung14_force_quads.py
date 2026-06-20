"""
Rung 14 — force interior vertices to valence 4, no triangles.

Directive: boundary vertices may be any valence; every INTERIOR vertex MUST have
4 edges; no triangles. Mechanism = nearest-neighbour fill (ink-beam preferred,
literal-nearest fallback).

The reconciliation (why force-4 doesn't fight no-tris): an edge is only added
between vertices that share NO common neighbour. A legit missing quad-side joins
two corners with no shared neighbour; a DIAGONAL joins two corners that share two
neighbours — and a diagonal IS two triangles. So the no-shared-neighbour gate
forbids diagonals and tris while still letting us force valence up. Plus a
no-crossing gate (planarity).

Boundary vs interior, by INK: a vertex with a wide angular gap in its edges is
either on a rim or under-extracted. If there's ink across the gap -> a wire we
missed -> interior, fill it. If the gap is empty -> true boundary -> leave open.

Run:  uv run --with numpy --with opencv-python --with scipy --with scikit-image \
        python rung14_force_quads.py v3_front.jpg v3_side.jpg
"""

import sys
import numpy as np
import cv2
from collections import defaultdict
from scipy.spatial import cKDTree

from rung9_trace import detect, extract, chord_eval
from rung10_mesh_from_graph import faces_from_graph
from rung12_close_quads import close_quads, _seg_cross
from rung13_mirror import symmetry_axis, pair_twins, mirror_edges, write_obj
from rung7_reconstruct import head_mask


def build_adj(edges, n):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return adj


def de_triangulate(V, edges, dt):
    """Remove triangles by dropping each tri's worst-on-ink edge, until none."""
    edges = set(edges)
    while True:
        adj = build_adj(edges, len(V))
        tri = None
        for a, b in edges:
            common = adj[a] & adj[b]
            if common:
                c = next(iter(common))
                tri = (a, b, c)
                break
        if tri is None:
            break
        a, b, c = tri
        worst, wkey = -1.0, None
        for (i, j) in ((a, b), (b, c), (c, a)):
            _, med = chord_eval(dt, V[i][0], V[i][1], V[j][0], V[j][1])
            if med > worst:
                worst, wkey = med, (min(i, j), max(i, j))
        edges.discard(wkey)
    return edges


def gaps(V, i, adj):
    """Sorted edge angles and the circular gaps between them (radians)."""
    if not adj[i]:
        return [], [2 * np.pi]
    ang = sorted(np.arctan2(V[j][0] - V[i][0], V[j][1] - V[i][1]) for j in adj[i])
    g = [(ang[(k + 1) % len(ang)] - ang[k]) % (2 * np.pi) for k in range(len(ang))]
    return ang, g


def ink_in_arc(dt, V, i, a0, a1, r, tol=1.6, n=24):
    """Fraction of the arc (a0->a1 CCW) at radius r that sits on ink."""
    span = (a1 - a0) % (2 * np.pi)
    ts = a0 + np.linspace(0.15, 0.85, n) * span
    yy = np.clip((V[i][0] + r * np.sin(ts)).astype(int), 0, dt.shape[0] - 1)
    xx = np.clip((V[i][1] + r * np.cos(ts)).astype(int), 0, dt.shape[1] - 1)
    return float((dt[yy, xx] <= tol).mean())


def classify_boundary(V, edges, dt, nn, big_gap=np.radians(130)):
    adj = build_adj(edges, len(V))
    boundary = np.zeros(len(V), bool)
    for i in range(len(V)):
        ang, g = gaps(V, i, adj)
        if not ang:
            boundary[i] = True
            continue
        k = int(np.argmax(g))
        if g[k] >= big_gap:
            a0 = ang[k]
            ink = ink_in_arc(dt, V, i, a0, a0 + g[k], 0.7 * nn[i])
            if ink < 0.25:                       # empty gap -> true boundary
                boundary[i] = True
    return boundary


def force_quads(V, edges, dt, boundary, nn):
    edges = set(edges)
    tree = cKDTree(V)

    def crosses(a, d, elist):
        for (x, y) in elist:
            if x in (a, d) or y in (a, d):
                continue
            if _seg_cross(V[a], V[d], V[x], V[y]):
                return True
        return False

    forced_on, forced_off = [], []
    progress = True
    while progress:
        progress = False
        adj = build_adj(edges, len(V))
        elist = list(edges)
        order = sorted((i for i in range(len(V)) if not boundary[i]),
                       key=lambda i: len(adj[i]))
        for i in order:
            if len(adj[i]) >= 4:
                continue
            ang, g = gaps(V, i, adj)
            if ang:
                k = int(np.argmax(g))
                gap_lo, gap_hi = ang[k], ang[k] + g[k]
            else:
                gap_lo, gap_hi = -np.pi, np.pi
            # candidate dots within the largest gap, near, no shared neighbour
            cands = []
            for j in tree.query_ball_point(V[i], 2.4 * nn[i]):
                if j == i or j in adj[i]:
                    continue
                d = np.hypot(*(V[j] - V[i]))
                if d < 0.4 * nn[i]:
                    continue
                a = np.arctan2(V[j][0] - V[i][0], V[j][1] - V[i][1])
                if not (0 <= (a - gap_lo) % (2 * np.pi) <= g[k] if ang else True):
                    continue
                if adj[i] & adj[j]:              # shared neighbour -> diagonal/tri
                    continue
                if crosses(i, j, elist):
                    continue
                ok, med = chord_eval(dt, V[i][0], V[i][1], V[j][0], V[j][1])
                cands.append((0 if ok else 1, d, j, ok))   # ink-beam first
            if not cands:
                continue
            cands.sort()
            _, _, j, ok = cands[0]
            edges.add((min(i, j), max(i, j)))
            (forced_on if ok else forced_off).append((min(i, j), max(i, j)))
            progress = True
    return edges, forced_on, forced_off


def main(front="v3_front.jpg", side="v3_side.jpg", out="head_v9.obj"):
    im, V, ink, dt = detect(front)
    edges, valence, sp = extract(im, V, dt)
    base = set(edges.keys())
    cq_on, _ = close_quads(V, base, dt)
    x0 = symmetry_axis(V)
    twin = pair_twins(V, x0)
    m_on, _ = mirror_edges(V, base, twin, dt)
    g0 = base | set(cq_on) | set(m_on)
    nn = cKDTree(V).query(V, k=2)[0][:, 1]

    g1 = de_triangulate(V, g0, dt)
    boundary = classify_boundary(V, g1, dt, nn)
    g2, f_on, f_off = force_quads(V, g1, dt, boundary, nn)

    def report(E, label):
        f = faces_from_graph(V, E)
        from collections import Counter
        c = Counter(len(x) for x in f)
        adj = build_adj(E, len(V))
        interior = [i for i in range(len(V)) if not boundary[i]]
        v4 = sum(len(adj[i]) == 4 for i in interior)
        print(f"  {label:22} edges {len(E):4}  tris {c[3]:3}  quads {c[4]:3}  "
              f"pent {c[5]:3}  | interior@val4 {v4}/{len(interior)}")
        return f

    print(f"  nodes {len(V)}  boundary {int(boundary.sum())}  "
          f"interior {int((~boundary).sum())}")
    report(g0, "start (v8 graph)")
    report(g1, "de-triangulated")
    faces = report(g2, "forced valence-4")
    print(f"  forced edges: {len(f_on)} on-ink (beam) + {len(f_off)} literal-nearest")

    # coverage
    sil = head_mask(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)).sum()

    def area(f):
        P = np.array([[V[i, 1], V[i, 0]] for i in f])
        return abs(0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1)
                                - np.roll(P[:, 0], -1) * P[:, 1]))
    cov = sum(area(f) for f in faces if 3 <= len(f) <= 5)
    print(f"  surface coverage: {100*cov/sil:.0f}% of silhouette")

    write_obj(V, g2, faces, im, side, out)

    ov = np.full_like(im, 255)
    for (a, b) in g1:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (0, 170, 0), 1, cv2.LINE_AA)
    for (a, b) in f_on:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (200, 120, 0), 2, cv2.LINE_AA)
    for (a, b) in f_off:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (0, 0, 230), 2, cv2.LINE_AA)
    for i in range(len(V)):
        cv2.circle(ov, (int(V[i, 1]), int(V[i, 0])), 2,
                   (0, 0, 0) if boundary[i] else (200, 0, 0), -1)
    cv2.imwrite("rung14_overlay.png", ov)
    print(f"  wrote {out} and rung14_overlay.png "
          f"(green=real, blue=beam-forced, red=nearest-forced; black dot=boundary)")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

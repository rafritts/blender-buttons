"""
Rung 15 — outline boundary by cardinal scan, then loop it, then force interior.

Boundary definition (per the cleaner spec): a point is INTERIOR iff its column
has a point above AND below it, and its row has a point left AND right. Missing
any one -> it's on the outline -> BOUNDARY. (Catches the OUTER silhouette; hole
rims have points across the hole so they read interior — measured below.)

Then: every boundary point connects to its 2 nearest boundary points (no-cross,
no-shared-neighbour) -> the silhouette closes into a loop. Then force every
INTERIOR point to valence-4 (rung14 machinery). Report tris / coverage /
interior@4, and check the eyes didn't get stitched shut.

Run:  uv run --with numpy --with opencv-python --with scipy --with scikit-image \
        python rung15_boundary.py v3_front.jpg v3_side.jpg
"""

import sys
import numpy as np
import cv2
from collections import Counter
from scipy.spatial import cKDTree

from rung9_trace import detect, extract
from rung10_mesh_from_graph import faces_from_graph
from rung12_close_quads import close_quads, _seg_cross
from rung13_mirror import symmetry_axis, pair_twins, mirror_edges, write_obj
from rung14_force_quads import de_triangulate, force_quads, build_adj
from rung7_reconstruct import head_mask


def cardinal_boundary(V, nn, band_frac=0.6, eps_frac=0.25):
    y, x = V[:, 0], V[:, 1]
    boundary = np.zeros(len(V), bool)
    for i in range(len(V)):
        band, eps = band_frac * nn[i], eps_frac * nn[i]
        col = np.abs(x - x[i]) < band
        row = np.abs(y - y[i]) < band
        above = np.any(col & (y < y[i] - eps))
        below = np.any(col & (y > y[i] + eps))
        left = np.any(row & (x < x[i] - eps))
        right = np.any(row & (x > x[i] + eps))
        if not (above and below and left and right):
            boundary[i] = True
    return boundary


def loop_boundary(V, edges, boundary, nn):
    """Connect each boundary point to its 2 nearest boundary points (no-cross,
    no-shared-neighbour) -> a closed silhouette loop."""
    edges = set(edges)
    bidx = np.where(boundary)[0]
    tree = cKDTree(V[bidx])
    added = []
    for ii, i in enumerate(bidx):
        adj = build_adj(edges, len(V))
        have = sum(1 for j in adj[i] if boundary[j])
        if have >= 2:
            continue
        d, nb = tree.query(V[i], k=min(8, len(bidx)))
        elist = list(edges)
        for dist, jj in sorted(zip(d, nb)):
            j = bidx[jj]
            if j == i or j in adj[i] or dist > 3.0 * nn[i]:
                continue
            if adj[i] & adj[j]:
                continue
            if any((x not in (i, j) and y not in (i, j)
                    and _seg_cross(V[i], V[j], V[x], V[y])) for (x, y) in elist):
                continue
            edges.add((min(i, j), max(i, j)))
            added.append((min(i, j), max(i, j)))
            have += 1
            if have >= 2:
                break
    return edges, added


def main(front="v3_front.jpg", side="v3_side.jpg", out="head_v10.obj"):
    im, V, ink, dt = detect(front)
    edges, valence, sp = extract(im, V, dt)
    base = set(edges.keys())
    cq_on, _ = close_quads(V, base, dt)
    x0 = symmetry_axis(V)
    twin = pair_twins(V, x0)
    m_on, _ = mirror_edges(V, base, twin, dt)
    nn = cKDTree(V).query(V, k=2)[0][:, 1]

    g1 = de_triangulate(V, base | set(cq_on) | set(m_on), dt)
    boundary = cardinal_boundary(V, nn)
    g2, loop_added = loop_boundary(V, g1, boundary, nn)
    g3, f_on, f_off = force_quads(V, g2, dt, boundary, nn)
    g3 = de_triangulate(V, g3, dt)              # forcing can complete a few tris

    sil = head_mask(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)).sum()

    def area(f):
        P = np.array([[V[i, 1], V[i, 0]] for i in f])
        return abs(0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1)
                                - np.roll(P[:, 0], -1) * P[:, 1]))

    def report(E, label):
        f = faces_from_graph(V, E)
        c = Counter(len(x) for x in f)
        adj = build_adj(E, len(V))
        interior = [i for i in range(len(V)) if not boundary[i]]
        v4 = sum(len(adj[i]) == 4 for i in interior)
        cov = sum(area(x) for x in f if 3 <= len(x) <= 5)
        print(f"  {label:20} e{len(E):4} tris {c[3]:3} quads {c[4]:3} "
              f"pent {c[5]:3} | int@4 {v4}/{len(interior)} | cover {100*cov/sil:.0f}%")
        return f

    print(f"  nodes {len(V)}  boundary {int(boundary.sum())} "
          f"({100*boundary.mean():.0f}%)  interior {int((~boundary).sum())}")
    report(g1, "de-tri base")
    report(g2, "+ boundary loop")
    faces = report(g3, "+ forced interior")
    print(f"  boundary-loop edges added: {len(loop_added)}")
    print(f"  interior forced: {len(f_on)} beam + {len(f_off)} nearest")

    write_obj(V, g3, faces, im, side, out)

    ov = np.full_like(im, 255)
    for (a, b) in g1:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (0, 170, 0), 1, cv2.LINE_AA)
    for (a, b) in loop_added:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (160, 80, 0), 2, cv2.LINE_AA)               # dark-cyan: loop
    for (a, b) in f_on + f_off:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (0, 0, 230), 2, cv2.LINE_AA)
    for i in range(len(V)):
        cv2.circle(ov, (int(V[i, 1]), int(V[i, 0])), 3 if boundary[i] else 2,
                   (0, 0, 0) if boundary[i] else (200, 0, 0), -1)
    cv2.imwrite("rung15_overlay.png", ov)
    print(f"  wrote {out} and rung15_overlay.png "
          f"(black dot=boundary, red dot=interior, cyan=loop, blue=forced)")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

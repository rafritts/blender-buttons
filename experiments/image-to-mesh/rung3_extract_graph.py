"""
Rung 3 — extract the actual grid GRAPH from one clean front view.

Red dots = nodes, black lines = edges. Build a real (vertex, vertex) edge
list. This does two jobs:
  1) gives an HONEST valence (degree in the graph) instead of the fragile
     ring-crossing estimate from rung 1b,
  2) is the first half of CORRESPONDENCE -- we need the graph in each view
     before we can align front <-> side.

Method:
  detect dots -> nodes
  detect black-line skeleton
  PUNCH OUT a disk around every node -> skeleton splits into edge-segments,
    each running between exactly two nodes
  each segment's two endpoints -> snap to nearest node -> one edge
"""

import sys
import json
import numpy as np
import cv2
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize, remove_small_objects

K8 = np.ones((3, 3), int)


def detect(path):
    im = cv2.imread(path)
    B, G, R = (im[..., 0].astype(int), im[..., 1].astype(int), im[..., 2].astype(int))
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)

    # nodes: red dots
    red = ((R - (B + G) // 2) > 18) & (R > 50)
    red = remove_small_objects(red, 2)
    lbl, n = ndi.label(red)
    V = np.array(ndi.center_of_mass(red, lbl, range(1, n + 1)))  # (y, x)

    # edges: black lines, excluding red
    lines = (gray < 115) & ((R - (B + G) // 2) < 12)
    lines = remove_small_objects(lines, 25)
    skel = skeletonize(lines)
    return im, V, skel


def build_graph(V, skel):
    """Punch a disk (scaled to local spacing) around each node, splitting the
    skeleton into edge-segments; snap each segment's two ends to nearest node."""
    tree = cKDTree(V)
    d, _ = tree.query(V, k=2)
    nn = d[:, 1]
    spacing = float(np.median(nn))
    r_i = np.clip((0.30 * nn).astype(int), 2, 9)

    H, W = skel.shape
    nm = np.zeros((H, W), np.uint8)
    for (y, x), r in zip(V.astype(int), r_i):
        cv2.circle(nm, (int(x), int(y)), int(r), 1, -1)
    segs = skel & (~nm.astype(bool))
    lbl, n = ndi.label(segs, structure=K8)

    edges = set()
    for k in range(1, n + 1):
        ys, xs = np.where(lbl == k)
        if len(ys) < 3:
            continue
        pts = np.stack([ys, xs], 1)
        cset = set(map(tuple, pts))
        ends = [(y, x) for (y, x) in pts
                if sum((y + dy, x + dx) in cset
                       for dy in (-1, 0, 1) for dx in (-1, 0, 1)) - 1 == 1]
        if len(ends) >= 2:
            ee = np.array(ends)
            i, j = np.unravel_index(
                np.argmax(((ee[:, None] - ee[None]) ** 2).sum(-1)), (len(ee),) * 2)
            e1, e2 = ee[i], ee[j]
        else:
            i, j = np.unravel_index(
                np.argmax(((pts[:, None] - pts[None]) ** 2).sum(-1)), (len(pts),) * 2)
            e1, e2 = pts[i], pts[j]
        d1, a = tree.query(e1)
        d2, b = tree.query(e2)
        if a != b and d1 < r_i[a] + 0.8 * nn[a] and d2 < r_i[b] + 0.8 * nn[b]:
            edges.add((min(a, b), max(a, b)))

    return edges, spacing, int(np.median(r_i))


def report(V, edges):
    deg = np.zeros(len(V), int)
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1
    hist = {v: int((deg == v).sum()) for v in [0, 1, 2, 3, 4, 5]}
    hist["6+"] = int((deg >= 6).sum())
    interior = deg[deg >= 3]
    frac4 = (interior == 4).mean() if len(interior) else 0.0
    print(f"  vertices            : {len(V)}")
    print(f"  edges               : {len(edges)}")
    print(f"  valence histogram   : {hist}")
    print(f"  median valence      : {np.median(deg)}")
    print(f"  %% valence-4 (deg>=3): {100*frac4:.1f}%")
    print(f"  isolated (deg 0)    : {int((deg==0).sum())}")
    print(f"  dead-ends (deg 1)   : {int((deg==1).sum())}")
    return deg


def main(path):
    im, V, skel = detect(path)
    print("=" * 60)
    print(f"RUNG 3: extract grid graph from {path}")
    print("=" * 60)
    edges, spacing, r = build_graph(V, skel)
    print(f"  vertex spacing ~{spacing:.1f}px, median punch {r}px (skeleton)")
    deg = report(V, edges)

    # overlay the RECONSTRUCTED graph: green edges drawn dot-to-dot + nodes
    ov = im.copy()
    for a, b in edges:
        ya, xa = V[a]; yb, xb = V[b]
        cv2.line(ov, (int(xa), int(ya)), (int(xb), int(yb)), (0, 180, 0), 1, cv2.LINE_AA)
    for i, (y, x) in enumerate(V):
        col = (0, 200, 0) if deg[i] == 4 else (0, 165, 255) if deg[i] in (3, 5) else (0, 0, 255)
        cv2.circle(ov, (int(x), int(y)), 3, col, -1)
    cv2.imwrite("debug_graph.png", ov)

    # also a clean rebuild on white -> does the graph alone read as the mesh?
    canvas = np.full_like(im, 255)
    for a, b in edges:
        ya, xa = V[a]; yb, xb = V[b]
        cv2.line(canvas, (int(xa), int(ya)), (int(xb), int(yb)), (40, 40, 40), 1, cv2.LINE_AA)
    cv2.imwrite("debug_graph_clean.png", canvas)

    # persist the graph for correspondence / triangulation later
    json.dump({"vertices": V.tolist(), "edges": sorted(map(list, edges))},
              open("graph_front.json", "w"))
    print("  wrote debug_graph.png, debug_graph_clean.png, graph_front.json")
    print("=" * 60)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "clean_front.jpg")

"""
Rung 8 — rebuild the quad grid from dots + height-rows + hue, NO wire-tracing.
Then validate against the black wires Grok actually drew (overlay + edge-on-ink %).

Question: can connectivity come from (row, hue) instead of fragile line tracing?
  rows  = height bands (dots binned by y)
  within a row: order left->right by x; connect consecutive -> horizontal edges
  between rows: connect each dot to the nearest-x dot in the next row -> vertical
  hue   = independent check that the L->R order is right (corr of x-order vs hue)

Validation has teeth: for every proposed edge we sample along it and measure the
distance to the nearest black-wire pixel. An edge that lies on a real wire scores
~0; an invented edge scores high. % of edges on-ink = precision of the rebuild.
"""

import sys
import numpy as np
import cv2
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.morphology import remove_small_objects


def detect(path):
    im = cv2.imread(path)
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    Hh, S, Vv = hsv[..., 0].astype(int), hsv[..., 1], hsv[..., 2]
    B, G, R = (im[..., 0].astype(int), im[..., 1].astype(int), im[..., 2].astype(int))
    green_line = (G - (R + B) // 2 > 50) & (G > 120)
    blue_guide = (B - (R + G) // 2 > 10) & (B > 170) & (R > 140)
    dot = (S > 90) & (Vv > 60) & (~green_line) & (~blue_guide)
    dot = remove_small_objects(dot, 3)
    lbl, n = ndi.label(dot)
    V = np.array(ndi.center_of_mass(dot, lbl, range(1, n + 1)))      # (y, x)
    hue = np.array(ndi.mean(Hh, lbl, range(1, n + 1)))
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    wire = (gray < 120) & (S < 60)                                   # black lines only
    return im, V, hue, wire


def build_grid(V, rowstep):
    """rows by y-band; within row connect consecutive by x; link rows by nearest x."""
    y = V[:, 0]
    row_id = np.round((y - y.min()) / rowstep).astype(int)
    edges = set()
    rows = {}
    for i, r in enumerate(row_id):
        rows.setdefault(r, []).append(i)
    for r, idx in rows.items():
        idx = sorted(idx, key=lambda i: V[i, 1])                     # left -> right
        for a, b in zip(idx, idx[1:]):                              # horizontal edges
            edges.add((min(a, b), max(a, b)))
        nxt = rows.get(r + 1, [])
        if nxt:
            tree = cKDTree(V[nxt][:, 1:2])
            for i in idx:                                            # vertical edges
                j = nxt[tree.query(V[i, 1:2])[1]]
                edges.add((min(i, j), max(i, j)))
    return edges, row_id


def edge_on_ink(V, edges, wire):
    """For each edge, median distance (px) from its samples to nearest wire px."""
    dt = ndi.distance_transform_edt(~wire)
    H, W = wire.shape
    scores = []
    for a, b in edges:
        pa, pb = V[a], V[b]
        t = np.linspace(0, 1, 12)[:, None]
        pts = pa * (1 - t) + pb * t
        yy = np.clip(pts[:, 0].astype(int), 0, H - 1)
        xx = np.clip(pts[:, 1].astype(int), 0, W - 1)
        scores.append(np.median(dt[yy, xx]))
    return np.array(scores)


def main(path="rb_front.jpg", out="rung8_overlay.png"):
    im, V, hue, wire = detect(path)
    sp = float(np.median(cKDTree(V).query(V, k=2)[0][:, 1]))
    edges, row_id = build_grid(V, rowstep=sp)
    scores = edge_on_ink(V, edges, wire)
    on = (scores <= 3.0).mean()

    # hue should track left->right within rows -> sanity that ordering is real
    r = np.corrcoef(V[:, 1], hue)[0, 1]
    print(f"  dots {len(V)}  spacing {sp:.1f}px  rows {row_id.max()+1}  edges {len(edges)}")
    print(f"  edges on a real wire (<=3px): {100*on:.1f}%   median edge dist {np.median(scores):.1f}px")
    print(f"  hue-vs-x corr {r:+.3f} (ordering signal)")

    ov = im.copy()
    el = list(edges)
    for (a, b), s in zip(el, scores):
        col = (0, 180, 0) if s <= 3 else (0, 0, 255)               # green=on wire, red=invented
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])), col, 1, cv2.LINE_AA)
    cv2.imwrite(out, ov)
    print(f"  wrote {out} (green=matches a drawn wire, red=invented)")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

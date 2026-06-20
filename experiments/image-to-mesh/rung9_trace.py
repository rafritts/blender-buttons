"""
Rung 9 — dot-anchored connectivity extraction (the local link-prediction idea).

Premise under test: with every vertex already marked by a red dot, we do NOT
need global skeleton + junction reasoning (rung3, which leaks in dense regions).
Connectivity becomes LOCAL: for each dot, find the directions ink leaves it
(ring-sampling), follow each direction to the nearest dot, and accept the edge
ONLY if the straight segment between them actually lies on a drawn wire. A
length-sanity pass flags outliers for review.

Pieces:
  ring_dirs   "lines coming off a dot" -> sample a circle, ink crossings = edges
  propose     each direction -> nearest dot inside a cone (the "beam" target)
  validate    sample the chord, require it to ride the ink (rung8's edge_on_ink)
  flag        edges much longer than the median accepted edge -> review list

Swap vs literal pixel beam-search: for a fine quad mesh the wire between two
adjacent dots is ~straight, so chord-validation == "arrive at the next dot",
without the fragility of walking pixels through junctions. Escalate to true
tracing only if curved spans turn up.

Run:  uv run --with numpy --with opencv-python --with scipy --with scikit-image \
        python rung9_trace.py v3_front.jpg
"""

import sys
import numpy as np
import cv2
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.morphology import remove_small_objects

from rung7_reconstruct import centerline_verts, dedup


def detect(path):
    """Red dots = nodes. Ink = black wires + green centerline (NOT blue guides,
    NOT the red dots themselves). dt = distance to nearest ink pixel."""
    im = cv2.imread(path)
    B, G, R = (im[..., 0].astype(int), im[..., 1].astype(int), im[..., 2].astype(int))
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)

    red = ((R - (B + G) // 2) > 18) & (R > 50)
    red = remove_small_objects(red, 2)
    lbl, n = ndi.label(red)
    V = np.array(ndi.center_of_mass(red, lbl, range(1, n + 1)))      # (y, x)

    # The bright-green midline is painted OVER its vertex dots, so the whole
    # facial centre column is missing from the red detection. Recover it by
    # sampling the green seam as an explicit centre column (until the prompts
    # drop green entirely and these become ordinary red dots).
    sp0 = float(np.median(cKDTree(V).query(V, k=2)[0][:, 1]))
    V = dedup(np.vstack([V, centerline_verts(im, sp0)]), 0.5 * sp0)

    green = (G - (R + B) // 2 > 40) & (G > 90)
    blue = (B - (R + G) // 2 > 10) & (B > 170) & (R > 140)
    black = (gray < 115) & ((R - (B + G) // 2) < 12) & (~green) & (~blue)
    ink = remove_small_objects(black | green, 25)
    dt = ndi.distance_transform_edt(~ink)
    return im, V, ink, dt


def ring_dirs(dt, y, x, r, tol=1.5, n=144):
    """Angles (rad) at which ink crosses a circle of radius r about (y,x).
    Contiguous angular runs of on-ink samples collapse to one direction each."""
    H, W = dt.shape
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    yy = np.clip((y + r * np.sin(a)).astype(int), 0, H - 1)
    xx = np.clip((x + r * np.cos(a)).astype(int), 0, W - 1)
    on = dt[yy, xx] <= tol
    if not on.any():
        return []
    # rotate so index 0 starts on a gap, then split into runs
    start = np.argmin(on)
    on = np.roll(on, -start)
    dirs, i = [], 0
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]:
                j += 1
            mid = (i + j - 1) / 2.0
            dirs.append(a[(int(round(mid)) + start) % n])
            i = j
        else:
            i += 1
    return dirs


def chord_eval(dt, ya, xa, yb, xb, base=2.0, curve=0.18, k=24, frac=0.85, r_end=6.0):
    """Accept an edge whose ink stays inside a tube that WIDENS toward mid-span.

    Grok bows some edges; a straight chord cuts across the inside of the bow and
    leaves the ink, so the allowed deviation grows with edge length and peaks at
    the midpoint, tight in the dense (short-edge) regions where the diagonal trap
    lives. Endpoints are TRIMMED (r_end px): the red vertex dot blanks the wire
    under it, so the ink voids near each dot are not the edge's fault — judge the
    interior, which is where a false diagonal gives itself away. Returns
    (ok, median_dist)."""
    t = np.linspace(0, 1, k)
    yy = np.clip((ya * (1 - t) + yb * t).astype(int), 0, dt.shape[0] - 1)
    xx = np.clip((xa * (1 - t) + xb * t).astype(int), 0, dt.shape[1] - 1)
    d = dt[yy, xx]
    L = float(np.hypot(yb - ya, xb - xa))
    s = t * L                                                   # arc dist from a
    inner = (s >= r_end) & (s <= L - r_end)
    if inner.sum() < 3:
        inner = np.ones_like(t, bool)                          # tiny edge: use all
    allow = base + curve * L * (2.0 * np.minimum(t, 1 - t))     # tube, fat at mid
    ok = (d[inner] <= allow[inner]).mean() >= frac              # interior on ink
    return ok, float(np.median(d[inner]))


def extract(im, V, dt, cone_deg=40.0):
    nn = cKDTree(V).query(V, k=2)[0][:, 1]          # per-dot local spacing
    sp = float(np.median(nn))
    tree = cKDTree(V)
    cone = np.radians(cone_deg)

    edges = {}                                       # (min,max) -> (medd, length)
    valence = np.zeros(len(V), int)
    for i, (yi, xi) in enumerate(V):
        r = max(4.0, 0.5 * nn[i])
        # LOCAL window: skull/neck dots sit wider than face dots, so a global
        # cutoff drops their real edges. Chord-validation guards against the
        # false long edges a generous window would otherwise let in.
        lo, hi = 0.4 * nn[i], 3.2 * nn[i]
        dirs = ring_dirs(dt, yi, xi, r)
        valence[i] = len(dirs)
        cand = [j for j in tree.query_ball_point((yi, xi), hi)
                if j != i and np.hypot(*(V[j] - V[i])) >= lo]
        for d in dirs:
            # all dots inside the cone, nearest first; accept the first whose
            # chord actually validates (a wide cone may put a wrong diagonal
            # nearer than the real, aligned neighbour — don't let it block it).
            incone = []
            for j in cand:
                dy, dx = V[j] - V[i]
                ang = np.arctan2(dy, dx)
                diff = abs(np.arctan2(np.sin(ang - d), np.cos(ang - d)))
                if diff <= cone:
                    incone.append((np.hypot(dy, dx), j))
            for dist, j in sorted(incone):
                ok, medd = chord_eval(dt, yi, xi, V[j][0], V[j][1])
                if ok:
                    edges[(min(i, j), max(i, j))] = (medd, dist)
                    break
    return edges, valence, sp


def main(path="v3_front.jpg", out="rung9_overlay.png"):
    im, V, ink, dt = detect(path)
    edges, valence, sp = extract(im, V, dt)

    lengths = np.array([L for _, L in edges.values()]) if edges else np.array([])
    medL = float(np.median(lengths)) if len(lengths) else 0.0
    flagged = {e for e, (_, L) in edges.items() if L > 1.8 * medL}

    chord_med = np.array([m for m, _ in edges.values()]) if edges else np.array([])
    print(f"  dots {len(V)}   spacing {sp:.1f}px   edges {len(edges)}")
    print(f"  mean valence {valence.mean():.2f}  "
          f"(val=4 dots: {100*(valence==4).mean():.0f}%, "
          f"val>=3: {100*(valence>=3).mean():.0f}%, isolated: {(valence==0).sum()})")
    if len(chord_med):
        print(f"  chord fit: median {np.median(chord_med):.2f}px  "
              f"max {chord_med.max():.2f}px  (all accepted ride the ink)")
    print(f"  flagged long edges (>1.8x median {medL:.0f}px): {len(flagged)}")

    ov = np.full_like(im, 255)                                     # blank: show ONLY what we rebuilt
    for (a, b), (_, _) in edges.items():
        col = (0, 140, 255) if (a, b) in flagged else (0, 180, 0)   # orange / green
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])),
                 (int(V[b, 1]), int(V[b, 0])), col, 1, cv2.LINE_AA)
    for i, (y, x) in enumerate(V):
        c = (255, 0, 0) if valence[i] else (0, 0, 255)              # blue ok / red isolated
        cv2.circle(ov, (int(x), int(y)), 2, c, -1)
    cv2.imwrite(out, ov)
    print(f"  wrote {out} (green=edge, orange=flagged-long, red dot=isolated)")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

"""
Rung 11 — close the recall gap by STRUCTURAL assumption, after the fact.

rung9 extracts edges at ~perfect precision but ~2.7/4 recall, so quads don't
close (rung10). Instead of making extraction heroic, complete the grid with a
topology assumption: each vertex should connect to one neighbour in each of ~4
directions. NOT raw 4-nearest (diagonals are only 1.4x a side -> triangle soup;
and nearest-across-a-gap stitches the eyes shut). Instead: greedily take
neighbours nearest-first, rejecting any within ~40 deg of one already taken, and
cap at local spacing so holes stay open. -> one nearest neighbour per direction.

The honesty check: the assumed edges are PREDICTIONS made without looking at the
wires. We then test each against the ink (ground truth we didn't use):
  green  extracted  (rung9, already ink-verified)
  blue   assumed AND lands on a real wire   -> the assumption was RIGHT
  red    assumed, no wire there             -> pure invention (soup risk)
A big blue / small red pile means "4 closest = edges" holds; red means it doesn't.

Run:  uv run --with numpy --with opencv-python --with scipy --with scikit-image \
        python rung11_complete.py v3_front.jpg
"""

import sys
import numpy as np
import cv2
from scipy.spatial import cKDTree

from rung9_trace import detect, extract, chord_eval


def spread_neighbors(V, i, idx, dists, cap, spread_deg=40.0, kmax=4):
    """Greedy nearest-first neighbours that are angularly spread (>spread_deg
    apart) and within cap distance -> ~one per grid direction, no diagonals."""
    spread = np.radians(spread_deg)
    taken, dirs = [], []
    for d, j in sorted(zip(dists, idx)):
        if j == i or d > cap:
            continue
        dy, dx = V[j] - V[i]
        a = np.arctan2(dy, dx)
        if all(abs(np.arctan2(np.sin(a - t), np.cos(a - t))) > spread for t in dirs):
            taken.append(j)
            dirs.append(a)
        if len(taken) >= kmax:
            break
    return taken


def main(path="v3_front.jpg", out="rung11_overlay.png"):
    im, V, ink, dt = detect(path)
    edges0, valence, sp = extract(im, V, dt)          # rung9 extracted (verified)
    nn = cKDTree(V).query(V, k=2)[0][:, 1]
    tree = cKDTree(V)
    dd, ii = tree.query(V, k=8)

    proposed = set()
    for i in range(len(V)):
        cap = 2.0 * nn[i]                              # local; won't reach across holes
        for j in spread_neighbors(V, i, ii[i], dd[i], cap):
            proposed.add((min(i, j), max(i, j)))

    extracted = set(edges0.keys())
    assumed = proposed - extracted
    # classify assumed edges against the ink they never saw
    on, off = [], []
    for (a, b) in assumed:
        ok, _ = chord_eval(dt, V[a][0], V[a][1], V[b][0], V[b][1])
        (on if ok else off).append((a, b))

    final = extracted | set(on) | set(off)
    deg = 2 * len(final) / len(V)
    deg0 = 2 * len(extracted) / len(V)
    print(f"  nodes {len(V)}")
    print(f"  extracted edges {len(extracted)}  (degree {deg0:.2f})")
    print(f"  assumed edges   {len(assumed)}  -> on-ink {len(on)} "
          f"({100*len(on)/max(1,len(assumed)):.0f}%), off-ink {len(off)}")
    print(f"  COMPLETED total {len(final)}  (degree {deg:.2f})")
    print(f"  >> verdict: of the edges the assumption INVENTED, "
          f"{100*len(on)/max(1,len(assumed)):.0f}% land on a real wire")

    ov = np.full_like(im, 255)
    for (a, b) in extracted:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (0, 170, 0), 1, cv2.LINE_AA)                       # green
    for (a, b) in on:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (200, 120, 0), 1, cv2.LINE_AA)                     # blue
    for (a, b) in off:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (0, 0, 230), 1, cv2.LINE_AA)                       # red
    cv2.imwrite(out, ov)
    print(f"  wrote {out} (green=extracted, blue=assumed-on-ink, red=invented)")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

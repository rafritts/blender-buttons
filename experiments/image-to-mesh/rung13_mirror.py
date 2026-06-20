"""
Rung 13 — symmetric edge completion (mirror an edge to the other half).

The head is bilaterally symmetric (we prompt it so). Topology must match across
the midline: if edge (a,b) exists on one side and its mirror (a',b') is missing,
inserting the mirror is NOT invention — it enforces a known constraint. We still
ink-gate it as a confidence read.

The "too loose?" test, answered with numbers:
  1. find the symmetry axis x0 (minimise reflection mismatch over all dots)
  2. pair each vertex with its mirror twin (reflect across x0, nearest match);
     a pair is CLEAN only if it's mutual and the residual is small vs spacing
  3. for every edge whose endpoints are both cleanly paired, propose the mirror
     edge if absent. Report: pairing rate (how symmetric the graph really is),
     and what fraction of mirrored edges land on real ink (were they right?).

Run:  uv run --with numpy --with opencv-python --with scipy --with scikit-image \
        python rung13_mirror.py v3_front.jpg v3_side.jpg
"""

import sys
import numpy as np
import cv2
from scipy.spatial import cKDTree

from rung9_trace import detect, extract, chord_eval
from rung10_mesh_from_graph import faces_from_graph
from rung12_close_quads import close_quads, _seg_cross
from rung7_reconstruct import head_mask, col_profile, side_depth_fn


def symmetry_axis(V):
    """x0 minimising reflection mismatch: for a sweep of axes, reflect all dots
    and sum nearest-neighbour distance. The head's true midline is the min."""
    x = V[:, 1]
    tree = cKDTree(V)
    best, bx = 1e18, np.median(x)
    for x0 in np.linspace(np.percentile(x, 35), np.percentile(x, 65), 61):
        Vm = V.copy()
        Vm[:, 1] = 2 * x0 - x
        d, _ = tree.query(Vm)
        s = float(np.median(d))
        if s < best:
            best, bx = s, x0
    return bx


def pair_twins(V, x0, tol_frac=0.45):
    """Mutual nearest mirror match. twin[i]=j (j on the other side), or -1.
    A pair is clean only if reflecting i lands near j AND vice-versa, within
    tol_frac of local spacing. Midline dots (|x-x0|<eps) twin to themselves."""
    nn = cKDTree(V).query(V, k=2)[0][:, 1]
    tree = cKDTree(V)
    x = V[:, 1]
    Vm = V.copy()
    Vm[:, 1] = 2 * x0 - x
    d, j = tree.query(Vm)                       # i's reflection -> nearest real dot j
    twin = np.full(len(V), -1)
    for i in range(len(V)):
        if abs(x[i] - x0) < 0.25 * nn[i]:
            twin[i] = i                         # on the axis
        elif d[i] < tol_frac * nn[i] and j[j[i]] == i:   # mutual
            twin[i] = j[i]
    return twin


def mirror_edges(V, edges, twin, dt):
    eset = set(edges)
    elist = list(edges)

    def crosses(a, d):
        for (x, y) in elist:
            if x in (a, d) or y in (a, d):
                continue
            if _seg_cross(V[a], V[d], V[x], V[y]):
                return True
        return False

    on, off = [], []
    for (a, b) in edges:
        ta, tb = twin[a], twin[b]
        if ta < 0 or tb < 0:
            continue                            # an endpoint has no clean twin
        key = (min(ta, tb), max(ta, tb))
        if key == (min(a, b), max(a, b)) or key in eset:
            continue                            # self-mirror or already present
        if crosses(*key):
            continue
        ok, _ = chord_eval(dt, V[key[0]][0], V[key[0]][1], V[key[1]][0], V[key[1]][1])
        (on if ok else off).append(key)
    return set(on), set(off)


def write_obj(V, edges, faces, im, side, out):
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    top_f, bot_f, xc, hw = col_profile(head_mask(gray))
    Hf = float(bot_f - top_f)
    D = side_depth_fn(side)
    v3 = []
    for (vy, vx) in V:
        yy = int(np.clip(vy, 0, im.shape[0] - 1))
        t = (bot_f - vy) / Hf
        X = (vx - xc[yy]) / Hf
        Z = (bot_f - vy) / Hf
        frac = float(np.clip((vx - xc[yy]) / hw[yy], -1, 1))
        Y = D(t) * np.sqrt(max(0.0, 1 - frac * frac))
        v3.append((X, Y, Z))
    v3 = np.array(v3)
    used = sorted({i for f in faces for i in f} | {i for e in edges for i in e})
    rm = {o: n for n, o in enumerate(used)}
    v3 = v3[used]
    faces = [[rm[i] for i in f] for f in faces]
    edges = [(rm[a], rm[b]) for a, b in edges]
    v3 -= v3.mean(0)
    v3 /= (v3[:, 2].max() - v3[:, 2].min()) / 2.0
    with open(out, "w") as fh:
        for v in v3:
            fh.write(f"v {v[0]:.4f} {v[2]:.4f} {v[1]:.4f}\n")
        for f in faces:
            fh.write("f " + " ".join(str(i + 1) for i in f) + "\n")
        for a, b in edges:
            fh.write(f"l {a+1} {b+1}\n")


def main(front="v3_front.jpg", side="v3_side.jpg", out="head_v8.obj"):
    im, V, ink, dt = detect(front)
    edges, valence, sp = extract(im, V, dt)
    base = set(edges.keys())

    x0 = symmetry_axis(V)
    twin = pair_twins(V, x0)
    paired = int((twin >= 0).sum())
    print(f"  symmetry axis x0={x0:.0f}px   nodes {len(V)}")
    print(f"  cleanly paired twins: {paired}/{len(V)} "
          f"({100*paired/len(V):.0f}%)  <- how symmetric the graph really is")

    m_on, m_off = mirror_edges(V, base, twin, dt)
    print(f"  mirror-edge candidates: {len(m_on)+len(m_off)}  "
          f"-> on-ink {len(m_on)} (twin really there), off-ink {len(m_off)}")

    # stack the wins: extracted + close-the-quad(on-ink) + mirror(on-ink)
    cq_on, _ = close_quads(V, base, dt)
    f_base = faces_from_graph(V, base)
    full = base | set(cq_on) | m_on
    f_full = faces_from_graph(V, full)
    q0 = sum(len(f) == 4 for f in f_base)
    q1 = sum(len(f) == 4 for f in f_full)
    print(f"  base {len(base)}e {len(f_base)}f ({q0} quads)  ->  "
          f"+closequad+mirror {len(full)}e {len(f_full)}f ({q1} quads)  "
          f"[+{q1-q0} quads]")

    ov = np.full_like(im, 255)
    for (a, b) in base:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (0, 170, 0), 1, cv2.LINE_AA)
    for (a, b) in m_on:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (200, 60, 160), 2, cv2.LINE_AA)         # purple: mirrored, on ink
    for (a, b) in m_off:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (0, 0, 230), 1, cv2.LINE_AA)            # red: mirrored, no ink
    cv2.line(ov, (int(x0), 0), (int(x0), im.shape[0] - 1), (180, 180, 180), 1)
    cv2.imwrite("rung13_overlay.png", ov)
    write_obj(V, full, f_full, im, side, out)
    print(f"  wrote {out} and rung13_overlay.png "
          f"(green=extracted, purple=mirror-on-ink, red=mirror-no-ink)")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

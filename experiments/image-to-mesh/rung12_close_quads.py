"""
Rung 12 — close-the-quad: add the implied 4th side of any 3-sided cell.

NOT "force every vertex to valence 4" (topologically impossible on a curved /
bounded surface — Euler: a quad sphere needs Sum(4-val)=8 of irregular verts;
boundaries and poles MUST be valence 2/3/5). Instead, a surgical completion:
wherever a path a-b-c-d already has edges ab,bc,cd but not d-a, the 4th side is
implied by the existing three. Add it — but only if the four points form a
convex quad AND (for the safe set) the closing edge rides a real wire.

Can't make diagonals: the closing edge joins the two open ends of an existing
3-sided cell, never crosses it. Leaves holes/boundaries alone: a rim has no
3-sided cell reaching across it. The ink-gate separates "closed a real wire"
(green) from "manufactured" (red) so we never silently invent.

Run:  uv run --with numpy --with opencv-python --with scipy --with scikit-image \
        python rung12_close_quads.py v3_front.jpg v3_side.jpg
"""

import sys
import numpy as np
import cv2
from collections import defaultdict
from scipy.spatial import cKDTree

from rung9_trace import detect, extract, chord_eval
from rung10_mesh_from_graph import faces_from_graph
from rung7_reconstruct import head_mask, col_profile, side_depth_fn


def convex_quad(P):
    """True if the 4 points (in path order) form a convex, non-degenerate quad."""
    s = []
    for i in range(4):
        a, b, c = P[i], P[(i + 1) % 4], P[(i + 2) % 4]
        cz = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        s.append(cz)
    s = np.array(s)
    return np.all(s > 1e-6) or np.all(s < -1e-6)


def _seg_cross(p, q, r, s):
    """Do open segments p-q and r-s properly intersect? (shared endpoints ok)"""
    def o(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = o(r, s, p), o(r, s, q), o(p, q, r), o(p, q, s)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def close_quads(V, edges, dt):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    eset = set(edges)
    elist = list(edges)
    nn = cKDTree(V).query(V, k=2)[0][:, 1]

    def crosses(a, d):
        pa, pd = V[a], V[d]
        for (x, y) in elist:
            if x in (a, d) or y in (a, d):          # shared endpoint is fine
                continue
            if _seg_cross(pa, pd, V[x], V[y]):
                return True
        return False

    cand = {}                                       # (a,d) -> via (b,c)
    for (b, c) in edges:
        for a in adj[b]:
            if a == c:
                continue
            for d in adj[c]:
                if d in (a, b):
                    continue
                key = (min(a, d), max(a, d))
                if key in eset or key in cand:
                    continue
                L = np.hypot(*(V[a] - V[d]))
                if L > 1.8 * max(nn[a], nn[d]):     # 4th side ~ one cell wide
                    continue
                if not convex_quad([V[a], V[b], V[c], V[d]]):
                    continue
                if crosses(a, d):                   # don't slash existing cells
                    continue
                cand[key] = (b, c)

    on, off = [], []
    for (a, d) in cand:
        ok, _ = chord_eval(dt, V[a][0], V[a][1], V[d][0], V[d][1])
        (on if ok else off).append((a, d))
    return on, off


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


def main(front="v3_front.jpg", side="v3_side.jpg", out="head_v6.obj",
         manufacture=False):
    im, V, ink, dt = detect(front)
    edges, valence, sp = extract(im, V, dt)
    base = set(edges.keys())
    f0 = faces_from_graph(V, base)

    on, off = close_quads(V, base, dt)
    added = set(on) | (set(off) if manufacture else set())
    full = base | added
    f1 = faces_from_graph(V, full)

    q0 = sum(len(f) == 4 for f in f0)
    q1 = sum(len(f) == 4 for f in f1)
    print(f"  base graph: {len(base)} edges, {len(f0)} faces ({q0} quads)")
    print(f"  close-the-quad candidates: {len(on)+len(off)}  "
          f"-> on-ink {len(on)} (real wire), off-ink {len(off)} (manufacture)")
    print(f"  adding {'on-ink + manufactured' if manufacture else 'on-ink only'} "
          f"= +{len(added)} edges")
    print(f"  closed graph: {len(full)} edges, {len(f1)} faces ({q1} quads)  "
          f"[+{len(f1)-len(f0)} faces, +{q1-q0} quads]")

    ov = np.full_like(im, 255)
    for (a, b) in base:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (0, 170, 0), 1, cv2.LINE_AA)
    for (a, b) in on:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (200, 120, 0), 2, cv2.LINE_AA)                    # blue: real closure
    for (a, b) in off:
        cv2.line(ov, (int(V[a, 1]), int(V[a, 0])), (int(V[b, 1]), int(V[b, 0])),
                 (0, 0, 230), 1, cv2.LINE_AA)                      # red: manufacture
    cv2.imwrite("rung12_overlay.png", ov)
    write_obj(V, full, f1, im, side, out)
    print(f"  wrote {out} and rung12_overlay.png "
          f"(green=extracted, blue=real closure, red=manufactured)")


if __name__ == "__main__":
    a = sys.argv[1:]
    man = "--manufacture" in a
    a = [x for x in a if not x.startswith("--")]
    main(*(a or []), manufacture=man)

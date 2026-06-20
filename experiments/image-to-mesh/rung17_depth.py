"""
Rung 17 — re-profile the depth so the silhouette stops stretching.

Depth was an elliptical cross-section  Y = D(t)*sqrt(1 - frac^2)  (frac = signed
distance from the centreline / half-width). Its slope -> infinity as frac -> +-1,
so vertices near the silhouette (sides / back of skull) get huge depth steps for
tiny horizontal steps -> stretched quads. The front-centre (frac~0) is flat, so
it looks fine. That's the reported "back stretched, front ok".

Fix: a profile with FINITE edge slope.
  ellipse  : sqrt(1-f^2)   slope -> inf at edge   (old)
  parabola : 1 - f^2       slope = -2f at edge    (gentle)
  cosine   : cos(f*pi/2)   slope = -pi/2 at edge
Same depth at the centre; the edges pull in gently instead of curving vertically.

Stretch metric: per edge, |dY| / front-distance. Lower = less stretched.

Run:  uv run --with numpy --with opencv-python --with scipy --with scikit-image \
        python rung17_depth.py parabola
"""

import sys
import numpy as np
import cv2
from scipy.spatial import cKDTree

from rung9_trace import detect, extract
from rung12_close_quads import close_quads
from rung13_mirror import symmetry_axis, pair_twins, mirror_edges
from rung14_force_quads import de_triangulate, force_quads
from rung15_boundary import cardinal_boundary, loop_boundary
from rung10_mesh_from_graph import faces_from_graph
from rung7_reconstruct import head_mask, col_profile, side_depth_fn


def build_graph(front):
    im, V, ink, dt = detect(front)
    edges, val, sp = extract(im, V, dt)
    base = set(edges)
    cq, _ = close_quads(V, base, dt)
    x0 = symmetry_axis(V)
    tw = pair_twins(V, x0)
    m, _ = mirror_edges(V, base, tw, dt)
    nn = cKDTree(V).query(V, k=2)[0][:, 1]
    g = de_triangulate(V, base | set(cq) | set(m), dt)
    b = cardinal_boundary(V, nn)
    g, _ = loop_boundary(V, g, b, nn)
    g, _, _ = force_quads(V, g, dt, b, nn)
    g = de_triangulate(V, g, dt)
    return im, V, g, faces_from_graph(V, g), dt


def profile_fn(name):
    return {
        "ellipse": lambda f: np.sqrt(max(0.0, 1 - f * f)),
        "parabola": lambda f: 1 - f * f,
        "cosine": lambda f: np.cos(f * np.pi / 2),
    }[name]


def reconstruct(im, V, profile, scale=1.0):
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    top_f, bot_f, xc, hw = col_profile(head_mask(gray))
    Hf = float(bot_f - top_f)
    D = side_depth_fn("v3_side.jpg")
    prof = profile_fn(profile)
    out = []
    for (vy, vx) in V:
        yy = int(np.clip(vy, 0, im.shape[0] - 1))
        t = (bot_f - vy) / Hf
        X = (vx - xc[yy]) / Hf
        Z = (bot_f - vy) / Hf
        frac = float(np.clip((vx - xc[yy]) / hw[yy], -1, 1))
        Y = scale * D(t) * prof(frac)          # D is FULL head depth; scale<1 = front relief
        out.append((X, Y, Z))
    P = np.array(out)
    P -= P.mean(0)
    P /= (P[:, 2].max() - P[:, 2].min()) / 2.0
    return P


def repair_depth(P, k=8, z=3.5, floor=0.05):
    """rung16 robust outlier repair on the depth axis (neighbours by X+height)."""
    P = P.copy()
    _, idx = cKDTree(P[:, [0, 2]]).query(P[:, [0, 2]], k=k + 1)
    for i in range(len(P)):
        nb = idx[i, 1:]
        vals = P[nb, 1]
        med = np.median(vals)
        mad = np.median(np.abs(vals - med))
        if mad > 1e-9 and 0.6745 * abs(P[i, 1] - med) / mad > z \
                and abs(P[i, 1] - med) > floor:
            P[i, 1] = vals.mean()
    return P


def stretch(P, edges):
    """Per edge: |depth step| / front-plane step. High = stretched."""
    r = []
    for a, b in edges:
        dY = abs(P[a, 1] - P[b, 1])
        df = np.hypot(P[a, 0] - P[b, 0], P[a, 2] - P[b, 2])
        r.append(dY / (df + 1e-6))
    r = np.array(r)
    return r


def main(profile="parabola", front="v3_front.jpg", out=None):
    out = out or f"head_v12_{profile}.obj"
    im, V, edges, faces, dt = build_graph(front)
    print(f"  graph: {len(V)} verts, {len(edges)} edges, {len(faces)} faces\n")
    for sc in (1.0, 0.5):
        P = repair_depth(reconstruct(im, V, "ellipse", sc))
        r = stretch(P, edges)
        ds = P[:, 1].max() - P[:, 1].min()
        print(f"  ellipse x{sc}  depth-span {ds:.2f} ({ds/2.0:.2f}x height)  "
              f"stretch median {np.median(r):.2f}  p95 {np.percentile(r,95):.2f}  "
              f"edges>2: {(r>2).sum()}")

    P = repair_depth(reconstruct(im, V, "ellipse", 0.5))
    with open(out, "w") as fh:
        for v in P:
            fh.write(f"v {v[0]:.4f} {v[2]:.4f} {v[1]:.4f}\n")
        for f in faces:
            fh.write("f " + " ".join(str(i + 1) for i in f) + "\n")
        for a, b in edges:
            fh.write(f"l {a+1} {b+1}\n")
    print(f"\n  wrote {out}  (profile={profile})")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

"""
Rung 10 — build a real mesh from the AUTHORED edge graph (rung9), not Delaunay.

rung7 faked faces with a density-adaptive Delaunay of the dots (clean to look at,
but invented topology — the "low-rent Meshy" we rejected). This instead takes the
edges rung9 actually extracted from Grok's wires and recovers faces by a planar
half-edge traversal:

  - sort each node's neighbours by angle (we have 2D positions)
  - walk directed half-edges, always taking the clockwise-most turn at each node
  - each closed walk is a bounded face of the planar subdivision

Quads come out where four edges close; the eye/mouth openings and the outer
silhouette trace as large cycles and are dropped on size -> they stay as real
holes, which is correct. Depth reuses rung7's coherent side-profile (Y = side
depth * elliptical bulge), in the shared head-height unit.

Output: head_v4.obj  (import via the MCP `file op=import`).

Run:  uv run --with numpy --with opencv-python --with scipy --with scikit-image \
        python rung10_mesh_from_graph.py v3_front.jpg v3_side.jpg
"""

import sys
import math
import numpy as np
import cv2

from rung9_trace import detect, extract
from rung7_reconstruct import head_mask, col_profile, side_depth_fn


def faces_from_graph(V, edges, max_sides=5):
    """Planar-subdivision faces via clockwise-most half-edge traversal.
    Keeps cycles of 3..max_sides verts; the outer face and the big feature
    holes (eyes/mouth) are larger cycles -> dropped -> left open on purpose."""
    adj = {i: [] for i in range(len(V))}
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    # CCW order of neighbours around each node (image y is down; consistent)
    order = {}
    for i, nb in adj.items():
        nb.sort(key=lambda j: math.atan2(V[j][0] - V[i][0], V[j][1] - V[i][1]))
        order[i] = {j: k for k, j in enumerate(nb)}

    visited = set()                                    # directed half-edges
    faces = []
    for a, b in edges:
        for u0, v0 in ((a, b), (b, a)):
            if (u0, v0) in visited:
                continue
            cyc, u, v = [], u0, v0
            while (u, v) not in visited:
                visited.add((u, v))
                cyc.append(u)
                nb = adj[v]
                w = nb[(order[v][u] - 1) % len(nb)]    # clockwise-most turn at v
                u, v = v, w
                if len(cyc) > max_sides + 1:
                    break
            if 3 <= len(cyc) <= max_sides and (u, v) == (u0, v0):
                # keep interior winding only (drop the CW-traced outer face)
                pts = np.array([[V[i][1], V[i][0]] for i in cyc])
                area = 0.5 * np.sum(pts[:, 0] * np.roll(pts[:, 1], -1)
                                    - np.roll(pts[:, 0], -1) * pts[:, 1])
                if area > 0:
                    faces.append(cyc)
    # dedup by vertex set
    seen, uniq = set(), []
    for f in faces:
        k = frozenset(f)
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


def main(front="v3_front.jpg", side="v3_side.jpg", out="head_v4.obj"):
    im, V, ink, dt = detect(front)
    edges, valence, sp = extract(im, V, dt)
    faces = faces_from_graph(V, edges)
    nq = sum(len(f) == 4 for f in faces)
    nt = sum(len(f) == 3 for f in faces)
    print(f"  graph: {len(V)} nodes, {len(edges)} edges")
    print(f"  faces: {len(faces)}  ({nq} quads, {nt} tris, "
          f"{len(faces)-nq-nt} pentagons)")

    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    mf = head_mask(gray)
    top_f, bot_f, xc, hw = col_profile(mf)
    Hf = float(bot_f - top_f)
    D = side_depth_fn(side)

    verts3d = []
    for (vy, vx) in V:
        yy = int(np.clip(vy, 0, im.shape[0] - 1))
        t = (bot_f - vy) / Hf
        X = (vx - xc[yy]) / Hf
        Z = (bot_f - vy) / Hf
        frac = float(np.clip((vx - xc[yy]) / hw[yy], -1, 1))
        Y = D(t) * np.sqrt(max(0.0, 1 - frac * frac))
        verts3d.append((X, Y, Z))
    verts3d = np.array(verts3d)

    # keep only nodes used by a face or an edge; remap
    used = sorted({i for f in faces for i in f} | {i for e in edges for i in e})
    remap = {o: n for n, o in enumerate(used)}
    verts3d = verts3d[used]
    faces = [[remap[i] for i in f] for f in faces]
    edges = [(remap[a], remap[b]) for a, b in edges]

    verts3d -= verts3d.mean(0)
    verts3d /= (verts3d[:, 2].max() - verts3d[:, 2].min()) / 2.0

    with open(out, "w") as fh:
        for v in verts3d:
            fh.write(f"v {v[0]:.4f} {v[2]:.4f} {v[1]:.4f}\n")        # OBJ Y-up
        for f in faces:
            fh.write("f " + " ".join(str(i + 1) for i in f) + "\n")
        for a, b in edges:
            fh.write(f"l {a+1} {b+1}\n")
    print(f"  wrote {out}  ({len(verts3d)} verts, {len(faces)} faces, "
          f"{len(edges)} edges)")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

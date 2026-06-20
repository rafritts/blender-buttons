"""
Rung 18 — RAW nearest-neighbour force. No beam, no gates. "I want to see something."

For every interior vertex with <4 edges, connect it to its nearest dots until it
has 4. NO ink/beam preference, NO no-crossing gate, NO no-shared-neighbour gate.
This is the unconstrained version of the force — expected to hit valence-4 almost
everywhere AND to produce triangles / crossings (diagonals). The point is to see
the raw result, not to keep it clean.

Depth = same as head_v12 (ellipse x0.5, spike-repaired) so ONLY topology changes.

Run:  uv run --with numpy --with opencv-python --with scipy --with scikit-image \
        python rung18_raw.py
"""

import sys
import numpy as np
from collections import Counter
from scipy.spatial import cKDTree

from rung9_trace import detect, extract
from rung12_close_quads import close_quads
from rung13_mirror import symmetry_axis, pair_twins, mirror_edges
from rung14_force_quads import de_triangulate, build_adj
from rung15_boundary import cardinal_boundary, loop_boundary
from rung10_mesh_from_graph import faces_from_graph
from rung17_depth import reconstruct, repair_depth


def raw_force(V, edges, boundary, kmax=4):
    edges = set(edges)
    tree = cKDTree(V)
    added = []
    changed = True
    while changed:
        changed = False
        adj = build_adj(edges, len(V))
        for i in range(len(V)):
            if boundary[i] or len(adj[i]) >= kmax:
                continue
            _, idx = tree.query(V[i], k=12)
            for j in idx:
                if j == i or j in adj[i]:
                    continue
                # ---- NO GATES ----
                # ok, med = chord_eval(...)          # beam: commented out
                # if adj[i] & adj[j]: continue        # no-shared-neighbour: off
                # if crosses(i, j): continue          # no-crossing: off
                edges.add((min(i, j), max(i, j)))
                added.append((min(i, j), max(i, j)))
                adj[i].add(j)
                adj[j].add(i)
                changed = True
                if len(adj[i]) >= kmax:
                    break
    return edges, added


def main(front="v3_front.jpg", out="head_v13_raw.obj"):
    im, V, ink, dt = detect(front)
    edges, val, sp = extract(im, V, dt)
    base = set(edges)
    cq, _ = close_quads(V, base, dt)
    x0 = symmetry_axis(V)
    tw = pair_twins(V, x0)
    m, _ = mirror_edges(V, base, tw, dt)
    nn = cKDTree(V).query(V, k=2)[0][:, 1]
    g = de_triangulate(V, base | set(cq) | set(m), dt)
    boundary = cardinal_boundary(V, nn)
    g, _ = loop_boundary(V, g, boundary, nn)

    g2, added = raw_force(V, g, boundary)

    faces = faces_from_graph(V, g2)
    c = Counter(len(f) for f in faces)
    adj = build_adj(g2, len(V))
    interior = [i for i in range(len(V)) if not boundary[i]]
    v4 = sum(len(adj[i]) == 4 for i in interior)
    print(f"  raw-forced edges added: {len(added)}  (no beam, no gates)")
    print(f"  edges {len(g2)}  tris {c[3]}  quads {c[4]}  pent {c[5]}")
    print(f"  interior@val4: {v4}/{len(interior)}")

    P = repair_depth(reconstruct(im, V, "ellipse", 0.5))
    with open(out, "w") as fh:
        for v in P:
            fh.write(f"v {v[0]:.4f} {v[2]:.4f} {v[1]:.4f}\n")
        for f in faces:
            fh.write("f " + " ".join(str(i + 1) for i in f) + "\n")
        for a, b in g2:
            fh.write(f"l {a+1} {b+1}\n")
    print(f"  wrote {out}")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

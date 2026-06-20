"""
Rung 16 — outlier repair on the vertex coordinate matrix.

For each vertex, take its 8 nearest neighbours (by the reliable front plane:
X and height — depth is the noisy axis, so we don't let it pick neighbours).
On each axis, if the vertex's value is a wild outlier vs those neighbours
(robust z = 0.6745·|v−median|/MAD > 3.5, and the gap exceeds an absolute floor),
replace it with the neighbour mean. Robust stats (median/MAD) so one spike
doesn't hide behind its own influence.

Operates directly on an OBJ's v-matrix; faces/edges pass through untouched.

Run:  uv run --with numpy --with scipy python rung16_repair.py head_v10.obj head_v11.obj
"""

import sys
import numpy as np
from scipy.spatial import cKDTree

AXIS = ["X", "height", "depth"]          # OBJ columns: v X Z(height) Y(depth)


def main(src="head_v10.obj", out="head_v11.obj", z_thresh=3.5, floor=0.05, k=8):
    verts, passthrough = [], []
    for line in open(src):
        p = line.split()
        if p and p[0] == "v":
            verts.append([float(x) for x in p[1:4]])
        elif p and p[0] in ("f", "l"):
            passthrough.append(line.rstrip("\n"))
    V = np.array(verts)
    fixed = V.copy()

    tree = cKDTree(V[:, :2])              # neighbours by X + height only
    _, idx = tree.query(V[:, :2], k=k + 1)

    report = []
    for i in range(len(V)):
        nb = idx[i, 1:]                   # 8 nearest, excluding self
        for c in range(3):
            vals = V[nb, c]
            med = np.median(vals)
            mad = np.median(np.abs(vals - med))
            sigma = 1.4826 * mad
            gap = abs(V[i, c] - med)
            if sigma > 1e-9 and 0.6745 * gap / mad > z_thresh and gap > floor:
                newv = float(vals.mean())
                report.append((i, AXIS[c], V[i, c], newv, gap))
                fixed[i, c] = newv

    report.sort(key=lambda r: -r[4])
    print(f"  {len(V)} verts, {k}-NN robust outlier repair "
          f"(z>{z_thresh}, floor {floor})")
    print(f"  repaired {len(report)} coordinate(s):")
    for i, ax, old, new, gap in report[:25]:
        print(f"    v{i:3} {ax:6}  {old:+.3f} -> {new:+.3f}   (gap {gap:.3f})")
    if len(report) > 25:
        print(f"    ... and {len(report)-25} more")
    by_axis = {a: sum(1 for r in report if r[1] == a) for a in AXIS}
    print(f"  by axis: {by_axis}")

    with open(out, "w") as fh:
        for v in fixed:
            fh.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
        for line in passthrough:
            fh.write(line + "\n")
    print(f"  wrote {out}")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

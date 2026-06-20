"""
Rung 19 — just the point cloud. Extract the dots, place them in 3D (ellipse x0.5
depth, spike-repaired), write vertices ONLY. No edges, no faces. See the raw
vertex distribution the whole pipeline is built on.

Run:  uv run --with numpy --with opencv-python --with scipy --with scikit-image \
        python rung19_cloud.py
"""

import sys
import numpy as np

from rung9_trace import detect
from rung17_depth import reconstruct, repair_depth


def main(front="v3_front.jpg", out="head_cloud.obj"):
    im, V, ink, dt = detect(front)
    P = repair_depth(reconstruct(im, V, "ellipse", 0.5))
    with open(out, "w") as fh:
        for v in P:
            fh.write(f"v {v[0]:.4f} {v[2]:.4f} {v[1]:.4f}\n")
    print(f"  {len(P)} points -> {out}  (vertices only, no edges/faces)")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

"""
Rung 19b — render the extracted point cloud to a PNG (3 orthographic views).
Front (X up=height), side/depth (depth vs height), top (X vs depth).

Run:  uv run --with numpy --with opencv-python --with scipy --with scikit-image \
        --with matplotlib python rung19_cloud_png.py
"""

import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from rung9_trace import detect
from rung17_depth import reconstruct, repair_depth


def main(front="v3_front.jpg", out="head_cloud.png"):
    im, V, ink, dt = detect(front)
    P = repair_depth(reconstruct(im, V, "ellipse", 0.5))
    X, Y, Z = P[:, 0], P[:, 1], P[:, 2]      # X=left-right, Y=depth, Z=height

    fig, ax = plt.subplots(1, 3, figsize=(15, 6))
    fig.suptitle(f"Extracted point cloud — {len(P)} points (front view v3_front.jpg)")

    ax[0].scatter(X, Z, s=10, c="crimson")
    ax[0].set_title("FRONT  (X right, height up)")
    ax[0].set_xlabel("X"); ax[0].set_ylabel("height")

    ax[1].scatter(Y, Z, s=10, c="crimson")
    ax[1].set_title("SIDE  (depth right, height up)")
    ax[1].set_xlabel("depth"); ax[1].set_ylabel("height")

    ax[2].scatter(X, Y, s=10, c="crimson")
    ax[2].set_title("TOP  (X right, depth up)")
    ax[2].set_xlabel("X"); ax[2].set_ylabel("depth")

    for a in ax:
        a.set_aspect("equal"); a.grid(True, alpha=0.3); a.invert_yaxis() if False else None
    plt.tight_layout()
    plt.savefig(out, dpi=110)
    print(f"  {len(P)} points -> {out}")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))

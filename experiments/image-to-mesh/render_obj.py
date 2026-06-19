"""Quick offscreen render of an OBJ so we can eyeball it before importing."""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def load(path):
    V, F = [], []
    for ln in open(path):
        if ln.startswith("v "):
            V.append([float(x) for x in ln.split()[1:4]])
        elif ln.startswith("f "):
            F.append([int(p.split("/")[0]) - 1 for p in ln.split()[1:]])
    return np.array(V), F


def main(path):
    V, F = load(path)
    polys = [V[f] for f in F]
    fig = plt.figure(figsize=(12, 5))
    for i, (az, el) in enumerate([(-90, 90), (-60, 75), (0, 80)]):
        ax = fig.add_subplot(1, 3, i + 1, projection="3d")
        pc = Poly3DCollection(polys, facecolor="lightgray", edgecolor="black", linewidths=0.3)
        ax.add_collection3d(pc)
        ax.scatter(V[:, 0], V[:, 1], V[:, 2], s=1, c="red")
        for a in (ax.set_xlim, ax.set_ylim, ax.set_zlim):
            a(-1.2, 1.2)
        ax.view_init(elev=el, azim=az)
        ax.set_box_aspect((1, 1, 1))
        ax.set_title(f"az={az} el={el}")
        ax.set_axis_off()
    plt.tight_layout()
    plt.savefig("head_render.png", dpi=90)
    print("wrote head_render.png")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "head.obj")

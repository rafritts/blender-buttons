"""
Rung 4 — first correspondence pass: front grid + side-silhouette depth -> 3D.

Pragmatic, not perfect (by design — we clean up in Blender afterward):
  FRONT view  -> (X, Z) vertex grid + faces  (real)
  SIDE view   -> depth envelope D(height)     (real, from the silhouette —
                 robust, avoids the fragile dense-region graph)
  loft        -> each front vertex bulged forward by an elliptical cross-
                 section scaled to the side depth at its height

Front + side are the two top quadrants of ONE 4-up sheet, so they're the same
head at the same scale (rung 2). Output: head.obj for manual import to Blender.
Eyes/nose/mouth will be rough; that's expected — they get fixed or swapped.
"""

import sys
import numpy as np
import cv2
from scipy import ndimage as ndi
from skimage.morphology import skeletonize, remove_small_objects
from rung3_extract_graph import build_graph


def detect_crop(crop):
    B, G, R = (crop[..., 0].astype(int), crop[..., 1].astype(int), crop[..., 2].astype(int))
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    red = ((R - (B + G) // 2) > 16) & (R > 45)
    red = remove_small_objects(red, 1)
    lbl, n = ndi.label(red)
    V = np.array(ndi.center_of_mass(red, lbl, range(1, n + 1)))  # (y,x)
    lines = (gray < 120) & ((R - (B + G) // 2) < 12)
    lines = remove_small_objects(lines, 15)
    skel = skeletonize(lines)
    return V, skel, gray


def head_mask(gray):
    m = gray < 235
    lbl, n = ndi.label(m)
    if n == 0:
        return m
    biggest = 1 + np.argmax(ndi.sum(np.ones_like(lbl), lbl, range(1, n + 1)))
    return ndi.binary_fill_holes(lbl == biggest)


def quads_from_edges(V, edges):
    adj = {i: set() for i in range(len(V))}
    for a, b in edges:
        adj[a].add(b); adj[b].add(a)
    faces = set()
    eset = set(edges)
    for (a, b) in edges:
        for c in adj[a]:
            if c == b:
                continue
            for d in adj[b]:
                if d == a or d == c:
                    continue
                if (min(c, d), max(c, d)) in eset:
                    faces.add(tuple(sorted((a, b, d, c))))
    return faces


def loft_front(front, depth_of_row, top_s_bot_s, out="head.obj"):
    """Shared loft: front grid + a depth(row) function -> 3D OBJ."""
    Vf, skel_f, _ = detect_crop(front)
    edges, spacing, _ = build_graph(Vf, skel_f)
    faces = quads_from_edges(Vf, edges)
    print(f"  front: {len(Vf)} verts, {len(edges)} edges, {len(faces)} quad faces")

    mf = head_mask(cv2.cvtColor(front, cv2.COLOR_BGR2GRAY))
    rows_f = np.where(mf.any(1))[0]
    top_f, bot_f = rows_f.min(), rows_f.max()
    xc = np.full(front.shape[0], front.shape[1] / 2.0)
    hw = np.ones(front.shape[0])
    for y in range(top_f, bot_f + 1):
        xs = np.where(mf[y])[0]
        if len(xs):
            xc[y] = (xs.min() + xs.max()) / 2.0
            hw[y] = max(2.0, (xs.max() - xs.min()) / 2.0)

    top_s, bot_s = top_s_bot_s
    verts3d = []
    for (vy, vx) in Vf:
        z = bot_f - vy
        yy = int(np.clip(vy, 0, front.shape[0] - 1))
        x = vx - xc[yy]
        w = hw[yy]
        frac = float(np.clip(x / w, -1, 1))
        f = (vy - top_f) / max(1, (bot_f - top_f))
        D = depth_of_row(f, w)
        y = np.sqrt(max(0.0, 1 - frac * frac)) * (D / 2.0)
        verts3d.append((x, y, z))
    verts3d = np.array(verts3d)
    verts3d -= verts3d.mean(0)
    verts3d /= (verts3d[:, 2].max() - verts3d[:, 2].min()) / 2.0

    with open(out, "w") as fh:
        for v in verts3d:
            fh.write(f"v {v[0]:.4f} {v[2]:.4f} {v[1]:.4f}\n")
        for q in faces:
            fh.write("f " + " ".join(str(i + 1) for i in q) + "\n")
        for a, b in edges:
            fh.write(f"l {a+1} {b+1}\n")
    print(f"  wrote {out}  ({len(verts3d)} verts, {len(faces)} faces, {len(edges)} edges)")
    print("  import in Blender: File > Import > Wavefront (.obj)")


def main_single(path):
    """Full-res single front view + GENERIC depth (no side). Recognizable
    relief; depth is assumed (~1.3x local width), not reconstructed."""
    front = cv2.imread(path)
    loft_front(front, depth_of_row=lambda f, w: 1.3 * 2 * w, top_s_bot_s=(0, 1))


def main(path):
    im = cv2.imread(path)
    H, W = im.shape[:2]
    front = im[0:H // 2, 0:W // 2]
    side = im[0:H // 2, W // 2:W]

    # --- FRONT: vertex grid + faces ---
    Vf, skel_f, _ = detect_crop(front)
    edges, spacing, _ = build_graph(Vf, skel_f)
    faces = quads_from_edges(Vf, edges)
    print(f"  front: {len(Vf)} verts, {len(edges)} edges, {len(faces)} quad faces")

    # front extents -> centerline X_c(row) and half-width W(row)
    mf = head_mask(cv2.cvtColor(front, cv2.COLOR_BGR2GRAY))
    rows_f = np.where(mf.any(1))[0]
    top_f, bot_f = rows_f.min(), rows_f.max()
    xc = np.full(front.shape[0], front.shape[1] / 2.0)
    hw = np.ones(front.shape[0])
    for y in range(top_f, bot_f + 1):
        xs = np.where(mf[y])[0]
        if len(xs):
            xc[y] = (xs.min() + xs.max()) / 2.0
            hw[y] = max(2.0, (xs.max() - xs.min()) / 2.0)

    # --- SIDE: depth envelope D(row) from silhouette ---
    ms = head_mask(cv2.cvtColor(side, cv2.COLOR_BGR2GRAY))
    rows_s = np.where(ms.any(1))[0]
    top_s, bot_s = rows_s.min(), rows_s.max()
    depth = np.zeros(side.shape[0])
    for y in range(top_s, bot_s + 1):
        xs = np.where(ms[y])[0]
        if len(xs):
            depth[y] = xs.max() - xs.min()

    # --- LOFT each front vertex into 3D ---
    verts3d = []
    for (vy, vx) in Vf:
        z = bot_f - vy                       # height (up positive)
        x = vx - xc[int(np.clip(vy, 0, front.shape[0] - 1))]
        w = hw[int(np.clip(vy, 0, front.shape[0] - 1))]
        frac = float(np.clip(x / w, -1, 1))
        # map this height to the side view (rung-2: heights are registered)
        f = (vy - top_f) / max(1, (bot_f - top_f))
        sy = int(np.clip(top_s + f * (bot_s - top_s), 0, side.shape[0] - 1))
        D = depth[sy]
        y = np.sqrt(max(0.0, 1 - frac * frac)) * (D / 2.0)   # forward bulge
        verts3d.append((x, y, z))                              # X right, Y fwd, Z up
    verts3d = np.array(verts3d)

    # normalize to ~2 units tall, centered
    verts3d -= verts3d.mean(0)
    verts3d /= (verts3d[:, 2].max() - verts3d[:, 2].min()) / 2.0

    # --- write OBJ (faces + edges so it always shows something) ---
    with open("head.obj", "w") as fh:
        for v in verts3d:
            fh.write(f"v {v[0]:.4f} {v[2]:.4f} {v[1]:.4f}\n")   # OBJ Y-up
        for q in faces:
            fh.write("f " + " ".join(str(i + 1) for i in q) + "\n")
        for a, b in edges:
            fh.write(f"l {a+1} {b+1}\n")
    print(f"  wrote head.obj  ({len(verts3d)} verts, {len(faces)} faces, {len(edges)} edges)")
    print("  import in Blender: File > Import > Wavefront (.obj)")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "single":
        main_single(sys.argv[1])
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else "multiview.jpg")

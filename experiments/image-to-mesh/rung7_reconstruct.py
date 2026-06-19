"""
Rung 7 — reconstruct a real derived head from the coherent 3-view set.

Pragmatic first mesh (rough is fine — we clean up / swap regions in Blender):
  FRONT  -> full vertex grid (X,Z) + edges + quad faces. Symmetric, both halves
            visible, so NO occlusion problem for topology.
  SIDE   -> real depth-per-height D(t) from the silhouette (nose/brow/chin
            projection), in the SAME head-height unit as the front (rung 6 proved
            the views register).
  loft   -> each front vertex bulged forward by an elliptical cross-section
            scaled to the real side depth at its height.

This is rung 4's loft but driven by COHERENT, full-res, registered views instead
of a blind ellipse on a low-res 4-up. Off-centre fine relief (eye sockets) still
awaits 3/4-per-vertex depth (next rung); the dominant facial profile is real.

Output: head_v3.obj  (import via the MCP `file op=import`).
"""

import sys
import numpy as np
import cv2
from scipy import ndimage as ndi
from scipy.spatial import Delaunay, cKDTree
from skimage.morphology import skeletonize, remove_small_objects


def detect_front(path):
    """Like rung3.detect, but FOLD THE GREEN CENTERLINE into the line skeleton —
    otherwise the non-black seam drops the centre edges and splits the mesh L/R."""
    im = cv2.imread(path)
    B, G, R = (im[..., 0].astype(int), im[..., 1].astype(int), im[..., 2].astype(int))
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    red = ((R - (B + G) // 2) > 18) & (R > 50)
    red = remove_small_objects(red, 2)
    lbl, n = ndi.label(red)
    V = np.array(ndi.center_of_mass(red, lbl, range(1, n + 1)))   # (y, x)
    green = (G - (R + B) // 2 > 40) & (G > 90)
    black = (gray < 115) & ((R - (B + G) // 2) < 12) & (~green)
    lines = remove_small_objects(black | green, 25)
    return im, V, skeletonize(lines)


def head_mask(gray):
    m = gray < 232
    lbl, n = ndi.label(m)
    if n == 0:
        return m
    sizes = ndi.sum(np.ones_like(lbl), lbl, range(1, n + 1))
    big = 1 + int(np.argmax(sizes))
    return ndi.binary_fill_holes(lbl == big)


def col_profile(mask):
    """Per-row center x and half-width from a silhouette mask."""
    H = mask.shape[0]
    rows = np.where(mask.any(1))[0]
    top, bot = rows.min(), rows.max()
    xc = np.full(H, mask.shape[1] / 2.0)
    hw = np.ones(H)
    for y in range(top, bot + 1):
        xs = np.where(mask[y])[0]
        if len(xs):
            xc[y] = (xs.min() + xs.max()) / 2.0
            hw[y] = max(2.0, (xs.max() - xs.min()) / 2.0)
    return top, bot, xc, hw


def centerline_verts(im, spacing):
    """Sample the green seam as an explicit centre column, so the wide seam
    doesn't leave a dot-void that the triangulation can't bridge."""
    B, G, R = (im[..., 0].astype(int), im[..., 1].astype(int), im[..., 2].astype(int))
    green = (G - (R + B) // 2 > 40) & (G > 90)
    ys = np.where(green.any(1))[0]
    if not len(ys):
        return np.empty((0, 2))
    out = []
    for y in range(ys.min(), ys.max() + 1, max(1, int(round(spacing)))):
        xs = np.where(green[y])[0]
        if len(xs):
            out.append((y, xs.mean()))
    return np.array(out)


def dedup(V, r):
    """Merge dots within radius r into their centroid (kills doubled detections,
    e.g. along the green seam, which otherwise poison local-spacing estimates)."""
    tree = cKDTree(V)
    parent = list(range(len(V)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in tree.query_pairs(r):
        parent[find(a)] = find(b)
    groups = {}
    for i in range(len(V)):
        groups.setdefault(find(i), []).append(i)
    return np.array([V[ix].mean(0) for ix in groups.values()])


def surface_faces(V, k=2.0):
    """Triangulate the front dots and drop triangles whose longest edge is large
    relative to the LOCAL dot spacing. Local (not global) because density varies
    — tight in the face, loose on skull/neck. Long-vs-local edges span the
    eye/mouth holes and jaw/neck concavity, so dropping them re-opens the real
    holes while keeping the whole surface faced. Uses only the clean dots."""
    d, _ = cKDTree(V).query(V, k=2)
    nn = d[:, 1]                                        # per-vertex local spacing
    floor = 0.6 * float(np.median(nn))                 # don't let local go too tight
    pts = np.column_stack([V[:, 1], V[:, 0]])          # (x, y)
    tri = Delaunay(pts)
    faces, edges = [], set()
    for a, b, c in tri.simplices:
        e = [np.hypot(*(pts[i] - pts[j])) for i, j in ((a, b), (b, c), (c, a))]
        local = max((nn[a] + nn[b] + nn[c]) / 3.0, floor)
        if max(e) <= k * local:
            faces.append((a, b, c))
            for i, j in ((a, b), (b, c), (c, a)):
                edges.add((min(i, j), max(i, j)))
    return faces, edges, float(np.median(nn))


def side_depth_fn(path):
    """D(t): full front-to-back head depth at normalized height t, in units of
    the side view's head height (== head-height unit, coherent with front)."""
    im = cv2.imread(path)
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    m = head_mask(gray)
    top, bot, _, hw = col_profile(m)
    hh = bot - top
    t = (bot - np.arange(top, bot + 1)) / hh           # 0 chin .. 1 skull
    D = (2 * hw[top:bot + 1]) / hh                      # width(=depth) in head-h
    order = np.argsort(t)
    tt, DD = t[order], D[order]
    return lambda q: np.interp(np.clip(q, 0, 1), tt, DD)


def main(front_path="v3_front.jpg", side_path="v3_side.jpg", out="head_v3.obj"):
    im, V, _ = detect_front(front_path)                # red dots = vertices
    sp0 = float(np.median(cKDTree(V).query(V, k=2)[0][:, 1]))
    V = np.vstack([V, centerline_verts(im, sp0)])      # add explicit centre column
    V = dedup(V, 0.5 * sp0)                             # merge doubled detections
    faces, edges, spacing = surface_faces(V)
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    mf = head_mask(gray)
    top_f, bot_f, xc, hw = col_profile(mf)
    Hf = float(bot_f - top_f)
    D = side_depth_fn(side_path)
    print(f"  front: {len(V)} verts, {len(edges)} edges, {len(faces)} tri faces")

    verts3d = []
    for (vy, vx) in V:
        yy = int(np.clip(vy, 0, im.shape[0] - 1))
        t = (bot_f - vy) / Hf
        X = (vx - xc[yy]) / Hf                          # head-height units
        Z = (bot_f - vy) / Hf
        frac = float(np.clip((vx - xc[yy]) / hw[yy], -1, 1))
        Y = D(t) * np.sqrt(max(0.0, 1 - frac * frac))   # forward bulge
        verts3d.append((X, Y, Z))
    verts3d = np.array(verts3d)

    # drop loose verts (false dots in no face), remap faces/edges
    used = sorted({i for f in faces for i in f} | {i for e in edges for i in e})
    remap = {o: n for n, o in enumerate(used)}
    verts3d = verts3d[used]
    faces = [[remap[i] for i in f] for f in faces]
    edges = [(remap[a], remap[b]) for a, b in edges]

    verts3d -= verts3d.mean(0)
    verts3d /= (verts3d[:, 2].max() - verts3d[:, 2].min()) / 2.0   # ~2 units tall

    with open(out, "w") as fh:
        for v in verts3d:
            fh.write(f"v {v[0]:.4f} {v[2]:.4f} {v[1]:.4f}\n")       # OBJ Y-up
        for q in faces:
            fh.write("f " + " ".join(str(i + 1) for i in q) + "\n")
        for a, b in edges:
            fh.write(f"l {a+1} {b+1}\n")
    print(f"  wrote {out}  ({len(verts3d)} verts, {len(faces)} faces, {len(edges)} edges)")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(*(a or []))

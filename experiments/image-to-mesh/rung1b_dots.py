"""
Rung 1b — clean wireframe WITH red vertex dots.

When the image gives us red dots at vertices, detection inverts: instead of
inferring vertices from where lines cross, we grab the dots DIRECTLY by color
(robust), then read connectivity from the black lines. Vertex localization
stops being a guess.

  red dots   -> vertices   (color-key red channel)
  black lines-> edges      (dark, non-red)
  valence    -> count how many line branches leave each vertex (ring crossing)
"""

import sys
import numpy as np
import cv2
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize, remove_small_objects


def main(path):
    img = cv2.imread(path)
    B, G, R = (img[..., 0].astype(int), img[..., 1].astype(int), img[..., 2].astype(int))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- vertices: red dots ---
    red_score = R - (G + B) // 2
    red = (red_score > 18) & (R > 50)
    red = remove_small_objects(red, 2)
    lbl, n = ndi.label(red)
    cents = ndi.center_of_mass(red, lbl, range(1, n + 1))
    verts = np.array(cents)  # (y, x)

    # --- edges: black lines, excluding the red dots ---
    lines = (gray < 115) & (red_score < 12)
    lines = remove_small_objects(lines, 25)
    skel = skeletonize(lines)

    # --- ring radius from typical vertex spacing ---
    tree = cKDTree(verts)
    d, _ = tree.query(verts, k=2)
    rad = max(4, int(np.median(d[:, 1]) * 0.5))

    # --- valence = number of skeleton branches crossing a ring at each vertex ---
    H, W = skel.shape
    angs = np.linspace(0, 2 * np.pi, 96, endpoint=False)
    sa, ca = np.sin(angs), np.cos(angs)

    def valence(cy, cx):
        on = []
        for s, c in zip(sa, ca):
            y, x = int(round(cy + rad * s)), int(round(cx + rad * c))
            if 1 <= y < H - 1 and 1 <= x < W - 1:
                on.append(bool(skel[y - 1:y + 2, x - 1:x + 2].any()))
            else:
                on.append(False)
        on = np.array(on)
        return int(np.sum(on & ~np.roll(on, 1)))  # rising edges around the ring

    vals = np.array([valence(cy, cx) for cy, cx in verts])

    hist = {v: int((vals == v).sum()) for v in [0, 1, 2, 3, 4, 5]}
    hist["6+"] = int((vals >= 6).sum())
    interior = vals[vals >= 3]
    frac4 = (interior == 4).mean() if len(interior) else 0.0

    print("=" * 60)
    print("RUNG 1b: clean wireframe + red dots")
    print("=" * 60)
    print(f"  vertices detected (red dots) : {len(verts)}")
    print(f"  skeleton px (black lines)    : {int(skel.sum())}")
    print(f"  ring radius (px)             : {rad}")
    print(f"  valence histogram            : {hist}")
    print(f"  median valence               : {np.median(vals)}")
    print(f"  %% valence-4 (of deg>=3)      : {100*frac4:.1f}%")
    print(f"  dead-ends (valence 1)        : {int((vals==1).sum())}")
    print(f"  isolated dots (valence 0)    : {int((vals==0).sum())}")

    # overlay: blue skeleton + dots colored by valence
    ov = img.copy()
    ov[skel] = (255, 0, 0)
    for (cy, cx), v in zip(verts, vals):
        col = (0, 200, 0) if v == 4 else (0, 165, 255) if v in (3, 5) else (0, 0, 255)
        cv2.circle(ov, (int(cx), int(cy)), 4, col, -1)
    cv2.imwrite("debug_clean.png", ov)
    print("  wrote debug_clean.png (blue=lines, green=val4, orange=val3/5, red=other)")
    print("=" * 60)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "clean_front.jpg")

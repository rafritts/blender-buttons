"""
Rung 1 — Is the AI wireframe STRUCTURAL or DECORATIVE?

Before we can triangulate anything we must know whether the image contains a
real grid (lines that actually connect into a closed quad mesh) or just a
drawing that *looks* like a wireframe.

Method: isolate the head -> pull out the dark wire-lines -> thin to 1px ->
find junctions (where lines cross) and count how many lines meet at each
(= valence) -> histogram.

The fingerprint of a real quad mesh:
  * almost every interior junction has valence 4 (quads tile into a grid)
  * only a few poles at valence 3 or 5
  * almost NO interior dead-ends (valence-1) -- a closed mesh doesn't stop mid-surface

To make the AI number interpretable we run the IDENTICAL detector on a
synthetic grid we KNOW is perfect. That calibrates "what good looks like" and
also proves the detector itself isn't the thing producing noise.
"""

import sys
import numpy as np
import cv2
from scipy import ndimage as ndi
from skimage.morphology import skeletonize, remove_small_objects
from skimage.filters import sato


# ---------------------------------------------------------------------------
# Shared detector: image (grayscale) + optional head mask -> 1px skeleton
#
# The wireframe lines are faint DARK grooves sitting on a smoothly SHADED
# surface (bright forehead -> dark jaw). Plain thresholding loses the
# low-contrast lines. So:
#   1) CLAHE to flatten the shading (equalize local contrast)
#   2) Sato ridge filter -> responds to thin line structures by SHAPE,
#      not absolute brightness  (black_ridges=True for dark lines)
#   3) threshold the ridge response, clean, thin to 1px
# ---------------------------------------------------------------------------
def extract_skeleton(gray, mask=None, thresh=0.06, min_size=25):
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(16, 16))
    eq = clahe.apply(gray)
    resp = sato(eq, sigmas=[1.0, 1.5, 2.0, 2.5], black_ridges=True)
    resp = resp / (resp.max() + 1e-9)
    if mask is not None:
        resp = resp * mask
    bin = resp > thresh
    bin = remove_small_objects(bin, min_size=min_size)
    skel = skeletonize(bin)
    return skel


def segment_head(gray):
    # head is lighter than the dark background -> Otsu, largest blob, fill, erode
    _, m = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return np.ones_like(gray, bool)
    biggest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    mask = (lbl == biggest)
    mask = ndi.binary_fill_holes(mask)
    # pull in from the silhouette where wire meets background (messy there)
    mask = ndi.binary_erosion(mask, iterations=4)
    return mask


# ---------------------------------------------------------------------------
# Graph analysis from a skeleton: valence histogram + dead-end count.
# Junction = skeleton pixel with >=3 neighbors. Endpoint = exactly 1 neighbor.
# Valence of a junction-cluster = number of distinct branch segments leaving it.
# ---------------------------------------------------------------------------
K8 = np.ones((3, 3), int)


def analyze(skel):
    sk = skel.astype(int)
    nbr = ndi.convolve(sk, K8, mode="constant") - sk  # 8-neighbor count
    endpoints = sk & (nbr == 1)
    junctions = sk & (nbr >= 3)

    # branch segments = skeleton minus the junction pixels
    branches = sk & (junctions == 0)
    lbl_branch, n_branch = ndi.label(branches, structure=K8)
    lbl_junc, n_junc = ndi.label(junctions, structure=K8)

    valences = []
    for k in range(1, n_junc + 1):
        comp = lbl_junc == k
        ring = ndi.binary_dilation(comp, K8) & (~comp)
        adj = set(np.unique(lbl_branch[ring])) - {0}
        valences.append(len(adj))
    valences = np.array(valences)

    n_endpoints = int(ndi.label(endpoints, structure=K8)[1])

    hist = {v: int((valences == v).sum()) for v in [1, 2, 3, 4, 5]}
    hist["6+"] = int((valences >= 6).sum())
    interior = valences[valences >= 3]
    frac4 = (interior == 4).mean() if len(interior) else 0.0

    return {
        "skel_px": int(sk.sum()),
        "n_junctions": int(n_junc),
        "n_endpoints": n_endpoints,
        "endpoint_ratio": n_endpoints / max(n_junc, 1),
        "valence_hist": hist,
        "frac_valence4": frac4,
        "median_valence": float(np.median(interior)) if len(interior) else 0.0,
    }


def show(name, r):
    print(f"\n  [{name}]")
    print(f"    skeleton pixels      : {r['skel_px']}")
    print(f"    junctions (deg>=3)   : {r['n_junctions']}")
    print(f"    dead-ends (deg==1)   : {r['n_endpoints']}")
    print(f"    dead-end : junction  : {r['endpoint_ratio']:.3f}   "
          f"(low = closed grid; high = decorative)")
    print(f"    valence histogram    : {r['valence_hist']}")
    print(f"    %% valence-4 (interior): {100*r['frac_valence4']:.1f}%   "
          f"(high = quad mesh)")
    print(f"    median interior val. : {r['median_valence']}")


# ---------------------------------------------------------------------------
# Synthetic perfect quad grid -> the calibration reference.
# Interior nodes are valence-4 by construction; effectively zero dead-ends.
# ---------------------------------------------------------------------------
def synthetic_grid(size=900, nx=22, ny=26, line=2):
    img = np.full((size, size), 200, np.uint8)
    rng = np.random.default_rng(0)
    m = 130
    xs = np.linspace(m, size - m, nx)
    ys = np.linspace(m, size - m, ny)
    P = np.zeros((ny, nx, 2))
    for j in range(ny):
        for i in range(nx):
            P[j, i] = (xs[i] + rng.normal(0, 4), ys[j] + rng.normal(0, 4))
    pt = lambda a: (int(a[0]), int(a[1]))
    for j in range(ny):
        for i in range(nx):
            if i + 1 < nx:
                cv2.line(img, pt(P[j, i]), pt(P[j, i + 1]), 60, line, cv2.LINE_AA)
            if j + 1 < ny:
                cv2.line(img, pt(P[j, i]), pt(P[j + 1, i]), 60, line, cv2.LINE_AA)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    img = np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
    return img


def save_overlay(path, gray, skel):
    rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    rgb[skel] = (0, 0, 255)
    cv2.imwrite(path, rgb)


if __name__ == "__main__":
    ai_path = sys.argv[1] if len(sys.argv) > 1 else "ai_wireframe.png"

    print("=" * 64)
    print("RUNG 1: is the AI wireframe structural or decorative?")
    print("=" * 64)

    # --- calibration: synthetic perfect grid ---
    g_syn = synthetic_grid()
    skel_syn = extract_skeleton(g_syn, mask=None)
    r_syn = analyze(skel_syn)
    save_overlay("debug_synthetic.png", g_syn, skel_syn)
    show("SYNTHETIC perfect quad grid (calibration)", r_syn)

    # --- the real question: the AI image ---
    g_ai = cv2.imread(ai_path, cv2.IMREAD_GRAYSCALE)
    if g_ai is None:
        print(f"\nERROR: could not read {ai_path}")
        sys.exit(1)
    if max(g_ai.shape) > 1100:
        s = 1100 / max(g_ai.shape)
        g_ai = cv2.resize(g_ai, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    mask = segment_head(g_ai)
    skel_ai = extract_skeleton(g_ai, mask=mask)
    r_ai = analyze(skel_ai)
    save_overlay("debug_ai.png", g_ai, skel_ai)
    show("AI WIREFRAME", r_ai)

    print("\n" + "=" * 64)
    print("READ:")
    print(f"  synthetic %valence-4 = {100*r_syn['frac_valence4']:.1f}% , "
          f"dead-end ratio = {r_syn['endpoint_ratio']:.3f}")
    print(f"  AI image  %valence-4 = {100*r_ai['frac_valence4']:.1f}% , "
          f"dead-end ratio = {r_ai['endpoint_ratio']:.3f}")
    print("  Wrote debug_synthetic.png and debug_ai.png (skeleton in red).")
    print("=" * 64)

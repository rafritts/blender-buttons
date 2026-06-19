"""
Rung 2 — THE MAKE-OR-BREAK: are the front and side the SAME head?

We don't need full correspondence for the verdict. The shared axis is the
lie-detector: front and side both see HEIGHT (the vertical axis). If they're
one coherent head drawn at one scale, then every horizontal landmark band
(skull top, brow, eye line, nose base, mouth, chin) sits at the same height in
both views. If the views are unrelated drawings, the heights drift apart.

Two automatic, robust measurements on the top row of the 2x2 sheet:

  A) Head vertical SPAN agreement -- does the skull-top and chin land at the
     same height in front vs side? (same scale / registration)

  B) Internal landmark agreement -- cross-correlate the vertical density
     profile of the red vertex dots. Mesh loops cluster into horizontal bands;
     if it's the same head, those bands line up. Peak at ~0 shift + high
     correlation = coherent.
"""

import sys
import numpy as np
import cv2
from scipy import ndimage as ndi


def channels(im):
    B, G, R = im[..., 0].astype(int), im[..., 1].astype(int), im[..., 2].astype(int)
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    blue = (B - (R + G) // 2) > 30
    red = ((R - (B + G) // 2) > 18) & (R > 50)
    return gray, blue, red


def head_mask(gray, blue):
    m = (gray < 235) & (~blue)
    lbl, n = ndi.label(m)
    if n == 0:
        return m
    biggest = 1 + np.argmax(ndi.sum(np.ones_like(lbl), lbl, range(1, n + 1)))
    m = lbl == biggest
    return ndi.binary_fill_holes(m)


def analyze_view(im):
    gray, blue, red = channels(im)
    mask = head_mask(gray, blue)
    # span from RED DOTS (actual vertices) -- immune to blue guide-line leakage
    ys_all = np.where(red & mask)[0]
    top, bot = int(ys_all.min()), int(ys_all.max())
    H = im.shape[0]
    prof = np.bincount(ys_all, minlength=H).astype(float)
    prof = ndi.gaussian_filter1d(prof, 4)  # smooth into bands
    n = int(ndi.label(red & mask)[1])
    return {"top": top, "bot": bot, "height": bot - top, "profile": prof, "n_dots": n}


def xcorr(a, b):
    a = (a - a.mean()) / (a.std() + 1e-9)
    b = (b - b.mean()) / (b.std() + 1e-9)
    c = np.correlate(a, b, mode="full") / len(a)
    lag = np.argmax(c) - (len(a) - 1)
    return lag, float(c.max())


def blue_guides(top_half):
    B, G, R = (top_half[..., 0].astype(int), top_half[..., 1].astype(int),
               top_half[..., 2].astype(int))
    blue = (B - (R + G) // 2) > 12          # fainter threshold
    W = top_half.shape[1]
    rowsum = blue.sum(axis=1)
    rows = np.where(rowsum > 0.25 * W)[0]    # a guide spans >25% of width
    # cluster adjacent rows into single guide lines
    guides = []
    if len(rows):
        grp = [rows[0]]
        for r in rows[1:]:
            if r - grp[-1] <= 5:
                grp.append(r)
            else:
                guides.append(int(np.mean(grp)))
                grp = [r]
        guides.append(int(np.mean(grp)))
    return guides


def main(path):
    im = cv2.imread(path)
    H, W = im.shape[:2]
    half = H // 2
    front = im[0:half, 0:W // 2]
    side = im[0:half, W // 2:W]
    top_half = im[0:half, :]

    f = analyze_view(front)
    s = analyze_view(side)
    guides = blue_guides(top_half)

    print("=" * 64)
    print("RUNG 2: are front and side the SAME head?")
    print("=" * 64)
    print(f"\n  blue guide lines (shared, Y px): {guides}")

    print("\n  A) HEAD VERTICAL SPAN")
    print(f"     front: top={f['top']}  chin={f['bot']}  height={f['height']}")
    print(f"     side : top={s['top']}  chin={s['bot']}  height={s['height']}")
    href = (f["height"] + s["height"]) / 2
    d_top = abs(f["top"] - s["top"]) / href
    d_bot = abs(f["bot"] - s["bot"]) / href
    d_h = abs(f["height"] - s["height"]) / href
    print(f"     skull-top mismatch : {100*d_top:.1f}% of head height")
    print(f"     chin mismatch      : {100*d_bot:.1f}% of head height")
    print(f"     scale mismatch     : {100*d_h:.1f}% of head height")

    print("\n  B) INTERNAL LANDMARK BANDS (red-dot density cross-correlation)")
    lag, corr = xcorr(f["profile"], s["profile"])
    print(f"     best vertical shift: {lag} px ({100*abs(lag)/href:.1f}% of height)")
    print(f"     correlation at peak: {corr:.3f}   (1.0 = bands line up perfectly)")
    # NULL test: a coherent same-head must beat its own VERTICALLY FLIPPED self.
    # If front-vs-side barely beats front-vs-flipped, the 0.91 was just the
    # generic face envelope (dense middle, sparse top), not real alignment.
    _, null = xcorr(f["profile"], f["profile"][::-1])
    print(f"     null (front vs flipped-front): {null:.3f}   "
          f"-> signal beats null by {corr-null:+.3f}")

    print("\n" + "=" * 64)
    coherent = d_top < 0.06 and d_bot < 0.06 and abs(lag) / href < 0.06 and corr > 0.5
    print(f"  VERDICT: {'COHERENT — the idea works' if coherent else 'check overlay — borderline/incoherent'}")
    print(f"  (span agreement {'OK' if d_top<0.06 and d_bot<0.06 else 'WEAK'}, "
          f"band alignment {'OK' if abs(lag)/href<0.06 and corr>0.5 else 'WEAK'})")
    print("=" * 64)

    # overlay: draw detected head spans + guides on the top half
    ov = top_half.copy()
    for g in guides:
        cv2.line(ov, (0, g), (ov.shape[1], g), (255, 200, 0), 1)
    cv2.line(ov, (0, f["top"]), (W // 2, f["top"]), (0, 0, 255), 2)
    cv2.line(ov, (0, f["bot"]), (W // 2, f["bot"]), (0, 0, 255), 2)
    cv2.line(ov, (W // 2, s["top"]), (W, s["top"]), (0, 255, 0), 2)
    cv2.line(ov, (W // 2, s["bot"]), (W, s["bot"]), (0, 255, 0), 2)
    cv2.imwrite("debug_coherence.png", ov)
    print("  wrote debug_coherence.png (red=front span, green=side span, cyan=guides)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "multiview.jpg")

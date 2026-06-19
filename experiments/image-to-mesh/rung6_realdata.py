"""
Rung 6 — does Image Edit produce METRICALLY coherent views? (real data)

Rung 5 proved the correspondence math on synthetic geometry. This validates the
*input* side on real Grok output: one generated FRONT, then two Image-Edit
rotations (3/4, side) off it (PROMPTS.md section 3). The question is whether the
edits are true rigid rotations of one head — not just plausible redraws.

Test: the bright-green centerline seam is the facial midline. In the side view
it traces the facial PROFILE (the depth curve Y vs height, shown at true scale).
In the 3/4 view that same midline is foreshortened: its sideways deflection
should equal -sin(theta) * (that same profile). So:
  - front seam should be dead vertical (wobble ~ 0),
  - 3/4 seam deflection should correlate ~1.0 with the side profile,
  - the slope recovers the 3/4 angle.
A hallucinated 3/4 view cannot track the side profile.

Result on e0f3/23cc/4f08 (front/3-4/side): corr +0.999, angle ~31 deg.
"""

import math
import numpy as np
import cv2


def green_seam(path):
    """Green centerline x vs normalized height, in head-height units.
    t=0 chin (bottom) .. t=1 skull top."""
    im = cv2.imread(path)
    B, G, R = im[..., 0].astype(int), im[..., 1].astype(int), im[..., 2].astype(int)
    grn = (G - (R + B) // 2 > 40) & (G > 90)
    ink = im.min(2) < 200                      # any non-white mark -> head extent
    ys = np.where(ink.any(1))[0]
    top, bot = ys.min(), ys.max()
    hh = bot - top
    t, gx = [], []
    for y in range(top, bot + 1):
        xs = np.where(grn[y])[0]
        if len(xs):
            t.append((bot - y) / hh)
            gx.append(xs.mean() / hh)          # normalize x by head height too
    return np.array(t), np.array(gx), hh


def resample(t, v, grid):
    o = np.argsort(t)
    return np.interp(grid, t[o], v[o])


def main(front, q34, side):
    grid = np.linspace(0.05, 0.95, 60)
    tf, gf, hf = green_seam(front)
    tq, gq, hq = green_seam(q34)
    ts, gs, hs = green_seam(side)
    GF, GQ, GS = (resample(*a, grid) for a in [(tf, gf), (tq, gq), (ts, gs)])
    dF, dQ, dS = GF - GF.mean(), GQ - GQ.mean(), GS - GS.mean()

    print(f"head heights px : front {hf}  3/4 {hq}  side {hs}")
    print(f"front seam wobble (true front -> ~0)   : std {dF.std():.4f} head-h")
    print(f"side  profile relief (depth signal Y)  : std {dS.std():.4f} head-h")
    print(f"3/4   seam deflection (foreshortened)  : std {dQ.std():.4f} head-h")

    slope = np.polyfit(dS, dQ, 1)[0]           # dQ = -sin(theta) * dS
    corr = np.corrcoef(dS, dQ)[0, 1]
    theta = math.degrees(math.asin(min(1.0, abs(slope))))
    print(f"\n3/4-vs-side fit: dQ = {slope:+.3f}*dS   corr {corr:+.3f}")
    print(f"=> recovered 3/4 angle ~ {theta:.1f} deg  "
          f"(metric rotation confirmed if corr ~ 1.0)")


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    main(a[0] if a else "v3_front.jpg",
         a[1] if len(a) > 1 else "v3_q34.jpg",
         a[2] if len(a) > 2 else "v3_side.jpg")

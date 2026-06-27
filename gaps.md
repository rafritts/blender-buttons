# MCP gaps

> **This file is a live worklist of CURRENT, OPEN gaps only.** No history lives here.
> Shipped, fixed, or retired gaps are **deleted, not archived** — use `git log -- gaps.md`
> / `git blame` to see anything past. No changelogs, no "what we shipped," no "considered
> and declined." When a gap is closed, **delete its entry**. G-numbers are **stable and
> never reused** — a missing number just means that gap was retired.

## North star

The agent's vision can **judge** but cannot **measure**; it reasons over outlines,
profiles, scalars, and named regions — never coordinate dumps. The server's job is to let
it stay in **intent-space** ("wrap the grip", "seat the bulb", "rest it on the desk") and
hand back **legible ground truth** instead of making it dead-reckon coordinates. Every gap
below is a place the agent was forced out of intent-space — into hand-trig, a self-managed
mode, or a number it couldn't trust. A gap is a general Blender primitive, never a
task-specific shortcut.

---

## G171 — `feel op=fit model=swept_tube` reports a min-bend-radius on a baked tube, but the recovered CENTERLINE is garbage on any ≥90° bend

The read was wired — `feel op=fit model=swept_tube` on a baked tube mesh reports
`min_bend_radius` / `radius_range` / `bend_feasible` + a "baked tube self-intersects"
warning. **But on a curved tube the value is wildly wrong, because the recovered centerline
itself is wrong**, and `min_bend_radius` is computed faithfully from a bad centerline.

Live evidence (clean C-tube: control points trace a half-circle, true centerline radius ~5cm,
uniform tube radius 5mm; `validate` = **0** self-intersections): the fit reports
`min_bend_radius` **0.81cm** and fires `⚠ baked tube self-intersects … < tube radius 1.04cm`
— a false positive contradicting validate. Minting the recovered centerline (`as_curve`) and
reading it with `feel op=curve` exposes the real fault: it comes back an **"S-bend, 3
inflections, turn 436.4°, len 14.7cm"** for what is a smooth **180°** half-circle of length
10.9cm. The centerline zig-zags.

Root cause is in `fit_swept_tube` (extension/fit.py): it bins verts along a **single straight
global axis** (`axis_dir`, here X) and takes each slice's centroid as a centerline point. That
holds for a gently-curved tube, but where the tube bends ≥90° it runs nearly perpendicular to
that axis (here, vertical along Z at the C's ends). A thin axis-slice there spans a tall chunk
of tube whose centroid sits far off the true arc, and consecutive end-slices leapfrog —
scrambling the centerline (and inflating `radius_range`, since those oblique slices read as
fat ellipses, `section_ab_ratio` 0.743). It is NOT the center-fan cap (the earlier
guess/guard was reverted as ineffective — proven by a byte-identical result after reinstall).

Real fix (non-trivial, needs its own verify cycle): recover the centerline by the tube's own
arc-length / local-tangent ordering — a nearest-neighbour or principal-curve walk over the
slice centroids — instead of global-axis binning, so a ≥90° bend doesn't fold the parameter.
Then `min_bend_radius` over that ordered centerline should land within tolerance of
`feel op=curve` on the pre-bake curve, and `radius_range` should track the true uniform radius.

---

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

## G171 — `feel op=fit model=swept_tube` now reports a min-bend-radius on a baked tube, but the value is wildly wrong

The read was added — `feel op=fit model=swept_tube` on a baked tube mesh now recovers a
centerline and reports `min_bend_radius` / `radius_range` / `bend_feasible` plus a
"baked tube self-intersects" warning (the original gap — no bend read on baked geometry —
is wired). **But the number is unreliable to the point of being misleading.** Live check on
a clean C-tube (control points trace a half-circle of radius 5cm = 50mm, uniform tube radius
5mm): `validate` reports **0** self-intersections, yet the fit reports `min_bend_radius`
**0.81cm** (~8mm — 6× too small vs the true ~50mm) and `radius_range` up to 1.04cm (2× the
true 5mm), and fires `⚠ baked tube self-intersects: min bend radius 0.81cm < tube radius
1.04cm` — a **false positive that directly contradicts `validate`'s clean verdict on the same
mesh**. Almost certainly an interaction with the new center-fan end caps (the [G161]/[G177]
fix): the cap's near-coincident centroid becomes a degenerate end "ring," and the Menger
curvature over three consecutive ring centroids spikes there, collapsing the reported min bend
radius. Candidate fix: exclude the cap end-rings (or any near-zero-radius ring) from the
min-bend-radius pass, and reconcile the radius_range estimate so it tracks the true uniform
radius rather than inflating at the bend; verify the recovered `min_bend_radius` lands within
tolerance of `feel op=curve` on the pre-bake curve.

---

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

## G87 — selection not reliably preserved across `transform op=move_verts` → `edit` (intermittent)

`select op=all` → `transform op=move_verts` → `edit op=taper_end`, issued one-per-message
(per the chaining rule). On one mesh the taper landed; on an identical sequence on the next
mesh the taper **no-op'd**, and re-issuing `select op=all` immediately before the taper
fixed it. The live edit-mode selection appears not to survive a `move_verts` reliably.
**Want:** edit-mode selection state to persist deterministically across consecutive
edit-mode mutations regardless of which verb (`transform` vs `edit`) issues them.
**Status:** `move_vertices`/`scale_vertices` now call `bm.select_flush_mode()` before the
editmesh→mesh sync (matching every `select_*` op), so the edge/face selection is re-derived
from the moved verts and survives the OBJECT↔EDIT round-trip a following edit op triggers.
The headless round-trip case now passes (`tests/e2e_gaps_g91_g95.py`). **Still unconfirmed
on the live one-op-per-message path** — the original failure never reproduced headless, so
keep this open until a live dogfood run confirms the intermittency is gone.

---

## G99 — no parametric field deformer: apply σ(t) across a selection along an axis

Reshaping a skirt sub-shell (flared → pencil column) wanted one move: *apply a continuous
profile function across these verts along this axis*. There is no such primitive.
`taper_end` is the nearest thing and it **misfires on a fused mesh** — it indexes the
global ring structure (4196 rings) and grabbed a bevel sliver instead of the skirt wall, so
it no-op'd. The fallback was hand-banding: `scale_verts` on three Z-bands by three
constants — which flattened each band to a cylinder and **stepped at the junctions**
(`region_form` measured a 6.35 mm concave dip across the band-stack, perfectly L/R
symmetric — i.e. structural facets, not noise). The agent was forced out of intent-space
("taper to a column following these measured radii") into a piecewise-constant
approximation that looks blocky.

**Want:** a field/profile deformer over the **current selection** —
  • **parameter:** normalized position `t∈[0,1]` along a chosen `axis`;
  • **transform:** radial scale about the axis, `r' = σ(t)·r`, **multiplicative by default**
    (preserves pleats/asymmetry), with an absolute mode;
  • **anisotropic:** independent `σ_x(t)`, `σ_y(t)` (sections are ellipses, not circles);
  • **σ spec:** named families (`taper`, `power(k)`, `smoothstep`, `bell`, `sine`), control
    points `[[t, scale], …]`, or a provenance-clean `expr` escape hatch (params derived from
    measured radii = math on ground truth, not divination).
**Critical impl note:** bin the rings from the **selection's own verts** along the axis
(centroid + radius per bin), *never* the global mesh ring index — that binning is exactly
what `taper_end` gets wrong and what makes the field work on a sub-shell of a many-shell
mesh. Add `about: axis | spine` (straight centerline vs per-ring medial centroid, for
curved parts; ship `axis` first).
**Generalizes** `taper_end`/`taper_section`/`scale_rings`/`shape_profile`/`flute`
(angular parameter) and `twist` (rotation transform) into one primitive — parameter
∈ {axis-pos, angle, radius} × transform ∈ {radial-scale, axial-offset, twist}.
`edit op=shape_profile` is the embryo (control points by ring_index + absolute radius);
rebase it on selection-binned normalized `t`, analytic σ, and per-axis.

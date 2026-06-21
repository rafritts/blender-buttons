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

## G99 — no field deformer: apply an arbitrary function `p' = F(p)` over a selection

A whole class of edits is one move: *apply a function across these verts*. There is no
such primitive, so each shape gets a bespoke op and the off-pattern cases fall through.
Two dogfood drivers:
  • **Skirt (flared → pencil column).** Wanted a continuous radial profile `σ(t)`.
    `taper_end` is the nearest thing and **misfires on a fused mesh** — it indexes the
    global ring structure (4196 rings) and grabbed a bevel sliver instead of the wall, so
    it no-op'd. Fallback was hand-banding: `scale_verts` on three Z-bands by three
    constants → each band flattened to a cylinder and **stepped at the junctions**
    (`region_form`: 6.35 mm concave step, perfectly L/R symmetric — structural facets).
  • **Wavy hair.** "Select the hair, `sin()` it." Naive `sin(z)` on world coords shears the
    whole hair mass in lockstep and detaches the roots — useless. The real expression is
    `A·(s/L)·sin(2π·s/λ + φ)`: `s` = arc-length *down each strand* (not world Z), `(s/L)` =
    envelope pinning the root, `φ = hash(strand)` = per-strand phase. Every term is a
    *geometry-derived variable the tool must expose*, evaluated **per component** (per strand).

**Want:** a general point-field over the **current selection**: `p' = p + F(p)` (vector) or a
**scalar** `f(...)` driving one channel. The expression engine is the easy part — the value is
the **per-vertex variable namespace** (a clean parameterization measured from the geometry,
which is also what keeps `custom` on the ground-truth side of the intent/divination line):
  • `t,u,v` normalized position along the selection's principal/bbox axes ∈[0,1];
  • `r,theta` radial dist & angle about a chosen axis;
  • `s,L` arc-length along the component & its length (strands / edge-chains);
  • `nx,ny,nz` normal; `i,ring,ci` vert / ring / component index;
  • `rnd,crnd` seeded per-vertex and per-**component** random (← per-strand phase); `pi,e`.
**Output → application:** scalar → channel `normal | axis:Z | radial(σ scale) | twist`;
vector → added in frame `world | local | tangent-normal`. **Multiplicative default** for the
scale channel (preserves detail), absolute optional. **Scope per-connected-component** (the
hair needs it). **Presets** are named cases of the same engine: `taper/power(k)/smoothstep/
bell/sine` profiles, control points `[[t,val],…]`, anisotropic `σ_x,σ_y`; `custom` is first-class.
**Critical impl notes:**
  – For the radial/profile preset, **bin rings from the selection's own verts** along the axis
    (centroid + radius per bin), *never* the global mesh ring index — that binning is exactly
    what `taper_end` gets wrong, and what makes it work on a sub-shell of a many-shell mesh.
    `about: axis | spine` (straight centerline vs per-ring medial centroid; ship `axis` first).
  – **Sandbox** `custom` (restricted AST / math-only namespace, never raw `eval` — code-exec
    surface). **Vectorize** over numpy (hair is 22.5k verts; no per-vert Python loop).
**Generalizes** `taper_end`/`taper_section`/`scale_rings`/`shape_profile`/`flute`/`twist`/
`jitter`/`noise_displace` into one primitive (parameter ∈ {axis-pos, angle, radius, arclength,
normal} × transform ∈ {radial-scale, axial-offset, normal-offset, twist, free-vector}).
**Native precedent:** this is Geometry-Nodes "Set Position" fed by a field (Warp/SimpleDeform/
Displace are narrower native versions) — not new capability, but the intent-space front-end
(select region → named geometry-derived vars → one expression) that dodges hand-wiring a node
graph. `edit op=shape_profile` is the embryo; rebase on selection-binned normalized params.
**Spec:** full self-contained design in `docs/SPEC-13-field-deformer.md`.

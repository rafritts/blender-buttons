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

## G100 (residual) — model-free continuity/coverage read for NON-tubular selections

The motivating case — the missing upper-arm skin under a deleted garment — is now solved by
**`feel op=fit model=swept_tube`** (SPEC-14): the ring-sweep decomposition reports empty axial
bins as `gaps: s∈[…]`, naming the void directly instead of reverse-engineering it from a
`sel_bounds` floor mismatch (which only ever betrayed axis-aligned gaps). That covers the
**tubular** case (limbs, fingers, any swept region).

**What remains open:** a *cheaper, model-free* continuity/coverage read for selections that
are **not** swept tubes — flat sheets, doubly-curved patches, branching regions — where
fitting a generative model is the wrong frame. Want: given a selection, report "N disjoint
pieces with gaps at <where>" / a 2D coverage map over the patch's own (u,v) showing which
cells are empty / "the surface skips this interior region", without first asserting a model.
SPEC-14's coverage grid is the embryo (it already grids the fit's parametric domain); the
sibling op would expose that occupancy read on its own, model-free. Lower priority now that
the limb case — the one that bit in dogfood — is handled.

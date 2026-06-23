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




## G106 — `edit op=extrude` on an inset cap leaves the original face → sealed double-walled pocket, not an open cavity

Carving a coffee-mug cup the textbook way — cylinder → select top → `inset` → `extrude
down` — did **not** hollow an open cup. Ground truth after the fact: the inset cap face
stayed put capping the top while the extrude built a *second* wall + floor below it, yielding
a SEALED internal pocket (`feel` read χ=3 with an internal void) that from outside looks like
a solid cylinder — no visible opening. Deleting the top cap by hand opened it but left
near-coincident internal geometry that `feel op=overlaps` couldn't see and yet the renderer
z-fought on. A `edit op=boolean DIFFERENCE` with a cutter cylinder produced a clean
thick-walled open cup in **one** step (χ=2, watertight, consistent normals). Two asks:
**(a)** `extrude` on a face region should reliably *move* the face (consume the original, the
Blender default) so inset→extrude carves an open well as expected — the current behavior
silently doubles geometry; **(b)** a first-class `op=hollow` (wall thickness + depth, wrapping
the boolean) would make cup/bowl/vessel carving a single intent-level call instead of a manual
cutter-cylinder dance. Until then: **carve cavities with `edit op=boolean`, not
inset→extrude.**

## G109 — boolean UNION (EXACT) on a tube-meets-thin-wall join shatters into degenerate boundary loops; DIFFERENCE at the same scale is clean

Welding a 4.5mm-radius handle tube onto a 4mm-walled mug where they overlapped a clean 1.1mm
(verified by `feel op=contacts`) via `edit op=boolean UNION EXACT` produced a **26-boundary-loop
mess** — one real rim plus ~25 degenerate 1–2-vertex "holes" (`feel genus` χ=−50). The same
build's `edit op=boolean DIFFERENCE EXACT` (mug cavity carve, cutter cylinder through a 4mm
wall) came back flawless: closed genus-0, watertight, 1 shell. So the fragility is specific to
UNION across a thin-wall/tube tangential join, not booleans in general. **Want:** UNION should
weld a shallow tangential overlap as robustly as DIFFERENCE cuts one (or auto-clean the
sliver/degenerate output it knows it just produced). Workflow fallback proven: for a handle on
a vessel, keep it a **separate object** with a small (~1mm) verified overlap — it reads as
connected, no gap, no lump, and dodges the UNION shatter entirely.





## G125 (residual) — auto-recognize a settled scatter so its intent doesn't need a manual declaration

A large intended scatter (70 sprinkles resting in the icing) floods the validate line until
declared. Two of the three original asks are now handled: a COLLECTION-level declaration
(`validate expect Sprinkles↔Icing`) collapses the whole class in one call (G112), and the
intend-registry now PERSISTS into the .blend (a scene custom property reloaded on open), so a
reopen no longer drops the declarations and resurrects the noise wall. **What remains:** the
floor should AUTO-RECOGNIZE a settled scatter (N instances of one source resting on one
surface) and offer / auto-apply the collection-level intent, so the agent doesn't have to
notice and declare it by hand at all. Lower priority now that the declaration is one call and
survives a reopen.

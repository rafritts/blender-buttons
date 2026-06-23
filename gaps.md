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



## G105 — mutating ops don't auto-flag a NEW/leftover open boundary the way they auto-flag penetration

A coffee mug built blind — `add cylinder cap_fill=NGON` → `select top` → `inset` → `extrude
down` → `grid_fill` — came back an **open shell**: the bottom cap was missing (a 48-edge
boundary loop at the outer rim), and nothing said so. The carve sailed through six steps and
into materials + placement; only an explicit `feel op=topology` (because the human said "feel
your mug") surfaced it. Contrast the **penetration auto-flag**: every placing op volunteers
"X now penetrates Y 6mm" unasked, so collisions never hide. Open boundaries have no such
volunteer — whether `cap_fill=NGON` silently skipped the bottom cap, or an edit consumed it,
the *symptom* (a shell that was closed and is now open, or a carve that left an unexpected
rim) is exactly the kind of thing the status block already knows how to surface cheaply.
**Want:** mutating ops to auto-note a boundary-count *delta* on objects expected to stay
closed — "⚠ topology: 'Mug' now has 1 open boundary loop (48 edges) @ bottom" — the same
unasked, one-line guard that penetration gets, so an open shell can't masquerade as a solid
through the rest of a build. (Workflow lesson also stands: `feel` a multi-step carved part
before dressing it — don't dead-reckon a whole mug. But the tool should make the failure
loud, not silent.)

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





## G125 — a large intended scatter floods the validate line and buries genuinely-new findings until it's declared

Once 70 sprinkles were resting (intentionally embedded) in the icing, EVERY subsequent op's
status block carried a truncated wall of `clipping 12x new: sprinkle_0048↔icing …(+121 more)`,
drowning the one or two findings that were actually new and relevant to the op just performed.
The fix exists — group the scatter into a collection and `validate expect Sprinkles↔icing` — but
until then the floor is pure noise, and a real new defect on the touched part would have been lost
in the truncation. (Compounding: those declarations are runtime-only and were silently lost when
the agent re-opened the .blend, so the noise wall returned and had to be re-declared.) Candidate
fixes: auto-recognize a settled scatter (N instances of one source resting on one surface) and
offer/auto-apply a collection-level intent; persist the intend-registry into the .blend so a
re-open doesn't drop it; and always show NEW-this-op findings above the truncation line, never
behind it.

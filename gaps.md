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

## G101 — shading-only ops (`edit op=smooth_edges`, etc.) trip the geometry no-op detector

`edit op=smooth_edges` on the whole donut returned `⚠ no-op: byte-identical before and
after` even though shade-smooth applied correctly. Shade-smooth changes normals / the
sharp-edge + smooth flags, never vertex positions, so the geometry-diff guard — built for
deforming ops — fires a false alarm on every shading-only mutation (smooth/flat shading,
autosmooth angle, a material assignment that moves no verts). The agent has to *know* the
warning is spurious to trust the result. **Want:** the no-op detector to scope its verdict
to what the op claims to touch — diff shading attributes for shading ops, vert positions for
deform ops — so a successful shade-smooth reports success, not a warning that reads as
failure.

## G102 — `feel op=radial` takes the inner wall on a holed/ring mesh; no way to name the outer edge

On the donut, `radial anchor=Donut angle=130` returned a point on the **inner** rim (the
hole wall, r≈0.022) reporting `r=0.0m`, when the intent was the **outer** edge at the bbox
radius — the obvious landmark for "where does the glaze drip over the rim?". A ring presents
two surfaces along any radial cast and `radial` silently takes the one nearest the axis.
Fallback was `select op=boundary` → `between` axis-band INTERSECT (computing the band factor
from the reported bounds) — three calls and a derivation for what should be one read.
**Want:** `radial` to let you name which crossing you mean — outer vs inner, first vs last
hit, or a target radius — so "the point on the outer edge at 2 o'clock" is a single landmark.

## G103 — `transform op=scale` (scale_group) on instanced/multi-user meshes half-applies, then dirties the world

The 120 scattered sprinkles share one mesh datablock (scatter makes multi-user instances).
`scale_group ×1.07` on the group **mutated all 120 object transforms and then aborted** with
"Cannot apply to a multi user" when it reached the `transform_apply` that bakes scale into
mesh data — leaving the objects half-transformed AND tripping the SPEC-15 dirty-world lock,
which then mis-attributed the server's *own* aborted op as external mutation (120 phantom
"moved/scaled by something other than this server" entries). Two distinct gaps: **(a)
atomicity** — a group op that can't finish should mutate nothing and raise before touching
state, not half-apply; **(b)** instanced objects don't need the mesh-data bake at all —
object-level scale renders correctly — so `scale_group` should keep object-level scale on
multi-user meshes instead of forcing an apply that cannot run. **Workflow corollary for the
guidance doc:** finalize a substrate's size BEFORE scattering onto it — scaling the substrate
afterward buries/displaces every scattered child, and there is no cheap re-seat (the only fix
was delete + re-scatter). The good news: `object op=delete name=<group>` cleanly removed all
120 + the group in one call.

## G104 — `transform op=scatter` has no up-facing / face-orientation filter

Scattering sprinkles with `align_normal=True` placed copies on **every** face of the icing —
underside and inner-hole wall included — where they're hidden or wasted. `within=` masks an
XY footprint but cannot say *which faces by orientation*. **Want:** a normal-gate (only faces
whose normal is within N° of +Z, or of a given direction) or "scatter only onto the live face
selection," so "sprinkles on top only" doesn't mean scattering 2× the count and hiding the
rest.

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

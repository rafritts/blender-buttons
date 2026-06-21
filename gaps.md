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

## G98 — no one-sided clearance read: `feel op=contacts` can't tell "shell envelops surface" from "shell stabs through it"

Asked to put clothing on a humanoid (`Body2`), I built a fitted top as a copy of the torso
skin offset outward (see G97), then tried to VERIFY it clears the body: `feel op=contacts
targets=Top,Body2`. It reported `Top: penetrating Body2 264.8mm`. That number is the
**bbox-overlap depth** — and for a garment that *correctly* envelops the torso it is exactly
what you'd expect (the body's skin is supposed to live inside the garment's bounding box).
A garment that's fitted-and-clearing and a garment that's stabbing straight through the
ribs produce the **same alarming reading**. So the one check that matters for any cladding
task — "is my shell everywhere OUTSIDE the surface it wraps?" — is unanswerable. The agent
is left certifying its own work by construction-arithmetic ("I inflated +8mm then solidified
±6mm, so the inner wall sits +2mm proud") instead of reading ground truth, which is precisely
the dead-reckoning the north star exists to kill.

This generalizes well past clothing: armor over a body, a phone case over a phone, a lid
over a jar, snow on a roof, a press-fit sleeve — every one needs *signed* nearest-surface
proximity, not bbox overlap and not unsigned distance.

**Want:** a `feel` op (e.g. `clearance`, or a signed mode on `contacts`) that samples B's
surface verts against A's surface via BVH and reports the **signed** nearest-surface
distance field: min/mean clearance, the fraction of B outside A, and the patches (with
locations) where B dips *inside* A and by how much. "Shell B clears surface A by ≥2.0mm
everywhere" should be one read, not a 264.8mm bbox figure the agent has to mentally discard.

## G97 — no surface-offset SHELL primitive: cladding a body region is an 8-call hand-fabrication

"Add clothing to `Body2`." There is no garment/cloth/shell verb anywhere in the toolset, so
"clothing" had to be improvised as a generic retopo dance: `object op=duplicate` the whole
body → `select op=between` the torso Z-band → `select op=all action=INVERT` → `edit
op=delete` the rest → `select op=all` → `edit op=inflate` (lift the copied skin off the
body so it doesn't z-fight) → `modifier op=add SOLIDIFY` (wall thickness) → `material op=set`.
Eight calls, one-per-message for the dependent edits, plus the standing 3D knowledge that a
fitted garment *is* an offset copy of the wearer's surface. It worked — a maroon tube top
now hugs the torso — but only because the agent happened to know the retopo trick; nothing
in intent-space ("clothe the torso", "clad this face", "put a rind on it") points at it.

The missing primitive is general: **make a new watertight shell that follows a surface
region, held a clearance off it, with a given wall thickness.** That single op is clothing,
armor, plating, a phone case, bark over a trunk, an apple's skin, candle wax over a wick,
shrink-wrap film. Today the only building block is the SHRINKWRAP modifier — which fits a
shell you've *already* modelled and roughly placed onto a target; it does not *create* the
region-following shell, and it has no "stand off by Nmm" clearance dial (clothing's whole
point is to float just above the skin, not snap onto it).

Related friction in the same task: the figure is T-posed, so a naive torso band-select also
grabs the **arms** where they cross the chest height. `select op=limb` selects a protrusion,
but there is no inverse "trunk only / body minus limbs" — the agent had to keep the garment
*below* the armpits (Z<1.40) to dodge the arm bar, which is why this came out a strapless
top rather than something with shoulders.

**Want:** an op (e.g. `edit op=shell` / `object op=clad`, or an `on=` clothing target) that
takes a target surface + a region (the live selection, or a named anatomical region, or the
whole mesh) + an outward `clearance` + a `thickness`, and emits a new offset shell object in
one call — the create-half of shrinkwrap, with a clearance offset baked in. Pair it with a
"trunk = mesh minus limbs" selection so garment boundaries can follow anatomy (neckline,
armholes, hem) instead of axis bands.

## G96 — `edit op=flute` ignores the live selection — always corrugates the WHOLE mesh

Building a chalice as a single lathe (one revolved body: foot · stem · knop · cup), I tried
to reed only the cup: `select op=between axis=Z` the bowl band, then `edit op=flute
flute_count=24`. The status reported success and the cup got gadroons — but so did the
**foot, stem, and knop**. A second, local flute of just the knop band (`flute_count=8`) then
superimposed an 8-lobe wave on top of the 24-lobe one *everywhere*, beating into a mess;
the foot's footprint silently grew by exactly `flute_depth`. There is no way to flute a
sub-region.

Root cause (extension/rings.py `flute`): the handler does `verts = list(bm.verts)` and
loops over **all** of them, never consulting `v.select`; worse, it takes the rotation
center `(cu, cv)` as the **whole-mesh centroid**, so even if it did filter to a selection,
an off-axis feature would corrugate around the wrong center. Every other `rings.py` op that
should be local (`scale_rings`, `taper_section`, `shape_profile`) is ring-index scoped, but
`flute` is unscoped and unaware of the selection the agent just made.

This forces the agent out of intent-space: "reed the cup" is unreachable, so the only
options are (a) accept a fully-fluted object, (b) build the cup as a *separate* mesh so the
flute can't reach the rest (defeating the single-lathe approach), or (c) hand-mask — which
the tool gives no lever for.

**Want:** when a non-empty vertex selection exists in edit mode, `flute` restricts the
corrugation to the selected verts and computes its rotation center/axis from that selection
(its bbox center on the cross-plane), so a band can be reeded without touching the foot;
fall back to whole-mesh + mesh centroid only when nothing is selected. Same fix likely
applies to any other `rings.py` op that reads `bm.verts` wholesale rather than the
selection. Repro: `tests` could assert that fluting a Z-band of a tall cylinder leaves the
rings outside the band byte-identical.

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

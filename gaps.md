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

## G100 — no "where are the voids / is this region continuous" read on a SELECTION

After deleting a garment shell, the question was: does the body skin underneath actually
exist, or did removing the cloth reveal a hole (VRoid deletes body mesh under clothing)?
The skin's full-mesh bbox was no help — head + legs set the Z-extremes, so a hollow torso
or a missing arm segment is invisible in the bounds. There is no op that, given a live
selection, reports **where its geometry is absent** — the internal voids, the discontinuities,
the spans the surface skips. `feel op=topology boundaries` lists open edge loops, but
whole-mesh and far too noisy (130 loops here from hair cards / lash strips / tube caps) to
point at "the upper arm is gone."

What actually found the missing upper-arm skin: `select op=material` to isolate the skin,
`select op=by_axis X>0.166 INTERSECT` to clip to the arm, then **reading the `sel_bounds` X
floor** — I asked for verts past 0.166 and the selection's floor came back 0.344, an 18cm
span with no geometry. The void announced itself only as a mismatch between the threshold I
asked for and the floor I got. That's reverse-engineering a hole from a bounds number, and
it only works because the gap happened to lie along a clean axis; a void in the middle of a
patch, or a non-axis-aligned one, would leave the bounds unchanged and stay invisible.

**Want:** a read that takes the current selection (or a named region) and reports its
**continuity / coverage** in intent-legible terms — "this selection is N disjoint pieces
with gaps at <where>", or a coverage map along an axis showing which bands are empty, or
"the surface skips X∈[0.17,0.34]". The agent should be able to ask "is this region solid, or
is there a hole, and where?" directly, instead of inferring absence from a bounds floor that
only betrays axis-aligned gaps. Distinct from `components` (whole-mesh shell list, no
selection scope, doesn't say *where* the missing material is relative to what's present).

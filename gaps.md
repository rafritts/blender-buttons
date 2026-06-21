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

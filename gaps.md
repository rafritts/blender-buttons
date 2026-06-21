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
mesh the taper **no-op'd** (the no-op guard correctly flagged byte-identical geometry), and
re-issuing `select op=all` immediately before the taper fixed it. So the live edit-mode
selection appears not to survive a `move_verts` reliably — `move_verts` lives under the
`transform` verb but mutates verts in edit mode, and the following `edit` op sometimes sees
an empty/stale selection. The no-op detector is doing its job; the underlying
non-determinism is the gap — it forces a defensive re-select before every edit op that
follows a `move_verts`.
**Want:** edit-mode selection state to persist deterministically across consecutive
edit-mode mutations regardless of which verb (`transform` vs `edit`) issues them.
**Lead (unconfirmed):** not reproducible in the headless harness across repeated
`select_all → move_verts → taper_end` runs — it only bites the live one-op-per-message
path. Suspect the OBJECT↔EDIT mode-cycle in `execute_command` (`_enter_edit_for_target`):
whether a call enters via the "already in EDIT, skip the toggle" branch or force-cycles
modes depends on what mode the previous op left behind, and the toggle round-trips the
component selection through Blender's editmesh↔mesh sync. A deterministic fix likely lives
in making that entry/exit consistent rather than in `taper_end` (which reads no selection).

## G91 — no way to verify TOPOLOGICAL LINKAGE between two parts (threaded vs merely touching)

Connecting a chain to a watch bow needed a bail (a ring threaded through both the bow's
wire and the chain's end link). The agent could place and size the bail, but had **no way
to confirm it was actually linked** rather than resting against the outside: `feel
op=distance` returns ~0 for BOTH "threaded through the hole, wires near contact" and "two
rings tangent on their outer surfaces." `op=overlaps` only catches coplanar interpenetration
(useless for perpendicular rings), and `op=contacts` reports bbox penetration depth, which a
correct interlink and a bad clip share. So the one fact that matters here — *is A linked to
B?* — is unreadable, and the agent was forced into blind place-nudge-resize-eyeball loops
toward a result it could not verify (and nearly reported "linked ✓" off an ambiguous number).
The human closed it in ~2 s with `G`/`S` because they could SEE the linkage. This is the
canonical hand-off case, but it's a gap precisely because the agent had no ground-truth read
to stand on.
**Want:** a `feel` read that answers linkage directly — e.g. `op=linked a=<part> b=<part>`
returning a boolean + linking-number (does A's wire pass through B's hole / are they a
non-separable pair), computed from the meshes (Gauss linking integral over the two loops, or
a pierce test of one shell's hole-disk against the other's wire). Bonus: a relational
primitive to CREATE the link — `add`/`transform` "thread ring through <A> and <B>" that
seats a new loop linking two existing loops without hand-placed coordinates.
**Lead (unconfirmed):** for two closed-loop wire shells, extract each shell's centerline
loop and compute the Gauss linking number pairwise; |Lk|≥1 ⇒ linked. Cheap approximation:
cap one ring's hole with a disk and count signed intersections of the other ring's
centerline through it. Both are robust to the touching/threaded ambiguity that defeats
surface distance.

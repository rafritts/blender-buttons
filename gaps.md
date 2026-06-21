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

## G92 — `taper_section` scales RELATIVE TO CURRENT radius, so adjacent sections double-scale the shared boundary ring (collapse), and there's no absolute per-ring target

Shaping a surface of revolution (goblet, hourglass) from a loop-cut cylinder is the
intended lathe substitute: `taper_section from_ring..to_ring x_start..x_end`. But the
scale factor is applied to each ring's **current** radius, not to a reference. So when you
tile the profile as touching ranges — foot `0..4`, stem `4..11`, bowl `11..23` — the
shared endpoints (rings 4 and 11) get scaled by BOTH sections and collapse: 0.055 × 0.18 ×
0.16 = 0.0016 m, a pinhole pinch where the profile should be ~0.009. The interior rings are
fine (scaled once); only the seams crater. The workaround is to leave a one-ring gap
between ranges (hourglass: `0..12` and `13..25`, neck left as two rings) and then repair
each seam by hand with `scale_rings [n]` at a back-computed factor (target ÷ current) — a
divide-by-the-thing-you-just-broke dance, and you only learn it failed by reading `profile`
after. The relative model also means you cannot say "make ring 7 exactly 12 mm"; every
number is a ratio against a radius you have to remember or re-read.
**Want:** a profile-shaping op addressed in **absolute radii** — e.g.
`shape_profile axis=Z points=[(z|ring, radius), ...]` that sets each ring's radius outright
and interpolates between, idempotent and seam-safe by construction. Failing that,
`taper_section` should at minimum (a) take absolute `r_start`/`r_end` as an alternative to
ratio scales, and (b) make touching ranges safe — a ring named as the endpoint of two
calls should land at one well-defined radius, not the product of both scales.

## G93 — `array_radial start_angle=` with the default `end_angle=360` makes an ARC, not an offset full circle (silent uneven spacing)

Wanted 4 frame posts evenly at 90° but rotated 45° off-axis (so none sits dead-centre in
the front view). `array_radial count=4 start_angle=45` produced "arc 45→360°, step 105°" —
four copies at 45/150/255/360, uneven, with the last overlapping the first. The full-circle
case only works when `start_angle=0` (then `360/count` divides cleanly); any nonzero start
silently becomes a partial sweep because `end_angle` defaults to 360 instead of
`start+360`. The fix as a user is to pass `end_angle=405`, which is non-obvious and easy to
ship wrong (the copies look plausible until you count them). Partial arcs are a legitimate
feature — the gap is that "evenly spaced full ring, just rotated" is the common intent and
is the one that misfires.
**Want:** when the arc spans a full turn, spacing should be `360/count` regardless of
`start_angle` (treat default `end_angle` as `start_angle+360`), OR a distinct
`offset_angle=` that rotates a full ring without touching the arc math. Reserve
`start/end_angle` for deliberately partial fans.

## G94 — no meridional (vertical) loop selection, so you can't flute/gadroon a surface of revolution

A goblet bowl wants vertical flutes/gadroons — the signature ornament of a turned vessel.
Every primitive for it is missing: `select op=ring/rings` selects loops **perpendicular to
an axis** (the horizontal rings), but flutes need the **meridional** loops (the vertical
columns from rim to foot). There's no "select every Nth meridian" and no radial-flute
op, so the only paths are (a) boolean an array of cutter cylinders into the curved wall —
heavy, and the cutters must follow the flare angle, or (b) hand-pick vertical edges, which
the selection surface can't express. I fell back to *applied* ornament (arrayed bands,
beads, gem cabochons) instead, which is fine but sidesteps the actual feature.
**Want:** either meridional selection (`select op=meridians count=N` / every-Nth vertical
loop on a lathed mesh), or a direct `edit op=flute axis=Z count=N depth= profile=concave|
convex` that cuts evenly spaced grooves/lobes following the surface — the general
"corrugate a surface of revolution" primitive (flutes, gadroons, reeding, columns all fall
out of it).

## G95 — `add type=floor` fails with "Unknown placement key(s) ['z']"

`add type=floor size=3` errored: *Unknown placement key(s) ['z']. Valid keys:
[at_corner, axis, behind, ...]*. The floor path injects a `z` placement key its own
placement DSL then rejects — a self-inflicted bug; `floor` is unusable as documented. Worked
around with `add type=plane width=3 depth=3 on={on_floor:true}`, which is what `floor`
should reduce to anyway.
**Want:** `add type=floor` to spawn a ground plane at z=0 without emitting an illegal
placement key (or drop the type in favour of `plane on_floor`, but then remove it from the
`add` menu so it isn't a trap).

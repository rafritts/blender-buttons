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

_G203–G216 (the bead-of-icing donut-dogfood autopsy) were fixed and verified against
headless scenes — see `git log -- gaps.md` and `tests/e2e_g203_g216_deform.py`,
`e2e_g204_g207_scatter.py`, `e2e_g209_g212_handles.py`, `e2e_g214_bud.py`. Live re-verify
on the motivating donut scene (2026-07-10): G208/G212/G213/G215 hold up — refuse-before-
mutate fired with the meters hint, radial crossing=rim landed on the hem, one inflate
stroke auto-densified 124 edges and made a smooth +3.6mm dome with zero self-intersections.
G214's `bud` passed its closed-host e2e but fails live on the OPEN clad shell it was born
for — reopened as G217._

## G217 — `bud` on an open clad shell: EXACT eats the bead, FLOAT leaves a membrane — both report success

Live on the donut icing (the scene that minted G214): `bud host=Icing handle=hem_90
diameter=0.008` with the default EXACT solver reported "budded ✓ … welded 0 verts" while
the boolean DISCARDED the entire bead body — the mesh gained only 13 valence-2 scar verts
tracing the intersection ring, zero geometry below the hem ("welded 0" was the only tell).
solver=FLOAT keeps the bead (+174 verts, fused, hangs 9mm) but leaves 10 non-manifold
edges, two pinhole boundary loops, and χ=1 "impossible topology" — intent-free defects
with no suppression path, so the floor nags forever. A scoped merge-by-distance closed the
pinholes and halved the non-manifold count but cannot remove the interior MEMBRANE (the
bead's cap crossing between the shell's two walls) — repair doesn't compose in agent-reach
calls. The macro's warning even points to "apply its Solidify first" — advice a clad shell
can't take (it has no Solidify modifier; clad bakes its walls directly). The general
primitive: bud must be correct on the open shell its motivating intent lives on — delete
the bead cap and wall faces inside the fuse ring and WELD the bead's neck ring to the cut
ring (a local bridge, no global boolean), or at minimum DETECT the discarded-operand case
(result Δverts ≪ bead verts) and refuse+restore instead of reporting success. A macro
whose failure mode is "success" is worse than no macro.

## G219 — two selection stores: grow/flood silently no-op on seeds they can't see

Live on a VRoid body (semantic-selection dogfood, 2026-07-10): a fingertip seed minted
by `select op=by_index` would not grow — `op=grow steps=4` answered "GROW x4" while the
count sat at 16 before and after, in OBJECT mode *and* in EDIT mode; `op=flood` at least
reported its own no-op ("flooded 16 seed → 16 verts"). The IDENTICAL region seeded by an
edit-mode `by_axis`+`between INTERSECT` chain grew perfectly (208→250). So selections
live in two stores (mesh datablock vs live bmesh): the status block, `op=list`, and
handle-minting read one; the expansion walkers read the other; and ops written into the
store the walkers don't read succeed *visually* while being invisible *topologically*.
Also part of the same split-brain: edit-mode ops (`by_axis`, `grow`) run from OBJECT mode
without auto-entering edit despite `target=`'s promise, and quietly work on the sync'd
copy — until one doesn't. The general fix: ONE selection store per mesh as far as every
op is concerned — every select op flushes/syncs so any op's output is any other op's
valid input, regardless of mode; and an expansion op that adds zero verts must SAY SO
("grew 0 — seed may be an island or unsynced"), never bare-announce "GROW xN". Same law
as G217: a mutation whose failure mode is "success" is worse than no mutation.

## G220 — a selection is answered with a count (or nothing), never with what got grabbed

Same session: `select op=by_axis` from object mode returned only "ok
(threshold_world=-0.6667)" — not even a count; the same op in edit mode returned
"selected=208" — a count but no shape; `op=grow` returned neither. To learn WHAT was
selected I had to spend extra calls every time: `op=current` (bbox), `op=list` (vert
dump), `feel op=silhouette selection=true` (the read that finally showed the finger was
a clean 7cm rod, not a bleed into the palm). The right 92 verts and a disastrous 92
verts return the same integer. The general fix: every mutating select answers in the
same voice as auto-status — count PLUS a one-line legible description of the grabbed
region (connected patches, extent, centroid, boundary-crossing flag), so Look/Select/
Verify collapse into the one call that made the selection. A count is not ground truth;
it's a checksum with no reference value.

## G218 — declared intents die with the addon process; they are scene facts

Reinstalling the addon (the standard deploy step) wiped the intent registry: the
long-declared Icing↔Donut contact and the icing's open rims came back as NEW findings on
the next validate, and the declarations had to be re-made from memory of what they said.
The tripwire half also silently disarmed — if the intended overlap had vanished during the
downtime, nothing would have fired. Declarations are facts about the SCENE ("this clip is
design"), not about the server process; they belong in the .blend (scene/object custom
props), loaded with it, surviving addon restarts and file round-trips alike — same
persistence class as the geometry they annotate.

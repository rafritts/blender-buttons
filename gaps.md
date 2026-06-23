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

## G107 — `feel op=resting`/`contacts` measures a cavity-seated part against the cavity RIM, not the support surface under its footprint

A slumped donut (outer radius 4.5cm) seated into a shallow plate **well** (floor flat at
z=0.008 out past radius 5cm, rim lip at z=0.013) was reported `sunk 5.0mm` /
`penetrating Plate 5.0mm` when its underside ring actually rested *exactly* on the well
floor. The 5.0mm is precisely the rim-to-floor depth: the op took the plate's **highest face
overlapping the donut's XY footprint** — the rim lip — as the support datum, even though the
donut sits entirely *inside* the well where the real support is the floor 5mm lower. Acting
on that bad reading lifted the donut 5mm and floated it; only four `feel op=aim` raycasts
(which hit the true floor at 0.008 across radii 0–5cm) exposed it. Every placing op also
volunteered the same wrong "penetrates Plate 5mm" auto-flag for the rest of the build. **Want:**
when a part nests inside a concave region, `resting`/`contacts` should measure against the
**nearest support surface directly beneath the part's lowest geometry** (a downward cast from
its underside), not the tallest footprint-overlapping face — the rim is not what it's standing
on. Workflow corollary already proven: to verify a part seated in a well, trust a downward
`op=aim` cast onto the floor over `op=resting`'s rim-referenced verdict.

**Fixed (resting half) — `check_resting`:** the datum is no longer the support's bbox top.
`_surface_under` casts straight DOWN from the part's lowest verts onto the support's BVH and
takes the highest hit — the real load-bearing surface (the well floor), not the rim. A seated
donut now reads `resting`, not `sunk 5mm`. And it's **legible**: the result carries
`support_z`, and when the support is concave (rim well above the floor) a `note` names BOTH
the surface measured against and the rim it is NOT — shown in the agent text as a `↳`
sub-line. Silent for flat supports (no new noise). Regression: `tests/e2e_gaps_g107.py`
(seated→resting, datum=floor, concave→note, flat→no note, real float still caught).
**Fixed (contacts half) — `check_contacts` + `auto_proximity_note`:** penetration is now
gated on BOTH the old all-axis bbox overlap (kept, so nothing new is ever flagged) AND a
signed crossing test `_penetration_depth` — for each of a part's verts, a point pulled 25%
toward its centroid (just INSIDE its own surface) is tested against the other solid by the
nearest face's outward normal. Pulling inward is the trick that survives MATCHED FOOTPRINTS
(the case the old comment defended bbox-overlap for): raw verts on a shared plane are
sign-ambiguous, but an interior point is unambiguously in/out. A part seated in a recess has
its interior in the open cavity → reads 0 → no false "penetrates Nmm" unasked on every
placement; a genuine sunk marker / chain link still crosses → still flagged, now with a true
inside-depth instead of the bbox overlap. Because it's an AND-gate it can only REMOVE a false
penetration, never invent or lose one. Regression: `tests/e2e_gaps_g107b.py` — an
8-vertex matched-footprint interpenetration (the hard case) still reads penetrating with a
real depth; recess-seating reads connected; flush stacks read connected. **Caveat noted:** the
signed test trusts nearest-face normals, so on a NON-watertight other-mesh (an open shell with
ill-defined normals) the gate can miss a real crossing — acceptable because (a) bbox-overlap
was the only signal there anyway and (b) a missed flag is safer than the recess false-flag it
replaces; logged for a future watertight-guard if it bites.

## G108 — `transform op=rest_on` pushes a part that straddles the target plane DEEPER instead of lifting it to rest

A plate cylinder centered on the origin (bounds z=[-0.0065, 0.0065], so half *below* the
table plane at z=0) sent through `rest_on target=floor` moved **down** 1.5mm (to
z=[-0.008, 0.005]) — further into penetration — instead of rising 6.5mm to seat its bottom on
z=0. `rest_on` only travels along −axis, so a part that already intersects/sits below the
target has no way to come up; it drops to some lower BVH hit and deepens the overlap. **Want:**
`rest_on` should resolve to genuine resting regardless of starting side — detect that the
source's lowest geometry is at/below the target and **lift** it to contact, or at minimum
refuse-and-report ("source already below target, not dropping") rather than silently pushing
it deeper. Until then: seat parts that start straddling a plane by arithmetic on the status
bbox (lowest-bound → target-top delta), not `rest_on`.
**RESOLVED 2026-06-23:** rest_on now casts each ray from ABOVE the target's top (not from the
vert), so a vert already at/below the target still finds the surface beneath it and yields a
SIGNED clearance — the part is LIFTED to rest (negative `dropped_mm`, shown as ↑ in the verb)
when it straddles or sits below, dropped when above. Genuine resting from any starting side.
Tested in e2e_g108_rest_on.py (straddle / above / fully-below).

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

## G110 — `history op=undo` trips the SPEC-15 external-mutation lock on the server's OWN undo

After a bad `edit op=boolean`, `history op=undo steps=2` correctly reverted it — then the very
next mutating call (`shade_smooth`) was **ABORTED** with "WORLD STATE IS DIRTY … the scene
changed by something other than this server" citing the undo's own vert/face delta on the Mug.
The undo *is* a server op; its topology change should be self-attributed, not flagged as an
external edit that forces a `history op=acknowledge` round-trip before work can resume. (Same
self-mis-attribution family as G103's aborted-op case.) **Want:** state changes the server
itself causes via `history` undo/redo should update the baseline in-place, never arm the
external-mutation lock.
**RESOLVED 2026-06-23:** `history.undo_steps`/`redo_steps` now call `_rebaseline_after_history`
on success — re-grounding the SPEC-15 clean baseline to the post-undo scene so the next op sees
it as server-known, not external. Guarded by `if not _world_locked` so a genuine external edit
(which freezes the baseline) is never erased. (undo_to/restore delegate to undo_steps → covered.)
Tested in e2e_spec15_interlock.py.

## G111 — `validate` clipping DEPTH is nonsensical for small objects and doesn't update after a real move

The always-on floor reported `clipping NEW Donut↔Spr__0010 77.7mm` for a 6mm sprinkle that
`feel op=clearance` showed grazing the donut by **0.5mm** (13 verts inside, max 0.52mm). The
magnitude is off by ~150×, and after lifting the whole sprinkle group a real +0.9mm the floor
reprinted the **identical** "77.7mm" — i.e. the reported depth is not a live penetration
measurement at all (looks like a bbox-overlap or diagonal proxy), yet it's printed in `mm` as
if it were. This actively misleads: trusting it, I deleted ~20 correctly-placed sprinkles
chasing a "deep" clip that `feel` proved was a sub-millimetre graze. **Want:** either make the
clip line report the true BVH penetration depth (the number `feel op=clearance` already
computes), or drop the bogus magnitude and just name the pair + a verified-or-unknown flag, so
the floor's number can be trusted the way the status bbox can. Until fixed: **never act on a
`validate` clip magnitude for small parts — confirm with `feel op=clearance`/`overlaps` first.**
**RESOLVED 2026-06-23 (SPEC-16):** the clip line now recomputes the TRUE max vertex-penetration
depth (the signed nearest-surface read `feel op=clearance` uses) on every report, and gates on
it — sub-0.3mm grazes are dropped, not screamed as tens of mm. A matched-footprint overlap the
vertex sampling can't measure is still flagged but with a `feel op=clearance to measure` hint
instead of a bogus number (extension/validation.py `_true_penetration_mm`).

## G112 — `validate` reports "by exception" capped at ~4 findings, with no full-list mode, no bulk-declare, and no way to forget a declaration

Three compounding holes made declaring a *class* of intended contacts (37 sprinkles resting on
icing/donut) impractical:
- **Capped output:** every `validate op=run` (even `targets=Donut`) prints at most ~4 NEW
  findings with no "…and N more" and no verbose/full-list flag, so enumerating a large set is
  blind whack-a-mole (declare 4 → re-run → 4 more → …).
- **No bulk declare:** `op=expect` only takes a single `(a,b)` object pair. There's no way to
  declare a whole relationship intended (e.g. `Sprinkles`-group ↔ `Icing`, or `*`↔`Icing`),
  so a legitimately-intended class of contacts can't be quieted in one move.
- **No forget:** there is no `op=forget`/clear. After deleting a declared object its entry
  becomes a permanent `VANISHED … (declared intended — confirm or clear)` line with no way to
  *clear* it — so a re-scatter that renames parts leaves a trail of un-retir­able tripwires.
**Want:** `validate op=run verbose` (or `limit=`) for the full list; `op=expect` accepting a
group/collection (or a wildcard) for one-shot class declarations; and `op=forget a= b=` to
retire a stale declaration. Together these turn "declare the few real ones" from aspiration
into something actually doable when the count is >4.
**RESOLVED 2026-06-23 (SPEC-16):** `validate op=run verbose` lists every finding (cap lifted);
`op=expect` accepts a COLLECTION token in a/b (one `Sprinkles↔Icing` covers every member);
`op=forget a= b=` retires a declaration; and declarations whose object/collection is deleted are
auto-pruned, so a re-scatter no longer leaves un-retirable VANISHED tripwires. Also (feedback
P0.1) the per-op clip line is now delta-scoped — only NEW clips on objects the op TOUCHED, with
VANISHED gated to touched pairs, so a nudge on an unrelated object no longer re-prints the registry.

## G113 — per-instance MATERIAL variety is impossible after `scatter` (shared mesh) — `material op=set` writes the datablock, last colour wins for all

`transform op=scatter` makes linked instances sharing one mesh (cf. G103). Assigning four
colours to four name-list subsets via `material op=set` left **all 37 sprinkles the last
colour** — each call wrote the shared mesh's material slot, so the spec's "colour variety"
was unreachable post-hoc. The only handle is the `sources=` param **at scatter time** (scatter
N differently-materialed prototypes, each instance picks one), which isn't discoverable from
the failure and can't be applied retroactively without a full delete + re-scatter. **Want:**
either `material op=set` on a scattered instance auto-makes-single-user that one object (so
per-object colour sticks), or a post-scatter `transform op=tint_palette`/"randomize material
from a list" over a group, or at minimum a one-line note in the `scatter` schema: *"instances
share one mesh — for colour/material variety pass `sources=` (multiple prototypes) now; it
cannot be added later."*

## G114 — `object op=join` on a SUBSET of linked instances corrupts the shared mesh for the survivors

Joining 5 of ~50 scattered (instanced, shared-mesh) sprinkles to cull them wrote the merged
5-capsule geometry **into the shared datablock**, so every *non-joined* survivor instantly
rendered as 5 overlapping capsules (bboxes exploding, dozens of spurious `below_floor`
findings). Join must not mutate a mesh other instances still depend on. **Want:** `join`
should make the target single-user before appending (or refuse + warn when the targets share a
datablock with objects outside the join set). Safe workaround found: join **all** instances of
a shared mesh then delete the result — with no survivors there's nothing to corrupt — but a
subset join is a silent footgun. (Same shared-datablock root as G103/G113.)
**RESOLVED 2026-06-23:** `join_objects` now makes the join target single-user before
`bpy.ops.object.join()` — but only when its mesh is actually shared with an object OUTSIDE the
join set (so join-all, with no survivors, copies nothing). The merge writes into the private
copy; survivors keep the pristine datablock. Reported via `made_single_user` + a note. Tested
in e2e_g114_join_linked.py (subset / join-all / independent).

## G115 — no way to VALIDATE camera focus / depth-of-field; macro-scale DOF silently blurs everything and the agent can't see it

Set `view op=camera_dof focus_object=Donut aperture=4` on a sub-metre tabletop (subject 9cm,
camera 0.27–0.78m away). At those distances f/4 behaves like extreme macro — the in-focus slab
is a few mm deep — so **all three delivered renders came back blurry**, and there was no signal
anywhere to catch it: `view op=check_framing` validates *composition* (coverage/clipping) but
says nothing about *focus*, and the (correct, G-respected) "don't read the render back" rule
means the agent has **no** feedback loop on sharpness at all. The aperture f-number is also
scale-blind — f/4 is "readable tabletop" guidance for a human-scale set but paper-thin here —
and nothing warns that the subject's own depth exceeds the DOF. **Want:** a focus analogue of
`check_framing` — e.g. `view op=check_focus` (or a `focus:` block on `check_framing`) reporting
the near/far focus limits at the current lens+aperture+distance and a pass/fail for whether each
named target's bbox falls inside the in-focus zone ("Donut 27mm deep vs DOF slab 4mm → 85%
out of focus"). Bonus: an `aperture` resolver that, given "keep the whole donut sharp," solves
the f-stop from subject depth + distance instead of making the agent dead-reckon it. Until then
the agent is flying blind on the one render property it's explicitly forbidden to eyeball.

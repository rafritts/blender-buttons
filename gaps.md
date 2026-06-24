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
**RESOLVED 2026-06-23:** `transform op=scatter up_only=True` (with `max_slope`, default 45°)
gates sampling to up-facing faces, so the underside and inner-hole walls are excluded;
`normal_dir=[x,y,z]` gates to an arbitrary direction. Density is computed over the gated area.
A gate that matches no face errors cleanly. Tested in e2e_g104_scatter_up.py. (The fuller
weight-painted / scatter-as-modifier toolchain from the dogfood's P0.3 — and per-instance
material variety, G113 — remain open as larger follow-ons.)

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
**RESOLVED 2026-06-23:** added `view op=check_focus` (introspect.check_focus) — a thin-lens DOF
model (CoC = sensor_width/1500) that reports the near/far sharp limits + hyperfocal at the
camera's current (or a hypothetical aperture/focus_distance/focus_object) settings, and a
per-target SHARP/BLURRED verdict with in-focus-% by projecting each bbox onto the lens axis.
`resolve_for=<obj>` solves the widest aperture that keeps a subject's full depth sharp ("keep
the whole donut sharp" → an f-stop). Reports when DOF is disabled. Tested in e2e_g115_check_focus.py.

## G116 — `modifier add SHRINKWRAP` could land on the wrong (active) object and leave a half-built modifier on error

The partner-modifier family forces host = the active object, so `modifier add type=SHRINKWRAP
target=Cap` while Cap is active set target==host and Blender raised "target ID … assignment to
itself" — AND the modifier created just before the failing assignment was left in the stack
(a half-built SHRINKWRAP). The agent had no way to name the receiving object, only the wrap
surface. **RESOLVED 2026-06-23:** added a `host=` param for the partner mods (SHRINKWRAP/
MESH_DEFORM/ARMATURE/LATTICE) so the agent names the object that RECEIVES the modifier instead
of relying on selection; SHRINKWRAP now rejects a self-target with a clear message and removes
the just-created modifier, and the `mod.target` assignment is wrapped so ANY failure cleans up
(no half-built modifier ever survives). Tested in e2e_shrinkwrap_partial.py.

## G117 — no periodic whole-scene re-grounding on a long build (mental model goes stale)

On a 100+-call build the per-op feedback is the right spine, but nothing ever re-surfaces the
whole picture, so the agent's mental model of objects it hasn't touched in 40 ops silently goes
stale (the SPEC-15 "ground truth is perishable" problem at the model-attention level, not the
geometry level). **RESOLVED 2026-06-23 (feedback P1.6):** added an epistemic-DRIFT checkpoint in
`extension/validation.py` — each geometry op accrues drift weighted by how much it can break
(boolean/remesh/join 25, local topology edits 8, transforms 2); when the accrued drift crosses a
threshold (100) the next result carries a whole-scene re-ground recap (object map + the
intent/tripwire registry) and the counter resets. It triggers on DRIFT, not mutation count, and
never windows the hard-defect validate floor — per-op feedback stays the spine. Tested in
e2e_spec16.py.

## G118 — a construction op can betray its own intent (hollow that seals the top, opens the bottom) and report success

Hollowing a capped cylinder with `edit inset` (top cap) → `edit extrude down` (inner face)
produced a mug that was sealed by a flat cap at the TOP and open at the BOTTOM — the cavity
opened *downward* against the table, the exact inverse of intent. Every op reported success, the
status block's world bbox looked correct (a cylinder is a cylinder by its bounds), and the
always-on validate floor passed it: the floor checks manifold/normals/z-fight/clipping, none of
which fire on "this carved the cavity the wrong way." The mesh even carried an inconsistent Euler
characteristic (χ=2 with 1 boundary loop — impossible for a real surface), which is a cheap,
decisive tell that nothing surfaced. The agent only caught it when the HUMAN said "feel the mug,"
and a deliberate `feel op=topology genus,boundaries` + a boundary-loop Z read exposed it. By then
coffee, intend-declarations, and three renders had been built on top of the broken part. The
deeper problem: the whole server doctrine is "trust ground truth, not your eyes," so an op that
succeeds-but-does-the-opposite is the single most expensive failure mode, and right now nothing
guards it. Candidate fixes: (a) flag an inconsistent Euler characteristic (χ vs boundary-loop
count) as a hard defect — it's a near-free invariant; (b) a post-hollow sanity read that the new
open boundary is where the cut was made; (c) make `feel` cheaper to reach for on a freshly-built
part (the agent felt the donut/plate/icing thoroughly and rushed the mug — the epistemic-drift
re-ground of G117 nudges this but didn't force a re-read of the just-built object).

## G119 — `validate expect` is pair-scoped, so a broad intent declaration masks a *real* defect between the same pair

Declaring `coffee↔mug` intended (reason: "the coffee surface meets the inner wall") to quiet the
rim-contact finding ALSO silenced a genuine, unrelated defect: the coffee cylinder's wide flat
base was punching through the mug's converging bottom floor (an 11mm poke-through). The
declaration is scoped to the (a,b) *relationship*, so it collapses EVERY clip between those two
objects to a count — including ones the human never blessed and never saw. The floor's entire
selling point is "there is no ignore, only declared intent," but a blunt pair-level intent is an
ignore-by-the-back-door for any second clip between the same pair. The human caught it
("coffee is clipping through the bottom — does validate not show that?"); clearing the
declaration immediately re-surfaced `coffee↔mug 11.1mm`. The agent also reached for the broad
declaration instead of fixing geometry — a scalpel used as a lid — but the tool made that the path
of least resistance. Candidate fixes: scope a declaration to a contact REGION or a depth/extent
envelope ("intended up to ~1mm at the rim; anything deeper is still a finding"), and/or report
"this intended pair now also has a clip 10x deeper / in a new location than when declared" as its
own tripwire rather than folding it into the blessed count.

## G120 — subsurf domes the base of an unsupported capped cylinder; bounds hide it, only a profile read catches it

Applying SUBSURF (level 2) to a capped cylinder with no holding loop near the bottom edge pulled
the bottom cap into a downward dome converging to a single center vertex — the form sat on a point
like an egg, and the lower third of the wall tapered inward, when the intent was a flat-based mug.
The world bbox was unchanged-looking (still ~a cylinder), so the status block gave no hint; the
defect lives in *surface shape*, which bounds don't encode. It took `feel op=profile axis=Z` over
the bottom window (single-vertex girth-0 bands at the base) to see it, and the agent only looked
because the human asked. The human's instinct — "would a loop cut work? just drag it down" — was
exactly the fix (a holding edge loop at the base before subsurf), confirmed by a rebuild that put
the base at z=0, full-width by z=4mm. Gap: subsurf-on-a-capped-primitive with no support loop is a
known-classic doming trap, and nothing warns at `modifier add SUBSURF` time (e.g. "no holding loop
within N% of a capped end — expect rounding"). The build-blind doctrine has no ground-truth read
for "is this form plausible," so form-betrayal sails through unless you already suspect it.

## G121 — `add tube` self-intersects at bends tighter than the tube radius, with no min-bend guard

Building a mug handle as a swept `add tube` self-intersected (12 interior crossings) wherever the
centerline's bend radius fell below the tube radius — i.e. the natural sharp turns where a handle
meets the body. The crossings are interior to an opaque tube (invisible in render) but register as
a permanent `self_intersection` finding that can never be cleared (no intent path for self-int,
correctly — but also no way to say "this is hidden/benign"), so they sit as standing noise. It
cost three rebuilds chasing radius/point tweaks. The server already HAS the right check —
`feel op=curve profile_radius=` reports min-bend-vs-profile — but `add tube` doesn't consult it at
creation. Candidate fixes: have `add tube`/`add curve bevel_depth` auto-run the min-bend check and
warn (or auto-resample/auto-shrink the radius at the tight spans), and/or let a self-intersection
that is fully interior to a closed shell be reported separately from surface-breaking ones.

## G122 — isolating one of two concentric boundary loops takes a 6-call dance; `in_sphere` can't center on an object/coordinate, and select→feel drops edit mode

To drip ONLY the outer rim of the icing shell (it has two concentric open boundary loops, inner +
outer), the agent had to: select-all → boundary (gets both) → `between X` ∩ `between Y` to isolate
the inner loop → enter edit mode → mint a center handle from that loop → re-select boundary →
`in_sphere DESELECT` by radius around the handle. Six calls to express "the outer of two rim
loops." Two underlying gaps: (1) `select op=in_sphere` requires a named handle to center on — it
won't take an object's bbox center or a derived point directly, so isolating-by-radius needs a
handle minted first, which itself needs a vertex selection (chicken-and-egg solved only by the
X∩Y trick). A `center=<object>` or `center=<bbox of selection>` option would collapse this. (2)
There is no "select boundary loop by index / by radius / outer-vs-inner" — boundary is all-or-
nothing. (3) The `select`→`feel op=handle source=selection` handoff failed silently because the
select ops leave the mesh in OBJECT mode (status even reads `mode: OBJECT` after a select), so
`feel op=handle` errored "must be in edit mode" until an explicit `object mode=EDIT`; the
select→mint→sculpt loop the guidance advertises has a hidden mode-state seam.

## G123 — `rest_on` overshoots below the floor, and relational `place right_of` silently rewrites Z

Two relational placements produced sub-floor results that needed manual nudge corrections. (1)
`transform op=rest_on target=floor` on the mug (which had a subsurf-rounded/domed bottom) dropped
it 8mm BELOW z=0 instead of resting its lowest point at the floor — the BVH drop overshot on the
convex base. (2) `transform op=place on={right_of: plate}` correctly set X but ALSO reseated Z to
the plate's level, burying the mug 37mm below the floor; the relational vocabulary's "right_of"
carried an unwanted vertical component. Both are "derive don't divine" ops that the agent reached
for precisely to avoid typing coordinates, and both then required a hand-typed nudge to undo their
surprise — eroding the trust the relational DSL is meant to earn. A `place right_of` should
preserve the mover's floor contact (or its current Z) unless told otherwise, and `rest_on` should
clamp at first contact, not overshoot a convex base.

## G124 — BVH penetration depth is meaningless against open/non-watertight shells; the validate "clipping Xmm" number lies, `feel op=clearance` is the truth

Sprinkles resting ON the open icing shell reported validate clippings like "sprinkle↔icing 84.9mm"
and "donut↔sprinkle 83.6mm" — physically impossible (a 6mm sprinkle, a 26mm donut). The inside/
outside test that drives the penetration-depth metric is undefined for an open (non-manifold-
boundary) shell, so it returns garbage magnitudes. The trustworthy read was `feel op=clearance
shell=… surface=…`, which correctly reported 100% clearance / 0 penetration. The agent had to
*know* to distrust one number and trust the other; nothing in the output marks the clipping depth
as unreliable when one party is an open shell. Candidate fix: when a clip party isn't watertight,
either suppress the bogus depth (report "contact, depth N/A — open shell, use clearance") or fall
back to a signed-distance-free overlap test, so the headline number can't be a fabrication.

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

## G126 — a PBR set's alpha map silently makes an opaque object invisible, and `material op=set` can't un-wire it (reusing a material name only patches Principled inputs)

`material op=pbr folder=…FoodCoffee…` auto-detected an `alpha` map and wired it into the
Principled BSDF's Alpha, so the coffee — an opaque liquid — rendered 100% transparent (read as
"invisible"). The importer treats every detected map as wanted; an alpha channel in a *surface*
scan (a coffee/crema mask, a decal cutout) is almost never meant to drive whole-material
transparency. Worse, the obvious fix failed twice: `material op=set target=Coffee base_color=…
alpha=1` *reused the existing material datablock by name* and only overrode the Principled scalar
inputs, leaving the alpha **texture node** still connected and driving transparency (`object info`
confirmed `alpha_driven: nodegraph` after the "fix"). It only became opaque once set with a NEW
`material_name`, which mints a fresh Principled node with no texture graph. Two candidate fixes:
(1) `material op=pbr` should not hook an alpha map into transparency unless asked (a `use_alpha`
opt-in, or skip alpha for clearly-opaque presets); (2) `material op=set` on an existing
name should either fully rebuild the node graph or explicitly report "texture nodes still drive
metallic/roughness/alpha — pass a new material_name to replace" so the agent isn't left fighting a
node it can't see.

## G127 — boolean UNION of an open-ended tube leaves an internal non-manifold membrane; and a hollow-vessel build needs the one reliable recipe spelled out

Attaching a mug handle by unioning a converted-curve tube (open at both ends, embedded in the wall)
into the body left 12–14 **interior** non-manifold edges at each handle root that survived a
merge-by-distance — the open tube ends became dangling membranes the EXACT solver couldn't resolve.
A boolean operand that isn't watertight should be flagged (or auto-capped) *before* the op, not
silently fused into a defect. Compounding this, two earlier mug attempts burned calls on hollowing:
`inset top cap → extrude inner face DOWN` on a closed cylinder produced a phantom **bottom**
boundary (χ inconsistent, the opening landed at the base not the mouth), and `solidify`'s grow
direction was unverifiable before applying because the status bbox reports the **cage**, not the
evaluated mesh — both ±1 offsets appeared to grow inward. The recipe that actually worked, and
that the guidance should name for "hollow open vessel": delete the top cap → `SOLIDIFY` (closes
into a rounded-rim manifold cup) → bevel the rim. Candidate fixes: auto-cap non-watertight boolean
operands; have `modifier solidify` report the evaluated thickness/offset direction in its result;
and add a `hollow`/`shell` recipe so a mug/bowl/cup isn't reverse-engineered each time.

## G128 — `feel op=radial` collapses to the bbox centre (r=0) on a holed/ring anchor, minting identical useless handles

Trying to place drip handles at clock angles around the icing, `feel op=radial anchor=Icing
angle=35/155/255` returned the **same** point `[-0.009,-0.009,0.070]` for every angle — it resolved
the ring radius to 0 and handed back the bbox centre ("r=0.0m on Z") regardless of the angle asked.
For a torus/annulus/holed shell the centre is empty space, so a centre-anchored radial cast is
meaningless; the agent got three coincident handles and had to abandon the op for a 4-call
band∩half-space selection instead. Candidate fix: `radial` should cast from the centre OUT to the
surface at the requested angle (returning the silhouette/wall hit), or detect a degenerate r=0 and
refuse with a hint, rather than silently returning the centre point as if it were on the surface.

## G129 — the always-on non-manifold floor flags legitimate OPEN geometry (a flat tabletop, a vessel mouth) as an un-silenceable defect, with no `expect` path

The correctness floor counts open boundary loops as `non_manifold` and declares them
"never OK, cannot be silenced." But a flat ground-plane tabletop (4 boundary edges) and an open mug
mouth are *correct* geometry, not defects. This forced the table from a plane to a thin box, and
would force a coffee mug to be sealed shut (hiding the coffee the spec requires) if taken at face
value. Unlike clipping — which has `validate op=expect` to declare an intended overlap — there is
no way to declare "this boundary is intended," so the count sits there forever as noise next to the
genuine defects. Candidate fix: distinguish *boundary* edges (1 face — often intentional: planes,
cup rims, cloth) from true *non-manifold* edges (3+ faces — always wrong), and either stop flagging
clean boundaries or give them an `expect`-style intent so an open vessel can be declared open.

## G130 — there is no path to a volumetric light shaft (god-ray); the verbs expose no world/volume scatter and the addon bridge is bpy.ops-only

The brief explicitly asked for a visible morning "beam through the scene." A real volumetric shaft
needs EEVEE/Cycles volumetrics enabled plus a scattering medium (a world Volume Scatter node or a
volume domain) — none of which any verb exposes: `scene world` sets a flat colour/HDRI, `material`
has emission but no volume scatter, `render` has no volumetric toggle, and `addon op=run` only
dispatches registered operators, not node/property setup. The beam had to be faked with a tight
warm spot pooling light on the hero — a legible approximation, but not the literal shaft. Candidate
fix: a `scene world volume=` (density/colour) and/or `add type=volume` + a `light … beam=true`
helper that turns on volumetrics and sizes a cone, so atmosphere/god-rays/fog are reachable without
hand-editing nodes.

## G131 — `view op=check_framing` occlusion is measured over the whole object bbox, so a partially-visible surface reads as fully hidden (and "visible in render" needs camera-vs-cavity reasoning)

A coffee cylinder filling a mug reported `100.0% occluded` from the hero camera even though its top
surface was plainly visible through the mug's mouth — the metric occludes the *whole submerged
bbox* (almost all of it is inside opaque ceramic) and so can't answer the real question, "is the
liquid surface visible?" It also surfaced a genuine staging trap the tools don't help with: a
recessed liquid in a tall vessel is occluded by its own rim at low camera elevations, so "coffee
visible in the render" silently fails until you either raise the camera or fill closer to the rim —
something the agent only caught via `check_framing` returning 100% and reasoning about it, not from
any direct read. Candidate fixes: report occlusion of the *visible silhouette / front-facing
surface* (or expose a "fraction of surface area visible") rather than whole-bbox; and a
`check_visible target= from=camera` that answers yes/no for the surface a human would actually see.

## G132 — a `SOLIDIFY thickness=0.004` produced a ~7.5–10mm wall, the rim bevel silently pinched the cavity further, and there is no in-place "thin the wall / scale the inner shell" op

A mug built as delete-top-cap → `SOLIDIFY thickness=0.004 offset=-1` → bevel-rim was reported by
the agent (by *inference* from the solidify param) as a clean 4mm wall — and a section measurement
later proved that wrong: the inner radius was 0.030 (not the assumed 0.036), making the wall ~10mm
at the rim and ~7.5mm at the un-beveled base. Two compounding gaps: (1) the solidify wall came out
~1.85× the requested thickness at the base — the `thickness` arg did not map to the produced wall,
with no feedback in the result to catch it; (2) the rounded-rim bevel on the inner mouth edge pulled
the opening inward ~6mm — far more than its 2mm width — pinching the cavity and tapering the wall,
again silently. The deeper tooling gap is that there was **no easy way to thin the wall in place**:
the inner shell can't be selected by radius-from-axis (no cylindrical/by-distance vertex select, and
`in_sphere` needs a handle and is a 3-D ball, not a tube), and flooding from an interior vert crosses
the rounded rim into the exterior. The fix that worked was a throwaway BOOLEAN-DIFFERENCE cutter
cylinder sized to the desired inner radius — effective but non-obvious. Candidate fixes: have
`modifier solidify`/its apply report the *measured* resulting wall thickness; warn when an edge bevel
on a thin-walled shell consumes a large fraction of the wall; and add an in-place `shell`/`hollow`
thickness control or a `select by_radius`/cylindrical selector so a wall can be re-thinned without
CSG. Process note for the agent: don't report a derived dimension ("4mm") as fact — `feel op=section`
is one call and the user's eyeball was right.

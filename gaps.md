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

## G133 — the auto-fired `feel`/`validate` lines show their OUTPUT but not the CALL that produced it; echoing the invocation would teach the un-predictable verbs by demonstration

Every mutating op auto-fires a perception read and a correctness check and prints their results
(`feel: Donut — 1152v 2304e · dims …`, `validate: clipping 1 new: Donut↔Plate`), but never the
command that generated them. This is a missed teaching surface, and it bites precisely the verbs an
LLM *can't* predict from Blender pretraining — `feel`/`validate` are the server's invented
vocabulary, with no prior to lean on, so they have to be learned, and the floor fires them dozens of
times per build as free worked examples that currently go unlabelled. Three concrete costs observed
this build: (1) no spaced-repetition of the differentiated verbs' syntax — the agent learns them
once from the schema instead of absorbing them by watching them run; (2) when a deeper read was
wanted, the auto-`feel` prose was ambiguous about *which* op produced it, so the agent had to guess
between `contacts`/`clearance`/`resting` instead of just re-running the op it saw fire; (3) it
obscures *what the floor actually checked*, which matters because some of those checks return
unreliable numbers (open-shell penetration, G124) and seeing the invocation would cue when to
distrust the value. Candidate fix: lead each auto-fired line with a compact echo of the call
(`⟵ feel op=all target=Donut`, `⟵ validate run targets=Donut,Plate`) — one line, not a
pretty-printed block, to keep the token cost near zero — so every automatic read doubles as a
reproducible, extendable example of the exact verb to reach for.

## G134 — the no-op detector catches "the op did nothing"; there is no symmetric alarm for "the op succeeded but degraded the geometry" at the moment it happens

The no-op detector (byte-identical before/after) is a standout — it catches the worst silent-failure
class. But its mirror image is unguarded: ops that *succeed* and quietly make a mess. This build hit
it repeatedly — `grid_fill` that folded into 15 self-intersections, a boolean UNION that left a
14-edge internal non-manifold membrane, a `solidify` that grew the wrong direction, and a wall that
came out ~2× the requested thickness — none of which *errored*. Each only surfaced on the *next*
read's `validate` line, or (the wall) not until a human eyeballed it. So the agent learns of a
geometry regression one step late, and only if it happens to read the floor output, and only if the
floor's numbers are trustworthy for that geometry (they aren't on open shells, G124). The no-op
detector already diffs the mesh before/after; the same diff could carry a topology delta and warn at
the moment of the op: `⚠ this op added 2 boundary loops / 14 non-manifold edges / 15
self-intersections / changed genus 0→?`. That single addition would have caught most of the
afternoons that actually hurt — the silent-success-with-bad-geometry class is the one the agent has
no proactive defense against, only the always-one-step-behind validate line.

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

> The gaps below (G70–G76) were surfaced building a full pocketwatch vignette (105 objects:
> cased watch + open hunter lid + Albert chain + display base). The "perceive-and-stack" half
> of the toolkit (status-block bounds, `feel`, `array_radial`, `check_framing`, materials)
> performed well; these are the "repeat-and-pivot" failures that forced workarounds. Each entry
> is self-contained with a live repro.

## G70 — `transform op=rotate pivot_object=<name>` crashes (`world_center` undefined) 🐞 BUG

**Symptom.** `transform op=rotate axis=Y angle=-125 pivot_object=Hinge` returned the error
string `name 'world_center' is not defined` and changed nothing. Any `rotate` with
`pivot_object=` set hits it.

**Impact.** The canonical "rotate about another object's origin" — a lid/door swing on a named
hinge, a part pivoting on an axle — is unavailable. Forced workaround: translate the pivot
point to the world origin → `rotate pivot=origin` → translate back (3 calls, hand-managed).

**Fix.** Find the `pivot_object` branch in the `transform`/`rotate` handler. `world_center` is
almost certainly a typo / renamed variable for the pivot object's world-space origin — set the
pivot to `pivot_object.matrix_world.translation`. Test: rotate a box about a second object's
origin, assert it orbits that point.

## G71 — `pivot` enum naming is inverted from intuition (`origin`=WORLD, `center`=object's OWN) ⚠️ TRAP

**Symptom.** `pivot=origin` rotates about the WORLD origin (0,0,0); `pivot=center` rotates about
the object's OWN origin — the opposite of what the names imply. I read "origin" as "the object's
origin" and flung the sub-dial seconds hand across the dial. The hour/minute hands only worked by
luck (their origins sat at world zero).

**Impact.** Silent wrong-pivot rotations — no error, geometry just lands wrong. Pure naming/docs
trap, easy to flip.

**Fix (pick one).** (a) Rename enum values to `world` / `self` (clearest); (b) keep aliases for
compat but state explicitly which is which in every `pivot` field's schema description; (c) at
minimum, echo the world-space pivot point used in the status block for ALL pivots (it already
prints "about [x,y,z]" for `pivot=origin` — do it for `center`/`cursor`/`bbox_center` too so a
wrong pivot is catchable). Lives in the `transform` schema + rotate handler.

## G72 — `transform op=move_verts` x/y/z are NOT meters (scaled by bbox dimension) 🐞 BUG

**Symptom.** `move_verts y=0.15` on a 0.46-long blade moved verts by 0.069 m (= 0.15 × 0.46);
`y=0.176` → 0.081 m. The multiplier equals the object's bbox extent along that axis — so explicit
x/y/z behave as a *fraction of bbox*, while the schema says "(m)". I had to drive every vert move
by reading bounds and back-solving the fraction.

**Impact.** Can't move verts a known metric distance — breaks the "self-authored coordinates are
trustworthy" regime for edit-mode moves.

**Fix.** In the `move_verts` handler, the *named* offsets (right/left/up/down/back/forward/in/out)
read correctly in meters — only the explicit x/y/z are scaled. The x/y/z path is multiplying by a
dimension it shouldn't (or routing through a normalized op). Make x/y/z translate by raw meters.
Test: add box depth 0.46, `move_verts y=0.1`, assert bbox shifted exactly 0.1 m.

## G73 — ARRAY modifier offset is uncontrollable and defaults to unusably tight 🧩 MISSING CONTROL

**Symptom.** `modifier op=add type=ARRAY count=18` gave ~0.01 m per-copy spacing (18 copies packed
into ~2× the unit length, basically overlapping). `modifier op=modify modifier_name=Array
factor=0.667` returned `(skipped: ['factor'])` — the wrapper exposes no way to set array spacing.

**Impact.** The natural primitive for any linear repeat (chain links, pickets, watch-band, stair
treads, baluster runs) is dead on arrival. Fell back to duplicate→nudge→join doubling.

**Fix.** In the `modifier` verb, expose ARRAY offset controls — at minimum a constant-offset
distance (`use_constant_offset` + `constant_offset_displace`) and/or the relative-offset factor —
and make `modify` accept them. Pick a sane default (relative offset 1.0 = one bbox length, not the
current ~0.06). Test: array a 0.165 m box, count 8, constant offset 0.11; assert length ≈ 0.825 m.

## G74 — `transform op=array_along between=[A,B]` ignores the endpoints (stacks at origin) 🐞 BUG

**Symptom.** `array_along prototype=Chain between=["ChainStart","ChainEnd"] count=15` (markers at
x=0 and x=1.55) reported `placed 15 copies on Z (spacing 0.0 m)` and dropped all 15 at the origin,
overlapping. The A/B endpoints were never read; it fell through to a default Z axis with zero
spacing.

**Impact.** The relational "distribute N copies between these two things" primitive — the
intent-space tool for a draped chain, or balusters between two posts — silently no-ops.

**Fix.** In the `array_along` handler, when `between=[A,B]` is given, resolve both objects' world
origins, derive axis + length from A→B, and space copies = |B−A|/(count−1). The "spacing 0.0 m / on
Z" message says it took a default branch without parsing `between`. Test: two markers 1.5 m apart on
X, `array_along count=4`, assert copies at 0, 0.5, 1.0, 1.5.

## G75 — sequential edit-ops on one mesh can't be batched in a single message (silent no-op) ⚠️ FOOTGUN

**Symptom.** Issuing `loop_cut` + `taper_end MAX` + `taper_end MIN` on the same mesh in one
tool-batch left the MAX taper byte-identical — the no-op detector caught it ("reported success but
geometry is byte-identical"). Re-run standalone, it worked. Batched edit ops run against stale
mesh/bmesh state, and only SOME ops in the batch fail.

**Impact.** Edit-mode work can't be parallelized; the partial-failure mode is the dangerous part.
(The no-op detector is the hero here — keep it.)

**Fix.** Edit ops likely each snapshot a bmesh at dispatch time rather than re-reading sequentially.
Either serialize edit-op execution within a batch (per target), or document loudly that edit ops on
the same target must be one-per-message. At minimum, a doc line. Lower priority than the bugs above.

## G76 — status block `active`/`selected` lags the last mutation 🔍 LEGIBILITY

**Symptom.** The `── blender status ──` block repeatedly reported a stale `active:` object — it kept
showing `WoodBase` through six material assignments to other objects, and `Hinge` after `LidCover`
nudges. The bounds printed then describe the WRONG object, so I had to call `object info <name>` to
get real post-op bounds.

**Impact.** Undercuts "the status block is ground truth" for any op where the acted-on object isn't
the viewport-active one (multi-target material/transform, name-addressed ops). Cost extra `object
info` round-trips.

**Fix.** Have the status block report the object(s) the OP acted on (the verb already knows its
target), not `context.view_layer.objects.active`. For multi-target ops, summarize the set or report
the primary target's bounds. Lives in `_status()` / per-verb result assembly in `_core.py`.

## G77 — spatial verification isn't effortless; the agent dead-reckons clearance/facing instead of reaching for it 🧭 NORTH-STAR

**Symptom.** Building the pocketwatch I (a) worked out the open lid's facing direction with a
rotation matrix in my head instead of reading it, and (b) verified the dial-stack (markers / hands /
crystal) didn't intersect by arithmetic on z-bounds instead of `feel op=overlaps`. Both are spatial
questions the server can answer exactly — both got hand-computed because reaching for the read
wasn't the reflex.

**This is the most important finding of the build.** The perceive-and-stack loop (status bounds,
`feel topology`, `check_framing`) is strong, yet it still *let* me dead-reckon. Two root causes:

1. **The verify-half of `feel` (`overlaps`, `contacts`, `facing`, `resting`) isn't surfaced at the
   moment of need.** Nothing in an `add`/`transform` status block says "the part you just placed now
   intersects X" or "this rests on nothing." So the agent runs them only if it remembers to — and
   under load it falls back to math. Effortless means the agent shouldn't have to remember.

2. **Nothing *enforces* "read, don't compute."** THE ONE RULE (single-sourced in the server
   `instructions`) now tells the agent to read spatial relationships with `feel` and treats
   coordinates as decaying with token-distance from authorship — but a rule the agent can silently
   ignore isn't enough. Without #1 (effortless, surfaced verification) it still falls back to math on
   stale coordinates under load.

**North star = effortless.** The agent should never hand-compute a spatial relationship. Either the
value falls out of a read it is already doing, or the status block surfaces the drift unasked.

**Fix directions.**
- Auto-surface collision / loss-of-contact: after a `transform`/`add` that places a part, the status
  block (or a G9-style follow-up) flags *new* intersections / lost rests against neighbours. The
  agent learns it without asking.
- Consider a lightweight staleness signal: a read echoes how many calls ago an object was last
  mutated, so the agent knows when its remembered bounds have gone stale.

---

> G78–G80 are the holes opened by the **coordinate amputation** (all typed absolute world
> coordinates removed from the verb surface — at_x/y/z, to_x/y/z, anchor/center/target coords,
> on={"at":[x,y,z]}, raise_to, select in_sphere center, light/camera/helix placement). The cut
> forces every position to be relational/handle-addressed; these are the relational primitives that
> now MUST exist for the freed-up workflows to stay possible. (Kept by deliberate decision: relative
> *nudges* everywhere, curve/tube `points` as geometry-definition, pose `loc` as bone-space relative.)

## G78 — a measured read (`feel op=aim` / `op=place` / `op=map`) produces a point nothing can consume 🧭 NORTH-STAR

**Symptom.** `feel op=aim` / `op=place` / `op=map` hand back a world point + normal. The old
workflow fed that point to `sculpt at_x/y/z`, `select in_sphere center=`, or `add on={"at":...}` —
all removed. There is now no way to ACT on a point a read discovered: handles only mint from the
live edit-mode *selection* (`feel op=handle source=selection`), not from an arbitrary point.

**Impact.** The "judge where, server measures, then act there" loop is broken at the last step for
any feature located by a cast rather than a vertex selection. The reads still measure; their output
is now a dead end.

**Fix.** Let a read MINT a handle at its hit so it's addressable by name: e.g. `feel op=handle
source=point` (mint at a supplied/last-read point), or an `as_handle=<name>` flag on `aim`/`place`/
`map` that mints the cast point directly. Then the existing handle-based verbs (`sculpt handle=`,
`select op=in_sphere handle=`, `transform op=move_to handle=`) consume it. This is the keystone that
keeps the coordinate ban from removing capability instead of just removing dead-reckoning.

## G79 — no relational placement/aim for lights & cameras 🧩 MISSING CONTROL

**Symptom.** `add light/camera` lost x/y/z + target_x/y/z; `object op=light` lost x/y/z; `view
op=camera_position` is gone. Lights/cameras now spawn at a fixed default and can only be moved with
`transform op=place`/`nudge` (they are objects, so this works) — but there is no relational way to
**aim** them (`view op=orbit` aims at a fixed point, not a named object) nor to **rig** them
(key/fill/rim at an angle + distance around a subject), which is the actual intent.

**Impact.** Lighting and camera framing — the last mile of every hero render — got harder, not just
coordinate-free. Aiming a camera/light at a named object, or placing one "3/4 front, 30° up, 2 m out
from the subject," has no primitive.

**Fix.** (a) `view op=orbit target=<object>` and an `aim=<object>` on camera/light ops (aim by name,
not by point). (b) A relational light-rig primitive: position by angle (azimuth/elevation) + distance
around a named subject — the spherical-relative analogue of `array_radial`, reusing the orbit math.

## G80 — dead coordinate plumbing left in the internal adapters 🧹 CLEANUP

**Symptom.** The cut was made at the agent-facing verb layer; the pruned internal adapters still
carry coordinate params now fed defaults/None: `transforms.move_to`, `scene.add_light/add_camera`
(baked spawn defaults), `scene.set_camera_position` (now orphaned — no verb calls it),
`viewport.orbit_viewport`, `queries.place_on_surface` (dead `anchor_x/y/z` branch), every `sculpt._s.*`
(`at_x/y/z`, grab `to_x/y/z`). The Blender-side executors (extension/) still accept the same params.

**Impact.** None functional (unreachable from the agent), but it's dead code and a re-exposure risk.

**Fix.** Strip the coordinate params from the adapter signatures + their extension counterparts; delete
`set_camera_position` (server + extension handler). Low priority — do it once G78/G79 settle, since
the relational replacements may reuse some of this plumbing.

> ⚙️ **Deploy note:** the coordinate cut touched `extension/placement.py` (removed the `at`/`x`/`y`/`z`/
> `raise_to` keys from the placement DSL). That change only takes effect after the addon is **rebuilt
> and reinstalled** in Blender — until then the running addon still accepts `on={"at":[...]}`.

---

> G81–G83 surfaced building a second pocketwatch hero asset (open-face gold case + enamel dial +
> sub-seconds + blued hands + Albert chain, for UE5). The pivot bugs (G70/G71) and the ARRAY-offset
> hole (G73) re-surfaced verbatim — confirming they bite on every repeat-and-pivot build. These three
> are the *new* misses: a round-face layout couldn't stay in intent-space, a part couldn't be seated
> into a cavity, and dial lettering had no primitive.

## G81 — no way to mint a landmark by ANGLE on a round face (forces hand-trig) 🧩 MISSING CONTROL

**Symptom.** Laying out a round dial — sub-seconds register at "6 o'clock, 0.11 m out", a hand pivot
there, hour-index anchors at each clock hour — has no angular primitive. `feel op=place` takes only
*cartesian* offsets (left/right/up/down/front/back), so a cardinal direction (−Y = 6 o'clock) works,
but any off-axis hour (2 o'clock = 60°) forces me to decompose `radius·(sin θ, cos θ)` into x/y by
hand. `array_radial` *places copies* on a ring but yields no named, addressable point to then act at.
I fell back to typed x/y for every register.

**Impact.** Any radial layout on a round face — sub-dials, bolt circles, clock numerals, lug/lug-hole
positions, gauge ticks, dice pips — leaves intent-space; each off-cardinal position is hand-trig. The
angle/radius are legitimate *derived* magnitudes (per THE ONE RULE) — there's just no verb that
accepts them.

**Fix.** Add an angular term to `feel op=place` (or a dedicated radial-landmark op): `anchor=<disc or
handle>`, `angle=<deg>`, `radius=<m>`, surface-snap → **mint a handle by name** at that point (pairs
with G78, which lets the minted point be consumed by `sculpt handle=` / `move_to handle=` / etc.).
Test: on a disc, `place anchor=Dial angle=60 radius=0.11` mints a handle at the 2-o'clock surface
point; its mirror is addressable by name.

## G82 — `rest_on` seats only on TOP; nothing seats a part DOWN INTO a cavity 🧩 MISSING CONTROL

**Symptom.** Dropping the enamel dial into the case's recessed bezel well had no relational op.
`transform op=rest_on` drops a part until it lands on the *outer top* surface of a target (BVH cast
from below) — it cannot lower a part into an interior pocket until it rests on the *pocket floor*.
Seating the dial was a derived typed height — which the coordinate amputation (G78–G80) now removes
entirely, leaving **no path at all**.

**Impact.** Post-amputation this is a hard hole. Seating anything into a cavity — a dial in its bezel
well, a gem in a setting, a lens in a barrel, a battery in a compartment, a panel into a rebate — has
no relational primitive; `rest_on` only does on-top.

**Fix.** Extend `rest_on` (or add `op=seat`) with a "drop into" mode: lower along −axis until the
part contacts the highest *interior* surface beneath its footprint (the cavity floor it is entering
from above), with an `offset=` clearance — optionally targeting a named recess/face. Test: a disc
lowered into a cylindrical counterbore seats on the bore floor at the given clearance, not on the
part's own rim.

## G83 — no text / numeral primitive 🧩 MISSING CONTROL

**Symptom.** Putting "XII" / "12" or a maker's name on the dial is impossible — `add` has no `text`
type. I modeled applied baton indices instead; the watch reads as *a* watch, not a *named* one.

**Impact.** Engraved / embossed / applied lettering — dial numerals, brand marks, gauge labels,
keycaps, signage, dice pips — is a native Blender object type (FONT/Text, extrudable + bevelable) with
no surface here. It is a general primitive, not a watch-specific shortcut, so it belongs.

**Fix.** `add type=text` — `body` string, `font` (default ok), `size`, extrude `depth`, optional
`bevel`; emit a real mesh (or a FONT object convertible via `object op=convert`, like curves),
placeable with the relational DSL and the existing box-projection materials. Test: `add type=text
body="XII" depth=0.004` yields a readable extruded mesh seatable on the dial.


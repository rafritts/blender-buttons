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

> The gaps below were surfaced building a full pocketwatch vignette (105 objects: cased watch +
> open hunter lid + Albert chain + display base). The "perceive-and-stack" half of the toolkit
> (status-block bounds, `feel`, `array_radial`, `check_framing`, materials) performed well; these
> are the "repeat-and-pivot" failures that forced workarounds. Each entry is self-contained.

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
> sub-seconds + blued hands + Albert chain, for UE5). These three are the misses left after the
> pivot/array bugs were closed: a round-face layout couldn't stay in intent-space, a part couldn't
> be seated into a cavity, and dial lettering had no primitive.

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


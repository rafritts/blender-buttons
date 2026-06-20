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



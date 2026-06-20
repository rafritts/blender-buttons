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

2. **THE ONE RULE grants a blanket "geometry you authored is trustworthy" exception**, which invites
   dead-reckoning coordinates authored 100k+ tokens / dozens of calls ago. The exception should be
   *temporal*: coordinate math is never trustworthy — only pragmatically safe within ~1–2 calls of
   the authoring action; staleness rises monotonically with token-distance. Re-read beyond that.

**North star = effortless.** The agent should never hand-compute a spatial relationship. Either the
value falls out of a read it is already doing, or the status block surfaces the drift unasked.

**Fix directions.**
- Auto-surface collision / loss-of-contact: after a `transform`/`add` that places a part, the status
  block (or a G9-style follow-up) flags *new* intersections / lost rests against neighbours. The
  agent learns it without asking.
- Reword THE ONE RULE in `guidance://llms`, the MCP server instructions, and `GUIDANCE_FOR_LLMS.md`:
  drop the authorship exception; replace with "coordinate math is never trustworthy — pragmatically
  safe only within ~1–2 calls of authorship; re-read ground truth beyond that." (See also
  [[feel_operates_on_meshes_i_didnt_author]]: the rule is about *un-perceived* geometry, not
  authorship — staleness is just un-perception over time.)
- Consider a lightweight staleness signal: a read echoes how many calls ago an object was last
  mutated, so the agent knows when its remembered bounds have gone stale.


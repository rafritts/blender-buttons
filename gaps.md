# MCP gaps

_A **live worklist of OPEN gaps** — fixable limitations in the MCP surface, nothing
historical. Shipped/fixed items are **removed** (they live in git history), so this file
is only ever "what's still wrong." G-numbers are **stable across rewrites**: a number
missing from the sequence (G1–G8, G10–G13, G15–G22, G24–G29) means that gap shipped and
was retired. Last updated 2026-06-17 — relational-placement primitives shipped (dogfooded
by a Newton's-cradle build that refused to dead-reckon): `on`/`under` accept an anchor LIST
(span across / hang between supports), `at_corner` gains `top:true` (rest on the target's
top, not embed), and `add type=tube between=[A,B]` (strut between two anchors on
nearest-surface endpoints) — all covered by `tests/e2e_relational.py`. Also G23 moves 1–3 shipped (the per-verb scan tax:
polymorphic-param split, per-op param manifests, and teaching errors via
`server/verbs/_common.py:teach()`, covered by `tests/g23_teaching.py`); move 4 (splitting
fat verbs) deferred as unwarranted. Earlier: G24–G29 shipped (render preflight, aim_axis,
rest_on, material target list, edit-mode contract, nearest-surface distance), covered by
`tests/e2e_gaps_b.py`._

## North star

The agent's vision can **judge** but cannot **measure**; it reasons over outlines,
profiles, scalars, and named regions — never coordinate dumps. The server's job is to let
it stay in **intent-space** ("wrap the grip", "seat the bulb", "rest it on the desk") and
hand back **legible ground truth** instead of making it dead-reckon coordinates. Every gap
below is a place the agent was forced out of intent-space — into hand-trig, a self-managed
mode, or a number it couldn't trust. A gap is a general Blender primitive, never a
task-specific shortcut.

---

## G9 — responses are dead-end documents (the "dark cave") 🕯️ SPEC'D, NOT IMPLEMENTED

Every tool answers the question asked, then goes silent — it never points at the **adjacent
read or action that refines it**. The cross-references that exist live only in docstrings
(at tool-*selection* time), which under deferred/`ToolSearch` loading aren't even reliably
in context. The *response payload* says nothing. A knowing operator who doesn't already know
the whole surface is spelunking blind (e.g. `object info` reports `vertex_count: 3288` and
stops — that those verts are two open shells only surfaces if you already know to reach for
`feel op=topology`).

This is the perception→action bridge applied to **responses**: a read tool should hand back
the **next read**, the way `feel structure` hands back a named limb handle. Call it a
**follow-up** (hypermedia control, named-tool not URL). Principle: the server should never
feel like a dark cave.

**Mechanism (cheap — machinery exists).** `_status()` in `_core.py` already drains ride-along
channels (`notes`, `bind_warning`, …). Add a fourth: one new **`server/followups.py`** with a
single *pure* function — given the result dict + verb/op, return 0–2 follow-up lines —
rendered as a uniform `next:` line. **One central helper + a gating table, not an edit to all
15 verbs.**

**Discipline (where it goes wrong if rushed).** A follow-up must be *earned, conditional,
factual*: fire only when the data warrants it, ≤2 lines, name the concrete tool+op+arg, state
a fact about the object — never a static "you might also like," never divine intent. When in
doubt, stay silent.

**The reviewable artifact is the table (sign off before coding):**

| After this… | …when | Follow-up |
|---|---|---|
| `object info`/`describe` (MESH w/ modifiers) | rigged geo | counts are the **cage**; `feel op=topology` for shells/holes, `base=evaluated` for the final surface |
| `object info` (coord dump) | normal flow | `object describe` for the relational read |
| `feel op=topology` (cheap bundle) | holes/poles/multiple shells found | the deeper method — `structure`, `region_form`, `thickness` |
| `feel op=topology` | a protrusion/limb named | `select op=limb` to anchor + act |
| `select` (edit-mode selection) | a patch selected | `feel op=region_form` to read its form |
| `feel op=aim` | returns point+normal | `sculpt … at_x/y/z`, `transform op=move_to`, `select op=in_sphere` |
| `feel op=assembly` | two openings found | `feel op=relate` → `transform op=snap_loop` → `edit op=bridge` |
| `add` (primitive) | always | `edit` to shape, `transform` to place |
| `modifier` add (subsurf/deform) | always | `feel … base=evaluated` to read the final surface |

Start with the `info`/`describe → feel` row (the proven one) and grow. When promoted, this is
its own SPEC: pattern + `followups.py` + table, table signed off first.

## G14 — live X-symmetry edit mode 🪞 TABLED (real gap, deferred by decision)

Shaping one side and having it mirror live is the natural primitive for torsos, soft-form
work, almost all character modelling — mirroring as post-hoc cleanup means shaping twice or
mirror-and-pray. Acknowledged real, deliberately tabled. Handles ease the manual path (mint
`…_L`, mirror to `…_R`); the symmetry *mode* itself is separate work.

**Narrower sibling worth building first — "match a twin's edit."** When the human hand-edits
*one* side of a symmetric pair, the agent can read the transform delta (`object info`) but
must re-apply it to the twin by hand. A one-call `object op=mirror_edit name=<src> twin=<dst>`
(read src's delta-from-twin, apply the mirrored transform) makes "you yawed the left form
+25° — mirror it right" a single move. Post-hoc twin-matching, not a live mode — cheaper than
G14 proper and independently useful.

## G23 — the per-verb **parameter union**: scan tax 🪢 MITIGATED (moves 1–3 shipped; move 4 deferred)

The 17-verb consolidation is right — **do not undo it.** But each fat verb (`transform`,
`add`, `edit`) carries ~40–50 params; any one op uses a handful, so picking an op means
scanning and filtering. Three of the four moves shipped; the scan tax is now mitigated
without paying the cost of splitting verbs.

**Litmus test (still the bar for any new param):** a param is correctly designed if its
meaning is unambiguous from **op name + param name alone**, no description needed.

- **Move 1 — kill polymorphic params** ✅ `rotate_to` got its own `deg_*`, so no field means
  two things depending on op.
- **Move 2 — param manifest per op** ✅ each op line in the fat verbs' docstrings carries its
  own `(params)` manifest, plus `[op]`-prefix tags on every param — picking the op hands you
  its handful instead of scan-and-filter.
- **Move 3 — teaching errors + a canonical example per op** ✅ `server/verbs/_common.py:teach()`
  + a per-verb guard table: a valid op missing a structurally-required param (a destination, a
  target, a prototype, two endpoints, a name) returns `needs … — got none. e.g. <canonical
  call>` instead of a silent no-op (`move_to` with no destination used to report "moved" and
  change nothing) or a deep crash. Covered by `tests/g23_teaching.py` (25 checks).
- **Move 4 — split the 2–3 genuinely fat verbs into namespaced sub-tools** (`transform_move_to`)
  🪞 DEFERRED. Honest cost = a discovery hop + a sliver of the old 150-tool world. Moves 1–3
  make it unwarranted today; revisit only if the union scan tax resurfaces in real use, and
  only on the genuinely-fat verbs — never the lean ones (`scene`/`view`/`render`).

Note: JSON-Schema conditionals help server-side *validation* but *hurt* readability — catch
errors with `teach()` (move 3), don't buy obviousness with schema conditionals. Obviousness
comes from move 2.

## G33 — `edit op=taper_section` ignores `from_ring`→`to_ring` direction 🔀 OPEN

The param docs read `x_start` = "X scale at **from_ring**", `x_end` = "X scale at **to_ring**".
But empirically the endpoints bind to **ascending ring index**, not to the from→to order
passed: calling `from_ring=16, to_ring=1, x_start=1.0, x_end=0.16` put the `0.16` pinch at
ring 1 (the lower index) and `1.0` at ring 16 — i.e. it behaved as if `from_ring=1`. A
directional taper "narrow toward the **from** end" silently inverts, and you only catch it
by reading `feel op=profile` afterward. The operator is forced out of intent-space ("pinch
the bottom toward the mouth") into "which ring index is numerically smaller, and does that
match my from/to?" trial-and-error.

**General fix:** honor the caller's from→to ordering — `x_start` lands on `from_ring`
whichever end that is — OR, if ascending-index binding is intentional, say so in the param
docs and reject/ignore a descending `from_ring`>`to_ring` with a `teach()` note. Either way
the meaning must be unambiguous from op+param name (the G23 litmus). Dogfood: hot-air-balloon
envelope — first taper produced an upside-down silhouette (pinch under the equator, bulge at
the base); only the profile read revealed the flip.

## G34 — `select op=all` / `op=none` don't honor the `target`=auto-enter-edit contract 🎯 OPEN

The edit-mode select ops (`by_axis`, `between`, `boundary`, `limb`, `ring`, …) all take
`target` and auto-enter Edit mode on it so a stray click can't hijack the op. `op=all` (and
`op=none`) **don't** — `select op=all target=basket` from Object mode returns
`bpy.ops.mesh.select_all.poll() failed, context is incorrect` instead of switching to Edit
on `basket` like its siblings. The operator has to know that *this one* select op breaks the
contract and insert a manual `object op=mode mode=EDIT` first.

**General fix:** make `op=all`/`op=none` respect the same `target`→enter-Edit contract the
other component-level select ops already implement. Dogfood: beveling the balloon basket —
`select op=all target=basket` failed; had to switch mode by hand.

## G35 — camera-write ops can't address a **named** camera; no "set active camera" primitive 🎥 OPEN

`view op=camera_position` and `op=camera_dof` write to the scene's **active** camera and have
no `camera=` param — yet the *read* sibling `check_framing` does take `camera=`. With two
cameras present (the default `Camera` + an added `hero_cam`), `camera_position` silently moved
`Camera` while I was checking `hero_cam`, so the framing readout never changed and the move
looked like a no-op. Worse, there is **no primitive to set the active scene camera** at all:
`add type=camera` doesn't make the new camera active, and nothing else does, so a freshly-added
hero camera can't be driven by the camera-write ops or become the render camera without
deleting every other camera and hoping.

**General fix:** (a) give `camera_position`/`camera_dof` a `camera=` param symmetric with
`check_framing`; (b) add a "set active scene camera" primitive (or an `active=true` flag on
`add type=camera`). Dogfood: positioning the balloon hero shot — three `camera_position` calls
moved the wrong camera before the cause was found.

## G36 — `check_framing` and `render op=image` disagree on the default (unset) camera 🧭 OPEN

With no explicit `camera=` and `scene.camera` unset, `check_framing` returns
`no camera (pass camera=<name> or set the scene camera)` — but `render op=image` with the same
state **succeeds**, falling back to an available camera and producing a correct image. Two
tools, two different default-camera resolutions: a preflight (`check_framing`) that says the
shot is unshootable, and a render that shoots it fine. The preflight can't be trusted as the
render's ground truth, which is the whole point of having it.

**General fix:** unify default-camera resolution across the camera-consuming tools — both
fall back to the sole/active camera, or both require explicit naming with the same `teach()`
message. Dogfood: balloon hero render — `check_framing` (no arg) reported "no camera" seconds
before `render` (no arg) wrote a 1.97 MB frame.

## G37 — no projected-**silhouette** read; 2D shape must be reconstructed from orthogonal 1D sweeps 👤 OPEN

`feel op=profile` gives a **1D** width sweep (bounding girth per band along one axis) and
`op=sections` gives slice **contour counts** — but nothing returns the **2D projected outline**
of the form along a view axis (its orthographic shadow). To answer the most natural perception
question — "what is the gross shape of this?" — the agent must fire several reads and then
*mentally cross-multiply two orthogonal width-tables into a 2D silhouette*. That reconstruction
is exactly the dead-reckon-from-scalars the server exists to eliminate, and it's lossy: the
per-band girth is a **bounding** width, so it can't by itself tell a thin horizontal crossbar
from a tapering V — a concavity is invisible until you correlate it against the other axis's
sweep. It happened to be enough here, but it's brittle (a different pose defeats the
bounding-width heuristic).

**General fix:** a `feel op=silhouette` (a.k.a. `outline`) — deterministic orthographic
projection of the mesh onto a plane (`axis=X|Y|Z`), returned as a **coarse occupancy grid or a
boundary polygon**, coarse-to-fine, in scene units. Pure geometry, **not** vision — it keeps the
no-render-readback thesis intact while letting the agent read the projected form *directly*
instead of triangulating it. Complements `profile` (1D girth) and `sections` (slice counts) with
the missing 2D read. Dogfood: identifying an unnamed imported mesh (`polySurface25`) blind from
ground truth — correctly read as a T-posed human figure, but only by hand-assembling the
silhouette from a Z-profile + an X-profile + section counts + curvature + symmetry.

## G38 — no salient-**feature discovery**; `region_form` reads "what's here?" but nothing reads "where are the features?" 🔎 OPEN

The form scalars `region_form` returns are genuinely good — on a female base mesh it cleanly
measured the bust (convex, +2.76cm, perfect L/R symmetry), a buttock cheek (convex), and even a
navel (concave, −3.6mm, symmetric on the centerline). **But every one of those reads only worked
because the operator already knew a body has a bust at chest height, a navel on the lower
centerline, etc., and aimed an `in_sphere` there.** There is a chicken-and-egg: `region_form`
answers *"what is the form at this patch I selected?"* — nothing answers *"where are the
salient bumps and dents on this surface?"*. So the agent cannot **discover** anatomy/detail
blind; it can only **confirm** what it already hypothesised. `feel … method=curvature` is the
nearest thing but is self-flagged *"fuzzy — a guess (v2 = exact)"*, dumps only a top-N extrema
list with coarse region labels (`top-front`) and **no world coordinates** to act on, and never
clusters extrema into a *feature*.

Two concrete sub-failures observed:
- **Single-dome model mislabels multi-lobed regions.** A whole-buttocks patch reported
  `form: flat (centre−rim 0.37mm)` while simultaneously reporting **±6.8cm** of projection across
  it — the two cheeks + the centerline cleft averaged the centre-vs-rim verdict to "flat." A
  feature read that contradicts its own projection range is untrustworthy. It needs to recognise
  bilobed/saddle forms instead of forcing a centre-vs-rim dome.
- **Fine structure averages to mush.** The face packed ~14% of all verts into one 8cm sphere
  (a strong density signal that detail lives there), yet `region_form` collapsed eyes+nose+mouth
  to a single `convex` verdict. The presence of *a face* is inferable (vert density + curvature
  spikes), but `feel` never parses or even flags it as structured relief.

**General fix:** a relief/feature-discovery read — scan a surface (or a selected region) and
return the **ranked salient convex/concave features with world-space locations, projection
magnitude, extent, and L/R symmetry**, so the agent can find detail without prior knowledge of
where it sits. This is the "where" half that makes `region_form`'s "what" actionable, and it
must report multi-lobed/saddle forms honestly rather than averaging them to "flat." Deterministic
geometry, not vision. Dogfood: asked whether `feel` can discern face/bust/butt/navel on a base
female mesh — yes to *measure* each once located, no to *find* them; the butt read "flat."

## G39 — `feel op=aim` casts in the object's **local (rotation-baked) frame** while every other read is world-space 🧭 OPEN

`aim`'s `face` (`-Y/+Y/...`) and `u`/`v` parameters are interpreted in the mesh's **local bbox
frame**, but `object info`, `profile`, bounds, and `in_sphere` all speak **world space**. On the
imported base mesh (rotated 90° about X, a routine Maya Y-up→Z-up import), casting `face=-Y v=0.93`
expecting the top of the head hit mid-torso instead — local +Y had been rotated onto world +Z, so
the "vertical" v-axis was actually world depth. The operator gets no warning; the ray just lands
somewhere unrelated, and the only tell is that the returned world coordinate doesn't match the
intended feature. Mixing frames across sibling reads is exactly the kind of silent
coordinate-trap the server exists to remove.

**General fix:** either accept `aim` targets in world space (symmetric with `in_sphere`/`profile`),
or have it **state the world direction each `face` resolves to** in the response (e.g. `face=-Y →
world +Z`) and/or honour a `frame=world|local` flag. Whichever — the meaning of `face`/`u`/`v` must
be unambiguous without the operator first checking `rotation_deg` and mentally un-rotating. Dogfood:
locating the nose on the base mesh — two casts missed the head entirely because the bbox frame was
rotated.

## Considered and declined — pencil dogfood (2026-06-17)

Logged so they aren't re-raised. Each conflicts with a settled design principle, not a missing build.

- **Post-action render thumbnail** — against the core thesis (instrumented API, *not* a screenshot
  puzzle) and the agent never reads renders back; ground truth is the status block + `feel`. The same
  review praised the no-screenshot thesis, then asked for screenshots.
- **Scene tree with "functional roles" (container / top-surface)** — divination. The tree already
  shows collections + their parts; naming "the top surface" *for* the agent is the semantic guessing
  the server deliberately won't do (legibility, not divination). `object info` bounds make the surface
  legible without it.
- **Mandatory / auto `targets`** — already solved: every `transform` takes `targets` (object, list,
  OR a collection name, which expands to members). A stale active object is normal Blender; the
  active-object default is a convenience, not a bug.
- **`lay_on(target, angle)` high-level intent** — the angle is *taste* (the human's domain), and
  `rotate_to` → `rest_on` already seats arbitrary rotated geometry on real contact. The extra
  choreography hit was the coil penetration (G32), not a missing primitive. No bespoke verb.

---

## Carried over — bigger build-outs (not yet started)

- **Multires + dyntopo** as real multi-level sculpt targets — the proper organic-sculpt
  resolution story (distinct from the local-subdivide that shipped under G3).
- **Retopology** (auto or guided) — deformation-grade edge flow once a form is sculpted.
- **UV unwrap, material node graph, hair cards, face-loop topology** — further out, the road to
  a finished character.

## Open (older, unverified against current build)

- `check_contacts` / contact queries timing out on dense evaluated meshes (Spring's production
  geometry) vs the socket window.
- bbox-vs-`sel_z` self-contradiction flag (a stale-eval-cache symptom — may already be cured by
  the G19 depsgraph-refresh fix; needs re-checking on dense geo).
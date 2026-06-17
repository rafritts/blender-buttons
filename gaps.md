# MCP gaps

_Rewritten 2026-06-16, from the first real body-sculpting session (building a
character torso onto the Spring rig — soft-body forms from scratch, by feel + partnership).
The old contents (J-hatchets, I1 consolidation, H1/H2, F/G closed items) are in
git history if needed._

---

## The headline: the **constructive** half has no perception→action bridge

This is the one that matters; everything below is a facet of it.

The **destructive / structural** half of this MCP grew a clean perception→action
bridge and it works beautifully:

> `feel structure` finds a protrusion → `select op=limb` anchors to that
> topology → `edit delete`. **Zero coordinates.** It works because the target
> *is* a real topological feature (an open loop, a tube).

The **constructive / sculpt** half lacked that bridge: "where a soft raised form goes" is a
smooth, blank, featureless patch — no loop, pole, or boundary to anchor to — so
`sculpt` fell back to raw world coordinates, the **exact thing `feel` exists to
cure**. As of 2026-06-16 it has a **Phase-1 bridge**: `feel op=aim` (G1 below)
casts a normalized framing onto the surface and hands back the world point +
normal, the way `feel structure` hands back limb handles. The agent now aims in
fractions of the form and *learns* the coordinate. Phases 2–3 (one-call sculpt,
normalized placement) are speced in docs/SPEC-06; this section is no longer the
project's blocker, it's its newest working seam.

---

## G1 — surface-relative / local-frame brush addressing  ⭐ ✅ PHASE 1 SHIPPED 2026-06-16

`sculpt(brush, at_x/y/z, radius)` demanded a world point on a featureless surface —
the exact thing an LLM can't dead-reckon. **Now there's a resolver:**

**`feel op=aim target=<mesh> face=-Y u=0.25 v=0.65`** (engine `aim_surface`) →
casts that normalized bbox-face aim onto the EVALUATED surface and returns the
**world point + surface normal + region word**. The agent then feeds the point to
the existing verbs — `sculpt … at_x/y/z=point` (push along the normal), `select
op=in_sphere center=point`, `add … on={"at":point}`. It **hands the coordinate
back**, so the agent learns the point instead of inventing it.

This is the constructive-side `feel structure` → handles: aim in fractions of the
form, get the coordinate back, act with a normal-correct push. Fully general, no
anatomy baked in. See **docs/SPEC-06** for the addressing model + Phases 2–3
(one-call `sculpt face/u/v`; normalized placement for move_verts/add + absolute
move-to, which folds in G8).

**To verify live (written without a running Blender):** confirm
`Object.ray_cast(origin, dir, distance)` hits the subsurfed surface (not the
cage), the outside-origin + inward ray finds the NEAR wall, and the normal points
out. Tune `margin`. This is the one to dogfood carefully first.

## G2 — `feel` cannot read **form** back, only the bounding box ✅ FIXED 2026-06-16 (needs live tuning)

After a form sculpt the agent was blind: a concave slope, a teardrop, a dome, a
splay are all invisible to an axis-aligned bbox. The only form-feedback channel
was the human pasting a screenshot.

**Added `feel topology method=region_form`** (engine `_m_region_form`): reads the
FORM of the current SELECTION and emits compact scalars + a one-word verdict —
- **curvature verdict**: convex / concave / flat, from inner-third vs outer-third
  signed distance to the best-fit plane (`center_vs_rim_mm`). Answers "is this
  slope concave?" directly.
- **projection**: `+X cm out / Y cm in` over the patch (peak bulge along the
  outward normal).
- **L/R mirror error**: mirror the selection across the X plane, nearest-vert
  distance to the whole mesh — finds the mirror twin if one exists.
Raw scalars are reported alongside the verdict (legible-not-divine: trust the
numbers even if a threshold word is off). Closes the loop *between strokes*.

**Caveat — verify/tune live:** thresholds (0.5 mm flat cutoff) and the
selection-sync path (reads `v.select` on the base mesh; read in OBJECT mode or
right after a select op) were written without a running Blender. Dogfood this one
first and adjust the cutoffs against real patches. The math (PCA plane fit, signed
distance, KDTree mirror) is sound; the calibration is the unknown.

(The old `op=profile` 200-line per-ring dump is left as-is — `region_form` is the
verdict channel it failed to be.)

## G3 — no clean path to **sculptable resolution** in a region ✅ MOSTLY FIXED 2026-06-16

The body cage has ~**12 verts / 5 faces** across a whole palm-sized patch —
far too coarse for a dome *and* a crisp root. The densification paths are now open:
- **Apply-Subsurf** (`modifier op=apply`, → dense clay) and **dyntopo**
  (`sculpt … subdivide=True`) were only ever blocked by shape keys — **G4 unblocks
  both** (clear the keys, then either works).
- **Local subdivide** — NEW `edit op=subdivide` (cuts, subdivide_smooth) densifies
  exactly the SELECTED patch, no global loops, no shape-key block. The direct "add
  resolution here" affordance for a coarse 5-face region. (Engine
  `subdivide_selection`; boundary fans to tris — fine for clay, retopo later.)
- `loop_cut` still adds whole loops (by design — it's the global tool).

**Remaining (carried over):** **Multires** as a real multi-level sculpt target is
still unexposed — that's the proper organic-sculpt resolution story, distinct from
these three. Tracked below under "carried over". The immediate coarse-patch blocker
is closed.

## G4 — no `delete` / `bake-to-basis` for shape keys ✅ FIXED 2026-06-16

`pose` had `shape_keys` / `shape_key_set` / `shape_key_active` — but no
**delete**, and no **"flatten current mix into Basis."** A mesh derived from a
rigged source inherits its shape keys, which (a) silently capture edits into the
active non-basis key, and (b) block apply-Subsurf and dyntopo (G3). The only fix
was a manual hand-off to the human.

**Added:** `pose op=shape_key_delete` (one key, or key=""/"ALL" → clear all) and
`pose op=shape_key_bake` (flatten the current mix into Basis, drop every key).
Engine handlers `delete_shape_key` / `bake_shape_keys_to_basis` in objects.py.
Clearing all keys is what unblocks apply-Subsurf / dyntopo — no more manual
hand-off.

## G5 — ~~no `shade_smooth` on the verb surface~~ ✗ NOT A GAP (verified 2026-06-16)

This was wrong. `shade_smooth` / `shade_flat` ARE reachable — as
`material op=shade_smooth` (with `auto_smooth_angle`) and `material op=shade_flat`,
wired to the engine `shade_smooth`/`shade_flat` handlers via `finishes.py`. They
just live under `material`, not `object`/`view`, which is where I looked. Plain
shade is the donut-tutorial *material/finish* step, so `material` is a defensible
home. (`edit smooth_edges` is the separate bevel-and-reshade primitive.)
Left as-is — relocating it under `object` would only duplicate the surface.

## G6 — schema↔engine mismatches (small, but they cost a round trip each) ✅ FIXED 2026-06-16

- `edit taper_section curve_shape`: docstring said `linear|smooth`; engine rejects
  `smooth`. **Fixed:** the `curve_shape` tag + the `rings.taper_section` proxy
  docstring now list the real enum `linear | ease_in | ease_out | ease_in_out |
  smoothstep`.
- `transform rotate pivot`: passing `pivot="center"` errored with `pivot object
  'center' not found` — the default string was sent straight to an object lookup,
  so the pivot-**mode** path was unreachable (and the default itself errored).
  **Fixed:** the server wrapper no longer forwards the `"center"` default (→ each
  object spins about its own origin, as documented), and the engine now recognizes
  mode strings `bbox_center | cursor | origin` before falling back to an
  object-name lookup. `bbox_center` is the in-place rotate that was blocked.

## G7 — shared selection / active-object / mode collides with the human ✅ FIXED 2026-06-16

Blender has exactly **one** active object, **one** selection, **one** mode,
globally — and both the human's clicks and the MCP write them. This bit us three
times (a deleted selection, a cleared selection, an "enter Edit mode" landing on
the wrong object after a stray click).

**Added the explicit-`target` escape hatch everywhere it was missing:**
- `object op=mode` now takes `name` — it selects + activates that object *before*
  switching mode, so a stray click can't make "enter Edit" land on the wrong
  object (`set_mode` grew a `target`).
- `select op=limb` was the one edit-mode select missing the auto-`target` path —
  added to `EDIT_MODE_TOOLS`. The `select` verb's `target` now threads into
  by_axis / between / boundary / limb / grow / shrink / in_sphere / component_mode
  (each auto-selects + enters edit on the named object, exits after).

**Still true (document for drivers):** the **camera is conflict-free**
(orbit/pan/zoom/shading never touch MCP state); **only selection + active + mode
collide** — and now every collision-prone op can be pinned to a name. Driver
discipline still applies: address by name and re-assert the target before each
step.

## G8 — no absolute "move/rotate to", and the local-frame placement story ✅ FIXED 2026-06-16

`add` is relational-first (`on: seat/between/on_floor`) — good philosophy — but
dropping a marker at a *computed* point needed the obscure `on={"at":[x,y,z]}`,
and `transform` offered only **relative** `nudge` — no absolute set-position or
set-rotation.

**Added** `transform op=move_to` (absolute world position) and `transform
op=rotate_to` (absolute euler degrees), both via `to_x/to_y/to_z` with any axis
omitted left unchanged (engine `move_to` / `rotate_to`). Pairs directly with `feel
op=aim`: aim returns a world point → `move_to` drops an object there.

The normalized local-frame placement layer (aim in fractions of the form for
placement too, not just sculpt) is **SPEC-06 Phase 3** — this closes the absolute
half of G8; the relative-to-the-form half rides on the G1 frame.

## G9 — responses are dead-end documents (the "dark cave") 🕯️ SPEC'D, NOT IMPLEMENTED

Every tool answers the question asked and then goes silent. It never points at the
**adjacent read or action that refines it** — so a driver who doesn't already know
the tool surface is spelunking blind. The cross-references that *do* exist live only
in docstrings (`info` says "prefer `describe`"), i.e. at tool-*selection* time — and
under the deferred/`ToolSearch` loading model those schemas aren't even reliably in
context. The response payload itself says nothing.

**Proof from this session:** `object info` on `GEO_spring_arms` reported
`vertex_count: 3288` and stopped. That those 3288 verts are **two disconnected
shells with two open armholes** — the entire structural truth of the mesh — only
surfaced because the driver already knew to reach for `feel op=topology`. A knowing
operator who didn't was left in the dark by a response that had every reason to
light the doorway.

This is the **same perception→action bridge** the rest of this file is about, applied
to the *responses* instead of the tools: `feel structure → select limb` works because
the structural read hands back a named handle; a read tool should likewise hand back
the **next read**. Call it a **follow-up** (the REST/HATEOAS idea — a hypermedia
control — but named-tool, not URL). The principle: **the server should never feel
like a dark cave.**

**Mechanism (cheap — the machinery already exists).** `_status()` in `_core.py` is the
shared renderer every verb appends, and it already drains generic ride-along channels
off the result dict (`notes`, `bind_warning`, `shape_key_warning`). A follow-up is a
fourth channel: a new **`server/followups.py`** with one *pure* function — given the
result dict + the verb/op that produced it, return 0–2 follow-up lines — rendered by
`_status` as a uniform `next:` line. **One central helper + a gating table, not an
edit to all 15 verbs.** That keeps it a general primitive ("a response advertises the
read/action that refines it"), never bespoke hint-strings per tool.

**Discipline (this is where it goes wrong if rushed).** A follow-up must be *earned,
conditional, factual*: fire only when the data warrants it, ≤2 lines, name the
concrete tool + op + arg, **state a fact about the object** — never a static "you
might also like" footer, never divining the driver's intent (cf. the
legible-not-divine rule). When in doubt, stay silent.

**The reviewable artifact is the table** (situation → follow-up) — sign off on this
*before* coding it anywhere:

| After this… | …when | Follow-up |
|---|---|---|
| `object info` / `describe` (MESH w/ modifiers) | always for rigged geo | counts are the **cage**; `feel op=topology` for shells/holes, `base=evaluated` for the final surface |
| `object info` (raw coord dump) | normal workflow | `object describe` for the relational read (move the existing docstring nudge into the payload) |
| `feel op=topology` (cheap bundle) | holes / poles / multiple shells found | the deeper method that explains it — `structure`, `region_form`, `thickness` |
| `feel op=topology` | a protrusion/limb is named | `select op=limb` to anchor + act on it |
| `select` (edit-mode selection) | a patch is selected | `feel op=region_form` to read its form back |
| `feel op=aim` | returns point + normal | `sculpt … at_x/y/z`, `transform op=move_to`, or `select op=in_sphere center=…` |
| `add` (primitive) | always | `edit` to shape it, `transform` to place it |
| `scene tree` | a named object of interest | `object describe <name>` |
| `modifier` add (subsurf/deform) | always | `feel … base=evaluated` to read the final surface, not the cage |

Table is representative, not exhaustive — the rollout would start with the
`info`/`describe → feel` row (the one this session proved) and grow from there. When
promoted to work, this is **its own later SPEC**: pattern + `followups.py` mechanism +
the table, table signed off first. (SPEC-07 is taken by multi-feel; the new multi-feel
ops are prime follow-up *producers* — `assembly → map → handle → weld`.)

## G10 — construction has no **bridge / weld** (you can fabricate a part but not attach it) ✅ SHIPPED 2026-06-16 (same-object; cross-object/rigged out of scope by design)

Surfaced building a torso onto Spring (the pullover hides that the body has *no*
torso mesh — `GEO_spring_arms` is two disconnected arm shells, each open at a 17.6 cm
armhole; the neck ring lives on the head). A blockout torso placed into the gap is
trivial (`add → resize → move_to`, exact bounds via the status loop). **Attaching it
is impossible on the current surface**, for three compounding reasons:

1. **No bridge-edge-loops primitive.** The single most fundamental "close the gap
   between two open loops" move in all of mesh modeling is absent from `edit`
   (extrude / bevel / loop_cut / merge / inflate / bend / boolean … none bridge two
   boundaries). Without it a fabricated part and its socket sit centimeters apart
   forever. Closest hacks — `extrude until_contact` then `merge by distance` — only
   work same-object with near-coincident loops.
2. **`edit` is single-object.** Every edit op acts on the active mesh's own
   selection; the neck ring and armholes are on *other* objects, untouchable from the
   torso's session.
3. **Rigged geometry can't be restructured.** The body carries Armature + MeshDeform
   + CorrectiveSmooth + Subsurf, so the "join everything, then bridge" escape hatch
   would corrupt the deform stack.

This is the mirror of the headline: the **destructive** half has its perception→action
bridge (`feel structure → select limb → delete`); **constructive welding has none.**
The missing primitive is `edit op=bridge` (two boundary loops on the active mesh →
bridged faces), plus an honest note that cross-object/rigged welds are out of scope
without a join. Until then, fabricated parts are *placed*, never *joined*.
(**SPEC-07 multi-feel** is the perception half — it mints the two named handles, e.g.
`torso.top_ring` + `arms.armhole_L`, that an `edit op=bridge` would weld.)

**Resolution (SPEC-07 Phase 5).** `edit op=bridge a=<handle> b=<handle>` ships the
bridge-edge-loops primitive: it selects the two boundary handles' rims and welds them
into a continuous skin. Held to the honest scope above — **same-object only** (cross-
object → directed error: `object op=join` first, then bridge on the joined mesh), and
**keyed/rigged meshes refused** (a topology change corrupts the shape-key block / deform
bind). Verified: two joined open tubes, bridge the facing rims → 2 shells collapse to 1,
4 boundaries to 2. The cross-object case (reasons 2–3 above) stays an explicit limit, not
a silent failure.

## G11 — render config is **write-only**, and the engine enum is **stale** 🎛️ ✅ FIXED 2026-06-16

The `render` verb can *set* engine / quality / cycles / color but offers **no read** —
no way to ask the build which engines exist, the current engine, or the live params
(samples, device, denoiser, view transform, resolution, output size). The only way to
learn the available engines is **discovery-by-exception**: send a bad `engine`, read
the list off the error. Proven this session — a render bounced and the error was the
first time the real engine list appeared.

Compounded by a **version-stale enum**: the schema advertises
`engine = CYCLES | BLENDER_EEVEE_NEXT`. `BLENDER_EEVEE_NEXT` was the 4.2–4.x id; in
**Blender 5.x** EEVEE-Next is the only Eevee and the id reverted to plain
`BLENDER_EEVEE`. Hardcoding a version-specific engine name **guarantees** a failed
round-trip on 5.x (the build under test is 5.1.2). The server shouldn't hardcode
engine names at all — it should surface the build's own list.

**Fix:** add `render op=settings` (read) → available engines (from the build), current
engine, and the active per-engine config (Cycles device/backend/samples/denoise; Eevee
samples/AO/shadows/raytracing; color view_transform/look/exposure/gamma; output
resolution/format). Stop hardcoding the engine enum; validate against the build's list.
Natural **G9 follow-up**: any `render` result points at `render op=settings`. (The
status block already shows the *current* engine — this is the missing *capabilities +
full-config* read.)

**Re-confirmed 2026-06-16 (sword session, Blender 5.1.2):** requested `engine=CYCLES`
on a render → bounced with `render engine 'CYCLES' not available in this build;
available: ['BLENDER_EEVEE']`. Discovery-by-exception again: the real engine list only
appeared *in the failure*. The schema's `CYCLES | BLENDER_EEVEE_NEXT` enum advertised
neither of the build's truths (CYCLES absent; Eevee is `BLENDER_EEVEE`, not `_NEXT`).

**Resolution 2026-06-16.** Added `render op=settings` (engine `render_settings` in
render.py, read-only): reports the **build's own** `available_engines`, the current
engine, resolution/format/transparency, color management, and the active engine's
params (Eevee samples/raytracing/ao/shadows; Cycles device/samples/denoise). The
schema enum was de-hardcoded — the `engine` param now says "the build's id, NOT a
hardcoded name; `render op=settings` lists what's real," and every render op already
validated against the build's live enum list. Verified headless (5.1.2): settings
read returns `['BLENDER_EEVEE']` with the current engine in it.

## G12 — no trusted checkpoint / rollback before risky edits 💾 ✅ FIXED 2026-06-16

Editing a rigged *production* file (`spring_cut.blend`), there was no cheap "snapshot
before I try the bridge — roll back if the modifier stack screams." The `history` verb
exists but its guarantees weren't legible enough to lean on mid-experiment, so edits
were made timidly. The fix is to **lean into Blender's own edit history / undo stack**
rather than invent a parallel one: expose a named, agent-facing checkpoint — `history
op=mark name=torso-experiment` → `history op=restore name=…` — backed by Blender undo
(and/or a scratch `.blend` copy for coarse-grained safety). The goal is bold
experimentation on someone's real file without fear: mark, try, restore. Relates to
G7 (shared undo stack with the human — a restore must not stomp the human's work; scope
the guarantee honestly).

**More evidence 2026-06-16 (sword session):** when `edit op=bend` went wrong (G21),
the *only* recovery was `object op=delete` + rebuild the guard from scratch — **twice**.
A `history op=mark` before the bend would have made it `restore` and retry. Every
irreversible op without a checkpoint is a small gamble the agent takes timidly; the
checkpoint is what lets it experiment boldly. Pairs with G18 (when a mode/edit op
misbehaves, restore beats hand-reconstruction).

**Resolution 2026-06-16.** Added `history op=mark name=…` / `history op=restore name=…`
(engine `mark_checkpoint` / `restore_checkpoint` in history.py). Exactly as the gap
asked — NOT a parallel snapshot store: `mark` records the current history-head op_id
in `state._marks`; `restore` undoes to it via the existing `undo_to`, which already
verifies the landed scene against its history snapshot. Refuses if newer edits forked
past the marked op (honest scope). Both are unlogged/non-undoable themselves (they
manipulate history). Verified headless: mark → add risky object → restore removes the
risky object and keeps everything before the mark.

## G13 — the scene tree is a firehose, not a map 🌲 ✅ FIXED 2026-06-16

First contact with Spring meant wading through **hundreds** of `cs_*` rig widgets to
find ~15 real geometry meshes — and `type=MESH` didn't help, because the widgets are
meshes too. `scene op=tree` prints everything at one depth. Fix (cheap): **print
high-level first and let the agent drill into "directories"** — collapsed collections
the agent expands by name — plus **filter and search**. A "show me what actually
renders / the real parts" semantic view (collection-aware, skip widget/helper
collections) would make first contact a map instead of a wall. This is the navigation
half of reflection-#2, merged here.

**Resolution 2026-06-16.** The drill-in/filter/search/summarize halves already shipped
(filter, type, max_depth, summarize collapse big collections to per-type counts). The
missing **"real parts" semantic view** is now `scene op=tree parts_only=True`: it hides
bone-shape widgets + render-hidden helpers, detected **generically** — an object is a
widget if it's referenced as some armature pose-bone's `custom_shape` or it's
`hide_render` (no `cs_`/`WGT-` name-prefix hardcoding, per the general-tools rule). First
contact with a rig becomes the ~15 real parts instead of the wall. Verified headless.

## G14 — live X-symmetry edit mode 🪞 TABLED (known, deferred by decision 2026-06-16)

Shaping one side and having it mirror live is the natural primitive for torsos, the
soft-form work, almost all character modelling — mirroring as a post-hoc cleanup step
means shaping twice or mirror-and-pray. **Acknowledged as a real gap and deliberately
tabled** this session — logged so it isn't lost, not because it's solved. Handles
(SPEC-07 C) ease the manual path (mint `…_L`, mirror to `…_R`); the symmetry *mode*
itself is separate work for later.

## G15 — handles have no garbage collection for orphans 🧹 ✅ FIXED 2026-06-16

Building the Phase-4 test, deleting a mesh left its handles behind: the `HANDLE_<name>`
vertex group dies with the mesh, but the **Empty lingers** in the `Handles` collection,
now permanently `✗ orphaned`. `feel op=handles` flags them, but there's no way to *act*
on the flag — no prune. The general primitive is a handle-lifecycle op: `feel
op=handles prune` (or `feel op=forget name=…`) that deletes the Empties whose
provenance can no longer replay (owner gone / vgroup gone), turning the orphaned state
from a permanent annotation into something collectable. Native-delete the Empty in the
Outliner already works; this is just the agent-facing equivalent so the registry can be
kept tidy without leaving the chat. Cheap, and it closes the loop the dirty/orphaned
model opened.

**Resolution 2026-06-16.** `feel op=handles prune=True` garbage-collects every orphaned
handle (deletes the Empty + any leftover HANDLE_ vgroup); clean/dirty handles are kept
(they still resolve). `feel op=forget name=…` is the targeted prune — delete ONE handle
regardless of state. Engine `prune_handles` / `forget_handle` in handles.py, validating
via the same `_validate` git-state the list already uses. Verified headless: deleting a
handle's owner mesh then `prune` removes the now-orphaned Empty.

## G16 — `assembly` relates object **bounding boxes**, not the **openings themselves** 📐 ✅ FIXED 2026-06-16

`feel op=assembly` reports the pairwise gap between two objects' AABBs (+ which axes
touch) — enough to know two parts are ~N cm apart, but it can't yet answer the question
assembly is *for*: "does **this** opening line up with **that** one?" The spec's section A
named "flush/aligned faces, contact"; Phase 4 shipped the bbox-level subset and the
per-opening `op=map` raycast, but not a **boundary-to-boundary** relation. The general
primitive is a relation between two *handles* (not two objects): given `arms.armhole_L`
and `torso.top_ring`, report centre-to-centre distance, whether their plane normals are
coaxial/opposed (do they face each other?), and the radius/circumference match — the
read a `bridge`/`weld` (G10) needs to decide *if* two openings can be joined before it
tries. `op=map` already computes the loop plane normal; this is that math applied to a
*named pair* instead of a raycast into the scene.

**Resolution 2026-06-16.** `feel op=relate a=<handle> b=<handle>` (engine `feel_relate`
in assembly.py) is exactly that: reuses `op=map`'s `_plane_normal` on a named handle PAIR
and reports centre gap (cm), axis alignment (opposed = face each other / coaxial / skew
N°), and the diameter/size match, plus a `join_ready` verdict (parallel + facing +
similar size). The read `edit op=bridge` needs *before* it tries. `feel op=assembly` now
advertises it in its follow-up line. Verified headless on two facing tubes.

---

## G17 — no **snap/fit a boundary loop onto a target** (the action half of G16) 🧲 UNDO DEFECT FIXED 2026-06-16 (primitive still the wrong tool for hiding a junction)

G16 wants to *measure* whether two openings line up; this is the **action** that should
follow — "take this boundary loop and **fit it onto** that one." Today you assemble it by
hand: read both handle points/sizes (`feel op=assembly`), compute the delta yourself,
`transform op=move_verts` the selected rim by it, `scale_verts` to match size, eyeball the
normal. The missing primitive is one op — **snap the selected boundary loop (or a named
handle) onto a target handle**: translate centre→centre, scale rim→rim, optionally rotate
to align plane normals. General (necks→collars, sleeves→armholes, pipe→flange, any tube→
any opening) and the natural precursor to `edit op=bridge` (G10): *fit, then weld*.
Distinct from `transform op=snap`, which is object-level (AABB side-to-side), not loop-to-
loop; and from `move_to handle=`, which moves a whole **object**, not a selected loop.
Surfaced live 2026-06-16 fitting a torso neck to a head's neck hole — the snap was a
hand-computed `move_verts` from two `assembly` points. Candidate surface: `transform
op=snap_loop handle=<target>` or `edit op=fit_boundary a=<sel> to=<handle>`.

**Implemented** as `transform op=snap_loop handle=<target> [fit_scale] [fit_rotation]`: source
is the live edit-mode selection (no deselect-on-entry), target is a named boundary handle.
Translates the selection's centroid onto the handle's live point; `fit_scale` (default on)
scales the loop rim→rim, `fit_rotation` (default off) tilts the plane parallel by the
shorter turn (no 180° flip). Reports move delta + both diameters.

**NOT verified — retracted 2026-06-16.** Two failures, both instructive:
1. **Outcome ≠ delivered.** I "validated" by confirming the loop centroid matched the handle
   coordinate — my own move-math, self-confirming. The *visible* result had a clear gap
   (user screenshot). Seating two open rims at a cage point is not a connection: both meshes
   are Subsurf'd (evaluated surfaces pull inward from the cage) and nothing welds them, so
   the junction gaps. Worse, seating the rim *at* the hole plane maximises the visible gap;
   a real connection needs deep overlap or a weld — and `edit op=bridge` can't weld into the
   rigged head. So snap-to-cage-handle is the wrong primitive for "hide a junction."
2. **Undo defect.** After `history undo_to` past the snap, the moved verts stayed put
   (z=1.0245, not restored to 1.03) — `snap_loop`'s `push_undo` doesn't register a real
   edit-mode undo step for the in-edit-mode call path. Had to hand-restore. Must fix before
   any re-ship.

The lesson belongs in the gap log: a tool is verified by the **delivered artifact**, not by
re-reading the numbers the tool just produced. Outcome test (the gap actually closes / the
evaluated surfaces meet), undo round-trip, THEN ship.

**Undo defect fixed 2026-06-16.** Root cause: `snap_loop` is *not* an `EDIT_MODE_TOOLS`
auto-switch op (it consumes the live selection the auto-target path would deselect), so it
ran AND pushed its undo step while still in EDIT mode — and an in-edit post-edit checkpoint
has no clean object-mode anchor to undo back to (exactly the "verts stayed put" symptom).
Fix: `snap_loop` now returns to OBJECT mode after committing the edit, so the dispatch's
`push_undo_step` lands an object-mode checkpoint like every other edit verb. **Verified
headless: a snap → `history undo` now restores the moved verts to their pre-snap positions
exactly.** The deeper lesson stands — seating a rim *at* a cage handle is still the wrong
primitive for hiding a Subsurf'd junction (use deep overlap + `edit op=bridge`); the undo
correctness is fixed, the use-case caveat is documented in the op's description.

---

# 2026-06-16 — hard-surface session (ornate longsword, built from primitives)

A different task *shape* from the torso work above: a hard-surface **assembly of
closed solids** (blade, curved quillon guard, wire-wrapped grip, jewelled wheel
pommel), built bottom-up from primitives with known dimensions and stacked by
overlap. It exercised the **actuators** (`add`/`edit`/`transform`/`material`) hard
and the **perception/constructive** half (`feel` topology, handles, assembly,
sculpt) almost not at all — by construction, the status block already knew every
coordinate, so `feel` had little to add and there were no open boundaries to mate.
So these gaps are the actuator-side complement to the file above.

**What this session is NOT:** it is not a verdict that the architecture is wrong —
the opposite. The 17-verb surface mirroring Blender's own menus (Add / Edit / Object
/ Select / Modifier / Material / View / Render) is *pre-learned*, the op-enum reads
as a one-glance capability map, and deferred loading meant ~7 schema loads equipped
the whole build. The agent stayed in intent-space ("seat the blade", "wrap the
grip", "set a gem") for long unbroken stretches — a genuine flow state. The items
below are (a) **two trust-breaking bugs** and (b) **polish toward "blatantly
obvious."** Fix tier (a) first; (b) is the gap between *good* (where it is) and
*breathtaking* (where it's aimed).

## G18 — `object op=mode` cannot switch EDIT→OBJECT 🐛 ✅ FIXED 2026-06-16 (trust-breaker)

`object op=mode name=<obj> mode=OBJECT` **fails every time** with
`Operator bpy.ops.object.select_all.poll() failed, context is incorrect`, and the
mesh stays in EDIT. Reproduced ≥4× this session on different objects. OBJECT→EDIT
works fine — it's specifically the **exit** half that's broken, i.e. half of the
core mode toggle.

**Proof / workaround:** the only way out of Edit mode this session was side effects —
`add` / `object op=delete` / `edit op=bend(apply=True)` all force OBJECT mode. I used
a **zero-angle `edit op=bend angle=0 apply=True`** as the escape hatch (select all →
bend 0 → returns to OBJECT). That a no-op deform is the reliable way to leave Edit
mode is the smell.

**Likely cause:** `set_mode`'s EDIT→OBJECT path calls an object-mode operator
(`object.select_all`, or a select inside the toggle) under a context/area override
where its `poll()` fails. Fix the context the operator runs in (or drop the
select_all from the exit path). This is the highest-priority item — a core verb is
half-dead and the workaround is a hack.

**Resolution 2026-06-16.** Confirmed root cause: with `name=<self>`, the target IS the
active edit-mode object, so the old `active is not obj` guard SKIPPED the edit→object
exit — then `object.select_all(action='DESELECT')` ran while still in EDIT mode and its
`poll()` failed. Fix (objects.py `set_mode`): exit to OBJECT whenever the active object
is in any non-OBJECT mode *before* the object-level select/activate calls, including the
target-is-self case; the target's pre-switch mode is captured first so the exit-edit bind
check still fires. **Verified headless: `set_mode EDIT name=g18` → `set_mode OBJECT
name=g18` now succeeds and actually lands in OBJECT mode.**

## G19 — `feel op=contacts` returns a **stale/constant** value (and mislabels interpenetration as a gap) 📐 ✅ FIXED 2026-06-16

`feel op=contacts` reported `Pommel: floating — nearest 'Grip', gap 1.7mm`. I nudged
the pommel **+6 mm** (`transform nudge up=0.006`, confirmed in the status bounds) and
re-ran contacts: **identical `gap 1.7mm`**, unchanged to the tenth of a millimetre
after a 6 mm move. The reading does not track the live geometry.

**Ground truth contradicts it:** by the bounds the tool itself returned, the pommel
(sphere, z=[-0.186,-0.138]) overlapped the grip (cylinder, bottom z=-0.16) and was
**wider than the grip** at the overlap — solid interpenetration, not a 1.7 mm gap.

**Diagnosis:** smells like AABB-distance math (or a cached value), not true
nearest-surface distance — a sphere seated into/around a cylinder is exactly the case
where bounding-box gap lies. This is the **same root as G16** ("assembly relates
bounding boxes, not the openings themselves") and a sharper instance of the older
`check_contacts` bullet under *Open*. **A verification tool returning a confident wrong
number is worse than returning nothing** — it directly contradicts the
"status-block-as-ground-truth" contract the server is built on. Fix: measure real
nearest-surface distance on the evaluated meshes; when shells interpenetrate, **say
"interpenetrating Nmm"**, never a phantom positive gap; and make the value track the
geometry (a 6 mm move must move the number).

**Resolution 2026-06-16.** The labeling logic was already correct (BVH nearest-surface
distance + all-axis bbox overlap → connected/floating/penetrating); the bug was pure
**staleness**. `check_contacts` reads `eval_world_bmesh`, which — unlike its sibling
`eval_world_bbox` (which already had the X6 `update_tag()`+`view_layer.update()` guard) —
did NOT force a depsgraph refresh. Socket-driven ops skip Blender's normal post-operator
update, so a prior `transform nudge` left `evaluated_depsgraph_get()` handing back the
OLD mesh → the frozen 1.7 mm. Fix: gave `eval_world_bmesh` the same refresh guard, so
every tactile read built on it (contacts, resting, symmetry, overlaps) now tracks live
geometry. **Verified headless: a 2 m nudge now changes the reported contacts gap.**

## G20 — no continuous **helix / coil** primitive (and `add points` caps at 32) 🌀 ✅ FIXED 2026-06-16

A wire-wrapped grip wants one continuous **helix**. `add type=tube points=[…]` rejected
it: `'points' supports at most 32 control points (got 73)` — a 9-turn coil at a
round-looking ~8 pts/turn needs ~73, and 32 caps you below ~4 usable turns. Fallback was
**11 separate torus rings** placed by a duplicate→nudge chain (~16 calls, and a banded
look, not a true spiral).

**General primitive:** a parametric `add type=helix|coil` — `turns, height, radius,
tube_radius, taper, handedness` — which subsumes wire wraps, springs, screw threads,
coiled cable, rope, twist-fluting. It sidesteps the point cap entirely instead of
fighting it. **Cheaper interim:** raise/justify the 32-point cap, and/or let
`tube`/`curve` interpolate control points smoothly (NURBS/Bézier) so few points stay
round — today a sparse `points` list bakes faceted. (The point cap also limited any
hand-authored swept path, not just helices.)

**Resolution 2026-06-16.** Added `add type=helix` (engine `helix_coil` in curves.py):
parametric `turns / height / radius / tube_radius / taper / handedness / axis / center /
segments_per_turn / sides`. It generates its OWN dense sample polyline and sweeps it with
the existing curve→mesh bevel machinery, so it **ignores the control-point cap entirely**
(the gap's preferred fix — sidestep, don't fight). Separately, the `points` cap on
`tube`/`curve` was raised 32 → **256** (the per-point resolve is cheap; 256 still guards a
runaway payload). **Verified headless: a 9-turn helix builds in one call** (the exact case
that needed ~73 points and was blocked).

## G21 — `edit op=bend` is **illegible** (can't predict pivot or curve shape) 🔁 ✅ FIXED 2026-06-16 (docs)

Bending a flat X-aligned bar into a curved crossguard, `edit op=bend axis=Y angle=55`
then `angle=34` produced a symmetric **humped / "mustache"** profile (center at z≈0,
apexes at z≈±0.06 at *mid-arm*, tips recurving back toward center) — not the clean
crescent I expected. I couldn't predict the direction or the pivot a priori; I had to
**measure tips-vs-center twice** to even read what it did, then **abandon `bend`
entirely** for a `proportional_move` tip-lift. Cost: **two full guard rebuilds**
(delete → re-add → re-cut loops).

The behaviour may be correct Blender SimpleDeform — the gap is **legibility**, not
math. The op never states its **pivot** (origin? cursor? selection centroid?) or the
(axis, angle) → resulting-arc mapping, so it's trial-and-measure. Fix: document the
pivot + axis convention concretely, with one worked example ("X-bar, axis=Y, +angle →
arc in XZ bulging +Z about the object origin"). No behaviour change needed — just make
it predictable. (Also document the OBJECT-mode side effect of `apply=True`; it's load-
bearing for the G18 workaround.)

**Resolution 2026-06-16 (docs, no behaviour change).** The `bend` docstrings (engine
finishes.py + both verb surfaces) now state: the pivot is the **object ORIGIN** and the
deform is **SYMMETRIC about it** — geometry on both sides curls equally, growing with
distance — so a part centred on its origin humps both ways (the "mustache"), NOT a single
tilted arc; move the origin to one end first for a clean one-way crescent. Includes the
worked example (X-bar, origin centred, axis=Y, +30° → symmetric smile in XZ) and the
`apply=True` forces-OBJECT-mode side effect (the G18 escape hatch).

## G22 — `view op=check_framing` percentages **silently change reference frame** 🎯 ✅ FIXED 2026-06-16

`check_framing` reports "% of frame," which is genuinely useful — but the frame
**aspect it measures against is invisible and mutable.** The same blade read **78.8 %**
of height before any render resolution was set (default/square sensor), then **48.8 %**
after a `render op=image` had set 1000×1400 portrait — same camera, different
unstated reference. The numbers aren't comparable call-to-call and I can't tell which
aspect a given reading assumes.

**Fix:** state the aspect/resolution each reading is computed against ("vs 1000×1400
portrait"), and ideally let `check_framing` take an explicit target aspect so framing
can be validated for the intended output *before* committing a render. Small, but it's
the same family as G23 — a number whose meaning quietly shifts underfoot.

**Resolution 2026-06-16.** `check_framing` now returns a `frame_ref` (resolution +
landscape/portrait/square word + ratio) and the rendered line prints it — "camera 'cam'
(vs 1920×1080 landscape):" — so every reading states the frame it measured against.
Added `aspect='WxH'|'W:H'`: it temporarily retargets the render frame to the intended
output, computes coverage, then restores the scene's own resolution exactly — so framing
can be validated for a planned render *before* committing one. **Verified headless: the
reference is reported, and `aspect='1000x1400'` is reflected in `frame_ref`.**

## G23 — the per-verb **parameter union**: polymorphic params + scan tax 🪢 ✅ PARTLY FIXED 2026-06-16 (move 1 done; 2–4 open)

The 17-verb consolidation got the important thing right (catalog legibility, above) —
**do not undo it.** But the cost migrated into the **parameter schema**: each fat verb
(`transform`, `add`, `edit`) carries a union of ~40–50 params, any one op uses a
handful, so choosing an op means scanning a long list and filtering. The `[op]`-prefix
tags on every param are the load-bearing mitigation and they work — but two sharp
edges remain, and they're exactly the "obvious / blatant / never put stuff in a weird
place" bar:

- **Polymorphic params (the real offender).** A field that changes meaning by op is a
  micro-betrayal of trust. `to_x` is *world X* under `move_to` but *euler degrees*
  under `rotate_to`; `axis` / `target` / `name` shift sense across ops. This session it
  was a **tax, not a failure** (navigated by careful reading) — but it's the gap between
  good and breathtaking.

**Litmus test for the fix:** a param is correctly designed if its meaning is
unambiguous from the **op name + param name alone**, without reading the description.

**Moves, ranked by leverage / effort:**
1. **Kill polymorphic params** (purely additive): give `rotate_to` its own
   `deg_x/deg_y/deg_z`; reserve `to_x/to_y/to_z` for position; never let one field mean
   two things. Wider-but-honest beats narrow-but-overloaded.
2. **Put each op's param manifest in the op-enum description** —
   `box — uses: name, width, depth, height, on`. Inverts the lookup: picking the op
   hands you its params instead of scan-and-filter. (The inverse of the `[op]` tags,
   pointed the direction that matters at decision time.) Cheap, description-only.
3. **Teaching errors + one canonical example per op** — `op=bevel needs width OR
   factor; got neither`, and `box → {op:box, name, width, depth, height}`. Turns the fat
   schema into a guided loop / pattern-match instead of a memorization burden. Fits the
   existing status-block-teaches philosophy.
4. **Last resort — split only the 2–3 genuinely fat verbs** into namespaced sub-tools
   (`transform_move_to`), the verb surviving as an index that lists its ops. Regains
   per-op precision; honest cost = a discovery hop + re-introduces a sliver of the old
   150-tool world, so apply it **only** where the schema is actually fat, never to the
   lean verbs (`scene`/`view`/`render`).

Note: JSON-Schema conditionals (`if op=X then required:[…]`) help **server-side
validation/enforcement** but *hurt* readability — use them to catch errors, not to buy
obviousness. Obviousness comes from moves 1–2.

**Resolution 2026-06-16 — Move 1 (the real offender) done.** Killed the worst
polymorphic param: `rotate_to` now has its own `deg_x/deg_y/deg_z` (absolute euler
degrees), and `to_x/to_y/to_z` are reserved for `move_to`'s world position. No field
means two things anymore — each param's meaning is unambiguous from op + name alone (the
litmus test). `rotate_to` still falls back to the old `to_*` if `deg_*` is unset, so
pre-change callers don't break while the schema steers to the clear name. **Moves 2–4
(op-enum param manifest, teaching errors + canonical examples, last-resort fat-verb
split) remain open** — they're broader schema-surface work, tracked here for a later
pass; do not undo the 17-verb collapse.

---

## What worked — formalize this, don't fight it

The soft volume was placed, sized, projected, teardropped, splayed, spaced,
and given a concave slope — **with zero new code**, by improvising the missing
bridge out of four ingredients. This is the template the server should lean into
instead of trying to make the agent a freehand sculptor:

1. **Parametric proxies, not freehand.** A guide sphere is four legible dials
   (center, radius) the agent *can* reason about; a brushstroke at a guessed
   point is not.
2. **The status block as a closed coordinate loop.** Every nudge returned exact
   new bounds — the agent navigates by instrument without "seeing."
3. **Human eyes as a first-class pipeline stage.** Every judgment the agent
   structurally can't make ("too wide", "generous isn't on-model") came from the
   user. Precision from the agent, taste from the human — a permanent division,
   not a phase.
4. **Deltas, not absolutes.** Start close, correct in small safe steps that
   converge.

**Partnership feedback channel worth making first-class:** the human hand-edits
*one* side; the agent reads the **transform delta** (`object info`) and
propagates it to the mirror twin. ("You rotated the left-side form +25° yaw — let
me mirror that onto the right.") A "match/mirror this object's edit to its twin"
affordance would make this a one-call move.

**The 17-verb surface itself (2026-06-16, sword session).** Formalize this, don't
drift from it: collapsing ~150 flat tools into 17 verbs × an `op` enum didn't just cut
the count — it imposed a **two-level tree** on ~250 operations, and the tree is what
made it navigable. Two properties carry it: (1) the verbs **mirror Blender's own menus**,
so a Blender-literate agent arrives *pre-trained* — no taxonomy to learn; (2) each verb's
**op-enum reads as a one-glance capability map** ("editing is these ~22 moves"), so the
agent discovers what's possible in one schema read instead of spelunking 150 descriptions.
With deferred loading, ~7 schema loads equipped the entire build. The result is the agent
staying in **intent-space** ("seat the blade", "wrap the grip", "set a gem") for long
unbroken stretches — flow. Every flow-*break* this session was a moment a bug or an
illegible op forced attention off the work and onto the tool (G18/G21/G19). The design
target is **ready-to-hand**: the server disappears. Guard this; the polish items (G22/G23)
serve it, they don't replace it.

---

## Corrections (things wrongly flagged this session)

- **`duplicate_mirrored` is fine.** It does *not* drop a rotated source's
  orientation — that read came from the bbox and was wrong. Logged here only as
  evidence for G2.

---

## Carried over (still relevant, bears directly on G3)

- **Multires + dyntopo wrappers** — the proper resolution story for organic
  sculpt.
- **Retopology** (auto or guided) — once the form is sculpted, deformation-grade
  edge flow.
- **UV unwrap, material node graph, hair cards, face-loop topology** — further
  out, on the road to a finished character.

## Open (older, unverified against current build)

- `check_contacts` / contact queries timing out on dense evaluated meshes
  (Spring's production geometry) vs the socket window.
- bbox-vs-`sel_z` self-contradiction flag (the stale-eval-cache symptom).

---

## The thesis these all serve

The agent's vision can **judge** but cannot **measure**; it reasons over
outlines, profiles, scalars, and named regions — never coordinate dumps. The
destructive half already honors this (`feel` → named handles → anchored verbs).
**The work now is to extend that same contract to construction:** aim in
fractions-of-the-form, get form-verdicts back, keep the human's eyes in the loop.

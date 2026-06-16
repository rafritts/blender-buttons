# MCP gaps

_Rewritten 2026-06-16, from the first real body-sculpting session (building a
female torso onto the Spring rig — breasts from scratch, by feel + partnership).
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

The **constructive / sculpt** half lacked that bridge: "where a breast goes" is a
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

The body cage has ~**12 verts / 5 faces** across a whole breast-sized patch —
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
promoted to work, this is **SPEC-07** territory: pattern + `followups.py` mechanism +
the table, table signed off first.

---

## What worked — formalize this, don't fight it

The breast volume was placed, sized, projected, teardropped, splayed, spaced,
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
propagates it to the mirror twin. ("You rotated the left breast +25° yaw — let
me mirror that onto the right.") A "match/mirror this object's edit to its twin"
affordance would make this a one-call move.

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

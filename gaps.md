# MCP gaps

_A **live worklist of OPEN gaps** — fixable limitations in the MCP surface, nothing
historical. Shipped/fixed items are **removed** (they live in git history), so this file
is only ever "what's still wrong." G-numbers are **stable across rewrites**: a number
missing from the sequence (G1–G8, G10–G13, G15–G22) means that gap shipped and was
retired. Last rewrite 2026-06-17 (desk-lamp session)._

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

## G23 — the per-verb **parameter union**: scan tax (moves 2–4 open) 🪢

The 17-verb consolidation is right — **do not undo it.** But each fat verb (`transform`,
`add`, `edit`) carries ~40–50 params; any one op uses a handful, so picking an op means
scanning and filtering. The `[op]`-prefix tags are the load-bearing mitigation and they work.
Move 1 (kill polymorphic params — `rotate_to` got its own `deg_*`) shipped. Remaining:

**Litmus test:** a param is correctly designed if its meaning is unambiguous from **op name +
param name alone**, no description needed.

2. **Put each op's param manifest in the op-enum description** — `box — uses: name, width,
   depth, height, on`. Inverts the lookup: picking the op hands you its params instead of
   scan-and-filter. Cheap, description-only.
3. **Teaching errors + one canonical example per op** — `op=bevel needs width OR factor; got
   neither`, and `box → {op:box, name, width, depth, height}`. Turns the fat schema into a
   guided loop instead of a memorization burden. Fits the status-block-teaches philosophy.
4. **Last resort — split only the 2–3 genuinely fat verbs** into namespaced sub-tools
   (`transform_move_to`), the verb surviving as an index of its ops. Honest cost = a discovery
   hop + a sliver of the old 150-tool world, so apply **only** where the schema is actually
   fat, never to lean verbs (`scene`/`view`/`render`).

Note: JSON-Schema conditionals help server-side *validation* but *hurt* readability — catch
errors with them, don't buy obviousness with them. Obviousness comes from moves 2.

## G24 — no render **preflight**: engine availability + GPU device are invisible 🖥️ ❗ RECURRING

Keeps biting across sessions. The whole architecture rests on **"don't read the render back,
trust ground truth"** — which makes those reads load-bearing. Rendering's reads currently
*lie*, and the agent has no fallback (it can't look at the image to catch the mistake).

**Three blind spots, all general:**
1. **Scene engine ≠ renderable engine.** The status block prints `scene.render.engine`
   verbatim — which can name an engine (`CYCLES`) the render path will *reject*. A *false*
   instrument is the worst failure for a "trust the instruments" design.
2. **The Cycles GPU layer is invisible.** GPU rendering lives in **addon preferences**, not
   the scene: `addons['cycles']` enabled?, `compute_device_type` (CUDA/OPTIX/HIP/…), the
   device list + which are enabled. `render op=settings` reports none of it — so "GPU, or
   silent CPU fallback?" is unanswerable.
3. **No SET path for the preference layer.** `render op=cycles device=GPU` only flips
   `scene.cycles.device`; it can't enable the addon, pick `compute_device_type`, or enable
   devices — and reports success regardless.

**Live evidence (desk-lamp session):**
- **`render op=settings` contradicts itself in one read:** `engine: CYCLES   available:
  BLENDER_EEVEE`, plus a full `cycles: device=GPU …` block. Blender refuses to set an invalid
  engine, so the engine genuinely *is* Cycles — the **`available` list is the liar**.
- **Validation on that list rejects the real engine.** `render op=image engine=CYCLES` →
  "not available… ['BLENDER_EEVEE']". **Workaround:** omit `engine=` (empty = keep scene
  engine) to bypass the broken check.
- **`device=GPU` reports success, then OOMs.** `render op=cycles device=GPU` returned clean;
  `render op=image` died with `Out of memory in CUDA queue enqueue` on a ~dozen-primitive
  scene. No VRAM visibility, so no CPU-vs-GPU choice up front — only recovery was hit OOM,
  set `device=CPU`, re-render.

**Fix:**
- **Make the status `render:` line truthful** — `render: CYCLES ⚠ NOT AVAILABLE (build has:
  BLENDER_EEVEE)`; never present a non-renderable engine as plain state. Fix `available_engines`
  so it lists the genuinely-active engine.
- **Turn `render op=settings` into a real preflight** — addon enabled?, `compute_device_type`,
  device list with enabled flags, the **effective** device (GPU vs CPU-fallback), free VRAM /
  a GPU-viability signal.
- **Give `render op=cycles` the preference-layer knobs** (`compute_device_type`, enable/disable
  devices) — and **refuse with a teaching error** for a config the machine can't provide,
  instead of a hollow success.

## G25 — no "orient along axis A→B" for non-tube primitives (off-axis placement forces hand-trig) 🧭

`add type=tube points=[A,B]` orients itself between two points — the right affordance. But
`cylinder`, `cone`, `helix`, `box` have no equivalent: to lay one along an arbitrary direction
you compute the euler yourself. This session the lamp's spring and the bulb socket both had to
be tilted by **hand-computed angles** (`deg_x=150`, axis `(0,−0.5,−0.866)`) plus a coaxial
offset — pulling the coordinate "ripcord" the whole server exists to avoid. Springs/coils/
threads almost never run along world Z; they run along *some* edge, so `helix` (G20) is
half-crippled without this.

**General primitive:** `transform op=aim_axis from=<pt|handle> to=<pt|handle> [axis=Z]` —
rotate the object so its local axis points down the A→B segment. And/or `wrap`/`align-to-edge`
so a coil seats on a named edge/handle directly. Endpoints accept handles, so it composes with
`feel op=aim`/assembly. This is the construction-side analogue of `tube`'s point list, for the
solids that don't have it.

## G26 — no "settle / rest onto a surface" using actual lowest geometry ⬇️

Three times this session I hand-computed a z so a part rests on what's under it: the notebook
coil onto the desk, the pencils onto the cup's inner floor, the page-stack height.
`transform op=snap` does flush-**AABB**-side-to-side — but for a rotated or irregular part the
AABB bottom ≠ the true contact point, so it mis-seats them, and there's no "lower this until
its real geometry touches that surface."

**General primitive:** `transform op=rest_on target=<obj> [axis=Z]` (a.k.a. `drop`) —
translate along −axis until the source's nearest geometry contacts the target, leaving them
tangent. Reuses the exact BVH nearest-surface math `feel op=contacts` already runs, and closes
the loop between "contacts says floating/penetrating 3mm" and an action that fixes it without
the agent doing the arithmetic.

## G27 — `material set` rejects a list of targets despite advertising "object(s)" 🎨

`material op=set target="base,hub,arm_lower,arm_upper,shade"` → `Target '…' not found`. The
docstring promises "object(s) to shade" with group-expansion, but a comma list isn't accepted,
so a 5-object recolor is 5 calls. A schema that promises plural and a tool that rejects it is a
small trust-nick (same family as G24's false instrument / G29's illegible number).

**Fix:** route `material`'s `target` through the same `_targets()` parser (`a,b,c` + group
names) that `transform`/`feel`/etc. already use everywhere else, so plural means plural across
the whole surface. (Falling back to "fix the docstring to say one-object-or-group" is the lesser
option — the parser already exists; make it consistent.)

## G28 — edit-mode ops are inconsistent about who manages mode + selection 🔀

`edit op=loop_cut` auto-enters edit mode, operates, and auto-returns to OBJECT — fully
self-contained. `edit op=jitter` refuses with **"Must be in edit mode"** and operates on the
current selection — so it needs a manual `object op=mode EDIT` + `select op=all` first. From
the caller's seat the two look identical (`edit op=…` on a target) but have **opposite
contracts**, and nothing in the schema says which is which. Cost three round-trips on the page
jitter this session.

**Fix:** make every `edit` op honor the same `target` auto-enter/select/exit path the
`EDIT_MODE_TOOLS` ops use (jitter + any peers join that set) — OR, if an op genuinely needs a
pre-existing selection, **say so in its description** and default to "whole mesh" when none is
present. One predictable contract across the verb, not a per-op coin-flip.

## G29 — `feel op=distance` "ANY" returns an illegible positive number 📏

`feel op=distance a=nb_cover_front b=base` reported **0.229 m** when the true nearest-surface
gap is ~0.03 m. Penetration readings are crisp and trustworthy (`penetrating by 9.3mm`), but
the positive-distance "ANY" mode handed back a value I couldn't reconcile with the geometry —
it reads like a centroid/vertex-pair distance, not true nearest-surface. In a server whose
pitch is "trust the instruments," a measurement the operator can't *explain* is corrosive even
when it doesn't change the decision (here it didn't, but only because the sign was right).

**Fix:** make "ANY" report genuine nearest-surface distance (the BVH path `contacts` already
uses) and **label what it measured between** — "nearest faces" + the two points — so the number
is checkable against the bounds the status block reports.

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

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
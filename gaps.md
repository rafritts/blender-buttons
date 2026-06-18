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

## G53 — a mesh's facing/orientation isn't handed back; the agent re-derives it every read 🧭 ✅ SHIPPED

Every read this session, the agent burned reasoning re-deriving the same fact — "front = −Y,
up = +Z, right = −X" — from the world bbox plus a handedness cross-product done in its head.
That's repeated, error-prone (the cross-product is easy to flip), and exactly the
dead-reckoning the server exists to kill: a *signed local frame* is ground truth the geometry
already determines, but no read states it. So the agent guesses orientation, and a flipped
guess silently poisons every downstream left/right/front call (e.g. grabbing the wrong half
of a mirrored pair, or casting `feel op=aim` from the wrong face).

**The ingredients are already computed.** `feel`'s cheap bundle includes `symmetry` (best
mirror plane) and `frame` (intrinsic principal axes). A facing read is a thin synthesis on
top: lateral axis = the symmetry plane's normal; up axis = the principal axis nearest world Z;
front = the remaining axis, *signed* toward the feature-dense / mass-forward side. Near-free —
it rides data the bundle already pays for.

**Discipline (legible, not divining — per [[feel_legibility_not_divination]]).** Report the
frame only when the geometry *supports* an inference (a clear symmetry plane + separated
principal axes), and **state the evidence** ("front −Y: shallowest axis, opposite the
symmetry-broken feature mass"). When ambiguous — a mug, a sphere, a radially-symmetric part —
say "no clear facing," don't invent one. The point is to hand back a defensible frame, not to
pretend every mesh has a front.

**General primitive, not "character facing."** An *orientation-frame* read: given any mesh,
name its signed local axes (which world axis is its long/up axis, which is its
symmetry/lateral axis, the sign of its front) with the evidence, or abstain. Natural home: a
line in `object describe` and/or `feel method=frame`.

**Shipped** as `feel method=facing` (`_m_facing` in `extension/topology.py`): up = the
principal axis most aligned to world +Z; lateral = the centroid-relative mirror plane when one
axis is a clear bilateral winner; front = the remaining axis signed toward the vertex-dense
(feature) side; left/right = `front × up`. Each axis prints its evidence; it abstains on a
rotated/near-isotropic mesh, on no clear mirror plane (→ left/right undefined), and on near-
centred front-to-back mass (→ front sign withheld). Kept OUT of the cheap bundle — orientation
is a distinct question the agent asks once, not per structure-read. Not yet wired into `object
describe` (deferred; `feel method=facing` covers the need).

## Carried over — bigger build-outs (not yet started)

- **Multires + dyntopo** as real multi-level sculpt targets — the proper organic-sculpt
  resolution story (distinct from the local-subdivide that shipped under G3).
- **Guided/interactive retopology** — deformation-grade edge flow drawn by hand once a form is
  sculpted. (Auto-retopo + the face-authoring primitives shipped: `object op=remesh`
  voxel/QuadriFlow, `edit op=poke/inset/grid_fill`, surface-tangential `edit op=relax/slide`.)
- **UV unwrap, material node graph, hair cards, face-loop topology** — further out, the road to
  a finished character.

## Open (older, unverified against current build)

- `check_contacts` / contact queries timing out on dense evaluated meshes (Spring's production
  geometry) vs the socket window.
- bbox-vs-`sel_z` self-contradiction flag (a stale-eval-cache symptom — may already be cured by
  the G19 depsgraph-refresh fix; needs re-checking on dense geo).
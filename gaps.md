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

**Further witnesses (yard build).** The agent deleted-and-re-added a camera to reframe the
scene instead of reaching for `view op=camera_position` (it existed; nothing pointed at it),
and reasoned about picket/rail z-fighting by hand instead of running `feel op=overlaps`. Both
capabilities were present and went unused — the response payloads never surfaced them, and
under deferred tool-loading their docstrings weren't in context either. Discoverability, not a
missing primitive.

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

## G58 — `bridge` is straight-only; the one cheap win for curved welds 🌉 🛠️ IMPLEMENTED — pending live dogfood

Welding two open loops (`edit op=bridge`) lays a **single ring of shortest-path quads** — no
curvature, no segments, no twist, no profile. Native Blender *Bridge Edge Loops* already
exposes **Number of Cuts, Smoothness, Profile Factor, Twist, Merge**; none are surfaced. So
the only weld the agent can make between two openings is a straight strut, and "organic"
is impossible at the weld step itself.

**Witness (two-cylinder connect, 2026-06-18).** Two capped cylinders, openings 75.8°
off-parallel and 2:1 in size. Removing the caps + `bridge` produced a clean watertight
manifold — but dead straight. To curve it, the agent had to subdivide that band and
`proportional_move` it by hand (5 destructive steps, no path control, and it deformed a
cylinder — see G60). One `cuts=`/`smoothness=` pair on `bridge` would have produced the
arch directly, on the real loops, with a dial.

**Fix (cheap, mechanical).** Pass through to the existing Bridge Edge Loops operator's
`number_cuts` / `interpolation` / `smoothness` / `profile_factor` / `twist`. This is the
**smallest change with the biggest payoff** in the whole curve story — a parameter
pass-through, not new machinery. The expressive, geometry-bound version is [[SPEC-10]];
this is the 80% that ships in an afternoon.

**Implemented** as new args on `edit op=bridge`: `bridge_cuts` (0=straight, the
unchanged default), `smoothness`, `interpolation` (linear|path|surface), `profile`
(profile_factor bulge), `twist` (rim-to-rim vertex offset, kills the spiral). Pure
pass-through to `bpy.ops.mesh.bridge_edge_loops` in `extension/editmode.py:bridge_handles`,
threaded through `server/editmode.py:bridge` and `server/verbs/edit.py`; the shape used
is echoed in the status line. Offline (teaching/dispatch) verified; **delete this entry
once the curved weld is dogfooded live** (needs addon reinstall + MCP reconnect).

## G59 — no geometry-bound curve: the agent is the only glue between curve and mesh → SPEC-10 ✍️

The deepest gap. The `curve`/`tube` primitives are **blind to the geometry they connect**;
`feel` reads the geometry but emits no curve. So to connect two openings the agent must, by
hand: read each opening's centre + outward normal, do the trig in a script, and feed raw
coordinates to a Bézier that has no idea the cylinders exist. There is **no primitive that
anchors a curve endpoint to a handle with tangent = the opening's normal** — and that
binding *is* every "organic" quality (leaving the pipe the way the pipe points, tangent
continuity at the seam). Without it, "organic" reduces to dead-reckoned control points.

This is net-new capability, not a fix — promoted to **[[SPEC-10]]** (geometry-bound,
parametric, weld-aware connectors). Both human prompts that exercised it — "make it a
singular elegant curve" and "connect it with a sequence of crazy curves" — are squarely
SPEC-10, not any existing verb.

## G60 — `proportional_move` bulges, not paths: no "lay geometry along a centreline" 🧊 🛠️ region-constraint half IMPLEMENTED — pending live dogfood

**Region-constraint sub-gap — IMPLEMENTED.** `edit op=proportional_move` fell off by
**straight-line distance, blind to topology / membership**, with no way to "deform this
connector, hold the cylinders rigid." Added `connected=true` (geodesic edge-distance
falloff — a different shell is unreachable, so a big pull can't drag it) and
`freeze=<handle>` (those verts held rigid, and in connected mode they wall off the
flood). Witness: `radius=1.7` dragged cylinder-wall verts and deformed a cylinder; freeze
now holds them. In `extension/editmode.py:proportional_move`, threaded through the server
verb. **Delete this half once dogfooded live** (addon reinstall + reconnect).

**Remaining sub-gap → [[SPEC-10]]: displacement ≠ path.** Even constrained,
`proportional_move` makes a *bulge*, not a *curve*: it pushes a blob in one direction.
There is no "lay this ring of geometry **along a centreline**, cross-sections kept
perpendicular to the tangent." Bulging a weld will never read as a swept curve — that's
why the hand-sculpted arch still "isn't a curve." This is the SPEC-10 sweep engine, not a
falloff dial; it stays open here as a pointer.

## G61 — no sweep yields a hollow, weldable, vert-count-matched tube 🪈

Connecting two *different-sized* openings needs one operation that **sweeps + tapers +
matches each opening's ring count (32→32) + welds both ends**. All three sweep paths fail a
different way:
- **`edit op=extrude_along_curve`** sweeps the *filled* face → a solid, non-manifold rod
  (read back `genus -24`); it's face-only, so it won't sweep an *open* rim into a hollow
  tube, and it ignores the curve's world placement (relaunches it along the face normal).
- **`add type=tube` (SPLINE_TUBE)** **creases** — no roll control on the cross-section, so
  the minimal-twist frame flips at a sharp bend — **forces 36 sides** (ignores `sides=`, so
  it can't 1:1 weld to a 32-vert hole), and **fragments into multiple shells** with doubled
  boundary loops (witnessed again 2026-06-18: 3 shells / 4 boundaries on a gentle arc).
- **`add type=curve` + `bevel_depth`** is clean and continuous but **constant-radius** (no
  taper to reconcile a 2:1 size mismatch), its **cross-section count is uncontrollable**
  (defaulted to a 12-gon → faceting that reads as creases; no param exposed), and it's a
  **separate, un-welded mesh**.

The need is a hollow profiled sweep with controllable section count, end-taper, and a stable
frame — the swept-geometry engine under [[SPEC-10]].

## G62 — a handle doesn't know if it's on an open boundary or a closed cap 🕳️ 🛠️ IMPLEMENTED — pending live dogfood

Boundary handles minted on the end of a *capped* cylinder read **"● clean"**, and `relate`
happily proposes welding them — but they sit on **closed walls** (`feel op=assembly`:
"closed — no open boundaries"), so there is nothing to weld into. The agent connected to
capped ends for three iterations before `assembly` surfaced the truth.

**Implemented** in `feel op=relate`: each endpoint is classified **open rim vs closed
cap** by counting open-boundary edges (one adjacent face) within the handle's vert-set —
computed **live** (capping/uncapping changes it, so a stored flag would go stale). A
closed cap is reported per-endpoint, forces `join_ready=false`, and emits a warning naming
which handle and to uncap it first. **Delete once dogfooded live.** (Left for later: the
same open/closed line on the generic `feel op=handle` read — relate is where the bug bit.)

## G63 — `object op=join` orphans handles instead of migrating them 🔗

After joining two meshes, their handles still claim their **old owners** (`big_cyl_face1` →
`Cylinder.001`, now gone), so `edit op=bridge` refused the loops as "cross-object" even
though they were now in one mesh. The agent had to prune and re-mint via `feel op=assembly`.
Handles should **follow their verts into the merged object** on join (re-point owner, keep
the name), or join should report which handles it re-homed.

## G64 — `feel op=assembly` (and the connection reads) are mesh-only, blind to live curves 👁️

You author a connector as a **curve datablock** but can only *verify* it as a **mesh** —
`feel op=assembly` returns "not a mesh / not found" for a live curve, so the agent must
`object op=convert` to even see the connection it just made. The authoring representation
and the verification representation don't overlap. Assembly/relate should evaluate a curve's
*beveled* surface (its `to_mesh()` eval) without a destructive bake.

## G65 — nothing reads *curve/connection quality*; verification sees watertight, not grace 📐

`feel op=mesh` certifies **watertight** and `feel op=assembly` certifies **contact** — but
neither judges the connector *as a connector*: **tangent continuity at the seam** (does it
leave along the opening's normal?), **curvature** (is it a single clean arc or a lump),
pinching, flow. The agent is aesthetically blind precisely on the axis that is the goal, and
(told correctly not to read renders back) has **no ground-truth way to see whether a curve is
elegant before baking it** — and can't even quantify "that's not a curve," having no
curvature read to cite. Needs a curve-centreline read (curvature κ along length, tangent-vs-
normal angle at each seam, min bend radius vs. profile radius) — generalising the one good
diagnostic that already exists (`extrude_along_curve`'s bend-radius-vs-profile preflight).

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
- status-block `dims`/`bounds` **inflate after joining a rotated multi-shell mesh** (reported
  7.73 m for geometry that was actually unchanged; `feel` shell sizes were correct). Looks like
  an OBB-in-rotated-local-frame projection, not real distortion — but the convenience bbox lied
  while ground-truth reads held. (Witnessed 2026-06-18, same family as the bbox item above.)
- **selection/mode silently resets to OBJECT between calls** — `select op=current` errored
  ("must be in edit mode") right after `select` ops that appeared to act; the edit selection
  survives on the mesh but mode does not, so multi-step edit sequences need an explicit
  `object op=mode mode=EDIT` re-entry. Workflow friction, re-confirmed 2026-06-18.
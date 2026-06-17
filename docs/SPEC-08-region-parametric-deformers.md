# SPEC-08 — Region-parametric deformers: put the sculpt skill in the tool

_Status: Proposed 2026-06-17. **Phase 1 (Tier A — gravity drape) + the eyeless verify
reads implemented 2026-06-17, untested — awaiting a live-build dogfood.** Tiers B–E and
the mask/bake shared infra remain open. Sourced from the bust enlarge → gravity-shaping
dogfood — see gaps.md G46 (and the "cone, not teardrop" reflection)._

## The problem

Two walls, compounding, both hit head-on this session trying to shape a breast
**organically** (enlarge it to a G cup that *hangs* like real tissue):

1. **Hand-driven strokes need a seeing operator, and the agent isn't one.** The
   `sculpt` brushes (grab, draw, inflate, …) are *expressive* tools — their correctness
   lives in the human's eye-hand loop, not in the algorithm. Driven by reasoning they
   produced a forward-projecting cone "held up by invisible hands," not a hanging
   teardrop. No amount of brush *access* fixes this: the missing part is the eye, not
   the brush.

2. **The numeric instruments are blind to the quality that failed — worse, they
   misreported it.** bbox cross-sections + `region_form` said "fullest point dropped,
   lower pole filled → teardrop"; the actual surface was a torpedo. A teardrop and a
   cone share the same fullest-Z and the same lower-pole depth. The instruments measure
   *bigger* and *lower*; they cannot see *drape vs. projection* — which is the entire
   axis that defines "organic."

The lesson (the human's, this session): stop hand-sculpting organic forms by reasoning.
The skill has to move **into the tool**.

## The principle

Expose deformers whose **correctness lives in the algorithm, not the operator's eye** —
**region-based** (a mask/selection picks *where*) and **parameter-driven** (gravity /
strength / stiffness say *how much*), producing a **physically-plausible result by
construction**.

This is the inversion the eyeless-agent constraint demands: the tools most valuable to a
*human* sculptor (Clay Strips, Scrape, Snake Hook — expressive, hand-guided) are the
*least* valuable here, and vice-versa. "Which sculpt tools to expose" is therefore **not**
"all of them" — it's "the ones that don't require a seeing operator."

It also rescues the instruments. When the tool **guarantees the class of deformation** (a
gravity solve *will* hang), the agent's job collapses from *invent the shape* (needs eyes)
to *tune the magnitude* (the numeric reads can verify). Correct-by-construction shape +
measurable magnitude = a loop the agent can actually close blind. The whole spec is that
trade: pay in tool machinery, get back a deformation whose *shape* you don't have to see
to trust.

## The deformers, ranked by alignment (cheapest + most-aligned first)

### Tier A — Mask + Mesh Filter (the lead primitive) 🜄

Sculpt-mode **Mesh Filters** apply one operation to a whole region in a single shot — no
stroke aiming, just a region + a strength. The set: **gravity**, inflate, smooth, relax,
sharpen. The **Gravity filter is literally "apply gravity to these verts"** — the thing
the human reached for, and lighter than any sim. The region comes from a **mask**
(sculpt-mode's "don't-touch" set): pin the chest, filter the breast.

- *Why it leads:* a region + a number, zero brush skill, native, often one call. The
  teardrop was plausibly one `mesh_filter gravity` away.
- *Shape:* `sculpt op=mesh_filter type=gravity|inflate|smooth|relax strength=… target=…`,
  honoring an active mask.
- *Needs:* mask authoring from a selection (Shared infra).

### Tier B — Cloth Filter / Cloth Brush 🧵

A **local cloth solve** in sculpt mode with a **gravity** option and a **pinned** region —
the lighter cousin of full Soft Body. Real artists use it for quick drape / sag / folds.
Same region+parameter shape as Tier A, plus a bounded sim's natural folding. Bake-free
(the filter settles in place).

### Tier C — Elastic Deform brush 🫳

The **volume-preserving, physically-plausible grab** — what should have replaced plain
Grab this session. It moves a soft mass the way flesh moves (surrounding volume follows
elastically) instead of dragging a rigid blob through the surface. Still stroke-based, so
partly eye-dependent, but the physics in the brush carries the plausibility the agent
can't supply by hand. A new `brush=elastic` on the `sculpt` verb — the cheapest tier to
add (a brush-id and a falloff).

### Tier D — Lattice deform 🪟

A **coarse control cage** (e.g. 3×3×3) drives a smooth deformation of the dense mesh.
**The most numeric-friendly deformer in Blender:** the agent reasons about ~8–27 cage
points instead of ~9,000 verts, and the smoothness comes for free. Underrated *precisely
because* it shrinks the problem to a size the agent can hold in its head. Needs
`modifier type=LATTICE` + a way to move named cage points (a small addressing scheme over
the lattice's grid).

### Tier E — Soft Body / Cloth sim + bake (the heavyweight) ⚙️

Full physics: a pin/goal vertex group, **mass**, **goal stiffness** (≈ the human's
"elasticity" — how hard it holds its shape vs. sags), gravity → settle over frames → bake
→ apply. Correct-by-construction for *real* draping / jiggle / collision, but the most
machinery, and most prone to collapse if under-tuned. Use only when A–D don't reach.
**Needs all three shared sub-primitives below.**

## Shared infrastructure (what A–E lean on)

- **selection → vertex group / mask.** The bridge from an edit-mode selection (the agent's
  existing "where") to a sculpt **mask** (Tier A/B) and a physics **pin/goal group**
  (Tier E). One primitive, many consumers; it also serves G43 (region-coherent selection)
  and **reuses SPEC-07's path** — handles already mint `HANDLE_<name>` vertex groups, so
  the selection→vgroup machinery is half-built.
- **frame-step / bake.** No timeline control exists anywhere in the 15 verbs today, and an
  unbaked physics modifier is **inert** — this is the single reason "flat out use gravity"
  was impossible this session. Tiers B (filter is bake-free) and E need "advance N frames,
  settle, then bake." General-purpose: any sim, any animation read.
- **apply-sim-to-mesh.** Freeze the settled result into static geometry. `modifier
  op=apply` already does the modifier-stack half; a sim needs the cache→mesh step.

## Verifying organic shape without eyes

The payoff of correct-by-construction: once **shape-class** is guaranteed, the agent can
verify **magnitude** with the instruments it has. After a gravity filter/sim, the
measurable signatures of "it actually *hung*":

- fullest-Z **below** the attachment ring (the mass sagged) — `feel profile`.
- lowest-front vert **forward of** the inframammary fold (the under-curl) — wants **G41**
  (absolute protrusion) to read cleanly.
- upper pole **concave/flat**, not convex-bulging — `region_form` on the upper patch (the
  exact read that *would* have caught the cone this session — it reported convex, which
  was the tell I read past).
- symmetry preserved — `feel symmetry`.

So this spec composes with, and argues for, two open gaps: **G37** (projected silhouette)
would show teardrop-vs-cone *directly* in one read; **G41** (absolute protrusion) gives
the under-curl number. Build those and the eyeless verify-loop for organic forms actually
closes — without them the agent is tuning magnitude against partial proxies.

## Build order — by tryability

1. **Mesh Filter `gravity`, region = whole active mesh or a sphere.** ✅ DONE (untested) —
   shipped as `sculpt brush=gravity` (a bmesh drape: pin the top, ramp the fall by height),
   not Blender's modal mesh-filter operator, to match the programmatic-bmesh sculpt family
   and stay reliable headless. inflate/smooth already exist as brushes. Re-run the bust:
   `sculpt brush=gravity target=… at_x/y/z=<breast apex> radius=… strength=0.03 pin=0.3`,
   then `feel op=silhouette axis=X` to see if it hangs.
2. **Mask from selection** → filters respect a pinned region (chest stays, breast falls).
   Still TODO — gravity scopes by sphere/whole-mesh today, not by an arbitrary selection mask.
3. **Elastic Deform brush** — drop-in `brush=elastic` on `sculpt`.
4. **Lattice deform** — cage + named-point moves.
5. **Cloth Filter** (gravity + pin) — first taste of a solve, still bake-free.
6. **Soft Body / Cloth + bake** — last; pulls in frame-step/bake + apply-sim.

Dev loop: A–C extend the `sculpt` verb (`server/verbs/sculpt.py` + the extension side), D
extends `modifier`, E adds the bake/apply infra; reload addon + `/mcp` reconnect after
each. Confirm the live server⇄extension layout before editing — don't trust a stale path.

## Out of scope (named so they're not silently assumed in)

- **Voxel Remesh / Dyntopo.** Genuinely useful for big deformations (uniform density to
  push hard without lumping), but it **rebuilds topology** — destroying UVs, shape keys,
  and the imported cage's vert identity, and breaking every existing handle/vgroup. A
  separate decision with real cost; not bundled here.
- **Cross-section perimeter / area read** (the cup-size measurement gap, gaps.md G47) — a
  *measurement* sibling, not a deformer. Tracked separately.
- **Rig-driven jiggle / animated soft-body.** This spec is **static shaping** (settle →
  bake → apply), not secondary animation.

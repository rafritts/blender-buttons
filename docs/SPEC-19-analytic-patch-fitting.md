# SPEC-19 — Analytic Patch Fitting: Geometry as Editable Math

_Status: **PHASE 1 BUILT & VERIFIED** (commit pending) — `feel op=fit model=quadric` ships the
READ + the round-trip `expr` emission; Phases 2–3 remain DESIGNED. Phase 1 landed on the proposed
verb home (§3.0: extend `feel op=fit`, reuse `edit op=field` as the writer — no new verb) and is
covered end-to-end by `tests/e2e_fit_analytic.py` (exact coefficient recovery, the field
round-trip closes, a fold refuses with high residual, the Phase-2 menu teach-errors). Captures the
round-trip the model needs in order to
**shape** a surface, not just assemble primitives: *select a region of quads → express it as an
editable analytic formula (with residual) → reason and edit in coefficient-space → instantiate
back to mesh at a chosen resolution → verify by re-fit → compose patches by continuity/blend.*
Builds on two halves that already ship: **SPEC-13 field deformer** (`edit op=field expr=` — the
formula→vertices **write** half) and **SPEC-14 geometry-fit** (`feel op=fit` — the
vertices→formula **read** half, today limited to canonical primitives). The whole spec is, in one
line, **"make `fit` speak the same expression language `field` already consumes, over a small menu
of legible bases, and close the loop."** The compose layer (§7 Phase 3) supersedes **gaps.md
G153** (no clean handle-to-body attach). Serves the `project-vision.md` named destination
(sculpt/retopo is "the destination," not the smoke test). The surface carries **two faces** — a
compact analytic store and a *legible curve-net* the model reads and draws, two views of one object
(§2, *the curve-net face*). Verb home is **proposed, not signed
off** (§3.0)._

Scope discipline: this exposes a **fixed, small menu of LEGIBLE analytic bases** as fit targets,
plus the formula↔mesh round-trip. It is **not** a NURBS/CAD surface editor, not per-vertex
authoring, not a retopo engine, not a general implicit-modelling kit. The whole bet is THE ONE
RULE in a new key: where a region's shape is captured by **a few interpretable coefficients**, we
let the model read / edit / instantiate *those numbers* — a representation it can hold in its head
— instead of dead-reckoning vertices it can never see. Anything that needs opaque high-order
coefficients or hand-placed verts is out of scope by construction (§1.1, §8).

---

## 0. What already exists (do not re-derive)

| Thing | Where | Relevance |
|-------|-------|-----------|
| **Formula → vertices (the write half)** | `edit op=field` — `extension/fields.py` (SPEC-13) | Already displaces a selection by a sandboxed scalar/vector `expr` over a measured var namespace, with `channel=radial\|normal\|axis\|vector`, `frame=world\|local\|tangent_normal`, and `preset=taper\|power\|bell\|sine\|lobes`. **This is the instantiate/edit-apply primitive — it stays.** The spec adds the *inverse* and the round-trip, not a new writer. |
| **Vertices → formula (the read half, canonical only)** | `feel op=fit` — `extension/fit.py` (SPEC-14) | Already fits `plane\|sphere\|cylinder\|cone\|ellipsoid\|torus\|swept_tube`, reports **residual mm + a clean/organic verdict**, does `per_component`, and **mints geometry** from the fit (`as_curve=` → a Bézier centerline; `as_handle=`). The residual-honesty machinery and the geometry-minting idiom are exactly what the new bases reuse. |
| **Region selection** | `select` verb (`between`, `by_axis`, `in_sphere`, `by_radius`, `flood`, `INTERSECT`) | The "relatively arbitrary selection of quads" the fit reads. Already relational, already feature-anchored (SPEC-06/09). A patch fit operates on the **live selection**, same contract as `field`/`anchor`. |
| **Best-fit local frame** | `feel op=fit model=plane` + `method=frame`/`facing` | A height-field formula needs a frame to be height *over*. The plane fit already returns it; `facing` gives the signed up/front frame so the model never re-derives handedness. |
| **Cross-section / profile reads** | `feel op=section`, `op=profile`, `rings.py` (`shape_profile`, `taper_section`, `scale_rings`) | The pre-existing **ring-topology** profile editors. A formula-instantiated patch has grid topology these already refine — the analytic layer and the discrete editors compose. |
| **Residual / correctness floor** | `validate` (SPEC-16) + the fit residual | "Did the formula actually capture the region" is the fit residual; "is the instantiated mesh manifold / self-intersection-free" is the always-on floor. Both are **non-suppressible honesty stamps** the round-trip leans on (§1.2, §5). |
| **Connectors (rim-to-rim)** | `edit op=bridge\|connect`, `connectors.py` (SPEC-10) | The *existing* merge for two open rims. The compose layer (§7 Phase 3) adds the two cases bridge can't do: B-spline shared-boundary continuity, and SDF `smooth-min` filleted union. |

Confirmed **absent** (greenfield): any analytic-basis fit beyond the canonical quadrics; any
coefficient-block emission in the `field` `expr` grammar; any progressive/residual layering; any
`fit → mesh patch` minting (`as_surface`); any SDF `smin` blend; any cross-patch boundary-sampling
negotiation. Nothing today reads a region and hands back an *editable formula*.

---

## 1. The laws this domain must obey

### 1.1 Legibility = LOCAL + INTERPRETABLE parameters (the basis admission test)

The whole representation is worthless the instant a coefficient stops meaning something the model
can predict. So a basis is admitted **iff changing one number changes one recognizable thing,
predictably, without smearing across the surface.** This is a hard gate, not a preference:

- **Admitted:** quadric / superquadric (each knob = a named shape property), B-spline control
  points (each pulls locally, convex-hull-bounded → no overshoot), sums of Gaussians/RBF (each term
  = one local bump), SDF `smin` (the blend `k` = one fillet radius).
- **Rejected, on purpose:** high-degree polynomials (coefficients mean nothing individually and the
  surface oscillates between samples — Runge), large Fourier / spherical-harmonic expansions past
  the lowest orders (low orders are a legible egg-shape; high orders smear into noise the model
  can't steer). Power without steerability is not admitted (§8).

The litmus the implementation enforces by *choosing the menu*: **can the model predict what moving
coefficient _k_ does?** If not, that basis is not in the menu.

### 1.2 Every fit ships its residual — a formula without it is a lie the model can't detect

`feel op=fit` already does this and it is **mandatory** for every new basis. A returned formula is
an *approximation*; if the region is wiggly and the basis is smooth, the formula misrepresents the
shape and the model will reason confidently off a fiction. So every fit returns, inseparably:
`captured 94% of variance · max error 3.1mm · RMS 0.6mm`. The residual is also the **refusal
signal** (§1.5): a basis that can't capture the region returns a *high residual*, never a quiet
bad formula.

### 1.3 Coefficient-space is BOTH author-space and verify-space

The model authors by editing coefficients / the `expr`; it verifies by **re-fitting the result and
reading the coefficients + residual back.** No step asks it to eyeball the mesh or read a render —
the loop closes entirely in math, the most legible space it has. This is the property that makes
the whole thing possible blind (cf. SPEC-16: never launder a mistake through a render).

### 1.4 The formula is the intent; the mesh is one instantiation of it

Shape lives in the formula. The mesh is the formula **sampled at a chosen resolution** — one or two
integers the model picks (`u_count × v_count`), never per-vertex positions. Two consequences the
spec must honour:

1. **Resolution is suggested, then chosen.** The tool proposes a count from the formula's curvature
   and a faceting tolerance (`≈14×14 keeps deviation < 1mm`); the model accepts or overrides. Same
   pattern as everywhere — it measures, the model decides; no divining a density cold.
2. **Topology is uniform and deferred.** The grid is a uniform quilt, not feature-aligned loops.
   Shape is exact; pretty edge-flow is a **separate retopo pass** (out of scope, §8). One hard thing
   at a time.

### 1.5 Refuse, don't corrupt (earned from gaps.md G175)

If the selected region cannot be captured by the requested basis — a folded/overhanging patch under
a single-valued height-field model, a ragged multi-feature blob, a degenerate selection — the fit
**refuses with the residual as the diagnostic** ("quadric residual 11mm over a 40mm patch — region
isn't height-field-like; try `model=vector` or split the selection"), never emits a garbage formula
that reads plausible. A tool driven by something that can't see the result must fail loud.

### 1.6 Taste routes to the human

Whether the shaped surface is *beautiful* or *reads as the intended face* is taste → the human.
Whether the mesh matches the authored formula to _X_ mm is **precision** → the model. Every op here
is a mechanical fit, a deterministic measure, or a sampling — no "make this surface look good" verb.

---

## 2. The math layer — the four admitted bases + progressive fitting

A fixed menu, gross-to-fine. Each entry: the form in plain terms, the legible knobs, its job, how
it fits, and how it composes.

| Basis (`model=`) | Plain shape | Legible knobs | Job | Fit | Compose |
|---|---|---|---|---|---|
| **`quadric`** | bowl / dome / saddle / tilt (a height-field `h(u,v)=au²+bv²+cuv+du+ev+f` over the best-fit plane) | `a,b` curvatures (dome±), `c` twist/saddle, `d,e` tilt, `f` offset — 6 numbers | the **gross form** of a single patch | **linear least squares** (closed-form, exact residual) | low-order; blends naturally as an SDF base |
| **`superquadric`** | sphere ↔ box ↔ pillow ↔ diamond mass (implicit, `\|x/A\|^r+\|y/B\|^r+\|z/C\|^t=1`) | `A,B,C` radii (size), `r,t` exponents (boxiness/pinch) — ~5 numbers | the **gross mass of a closed blob** (thumb, torso, pebble) | nonlinear least squares (few params, stable) | native SDF → `smin` merges for free |
| **`bspline`** | a smooth patch over a coarse control grid | the control points — **few, each pulls locally, convex-hull-bounded (no overshoot)** | the **workhorse stitchable surface** | linear least squares for control points given the knot vector | **clean seam continuity**: shared control rows → C0, the row behind → C1 |
| **`rbf` / `gaussians`** | base + a sum of localized bumps (`Σ aᵢ·exp(−‖p−cᵢ‖²/wᵢ²)`; `thin_plate` variant interpolates landmarks at minimum bending energy) | per term: `cᵢ` where, `aᵢ` height, `wᵢ` width — **local & independent** | **features** on top of the base (cheekbone, brow, knuckle) | amplitudes linear given centers; centers/widths nonlinear or seeded from `feel relief`/anchors | additive; terms compose by superposition |

**Progressive / residual fitting — the workflow, not a basis.** The model never fits one big
formula. It fits the **gross** layer (`quadric`/`superquadric`), reads the **residual** — what the
gross fit *missed* — then fits `gaussians` to *that*, then inspects the new, smaller residual and
adds finer terms only if needed. Each layer explains a chunk and hands back a simpler remainder
(matching-pursuit in spirit). This is the "block in the mass, then features, then detail" rhythm,
and it keeps every step legible because the model is never staring at fifty coupled coefficients —
it reads `base bowl + cheekbone bump + brow ridge`, one honest layer at a time. The fit verb
exposes this as `progressive=true` (auto-layer until residual < tol) or manual (fit, read residual,
fit again against `residual=true`).

**The curve-net face (Gordon surface) — the legible way to read and *draw* a patch.** The compact 2D
formula and a **net of 1D curves are two faces of the same surface**, and the net is the one the
model should author in — a 1D curve is the most legible object it has, and "draw the curve that fits
left→right, then top→bottom, then fill the interior" is *already* how it reads geometry (`feel
op=section`/`profile`). The net is two families of fitted **iso-curves** (each a *1D* fit from the
same menu — a 1D quadric is a parabola, a 1D `rbf` is bumps along the line); the surface is
reconstructed by the **Gordon construction** (loft through the u-family + loft through the v-family −
the tensor term that would double-count the overlap; the **Coons patch** is the four-boundary-curve
special case). Three properties make it the preferred editing face:

- **The net IS the wireframe.** Its crossing nodes are the shared sample points, so resolution
  (§1.4) and the matched-boundary rule fall straight out — no separate sampling story.
- **Refinement is drawable and local.** Two spanning (or four boundary) curves → coarse surface →
  read the residual → **add one interior iso-curve exactly where the surface is off.** That is
  progressive fitting in curve form, and far more legible than raising a polynomial order: "add a
  section line through the wrong part" is an action the model can picture; "raise the degree-4
  coefficient" is not.
- **Shared curves give continuity for free.** Two patches sharing a boundary curve are C0 by
  construction (C1 with a matched tangent ribbon) — the merge keeps dissolving the more the design
  leans on shared curves (§7 Phase 3).

**The one correctness requirement, do not skip:** the two families must **agree where they cross** —
each u-curve and v-curve must meet at the same 3D point (the net node). Fit the families
independently and they generally *won't* intersect, and the net won't close. Enforce it one of two
ways: fit one family first, then **constrain the second to pass through the first's nodes**; or use
the Gordon blend, which is *defined* to be node-consistent. This compatibility is to the curve-net
what the fillet was to the graft — looks like a detail, is actually the whole problem.

**Local frame & the height-field limit.** `h(u,v)` over a best-fit plane handles any patch that is
single-valued in its own frame (a cheek, a forehead). A **fold or overhang** (an ear, a lip
underside) is *not* single-valued → the fit must either refuse (§1.5) or use the **vector form**:
map `(u,v) → (x,y,z)` as three component formulas, which the `field` grammar already speaks
(`channel=vector frame=tangent_normal`). Genuinely branching forms are **multiple patches** (§7
Phase 3), not one heroic formula.

**Resolution / tessellation (§1.4).** Instantiation samples the chosen formula on a `u_count ×
v_count` grid. The **one cross-patch rule**: adjacent patches must sample a **shared boundary at the
same division count**, or the quilt cracks (T-junctions). Analytic continuity (§7) + matched
sampling = a watertight seam; either alone is not enough.

---

## 3. The verb surface

### 3.0 Verb home — PROPOSED (needs sign-off)

The round-trip splits cleanly across **verbs that already own each half**, so the proposal is to
**extend, not add a verb** (respecting the SPEC-05 collapse):

- **Read (region → formula):** generalize **`feel op=fit`** — it already fits, already reports
  residual, already mints geometry. New `model=` values + a coefficient/`expr` emission + progressive
  mode. The most natural home; no new verb.
- **Instantiate (formula → mesh patch):** mirror the existing `as_curve=` minting with
  **`feel op=fit … as_surface=<name> resolution=UxV`** — the fit result becomes a real patch — *and*
  reuse **`edit op=field expr=`** to apply an *edited* formula back onto an existing patch. Both exist
  in spirit; `as_surface` is the one new minting path.
- **Compose (Phase 3):** **`edit op=stitch`** (B-spline shared-boundary continuity) and
  **`edit op=graft mode=smin blend=<k>`** (SDF filleted union) — joins the `bridge`/`connect`
  family in `edit`, where welds already live.

Rejected alternative: a dedicated `surface`/`patch` verb gathering fit+field+stitch. Rejected
because the **write half already lives on `edit op=field` and the read half on `feel op=fit`** —
scattering them into a new verb would *duplicate* two shipped subsystems for discoverability we get
for free by extending them. (Recorded for posterity; reopen if the op list on `feel`/`edit` grows
unwieldy.)

### 3.1 `feel op=fit` — the generalized read

```
feel op=fit target= model=quadric|superquadric|bspline|rbf|thin_plate   # + existing canon
            [basis_terms=N]            # rbf: max bumps; bspline: grid size
            [progressive=true]         # auto-layer base→features until residual<tol
            [residual=true]            # fit the LEFTOVER of the prior fit (manual layering)
            [tol=<mm>]                 # residual target / refusal threshold (§1.5)
            [frame=auto|<plane-handle>]# height-field reference; auto = best-fit plane
            [as_surface=<name>] [resolution=UxV]   # instantiate the fit as a mesh patch
            [as_net=<name>]            # emit the fit as a NET of 1D iso-curves — the legible/drawable face (§2)
```

Returns, inseparably (§1.2): the **coefficient block** (named knobs, not raw matrix), the **`expr`
form** in the `field` grammar (so it round-trips), and the **residual stamp**. Example return:

```
Cheek_sel → model=quadric  h(u,v)= -0.31u² -0.18v² +0.04uv +0.02u +0.00v +0.01   (frame: best-fit plane)
            captured 91% · max 4.2mm · RMS 1.1mm
            residual is feature-shaped (1 broad lobe) → try progressive=true / model=rbf
```

With `as_net=`, the same fit returns as two families of mintable 1D iso-curves (reusing the
`as_curve` idiom per curve) instead of one coefficient block — the model then edits the patch **one
drawable curve at a time** and re-fits to verify (§5). Same object, legible face.

### 3.2 `edit op=field` — the edit-apply (exists, SPEC-13)

Already the writer. The model edits the returned `expr` (e.g. steepens the dome: `-0.31u²` →
`-0.45u²`, or adds a bump term) and applies it to the live patch selection. No new op — the spec's
contribution is that **`fit` now emits `expr` `field` can consume**, closing the loop.

---

## 4. The round-trip — the payoff, end to end

```
select op=in_sphere handle=cheekbone radius=0.06           # a coherent patch of quads
feel op=fit model=quadric progressive=true tol=1.0          # → base bowl + 1 gaussian, residual 0.8mm
   # read the formula: a gentle dome plus one broad bump where the cheekbone sits.
   # EDIT in coefficient-space: raise the bump amplitude, narrow its width.
edit op=field expr="<edited formula>" target=Head           # apply the edited math to the patch
feel op=fit model=quadric progressive=true                  # VERIFY by re-fit: coefficients match intent, residual still <1mm
```

No vertex was typed, no render was read, no shape was divined. The model **read** the surface as
math, **reasoned** about it as math, **edited** it as math, **applied** it, and **confirmed** it as
math. That is the entire thesis of this server — derive, don't divine — extended from *assembling*
primitives to *shaping* a surface.

---

## 5. Perception & verification

- **The fit residual** (§1.2) is the primary read: did the formula capture the region.
- **Re-fit** (§1.3) is the verification: instantiate/edit, then `fit` again and compare the
  coefficient block + residual to intent. Invariant to nothing that matters (unlike `region_form`,
  G41) because it reports the actual coefficients.
- **The validate floor** (SPEC-16) covers the *mesh* side of an instantiated patch: manifold,
  self-intersection, non-manifold edges — non-suppressible. A fit can be clean while the
  tessellation cracks at a seam; the floor catches the latter (§2 resolution rule).
- **`feel op=section`/`profile`** cross-check the instantiated patch against the authored profile in
  the discrete domain, for the model that prefers to verify a slice it can also reason about.

---

## 6. Where taste lives — the human handoff

1. **Is the form right?** "Does this read as a sad old man's cheek" is taste. The fit can only say
   "matches your formula to 0.8mm." If the human wants to judge the *look*, hand them a render —
   the SPEC-17 "render a variant, hand the call over" pattern — never an in-server aesthetic verdict.
2. **Basis choice when ambiguous.** If a region is part-dome part-fold, the model picks a basis,
   reports the residual, and the human can ask for a different cut (more terms, a split, the vector
   form). We never present one "best" fit as correct (§1.6).

---

## 7. Build phasing (effort = complexity/risk)

1. **Phase 1 — READ, one basis ("express multiple quads as math, even if limited"). ✅ BUILT.**
   `feel op=fit model=quadric` over a live selection → emits the coefficient block (named knobs +
   principal-curvature shape verdict), the `expr` in the `field` grammar, and the captured-% /
   residual stamp, height-field over the best-fit plane. This alone delivers the core ask: a region
   of quads becomes an editable formula the model can read and reason about. Lowest risk — **linear
   least squares** — and it reuses SPEC-14's residual/verdict machinery wholesale. The round-trip
   `expr` is exact because the fit derives its frame from the field deformer's own `_group_frame`
   (so in-plane `u,v` = field `z,x` and height = field `y`); the emitted apply line
   `edit op=field channel=axis:v field_mode=add expr="(quadric) - y"` lands every vert on the fitted
   surface (verified). No write *primitive* added, no instantiate (`as_surface`), no compose yet.
2. **Phase 2 — the full menu + progressive fit + the round-trip.** Add `superquadric`, `bspline`,
   `rbf`/`thin_plate`; `progressive=`/`residual=` layering; `as_surface=`+`resolution=` minting; and
   verify that an `edit op=field` of an edited formula **re-fits to the intended coefficients**
   (the closed loop, §4). Also the **curve-net face** (`as_net=`): emit the fit as two families of
   iso-curves with the Gordon node-reconciliation so the net closes (§2). The bulk of the value.
3. **Phase 3 — COMPOSE (the research; supersedes G153).** `edit op=stitch` (B-spline / curve-net shared-boundary
   C0/C1 — the net's boundary curves are the shared objects — + matched boundary sampling → watertight quilt) and `edit op=graft mode=smin blend=<k>`
   (convert parts to SDFs, smooth-min blend, marching-cubes mesh — the **fillet radius is one
   number**, the merge monster reduced to arithmetic). Highest risk; the merge we currently cannot do
   cleanly becomes algebraic. Retopo of the result stays out of scope.

Each phase is independently shippable and dogfoodable. Phase 1 is the smoke test; Phase 3 is the
destination.

---

## 8. Non-goals (hold the line)

- **No opaque bases.** No high-degree polynomials, no large Fourier/spherical-harmonic expansions —
  they fail the §1.1 admission test (uninterpretable, oscillating). Power without steerability is
  not a feature here.
- **No per-vertex authoring.** The model never types vertex positions; it types coefficients, a
  basis, and a resolution. The instant a tool wants a typed XYZ per vert, refuse and log a gap.
- **No NURBS/CAD surface editor** — no trim curves, knot insertion UI, surface-of-revolution
  modeller. We fit/instantiate a small basis menu, nothing more.
- **No retopo / edge-flow engine.** Instantiated topology is a uniform grid; feature-aligned loops
  are a separate pass (its own future spec).
- **No taste/beauty judge** (§1.6) — no "best fit" auto-pick presented as correct, no "make it look
  good."
- **No freeform curve-network CAD kit** — the net is *fitted* from a selection (or refined one
  curve at a time), never a from-scratch hand-drawn-curve modeller with trims/blends.
- **No general implicit-modelling kit** beyond the `smin` merge primitive in Phase 3.

---

## 9. Wiring checklist (per the architecture)

- **`extension/fit.py`** — new `model=` solvers (`quadric` linear LSQ first; then `superquadric`,
  `bspline`, `rbf`/`thin_plate`); the **coefficient-block + `expr` emitter** (reuse the SPEC-13
  `field` grammar so the formula round-trips); `progressive`/`residual` layering; `as_surface=` +
  `resolution=` minting (mirror the existing `as_curve=` path); the **`as_net=` emitter** — two
  families of fitted iso-curves (seed with `feel op=section`/`profile`, mint each via `as_curve`) +
  the **Gordon node-reconciliation** so families agree at crossings (§2).
- **`server/verbs/feel.py`** — thread `model` (new values), `basis_terms`, `progressive`,
  `residual`, `tol`, `frame`, `as_surface`, `resolution` onto `op=fit`; `teach()` errors for an
  out-of-menu `model`.
- **`extension/fields.py` / `server/verbs/edit.py`** — *no change to the writer*; confirm the
  `fit`-emitted `expr` parses in the `field` sandbox (shared grammar test). Document the loop in the
  `field` op help.
- **Phase 3 only — `extension/connectors.py` + `server/verbs/edit.py`** — `op=stitch` (B-spline
  boundary continuity + matched sampling) and `op=graft mode=smin` (SDF blend → marching cubes).
  Classify both as mutating + EDIT-mode in `extension/server.py`.
- **`extension/server.py`** — `fit` stays a read (already non-undoable); `as_surface` minting is a
  mutating op (takes the undo lock).
- **`GUIDANCE_FOR_LLMS.md`** — a short "shaping a surface: fit a region to an editable formula
  (`feel op=fit model=quadric…`), edit the coefficients, apply with `edit op=field`, verify by
  re-fit; this is how you *shape* instead of *assemble*" note, with the §2 basis menu as the cheat
  sheet.
- **`docs/art_pipeline.md`** — the sculpt/retopo destination stage gains these verb names in its
  TELLS/DONE-WHEN; note retopo remains downstream.
- **`gaps.md`** — on Phase 3 landing, **delete G153** (the graft it supersedes).
- **Tests** — `tests/e2e_fit_analytic.py`: fit a known synthetic quadric patch, assert recovered
  coefficients within tol + residual ≈ 0; **round-trip** — `field` a known `expr` onto a grid, then
  `fit` it back, assert coefficient recovery (the §4 loop); a folded patch under `model=quadric`
  asserts the high-residual refusal (§1.5); two `bspline` patches sharing a control row assert a
  watertight, crack-free seam (Phase 3); an `as_net` fit then Gordon-reconstruct asserts the net nodes
  coincide and the reconstruction residual ≈ the direct 2D fit (the two faces agree).

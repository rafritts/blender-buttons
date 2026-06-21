# SPEC-14 — Geometry fit: describe a region as parametric form `params = G⁻¹(selection)`

_Status: Proposed 2026-06-21. Sourced from gaps.md **G100** (jacket-delete dogfood: removing
the sleeves exposed that the body has no upper-arm skin; the void was only found by inferring
it from a `sel_bounds` floor mismatch). Net-new **read** primitive; the analytic inverse of
SPEC-13 (the field deformer turns params → geometry; this turns geometry → params). Nothing
here ships yet._

---

## The problem

The server has a rich **forward** map — params → geometry: `add` primitives, `edit op=field`
(an expression evaluator over a region, SPEC-13), sweeps (`extrude_along_curve`, `trace`,
`strands`), profiles (`shape_profile`), lofts (`bridge`, `connect`). The agent can *author* a
great deal of geometry from pure math.

It has almost no **inverse** map — geometry → params. It can *sample* a region (`feel
op=profile` gives radius-per-band along an axis; `op=rings`, `op=radial`, `op=curve`,
`op=region_form` give more), but nothing **fits a generative model to a selection and hands
back the formula plus a goodness-of-fit.** Two consequences kept biting in dogfood:

1. **You can't describe a form to reason about it.** To extend the severed forearm to the
   shoulder, the natural move is: read the forearm's shape as a *tapered swept tube*
   (centerline, radius profile, cross-section), then **extrapolate that description** to the
   shoulder and re-sweep — continuing the arm *in its own language* instead of bolting on a
   generic cylinder. There is no read that returns that description.
2. **Absence is invisible.** The missing upper-arm skin (G100) had no clean signal. The
   full-mesh bbox hid it (head + legs set the Z-extremes); it surfaced only because a
   `select … X>0.166 INTERSECT` came back with its X-floor at 0.344 — an 18cm void betrayed
   as a mismatch between the threshold asked for and the floor returned. That trick only
   catches **axis-aligned** gaps; an off-axis or mid-patch void leaves the bounds unchanged
   and stays invisible. A region's **continuity** should be readable directly, not
   reverse-engineered.

The right answer is one general read: **fit a small library of generative models to the
current selection and return the best fit's type, parameters, and residual** — where the
*residual is the honesty meter*. A clean tube fits with a 3mm residual; a face fits nothing
and says so. The fitted params are shaped to feed the forward engine directly (extrapolate,
re-sweep, match, verify).

## The principle

```
given the selected verts P:   find model type M and params θ minimizing  ‖P − G_M(θ)‖
return (M, θ, residual, coverage)
```

- **`G_M(θ)`** is a generative model the server can already *evaluate forward* (a primitive,
  or a swept tube the connectors/sweeps can rebuild). Fitting is the inverse of authoring.
- **`residual`** (RMS surface distance, reported in **mm/cm** — intent-legible, never a raw
  coordinate dump) is the load-bearing output. It tells the agent **when the math describes
  the shape and when it is lying.** Below threshold ⇒ trust the params; above ⇒ "no clean
  parametric form here (organic/irregular)," reported honestly rather than papered over.
- The fitted params are **legible ground truth** in intent-space: "cone, r 5.2→3.8cm over
  31cm, axis +X, residual 3mm" — a description the agent reasons over and extrapolates,
  exactly the THE-ONE-RULE substitution of a *measured* description for a guessed one.

This keeps the agent on the ground-truth side of the intent/divination line: it no longer
*dead-reckons* how to continue a form — it **reads the form's actual parameters** and extends
those.

## The model

### 1. The model library (what `G_M` can be)

Each entry is a closed-form surface the server can fit (least-squares / RANSAC) **and**
regenerate forward. Returned params are named and unit-tagged, never bare coordinate lists.

| model | params returned | typical fit method |
|---|---|---|
| `plane` | point, normal, extent (u×v) | total-least-squares (PCA, smallest eigenvector) |
| `sphere` | center, radius | algebraic + Gauss-Newton refine |
| `cylinder` | axis line (point+dir), radius, length | PCA seed → nonlinear refine |
| `cone` | apex, axis dir, half-angle, length | as cylinder + opening angle |
| `ellipsoid` | center, frame, semi-axes (a,b,c) | quadric fit, constrained |
| `torus` | center, axis, major R, minor r | nonlinear |
| `swept_tube` | **centerline** (polyline / Bézier), **R(s)** radius profile, **cross-section** ellipse (a/b ratio + roll), **twist(s)** | ring-sweep decomposition (below) |

`model=auto` (default) tries the cheap rigid primitives first, then `swept_tube`, and returns
the **lowest-residual** fit with a one-line verdict. `model=<name>` forces one (and reports
how badly it fits if forced onto the wrong shape — useful for "is this *actually* a
cylinder?").

### 2. The `swept_tube` decomposition (the limb case — the core deliverable)

This is the one that extends the arm, and it is mostly **assembling reads that already
exist** into a parametric package:

1. Resolve the longitudinal **axis** (`axis=X|Y|Z` or `auto` = first PCA principal axis of
   the selection — same frame derivation as SPEC-13 §1).
2. Bin the selected verts into **rings** along the axis (reuse the `feel op=profile` / `rings`
   binning).
3. Per ring: **centroid** → a point on the **centerline**; the spread of the ring's verts in
   the cross-plane → a fitted **ellipse** (semi-axes `a,b`, roll angle) → `R(s)` is the mean
   radius, the **a/b ratio** is the cross-section eccentricity, ring-to-ring roll is `twist`.
4. The ordered centerline centroids → a polyline; fit a low-order **Bézier/arc** for a smooth,
   extrapolable curve (reuse `feel op=curve` for the bend read).
5. **Coverage / continuity falls out for free:** a ring bin with **no verts** is a *gap in the
   sweep* — report it as a void at `s∈[…]`. This is the direct continuity read G100 wanted,
   as a byproduct of the decomposition (see §Relationship).

Output: `{centerline: <curve>, radius_profile: R(s) as control points, section: {ab_ratio,
roll}, twist: τ(s), length, residual, gaps: [...]}` — everything `trace`/`extrude_along_curve`
needs to **rebuild or continue** the tube.

### 3. Residual, coverage, verdict

- **`residual`** — RMS distance from selected verts to the fitted surface, in mm. Plus
  `residual_max` (worst vert) so a single spike isn't hidden by the mean.
- **`coverage`** — fraction of the fitted surface actually backed by verts (a half-cylinder
  of data fits a full cylinder with low residual but 50% coverage — the agent must know).
- **`verdict`** — one line: `"swept_tube, residual 2.8mm, coverage 96% — clean fit"` or
  `"best=ellipsoid, residual 41mm — no clean parametric form (organic)"`. The threshold is a
  parameter (`tol`, default ~ a few mm or a small fraction of the selection diagonal).

### 4. Replay / extension (closing the loop)

The fit is a **read** (`feel`, no mutation). To *act* on it, two thin affordances:

- **`as_handle=<name>` / `as_curve=<name>`** — mint the fitted **axis line** as a point/vector
  handle, or the **centerline** as a real Bézier curve object, so the description becomes
  addressable by name (feed it to `transform`, `extrude_along_curve`, etc.) — same
  handle-minting pattern as `feel op=aim … as_handle` (G78).
- **Extension is then existing forward ops:** extrapolate the centerline curve to the target
  (extend the Bézier), and `edit op=extrude_along_curve` / `trace` a section matching the
  fitted `R(s)`+ellipse, `bridge` the new rim to the shoulder loop. **No new mutate op is
  needed** — SPEC-14 supplies the *description*; SPEC-10/13 already supply the *construction*.

## Proposed API

A new op on the `feel` verb (read-only, no status mutation — consistent with `feel`):

```
feel op=fit
     model=auto|plane|sphere|cylinder|cone|ellipsoid|torus|swept_tube
     axis=X|Y|Z|auto          # longitudinal axis for cylinder/cone/swept_tube
     tol=<mm>                 # residual threshold for the clean/organic verdict
     per_component=false      # fit each connected sub-shell separately (don't average across a gap)
     bands=<n>               # ring count for swept_tube (default ~24, as profile)
     as_handle=<name>         # mint the fitted axis line as a named handle
     as_curve=<name>          # mint the fitted centerline as a Bézier curve object
     lod=low|medium|high      # how much of R(s)/twist/per-ring detail to dump
```

Operates on the **current edit-mode selection** (empty/whole-mesh allowed but warned, as
elsewhere). Returns a structured, unit-tagged param block + residual/coverage/verdict + any
detected `gaps`.

Worked examples (no asset specifics):

```
# 1. "What is this region, mathematically?" — let it classify:
feel op=fit model=auto
#   → "cylinder, axis +X, r=4.6cm, length 31cm, residual 2.8mm, coverage 94% — clean fit"

# 2. Describe a limb section as a swept tube and mint its centerline to extend it:
feel op=fit model=swept_tube axis=X as_curve=arm_spine
#   → centerline=arm_spine, R(s)=[5.2→3.8cm], section ab=0.9, residual 3mm, gaps=[]
#   (then: extend arm_spine to the shoulder, extrude_along_curve a matching section, bridge)

# 3. Honesty check — force a cylinder onto a face patch:
feel op=fit model=cylinder
#   → "cylinder forced, residual 38mm — does NOT fit; no clean parametric form here"

# 4. Continuity read as a byproduct (the original G100 question):
feel op=fit model=swept_tube axis=X
#   → "... gaps: void at s∈[0.00,0.18] (18cm, no verts)"  ← the missing upper arm, named directly
```

## Algorithm (what a fresh implementer does)

1. **Gather** selected verts from the active bmesh (stable order), as a numpy array. If
   `per_component`, split into connected components and fit each separately (never average a
   model across a gap between shells); else one group.
2. **Rigid primitives** (`plane/sphere/cylinder/cone/ellipsoid/torus`): seed with a linear/
   algebraic estimate (PCA for axis/plane; algebraic sphere/quadric), then refine with a few
   Gauss-Newton / Levenberg-Marquardt iterations minimizing point-to-surface distance. Use
   **RANSAC** seeding when outliers are likely (stray seam verts).
3. **`swept_tube`**: build the axis frame (SPEC-13 §1 frame derivation), ring-bin along it,
   per-ring centroid → centerline, per-ring cross-plane ellipse fit → `R(s)`/`ab`/roll, fit a
   low-order Bézier to the centerline (reuse `feel op=curve`). Flag empty ring bins as `gaps`.
4. **Score** every attempted model: RMS + max residual + coverage (fraction of the model's
   parametric domain with backing verts). For `model=auto`, pick the lowest residual that
   also clears a minimum coverage; tie-break toward the **simpler** model (a sphere over an
   ellipsoid when both fit) so the description is as legible as possible.
5. **Emit** a unit-tagged param block + `verdict` against `tol`. If `as_handle/as_curve`,
   mint the addressable object(s). **Read-only**: no vert is moved, no status block.

## Critical implementation notes

- **Residual is the product, not the params.** A fit always returns *some* numbers; without a
  trustworthy residual + coverage they are divination wearing a lab coat. Get the
  point-to-surface distance and coverage right before adding models. Report both mean and max.
- **Fit from the selection's own frame, never the global mesh.** Same discipline as SPEC-13:
  the axis/rings come from the selected verts, so the fit works on a sub-shell of a fused,
  many-shell mesh (the whole point — the forearm is one shell among 125).
- **Coverage guards the half-cylinder trap.** Low residual + low coverage = "fits the data you
  have, but the data is a patch" — must be surfaced or the agent will over-trust an
  extrapolation off 40% of a tube.
- **Simpler model wins ties** — the value is a *legible* description; don't return an
  ellipsoid where a sphere fits equally well.
- **Vectorize; be deterministic.** Pure function of the selection (+ fixed RANSAC seed); same
  selection ⇒ same params, so dogfood and tests are reproducible.
- **Don't average across components or gaps.** A model spanning a void is meaningless; honor
  `per_component` and let detected `gaps` short-circuit a single-tube fit with a clear note.

## Verification (acceptance criteria)

- **Round-trip a known primitive**: `add op=cylinder` (known r, length, axis) → select it →
  `feel op=fit model=auto` recovers `cylinder` with params within tolerance and residual
  ≈ mesh discretization (sub-mm). Same for sphere/cone/plane.
- **Limb fit**: on a real forearm selection, `model=swept_tube` returns a centerline +
  monotone-ish `R(s)` taper with residual ≤ a few mm and coverage ≥ ~90%; `as_curve` mints a
  Bézier that visually tracks the limb axis.
- **Honesty**: a face/hand/drapery patch returns a **high** residual and a verdict that
  explicitly declines ("no clean parametric form"), never a confident wrong primitive.
- **Continuity byproduct**: on the G100 arm (forearm present, upper arm absent),
  `model=swept_tube` reports a `gap` at the correct `s`-interval — the void named directly,
  not inferred from a bounds floor.
- **Extension e2e**: fit forearm → extend centerline → `extrude_along_curve` matching section
  → `bridge` to shoulder loop yields a watertight arm whose new span's `feel op=fit` matches
  the original forearm's params within tolerance.
- **Headless e2e** under `tests/`: primitive round-trips, a swept-tube fit with an injected
  gap, a forced-wrong-model high-residual case, and a half-covered low-coverage case.

## Build order (by tryability; each ships and is dogfood-verifiable alone)

1. **Rigid primitives** `plane, sphere, cylinder, cone` + residual/coverage/verdict. Immediately
   testable by round-tripping `add` primitives; covers "what is this, mathematically?"
2. **`ellipsoid, torus`** — rounds out the canonical library.
3. **`swept_tube`** decomposition + `gaps` detection — the limb extender and the G100
   continuity read. Highest value; reuses `profile`/`rings`/`curve`.
4. **`as_handle` / `as_curve`** minting — makes the description addressable, closing the loop
   into the forward sweep/connector ops (no new mutate op).

Code layout: add `fit` to `_OPS` and the dispatch in `server/verbs/feel.py`; implement the
math in a new `server/fit.py` (facade) driving a new `extension/fit.py` (bmesh + numpy) on the
Blender side, mirroring how `rings.*` / `fields.*` split server⇄extension. Reuse the
ring-binning from the profile/rings path and the frame derivation from `fields.py`. Reload the
addon + `/mcp` reconnect after each change; confirm the live server⇄extension paths before
editing.

## Relationship to existing ops

- **Complements `feel op=profile`** — profile already returns R-per-band along an axis but
  does **not** classify, fit a centerline, fit a cross-section, report a residual, or detect
  gaps. SPEC-14 is profile's binning **plus** the fit + verdict + continuity. (profile could
  later become a thin `lod=low` view of a `swept_tube` fit.)
- **Complements `feel op=region_form` / `op=curve`** — region_form gives a convex/concave
  verdict and projection; curve gives bend radius. SPEC-14 reuses `curve` for the centerline
  and adds the full parametric description around it.
- **Feeds SPEC-13 (field), SPEC-10 (connectors), the sweeps** — the fitted params are exactly
  the inputs those forward ops consume; SPEC-14 is the read that lets the agent *measure then
  replay/extend* instead of authoring blind.
- **Subsumes part of G100's continuity ask** — the `swept_tube` `gaps` output is the direct
  "where are the voids" read. If a cheaper, model-free continuity/coverage read proves wanted
  on its own (e.g. for non-tubular regions), split it into a small sibling op; SPEC-14 covers
  the tubular case that motivated it.

## Native precedent (be honest about it)

Blender has **no** native "fit a primitive/CAD form to a mesh selection" — this is
reverse-engineering / parametric reconstruction, the domain of CAD tools (Fusion's "convert
mesh", scan-to-BREP) and research add-ons (RANSAC primitive detection). The nearest native
relatives are *forward* or *projective*: Shrinkwrap (project onto a target), Decimate
(reduce, not describe), the "LoopTools → Circle/Curve" relaxers (snap a loop to an ideal, not
report it). So unlike SPEC-13 (an intent-space front-end over Geometry-Nodes that already
exists natively), SPEC-14 adds genuine **analysis capability the host lacks** — fitting and
residual-scoring — and exposes it in intent-space. That analysis *is* the product.

## Out of scope (named so they're not silently assumed in)

- **Full BREP / NURBS / CSG reconstruction** — recovering a whole solid-model feature tree.
  This fits *one* model to *one* selection.
- **Statistical / learned shape models** — anatomical priors for a "true" human arm. The
  swept_tube extension is geometric extrapolation, not anatomy.
- **Auto-segmentation** — deciding *which* region to fit. The agent selects; SPEC-14 fits the
  selection. (Pairs with feature-anchored selection, SPEC-06.)
- **Mutation** — SPEC-14 never moves a vert. Extension/repair is the forward ops it feeds.

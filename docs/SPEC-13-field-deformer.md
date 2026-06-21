# SPEC-13 — Field deformer: apply an explicit function `p' = F(p)` over a selection

_Status: Proposed 2026-06-21. Sourced from gaps.md **G99** (skirt flared→column + wavy-hair
dogfood). Net-new primitive; complements SPEC-08 (physics/correct-by-construction deformers)
— this one is the **explicit, analytic** deformer. Nothing here ships yet._

---

## The problem

A large class of edits is one conceptual move: **apply a function across the selected
verts.** The server has no primitive for it, so each shape gets a bespoke op
(`taper_end`, `taper_section`, `scale_rings`, `shape_profile`, `flute`, `jitter`,
`noise_displace`), and anything off those rails falls through. Two failure modes recur:

1. **The bespoke ops key off the *global* mesh ring structure**, so they break on a
   sub-region of a fused, many-shell mesh. `taper_end` on a selected sub-shell indexed the
   whole mesh's ring list and scaled a stray bevel sliver instead of the wall — a silent
   no-op.
2. **The fallback is constants where the shape wants a function.** Approximating a smooth
   profile by scaling a few axis-bands by a few constants flattens each band to a straight
   wall and **steps at the band junctions** — a measurable faceting (a few mm of concave
   step, perfectly symmetric, i.e. structural not noise). The agent was pushed out of
   intent-space ("taper to follow these measured radii") into a piecewise-constant
   approximation that looks blocky.

The right answer is one general engine: a **per-vertex field over the current selection**,
where the function reads a clean, geometry-derived coordinate namespace and writes through a
chosen channel. Presets are named cases of that engine; an arbitrary `custom` expression is
first-class.

## The principle

```
for each selected vertex p:   p' = p ⊕ F(vars(p))
```

- **`vars(p)`** is a per-vertex namespace **measured from the geometry** (normalized
  position, radius, angle, arc-length, normal, …). This is what keeps even a `custom`
  expression on the ground-truth side of the intent/divination line: the inputs are read
  from the mesh, not dead-reckoned.
- **`F`** is the function — a named preset, a control-point curve, or a sandboxed
  expression.
- **`⊕`** is the application channel (add along a direction / scale radially / twist), in a
  chosen frame.

Correctness is **analytic** — a smooth `F` yields a smooth surface *by construction*, so
there are no facets to remove afterward. The engine's real value is not the expression
evaluator (the easy 20%); it's **providing a good per-vertex parameterization** (the 80%).

## The model

### 1. The per-vertex variable namespace (the core deliverable)

All derived from the selection itself, exposed to presets and expressions alike. Computed
as numpy arrays over the selected verts.

| var | meaning |
|---|---|
| `t` | normalized position along the **longitudinal axis**, ∈ [0,1] over the selection's extent |
| `u, v` | normalized position along the other two frame axes, ∈ [0,1] (`us,vs` = signed [-1,1]) |
| `r` | radial distance from the longitudinal **axis line**, in the cross-plane |
| `theta` | azimuth around the longitudinal axis, ∈ [-π,π] |
| `s, L` | arc-length along the **component** from one end, and the component's total length |
| `nx, ny, nz` | vertex normal (unit, world) |
| `x, y, z` | position in the **selection-local frame** (origin = centroid; axes = frame); `X,Y,Z` = world |
| `i, ci, ring` | vertex index (stable order), component index, axis-bin index |
| `rnd, crnd` | deterministic hash → [0,1): per-vertex and **per-component** (seeded by `seed`) |
| consts | `pi`, `tau`, `e` |

**Frame derivation.** The longitudinal axis is `axis=X|Y|Z` (a world axis) or `axis=auto`
(first PCA principal axis of the selected verts). Origin = selection centroid. `r/theta` are
taken about the **axis line** through the origin (`about=axis`) or about **each component's
own medial centroid per ring** (`about=spine`, for curved parts). Ship `about=axis` first.

**`s` (arc-length).** For a thin/strand-like component (an edge-chain or tube), walk the
component's ordered spine and accumulate length; `s` resets per component, `L` is that
component's length. If the component is not strand-like, `s` falls back to the longitudinal
projection and any preset that strictly needs strand arc-length errors clearly rather than
producing nonsense.

### 2. The function `F`

Exactly one source, validated up front:

- **`preset=<name>`** + generic knobs `a,b` (endpoint values), `k` (exponent/curvature),
  `amp,freq,phase,center,width`. Named families:
  - `taper(a,b)` — linear `a→b` in `t`
  - `power(a,b,k)` — `a + (b-a)·t^k` (k>1 late bulge, k<1 early)
  - `smoothstep(a,b)` — eased `a→b`
  - `bell(center,width,amp)` — Gaussian bump
  - `sine(amp,freq,phase)` — `amp·sin(2π·freq·t + phase)`
  - `lobes(freq,amp,phase)` — `amp·cos(freq·theta + phase)` (the `flute` family, angular)
- **`points=[[t,val],…]` + `interp=linear|smooth|cubic`** — control-point curve in
  normalized `t` (the generalization of `shape_profile`: normalized param, any channel,
  not absolute-radius-by-ring-index).
- **`expr="..."`** — custom, sandboxed (see Impl notes). Scalar by default. For a vector
  channel, supply `expr_x,expr_y,expr_z` (any omitted = 0).

### 3. Channel + frame + mode (how `F`'s output becomes displacement)

- **`channel`**:
  - `radial` — scale the cross-plane offset: multiplicative `r' = F·r` (default) or absolute
    `r' = F`. **Anisotropic** via `sigma_x,sigma_y` (or `expr_x,expr_y`) so elliptical
    sections stay elliptical.
  - `normal` — `p' = p + F·n`
  - `axis:<X|Y|Z|long|u|v>` — `p' = p + F·dir`
  - `twist` — rotate the cross-plane offset about the longitudinal axis by angle `F` (radians)
  - `vector` — `p' = p + R·(Fx,Fy,Fz)` where `R` maps `frame` → world
- **`frame`** (for `vector`): `world | local | tangent_normal`
- **`mode`**: `add` (offset channels, default) | `multiply` | `set` (radial channel)
- **`clamp_min/clamp_max`** (optional) — bound `F` for safety.

### 4. Scope

Operates on the **current edit-mode selection**. `per_component=true` parameterizes and
applies independently per connected sub-shell (essential when `s/theta/crnd` must reset per
component, e.g. a field of separate strands). Empty/whole-mesh selection allowed but warned.

## Proposed API

A new op on the `edit` verb:

```
edit op=field
      axis=Z|X|Y|auto         # longitudinal/parameter axis
      about=axis|spine         # radial pivot (ship 'axis')
      channel=radial|normal|axis:Z|twist|vector
      mode=add|multiply|set
      per_component=false
      # exactly one function source:
      preset=<name> a= b= k= amp= freq= phase= center= width=
      points=[[t,val],...] interp=smooth
      expr="..."  (or expr_x= expr_y= expr_z= for channel=vector)
      sigma_x= sigma_y=       # anisotropic radial
      seed=0  clamp_min= clamp_max=
```

Generic examples (no asset specifics):

```
# 1. Smooth taper of a selected tube-section to 60% at one end (replaces taper_end, but
#    selection-scoped so it works on a sub-shell):
edit op=field axis=Z channel=radial mode=multiply preset=smoothstep a=1.0 b=0.6

# 2. Lateral wave down each strand of a multi-strand selection, root pinned, tip max:
edit op=field axis=Z channel=axis:X per_component=true \
     expr="0.02 * (s/L) * sin(6.283*s/0.08 + crnd*6.283)"

# 3. Custom barrel via expression on the radius:
edit op=field axis=Z channel=radial mode=multiply expr="1 + 0.15*sin(pi*t)"

# 4. 12 vertical flutes (replaces 'flute'):
edit op=field axis=Z channel=radial mode=add preset=lobes freq=12 amp=-0.004
```

## Algorithm (what a fresh implementer does)

1. **Gather** selected verts from the active bmesh (stable order). If `per_component`, split
   into connected components and loop steps 2–5 per component; else one group.
2. **Build the frame**: resolve longitudinal axis (world axis or PCA), origin = centroid.
   For `about=spine`, bin verts along the axis into rings and use per-ring centroids.
3. **Compute `vars`** as numpy arrays: `t,u,v` (normalize projections), `r,theta` (cross-plane
   polar), `s,L` (spine walk for strands), normals, indices, hashes. **No global mesh ring
   index** — every parameter is derived from the selection's own verts.
4. **Evaluate `F`** over the arrays (vectorized): dispatch preset → closed form; points →
   interpolate; expr → sandboxed numpy eval. Apply `clamp`.
5. **Map through channel/frame/mode** → per-vertex world-space delta → write `vert.co`.
6. **Finish**: `bm.select_flush_mode()` before the editmesh→mesh sync (per G87), so the
   selection survives a following op. Return a status block: verts moved, `F` range, the
   resulting selection bbox (so the agent can verify against intent without a render).

## Critical implementation notes

- **Parameterize from the selection, never the global mesh ring index.** This is the exact
  bug that breaks `taper_end`/`shape_profile` on a sub-shell; getting it right is what makes
  the field work on one part of a fused, many-shell mesh.
- **Sandbox `expr`.** Parse with a whitelisted AST (names from the namespace + a math
  function set: `sin,cos,tan,exp,log,sqrt,abs,floor,clamp,smoothstep,step,min,max,noise`),
  evaluate against **numpy arrays** — never raw `eval`/`exec`, no builtins, no attribute
  access. `custom` is a code-exec surface; treat it as one.
- **Vectorize.** Selections can be tens of thousands of verts; evaluate `F` once over arrays,
  no per-vertex Python loop.
- **Determinism.** Pure function of position + `seed`; same args twice ⇒ byte-identical
  result (so the no-op detector and history/undo behave, and dogfood is reproducible).
- **Multiplicative default for `radial`** preserves existing cross-section detail
  (asymmetry, prior corrugation); absolute/`set` is opt-in.

## Verification (acceptance criteria)

- **De-facet**: a `smoothstep`/`power` radial taper applied to a sub-shell of a multi-shell
  mesh yields a surface whose `feel … method=region_form` reports **no concave junction
  step** (≤ ~1 mm), where the constant-band approximation reported several mm. Front/side
  `feel op=silhouette` shows a smooth profile, not stacked cylinders.
- **Strand wave**: with `channel=axis` + `(s/L)` envelope, the root vert (`s≈0`) is
  unmoved and displacement grows to the tip; `feel op=symmetry` unchanged where expected.
- **Determinism**: re-running identical args is a detected no-op (byte-identical).
- **Headless e2e** under `tests/` covering: taper on a sub-shell, per-component strand wave,
  an expr clamp, and a sandbox-rejection case (expr with a forbidden name/builtin).

## Build order (by tryability; each ships and is dogfood-verifiable alone)

1. **Engine + scalar channels** (`radial`, `normal`, `axis`) with `preset` + `points`,
   selection-scoped, vectorized. Covers taper / profile / bulge / flute.
2. **`per_component` + arc-length `s`** → unlocks strand/wave fields.
3. **`expr` (sandboxed)** → custom scalar fields.
4. **`vector` output + `twist` channel** → free-form and rotational fields.
5. **`about=spine`** → curved-part radial fields.

Code layout: add `field` to `_OPS` and the dispatch in `server/verbs/edit.py`; implement the
math in a new `server/fields.py` (facade) driving a new `extension/fields.py` (bmesh +
numpy) on the Blender side, mirroring how `rings.*` ops are split server⇄extension. Reuse the
edit-mode selection access in `server/editmode.py` and the `select_flush_mode()` sync (G87).
Reload the addon + `/mcp` reconnect after each change; confirm the live server⇄extension
paths before editing.

## Relationship to existing ops

These become **named presets / thin wrappers** of the field engine (and can later be
retired to it): `taper_end`, `taper_section`, `scale_rings`, `shape_profile` (→ `points` in
normalized `t`), `flute` (→ `lobes` on `theta`), `jitter`/`noise_displace` (→ `normal`
channel with a `noise`/`rnd` expression). Don't break them on day one; converge over time.

**Native precedent (be honest about it):** this is Geometry-Nodes "Set Position" fed by a
field; `Warp`/`SimpleDeform`/`Displace` are narrower native versions. The server isn't adding
new deformation *capability* — it's adding the **intent-space front-end** (select a region →
clean geometry-derived variables → one expression) that spares the agent from hand-wiring a
node graph each time. That front-end *is* the product.

## Out of scope (named so they're not silently assumed in)

- **Neighbor/stencil fields** (blur, Laplacian smooth, curvature-driven) — need adjacency,
  not a pure point function. Separate primitive.
- **Topology change** — the field moves existing verts only; no subdivide/remesh.
- **UV-space or texture-space domains** — a later parameterization source, not v1.
- **Physics / time** — drape, cloth, jiggle, frame-bake live in SPEC-08, not here.

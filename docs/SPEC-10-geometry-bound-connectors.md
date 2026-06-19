# SPEC-10 — Geometry-bound parametric connectors: curves that know the openings

_Status: Phases 2–3 SHIPPED 2026-06-18 as `edit op=connect` (`extension/connectors.py`):
geometry-bound anchoring + normal-continuous launch, the hollow taper-matched stable-frame
sweep, weld-into-shell(s), and the G65 quality reads (length, min bend radius, per-seam
tangent-vs-normal angle, sweep feasibility) emitted in the status block. Closes gaps.md
G59/G60/G61/G65; verified live on the 2:1, 55°-off-axis two-pipe case (watertight 1-shell
weld, both seams 0.0° off-normal). Phases 4 (editable params) and 5 (expressive strand tier)
remain open — see "Phasing" + gaps.md "Carried over". v1 limit: equal rim vertex counts only.
Proposed 2026-06-18 from the two-cylinder dogfood — three failed approaches (SPLINE_TUBE,
curve+bevel, bridge-then-sculpt). G58 (curved `bridge`) shipped first as the cheap 80%._

## The problem

Connecting two openings with an **organic** curve is, today, impossible to do well — not for
lack of effort but because the toolset has **mesh-displacement tools and geometry-blind curve
tools, with nothing that bridges them, and the agent is the only glue.**

Walked head-on this session, two capped cylinders, openings 75.8° off-parallel and 2:1 in
size, asked for "a singular elegant curve":

1. **The curve and the mesh live in two worlds.** To place a Bézier between the openings the
   agent read each opening's centre + normal, did trig in a script, and typed control points
   into a curve that has no idea the cylinders exist. Every "organic" property — leaving each
   pipe along its own normal, tangent continuity at the seam — is exactly that binding, and no
   tool expresses it. (gaps.md G59.)
2. **No sweep makes a hollow, weldable, vert-count-matched tube.** `extrude_along_curve`
   sweeps a filled face → solid rod; SPLINE_TUBE creases (no roll control), forces 36 sides,
   and fragments; `curve`+`bevel` is constant-radius, uncontrollable 12-gon, un-welded.
   (gaps.md G61.)
3. **The weld primitive is straight.** `bridge` lays one ring of shortest-path quads — no
   curvature dial. (gaps.md G58.)
4. **Faking the curve by sculpting wrecks the neighbours.** Subdividing the straight weld and
   `proportional_move`-ing it bulges a blob (not a path) and — falloff being Euclidean and
   freeze-less — deformed a cylinder. (gaps.md G60.)
5. **The agent is blind to the goal.** Nothing reads tangent-continuity, curvature, or pinch;
   verification sees *watertight* and *contact*, never *grace*. Told (correctly) not to read
   renders back, the agent has no ground-truth way to see whether a curve is elegant before
   baking. (gaps.md G65.)

The result: three iterations, each "that's not a curve," and a damaged cylinder.

## The principle

Make the **connection a first-class, geometry-bound, parametric object** — one primitive that
knows the two openings, leaves each along its normal with tangent continuity, sweeps a profile
that matches and reconciles the two rims, welds both ends, and **stays editable as parameters**
(curvature, profile, twist, count) rather than baking to dumb quads on creation.

This is the same inversion SPEC-08 made for deformers: put the skill **in the tool**. There,
the agent's eye couldn't drive a sculpt; here, the agent's dead-reckoning can't author an
elegant curve. So the elegance must live in the algorithm — tangent continuity by
construction, a single `tension` scalar for "how much arc" — not in hand-placed control points.

## The primitive

A connection verb that consumes **handles, not coordinates**:

```
edit op=connect a=<handleA> b=<handleB>
    style   = arc | s_curve | direct | slack         # the gesture
    tension = 0..1                                    # how much it bows / bulges
    profile = match | round | <radius> | taper(rA,rB) # cross-section
    sections= <int>                                   # length resolution
    sides   = <int|match>                             # cross-section count (match → rim's)
    twist   = <deg|auto>                              # rim-to-rim vertex alignment
    weld    = true                                    # fuse both ends into the owning shell(s)
```

Returns an **editable connector** (re-evaluable; see Editability) plus a status block with the
quality reads that G65 asks for.

### Anchoring & continuity (the core of G59)

- Endpoints **bind to the handles' live points** — they ride deformation, survive a stray
  deselect, recompute on read (same contract as `feel op=handle`).
- The launch tangent at each end is the opening's **outward normal** by default — the curve
  *leaves the pipe the way the pipe points*. This is G1 continuity at the seam, the thing the
  agent cannot currently express. `style=s_curve` keeps both launch tangents along the normals
  and lets the midspan cross over; `style=direct` relaxes continuity toward the straight line.
- `tension` sets the control-handle length as a fraction of the gap — one legible scalar for
  "graceful vs. taut," no trig.

### Profile & weld (G61 + G58, done right)

- `profile=match` reads **each rim's ring** (count + radius) and sweeps a cross-section that is
  that count at each end, **tapering between** — so a ⌀2.0 (32-vert) opening reconciles to a
  ⌀1.19 (32-vert) opening with a 1:1 weldable tube, no 36-vs-32 mismatch.
- The sweep keeps **cross-sections perpendicular to the tangent** with a **stable frame**
  (parallel-transport / minimum-twist, `twist=auto` to align rim vertices and kill the spiral),
  fixing the SPLINE_TUBE crease.
- `weld=true` fuses both end loops into the owning shell(s) (auto-join if cross-object, auto
  vertex-count match) → one watertight manifold, no separate floating tube, no manual
  open-cap → join → re-mint → bridge dance (G62/G63 disappear for this path).

### Editability

The connector stores its **parameters**, not just the baked quads — adjust `tension`,
`style`, `profile`, re-evaluate, the surface updates against the *live* handles. "More arc,"
"shift the apex," "thinner at the small end" become parameter edits, not re-sculpts. (Impl
options: a lightweight modifier/node-group the verb authors, or a stored param block the verb
re-runs. Decide in Phase 2.)

## The expressive tier — "a sequence of crazy curves"

The single connector is the unit; expressiveness is **cheap relational generation of many**,
which today is "the single-curve manual slog × K" and so never happens. Needed:

- **Sub-address an opening.** Partition a rim loop into N arcs/outlets (`select op=boundary`
  → split into N) so multiple curves can leave one pipe. No tool currently carves a boundary
  loop into addressable sub-arcs.
- **Connector arrays / strands.** `edit op=connect ... count=N` → N strands between the two
  openings (or between the partitioned outlets), distributed around the rims.
- **A randomized control-point field.** `jitter=<amt> seed=<n>` perturbs each strand's midspan
  waypoints coherently → variety from a seed + a count, not K hand-placed Béziers.
- **Bundle-weld.** Weld a *set* of strand ends into a rim in one call.

"Crazy" = generation that is relational and parametric, so variety is `count` + `seed`, not K
afternoons. This tier rides entirely on the single-connector engine — build that first.

## What this subsumes vs. what stays a gap

- **Subsumed by this SPEC (net-new):** geometry-bound anchoring + normal continuity (G59), the
  hollow/taper/match/stable-frame sweep engine (G61), weld-aware connection that skips the
  open-cap/join/re-mint dance (touches G62/G63), curve-quality reads emitted on connect (G65),
  the whole expressive strand tier.
- **Stays a standalone gap (ships first, independently):** **G58** — curved `bridge` via the
  native Bridge Edge Loops dials (cuts/smoothness/profile/twist). It's a parameter
  pass-through and delivers ~80% of "a single elegant welded curve" in an afternoon; this SPEC
  is the geometry-aware, editable, taper-matching, multi-strand version.
- **Orthogonal gaps this exercise also raised** (fix regardless of this SPEC): G60
  (topology-blind falloff + vertex-freeze — needed for *any* soft shaping), G62 (handle
  cap-vs-hole awareness), G63 (join migrates handles), G64 (assembly reads live curves).

## Phasing

1. ✅ **G58 (not this SPEC).** Curved `bridge` parameter pass-through. Shipped the cheap win.
2. ✅ **Connector v1 — `edit op=connect`, `style=arc|s_curve|direct|slack`,
   `profile=match|round`, `weld=true`, stable-frame sweep, normal-continuous launch.** One
   curve, two openings, welded, watertight, tangent-continuous. Dogfooded the two-pipe case
   in one call. (`connect_handles` in `extension/connectors.py`.)
3. ✅ **Quality reads (G65).** Per-seam tangent-vs-normal angle, min bend radius + where,
   taper, sweep feasibility — emitted in the connect status block. (The standalone `feel
   op=curve` centreline read shipped under G65 earlier; the connector adds the seam angles
   that need both ends bound.)
4. **Editability.** Stored params, re-evaluation against live handles. (OPEN — v1 bakes; to
   reshape, re-run `connect`.)
5. **Expressive tier.** Sub-address rims, `count`/`jitter`/`seed` strands, bundle-weld. (OPEN.)

## Open questions

- **Editable representation:** modifier/node-group authored by the verb, vs. a stored param
  block the verb re-runs on demand. The former is live but heavier; the latter is simpler but
  "edit" means "re-invoke." Lean node-group if the bevel/sweep can be expressed there.
- **`profile=match` when rim counts differ** (e.g. 32 vs 24): auto-rering one end, or refuse
  and point at a re-ring op? Probably auto-match with a reported warning.
- **Continuity order:** G1 (tangent) is the floor; is G2 (curvature) worth it for "elegant,"
  or does it over-bulge near the seam? Decide empirically in Phase 2.
- **Where the verb lives:** `edit op=connect` (mesh-result framing) vs. a new top-level
  `connect` verb. `edit` keeps the weld-into-mesh mental model; revisit if the expressive tier
  outgrows it.

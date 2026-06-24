# GAP-174 — Relational sweeps: extrude/generate paths in measured frames, never coordinates

**One line:** The whole generative-sweep family (`add type=tube|helix|curve`,
`edit op=extrude_along_curve`) still demands **absolute control points**, which is the one
place the server forces the agent to *divine* coordinates. Extend the relational,
measured-frame vector language the server *already speaks elsewhere* to this family, so a
free or connecting extrude is authored as **vectors originating from a handle**, optionally
as a function `f(t)`, and never as a typed XYZ point.

This is **not net-new functionality.** It is the *uniform application* of a principle and a
mechanism the server already has, to the verb family that was left as the exception. See
"Why this is coverage, not invention" below.

---

## Where the agent is forced out of intent-space

Extrudes split into two felt experiences:

- **Grounded extrudes already work and feel right.** `edit op=extrude down=0.003`,
  `extrude until_contact=Plate`, `extrude until_length=…` push *measured* geometry by a
  *relative or measured* amount. Provenance is airtight; these never caused trouble (plate
  well floor, icing drip skirt). `until_contact` is the gold standard — a destination named
  by the thing it lands on.

- **Free / generative extrudes break the paradigm.** The instant a swept form travels
  through empty space — a handle, a spout, a horn, a faucet neck, a stem, a wick, a
  branch — its destination has **no surface to address against**. `aim`, `on=`, `between`,
  and minted handles all resolve *onto existing geometry*; empty space has no handles. So
  the sweep verbs take `points=[[x,y,z], …]`, and the agent is forced to fabricate
  intermediate coordinates and verify self-intersection *after the fact*. Fabricating "a
  point that looks about right" is exactly the divination the North Star forbids — and it is
  the **only** operation where the server gives the agent no grounded alternative.

The handle in the donut build made this concrete: `feel op=aim` minted two perfect named
anchors on the mug wall, and then there was **no verb that consumes them into a swept
form** — the relational vocabulary dead-ended, and the build dropped into typing Cartesian
control points (3 rebuilds, see [G161]).

---

## Why this is coverage, not invention

Every ingredient already ships; they simply don't compose along the sweep axis:

- **Measured local frames exist** — `feel op=aim` (point + outward normal), `op=facing`
  (signed up/front/left/right), `op=frame` (intrinsic principal axes), all mintable as named
  handles.
- **Vectors-in-a-local-frame-by-expression already exist** — `edit op=field` has
  `channel=vector`, `frame=tangent_normal`, and `expr_x/expr_y/expr_z`. That is *precisely*
  the language this gap asks for, down to the basis. It is wired to *displace existing
  verts*; it is not wired to *grow a centerline*.
- **Relational addressing is everywhere** — `on=`, `between`, `move_to handle=`, `aim_axis`,
  `until_contact`.
- **The gesture vocabulary exists** — `edit op=connect` already has `style=arc|s_curve|slack`,
  `tension`, `profile`.
- **Generative multi-path sweeps exist** — `edit op=strands` (fan, jitter, tension).

So there is no new *concept* and no new *engine*. `tube`/`curve` got the obvious
bpy-shaped "take points" interface early — almost certainly *before* the frame machinery
(`facing`, `frame`, `field`'s `tangent_normal`) matured — and were never retrofitted. The
principle outran its oldest verbs. This gap closes that lag.

---

## Proposed primitive — `edit op=sweep`

A path **grows from a start anchor** (a handle, or a face selection whose frame is
measured). The centerline is expressed as **displacements in the anchor's measured
orthonormal basis** `(n, u, v)` — outward normal + two tangents — so no world coordinate is
ever typed and every number has provenance (origin measured, basis measured, multipliers are
authored dimensions/angles).

Three input forms, one model:

1. **Parametric (`f(t)`)** — the superpower. The path is *computed*, not enumerated, so
   helices, spirals, tapered coils, and fans are one expression:

   ```
   edit op=sweep  from=CoilStart  frame=tangent_normal   # basis = anchor's measured (n,u,v)
     f: t in 0..1, steps=64
        n = 0.02*cos(2*pi*5*t)     # 5 wraps
        u = 0.02*sin(2*pi*5*t)
        v = 0.06*t                 # advance along the axis
     profile=round  radius=0.001
   ```

2. **Literal vector list** — for one-offs, the same frame, incremental steps:

   ```
   edit op=sweep  from=MugAttachTop  frame=tangent_normal
     vectors=[ [0.02,0,0.01], [0.015,0.01,0.018], ... ]   # (n,u,v) multiples, step-to-step
     to=MugAttachBot  weld=true
   ```

3. **Gestural sugar (optional, lowers to vectors)** — for freehand organic forms where
   "turn relative to my heading" is the natural unit. Must compile down to form (1)/(2); it
   is convenience, **not** a second engine (one trustworthy substrate is the point).

   ```
   path=[ {along: normal, dist: 0.05},
          {turn: {up: 35}, dist: 0.04},
          {turn: {up: 25}, dist: 0.03, taper: 0.6} ]
   ```

**Key unification:** a *free* extrude is a path that ends in air (no `to:`). A *connecting*
extrude is the identical path whose terminus carries `to=<anchor> weld=true`. So the second
anchor stops being a different operation and becomes an **optional terminator** — one verb
covers the spout (no `to:`), the handle (`to:` an anchor), the strut/bridge (`to:` another
part), and the straight grounded push (the degenerate one-segment case `until_contact`
already serves).

---

## Validity & provenance (subsumes [G171])

Because the path is a function (or an explicit polyline) in a known frame, the server can
evaluate **min bend radius analytically** and reject/clamp *before meshing*:

```
sweep CoilStart · 5 wraps · pitch 12mm
  ✗ min bend radius 0.8mm < profile 1.0mm at t≈0.5 — loosen pitch or thin the profile
```

This is the first time a swept form's self-intersection becomes *predictable* instead of a
post-hoc `validate` discovery. It directly retires the need for [G171] (no bend read on a
baked tube) by making the read live on the path definition, and it removes the root cause of
[G161] (absolute-point interface that self-intersects) by never accepting absolute points.

---

## Symptoms this gap is the root of

- **[G161]** `add type=tube` self-intersects on a clean path — the *interface* is wrong
  (absolute points), not just the meshing. A vector-path input removes the divined seed.
- **[G171]** no bend-radius read for a baked tube — becomes an analytic read on the path.
- **[G153]** no clean handle-to-body weld — this is the `to=…weld` *terminus* of a sweep;
  the hard meshing kernel still lives in G153, but the *interface* to invoke it lives here.

Closing G174 well would let G161 and G171 be deleted outright and would give G153 its
caller.

---

## Open questions / caveats (honest)

- **Incremental vs cumulative vectors** must be explicit — each vector a step from the
  previous point (default; composes locally, matches "and then go this way") vs an offset
  from the origin. Cannot be implicit.
- **Profile orientation along the sweep** isn't fixed by the centerline alone — a strap/D
  cross-section needs a "which way is flat" reference. Seed from the anchor frame, carry by
  parallel transport, allow an explicit up-component for deliberately twisting forms (or the
  strap silently spirals).
- **The weld kernel is genuinely hard** — fusing a swept terminus into a curved wall with
  clean manifold topology is the unsolved part of [G153]. This gap does *not* hand-wave it;
  even shipping `to=…` as `embed` (overlap + `validate op=expect`) first would already
  restore the relational flow, because the thing that broke the agent was *being kicked into
  coordinate-space*, not the meshing math.
- **Don't add a sixth one-off path syntax.** The value is *uniform* application of the
  existing `field` vector-frame language. A parallel bespoke syntax would be exactly the
  special-case sprawl the North Star warns against.

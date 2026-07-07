# Intrinsic sculpt spike — lengths and angles as the edit language

**The hypothesis (2026-07-06):** THE ONE RULE bans divined *coordinates*, but edge
**lengths** and **dihedral angles** are relative, local, measurable quantities — editing
them is dimension-arithmetic, not divination. If a solver can reconstruct vertex
positions from an edited length field, the agent gets a freeform-sculpt channel where
no coordinate is ever typed.

**Solver:** local-global edge projection ("shape-up" style). Local step aims each edge
at its target length along its current direction; global step is one sparse
least-squares solve (graph Laplacian + soft pins), factorized once. ~50 lines of
numpy/scipy. Dihedrals never need angle math: a shared edge's fold is encoded by its
**flap diagonal** (distance between the two opposite vertices), so bending edits stay
inside the lengths-only language.

## Rung results

- **rung1_roundtrip** — icosphere (642 v), positions mangled to 26% mean length error /
  0.33 shape RMSE; solving for the recorded lengths recovers lengths to 0.2% and shape
  to RMSE 0.023 on radius 1.0. Lengths pin down the embedding in practice.
- **rung2_bulge** — jittered icosphere (2562 v), lengths ×1.25 under a smooth falloff:
  clean 0.13 bulge, residual ~1e-4, pinned region drift 0.00000. Lengths-only leaves
  bending free (isometric wrinkles are cost-zero), so the raw delta field is somewhat
  rougher than a naive normal push.
- **rung3_crease** —
  - A) Flat sheet folded **by only shortening flap diagonals** on the fold line
    (target d·sin(φ/2)). **The first attempt was a laundered failure**: fold-line
    dihedral read 98.9° and off-fold read 0.11° — but the "tent" was a 10cm ridge
    *wave* (crease + counter-bends beside it; the wing never lifted; true tent height
    ~1.06m). The averaged flatness metric hid the two counter-bend rows; the viewport
    exposed it instantly. Lesson: the solver finds *a* shape satisfying the lengths —
    **which** basin it lands in depends on the seed, and scalar summaries can't tell
    the basins apart.
  - A2) Seeding the wing pre-rotated 45° about the fold line: true tent, height 1.086m
    (expected ~1.06), fold dihedral 104.8° with **spread ±0.0**, wings flat to 0.04°.
    Creases work; intentional folds need a topological seed (which way, roughly how
    far), then the solver polishes it exactly.
  - B) Bulge with flap diagonals preserved as a bending regularizer: final **surface**
    roughness 0.0112 vs 0.0109 input / 0.0109 naive push — the wrinkle objection from
    rung 2 was mostly a metric artifact; the intrinsic result is as smooth as the
    surface it started from.

## Verdict

Viable. The full edit vocabulary — grow/shrink a region (length scale), crease/fold at
a target angle (diagonal scale), preserve-what-you-didn't-touch (diagonals as
regularizer) — is expressible as **fields of scale factors over a selection**, exactly
the shape of `buttons-deform-macro op=field`, and every number has provenance.

## Open (rung 4+)

- Real-mesh scale: solve time + stability at VRoid density (~50k verts); patch-local
  solve on a selection with a pinned boundary ring is the expected shape.
- Fold-angle precision (v2 lands 104.8° for a 90° target — uniform, so likely a fixable
  bias in the d·sin(φ/2) mapping, not noise).
- Seed policy for folds: v2 proves a coarse pre-rotation suffices; the op needs a
  "which way / roughly how far" argument the agent can derive (a direction + angle),
  never a per-vertex seed.
- Blender-side integration: extension has numpy but no scipy — needs a hand-rolled CG
  or precomputed factorization strategy.

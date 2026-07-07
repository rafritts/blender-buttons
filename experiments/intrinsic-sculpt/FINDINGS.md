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
  - A) Flat sheet folded to a tent **by only shortening flap diagonals** on the fold
    line (target d·sin(φ/2)): achieved 98.9° vs 90° target (spread ±19°), rest of the
    sheet stays flat (0.11°). Caveat: a flat sheet is a buckling critical point — the
    solve needs a tiny symmetry-breaking seed to pick a fold direction.
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
- Buckling seeds for intentional folds on flat/symmetric regions (the solver needs to
  be told which way to break).
- Fold-angle precision (±19° spread) — likely wants a weighted/finer schedule.
- Blender-side integration: extension has numpy but no scipy — needs a hand-rolled CG
  or precomputed factorization strategy.

# MCP gaps

- **G1 — Sweep the selection along a curve: `extrude_along_curve`.**
  Origin (2026-06-12): live horn-building session. F1's `out=` removes the trig
  for straight segments, but deliberate curvature is still multi-call dead
  reckoning — a curved viking horn took 3 extrudes + 2 tapers per horn, with the
  direction hand-rotated (30°→55°→80°) between calls. The missing primitive is
  the classic SWEEP: extrude the current edit-mode selection along a curve in
  one call. `spline_tube` already sweeps a circle into a NEW object; this is the
  same idea aimed at the selection, in-mesh.

  Signature sketch: `extrude_along_curve(curve="horn_path", segments=8,
  taper=0.3)`.
  - `curve`: an existing curve object by name (authored with `add_curve` — the
    established pairing). The curve describes the SHAPE of the path, not its
    world placement: re-root it so its start sits at the selection's centroid
    with its initial tangent aligned to the selection's `out` normal (the F1
    frame). The local-frame convention, consistent with the rest of the API.
  - `segments`: N arc-length-EQUIDISTANT samples along the curve — one extrude
    step per sample. Equidistant matters: it doubles as bend-ready topology
    (same reason `bend` tells you to loop_cut first).
  - `taper`: optional end-scale factor (1.0 = none, 0.3 = tip at 30%), applied
    per-step in the selection's tangent plane (reuse F3's in_plane machinery) —
    a horn is sweep + taper in one call.

  Engineering constraints (the difference between this and a disaster):
  1. FRAME TRANSPORT: rotate the cap along the path with PARALLEL TRANSPORT
     (minimal twist) — never Frenet frames, which flip 180° at inflection
     points and candy-wrapper the mesh mid-sweep.
  2. SELF-INTERSECTION GUARD: where the curve's bend radius < the profile's
     radius, inner walls cross. Detect (per-sample: bend radius vs selection
     radius) and refuse or warn loudly — same spirit as F1's degeneracy guard.
  3. Degenerate selection: closed bands have no `out` to align the curve start
     to — refuse with the F1 message (extension-side, reuse `_avg_normal_world`).
  Result should report steps placed, total path length (m), and the F1-style
  frame line for the initial direction. Extension-side, headless-testable
  (build a curve, sweep a face, assert the cap's centroid follows the samples).

_New gaps from future builds go above this line._

(F1–F3 closed in batch 11 — local-frame direction vocabulary (out/inward +
nudge words, meters) on extrude/move_vertices/proportional_move, closed-loop
extrude termination (until_contact/until_length), and the second wave
(sculpt_grab offset words, scale_vertices in_plane, bevel width in meters).
Write-up in the batch-11 commit + `tests/e2e_batch11.py`.)

# Open

- **`check_contacts` timeout on heavy evaluated meshes** — timed out on Spring's
  production meshes (noted during the batch-8 session, right before the live
  server dropped). Needs its own look: BVH/eval cost on dense evaluated geometry
  vs the 30s socket window.
- **X6c — bbox-vs-sel_z self-contradiction flag** — nice-to-have left open from
  batch 9: flag when a status block's bbox and selection-Z visibly contradict
  (the stale-eval-cache symptom), instead of relying on the caller to notice.
- **DISPLACE in `add_modifier`** — deferred from batch 8: inert without a texture
  datablock and there's no texture-creation verb yet — half-shipping a dead
  modifier isn't worth it until textures are addressable.

## Tactile introspection — the design principle

The guiding principle for P4–P12, kept here because it governs all future
introspection work: the agent's vision can *judge* but cannot *measure*. These
tools convert geometry into short semantic verdicts in scene vocabulary (object
names, mm/deg deltas, frame %) — never coordinate dumps, which the agent cannot
reason over. Region words ("top-left-front") locate things without leaking
coordinates. BVHTree makes the proximity queries milliseconds-cheap at hobby poly counts.

---

# Closed

Closed-gap write-ups live in git history (the batch commits) and each batch's
e2e suite in `tests/e2e_batch*.py`, which documents what it closed.

# Long-term (character quality finish line)

- Rigify control-rig generation (the generic armature layer is in; this adds IK/FK controls on top)
- Multires + dyntopo wrappers
- Retopology — auto-retopo or guided
- UV unwrap with seam control
- Material node graph beyond Principled BSDF
- Hair card system
- Face topology: eyes/nose/mouth loops with subsurf-correct flow
- Camera path animation (Follow Path constraint + keyframed eval over `add_curve` paths)

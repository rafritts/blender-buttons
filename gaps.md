# MCP gaps

_New gaps from future builds go above this line._

(G1 closed in batch 12 — `extrude_along_curve`: sweep the current edit-mode face
selection along a curve in one call. The curve is re-rooted to the selection's
centroid with its start tangent aligned to the F1 `out` normal; rings are
arc-length-equidistant; frames carried by parallel transport (no candy-wrapping);
`taper` shrinks the cross-section per-step in its tangent plane (reusing the F3
in_plane split). Guards refuse — with numbers — on a closed-band selection (no
`out`) and on self-intersection (bend radius < profile radius). Write-up in the
batch-12 commit + `tests/e2e_batch12.py`.)

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

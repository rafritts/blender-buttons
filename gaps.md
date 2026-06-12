# MCP gaps

_New gaps from future builds go above this line._

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

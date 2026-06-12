# MCP gaps

## H1 — overlap warning on object creation

Floor-test finding (weak-driver sword session): four primitives spawned at the
origin, fully interpenetrating, and nine consecutive status blocks never said
so. The driver blamed "unreliable positioning"; the real failure is that
creation reports the new object but not its relationship to the scene.

Spec: after any creation verb (`add_*`, `duplicate_object`, `spline_tube`, ...)
that lands a new mesh object, check it against existing mesh objects and, when
it materially overlaps one, say so in the result — with the fix vocabulary:

    ⚠ grip overlaps blade (~100% of grip's volume) — intentional (boolean)?
      place with on=/at=, or move with snap_to / nudge

Constraints:
- Warn, never refuse — overlap is often intentional (boolean workflows feed on
  it). One line in the status block, no extra round trip.
- Cheap broad phase only by default: world-AABB intersection volume as a
  fraction of the new object's AABB volume; report above ~25%. Narrow-phase
  (BVH) only when the AABB test fires AND both meshes are light — mind the
  known `check_contacts` cost blow-up on dense evaluated meshes (open gap
  below). AABB-only verdicts are fine; phrase them as "~" estimates.
- Check even when the caller passed `at=`/`on=` — explicit placement collides
  too. The origin pileup is just the loudest case.
- The warning must name the verbs that fix it. A result line is where a weak
  driver learns the vocabulary exists; this is the cheapest, most diagnostic
  moment to teach placement.

## H2 — screenshots and renders must be legible by default

Same session: "MATERIAL and RENDERED shading often came back washed out, dark,
or blank." Reproducible — an unlit scene renders near-black, and a driver that
cannot see cannot iterate (and cannot debug lighting *before* it can see).

Spec, two layers:
- Detection (always on): after `get_viewport_screenshot` / `render_to_file`,
  inspect the produced image; if it is near-black or near-uniform (mean
  luminance under ~5%, or variance ≈ 0), say so in the result with likely
  cause and fix: "image is ~97% black — scene has no lights (`add_light`) or
  the camera is inside geometry (`frame_scene`)". Never return a blank image
  as silent success. The uniformity check also catches camera-inside-mesh,
  not just lighting.
- Prevention (cheap prior): when shading is RENDERED/MATERIAL and the scene
  has zero lights and no emissive world, warn in the screenshot result before
  the driver burns a loop on it. Optional escape hatch:
  `render_to_file(ensure_lit=True)` injects a neutral studio world for that
  render only, never persisted into the scene.

Both extension-side, headless-testable (assert the black-render warning fires
on an unlit scene; assert the overlap line fires on two stacked cubes and does
NOT fire on separated ones).

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

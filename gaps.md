# MCP gaps

- **F1 — Local-frame direction vocabulary for vertex-moving verbs (wave 1).**
  Audit finding (2026-06-12): the vertex-moving tools are the last world-axis
  holdouts in an API that is otherwise local/semantic. `extrude(x,y,z)`,
  `move_vertices(x,y,z)`, and `proportional_move(x,y,z)` all take world-axis
  vectors in fraction-of-bbox units — to predict `x=0.5` the agent must know the
  object's world orientation AND its current dimensions, and the bbox changes as
  you edit, so the unit drifts between calls. `proportional_move` additionally
  mixes units in one signature (translation in bbox fractions, `radius` in
  meters). Meanwhile ~90% of real extrudes are "along the selection normal",
  which none of them can express on a tilted face.

  Fix: one shared direction vocabulary on all three, resolved extension-side so
  the headless e2e harness covers it. All distances in METERS:
  - `out` / `in` — along the selection's area-weighted average normal,
    recomputed fresh from the current selection each call (no drift).
  - `up/down/left/right/forward/back` — the established `nudge` words (world
    ±Z/±X/±Y).
  - Composable in one call: `extrude(out=0.05, down=0.01)`.
  - `move_vertices(out=...)` is a RIGID translation along the average normal —
    distinct from `inflate_selection`, which stays per-vert-normal.
  - Frame report: every result names the resolved direction in world-semantic
    words (e.g. "out ≈ forward, 15° above level") so the agent can cross-check
    its mental model.
  - Degeneracy guard: if the selection's normals cancel (closed ring/sphere band,
    |avg| below a threshold), REFUSE with a message pointing at
    `inflate_selection` (radial intent) or a world direction — never move along
    a garbage average.
  - Back-compat: legacy `x/y/z` fraction params stay accepted extension-side
    (old tests/transcripts keep working) but are demoted to a single "legacy"
    line in the server docstrings — the docstring is the prior the model samples.

- **F2 — Closed-loop extrude termination: `until_contact` / `until_length`.**
  Companion to F1, highest-leverage piece: `extrude(out=..., until_contact="floor")`
  raycasts along the resolved direction and stops where the new geometry touches
  the named object's evaluated surface; `until_length=0.3` extrudes until the
  moved geometry is that far (meters) from its start. Converts open-loop dead
  reckoning into closed-loop control — dimensions-over-coordinates applied to
  edit mode. When a termination param is given, the distance params become
  optional (direction still needed, default `out`).

- **F3 — Local-frame second wave: sculpt_grab offset words, scale_vertices
  in-plane, bevel meters.**
  - `sculpt_grab`: keep `at_x/y/z` (the coordinate ripcord, same as
    select_in_sphere), but allow the F1 direction words (`out=0.02`, `up=...`)
    as an alternative to the hand-computed `to_x/y/z` world point — the offset
    is the part that wants to be local.
  - `scale_vertices`: world-axis multipliers are meaningless on a tilted-surface
    selection; add an `in_plane=` uniform scale in the selection's tangent plane.
  - `bevel`: third unit system in the API (fraction of smallest dim); add
    `width=` in meters as the documented-primary, keep `factor` as legacy.

  Audit context for all three F-gaps — tools already local/intrinsic, do NOT
  touch: inflate_selection, jitter_vertices(NORMAL), all sculpt_* frames, the
  ring system (get_rings/select_ring(s)/scale_rings/taper_* — topology indices
  + per-ring centroids), select_boundary, grow_selection, band_around,
  round_corners. Semantic-global tools that are CORRECT as-is (object placement
  is genuinely global-relational): nudge, resize, snap_to, scale_group,
  rotate_object, bend, the mirror/array/distribute family, and the selection
  addressers select_by_axis/select_between (bbox-normalized axes are fine for
  CHOOSING verts; the gap is only in MOVING them).

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

# MCP gaps

## J — the hatchet tier: 2D→3D creation powertools (J1–J4)

The surface today is knives (primitives + boolean + placement) and scalpels
(edit-mode verbs, recently made aimable by F/G). The missing tier is hatchets:
one call → 80% of a shape. Design principle for all four, derived from what
already works (`auto_weight`, `match_dimension`, `until_contact`):

**A hatchet is a dimensionality reducer.** LLMs are weak at 3D vertex
reasoning but strong at 2D outlines, profiles, and scalar lists. Every classic
human Blender hatchet takes low-dimensional input — that's what these wrap.
All four are bone-stock Blender primitives (spin, fill+solidify, skin
modifier, metaballs) — no domain leakage, per the general-tools rule.

Shared requirements:
- Placement/naming params match the existing `add_*` convention; output is a
  normal mesh object that composes with every existing verb.
- Validate the cheap 2D input BEFORE executing; refuse with numbers, F1-style
  (self-intersecting outline: name the two crossing segments; negative radius:
  name the index).
- Clean, editable topology or it's a trap — a hatchet whose output only
  scalpels can fix is worse than no hatchet. State topology grade in the result.
- Escalation-ladder docstrings: each hatchet ends with "refine with: <verbs>";
  the relevant knives/scalpels gain one line pointing back up ("revolved
  shape? `add_lathe` does it in one call"). Cheap discoverability both ways.

**J1 — `add_lathe(name, profile=[[r, z], ...], segments=32)`** — surface of
revolution: profile revolved around local Z (bmesh spin). r=0 endpoints close
poles with merged verts. Pommels, helmets, vases, bottles, pillars, chess
pieces. Killer synergy: lathe output IS ring topology — `get_rings`,
`scale_rings`, `select_ring`, `taper_section` work on it immediately. Guards:
r ≥ 0, monotonic-z self-intersection check. Test: vase profile → assert ring
count == len(profile), dims match profile extents.

**J2 — `add_silhouette(name, outline=[[x, z], ...], thickness, bevel_width=0)`**
— flat 2D outline (front/XZ plane, the natural drawing plane), filled,
solidified along Y to `thickness`, optional edge bevel. Blades, guards,
plates, shields, brackets — how humans actually model swords. Outline
auto-closes; refuse self-intersection (segment-pair check, name the segments).
Prefer grid fill where the outline allows; report fill quality. Test: a
non-convex outline → manifold result, `check_mesh` clean, dims match outline
bbox × thickness.

**J3 — `add_skeleton(name, joints=[[x, y, z], ...], radii=[...])`** — stick
figure → organic mesh: edge chain + skin modifier (per-joint radii) +
subsurf, modifiers left LIVE so the result stays editable (`convert_to_mesh`
already exists for downstream booleans). Limbs, horns, antlers, trees,
tentacles. The 19-call viking horn becomes one call: 4 joints, tapering
radii. V1 is a single chain; branching is a follow-up, not v1 scope. Guards:
len(radii) == len(joints), radii > 0, joints non-coincident. Test: horn-like
chain → mesh dims, radii honored at each joint (measure ring diameters).

**J4 — `add_blob(name, blobs=[[x, y, z, r], ...], resolution=0.05)`** —
metaball fusion: place weighted blobs, they fuse smoothly, convert to mesh.
The organic blockout hatchet (torso+head+muzzle in one call). Honest topology
caveat in the result: metaball→mesh is blockout-grade tri soup — say so, and
suggest the remesh path for sculpt-readiness. Guards: r > 0, warn when a blob
is fully inside another (it contributes nothing).

Sequencing: independent of I1, but land names under I1's prefix discipline
(`add_*` = creates). These four are additive even against the ≤100 count
target. Each is extension-side and headless-testable.

## I1 — tool-surface consolidation: ~155 tools → ~95, name-as-namespace

The server has ~155 registered tools (count: `grep -c "@mcp.tool" server/*.py`).
MCP is a flat protocol — no folders, no paths; most clients inject every schema
into context (~20–30k tokens) and the only namespace a tool has is its own name
string. A weak-driver floor test (Grok 4.3) found 6 of 155 tools. The bloat is
not a long tail of weird tools — it's families of near-duplicate siblings that
collide in the driver's head.

**Cost model — judge every tool by this, not by usage frequency:**
1. context tokens (every schema rides along),
2. collision (a sibling similar enough that drivers pick the wrong one),
3. maintenance.
Niche-but-isolated (`set_camera_dof`) is nearly free. Common-but-colliding
(11 selection tools) is expensive even for strong drivers. Cut/merge by
collision, never by frequency alone.

**Phase 1 — audit table (its own commit, before any code changes).**
Produce `docs/tool-consolidation.md`: every tool, one row —
`name | verdict (keep / merge→target / cut) | rationale (one line)`.
Known collision families to resolve (pre-identified, verify and complete):
- selection (11): `select_all/object/ring/rings/between/boundary/by_axis/
  in_sphere`, `grow_selection`, `inflate_selection`, `random_select`
- scaling (5): `resize`, `scale_group`, `scale_vertices`, `scale_rings`,
  `match_dimension` — note these span three naming patterns, so the family is
  invisible to the driver today
- edge finish (5): `shade_smooth`, `shade_flat`, `mark_sharp`,
  `set_edge_crease`, `smooth_edges`
- info/list (6): `list_modifiers/constraints/shape_keys/designs`,
  `get_object_info` → fold into `describe`
- viewport/camera (8): `orbit_viewport`, `set_viewport_angle/shading/overlays`,
  `frame_scene`, `zoom_to_selected`, screenshot, collage
- mid-level shape verbs: `band_around`, `taper_end`, `taper_section`,
  `round_corners` vs `bevel`/`scale_rings` overlap
- pure twins: `snap_to_grid`→`snap_to`, `set_mode`+`set_component_mode`,
  `add_primitives` vs the ten `add_*`
Ultra-niche cut candidates (verify nothing in tests/ or saved designs depends):
`set_particle_visibility`, `set/get_custom_properties`, `set_color_management`,
`add_outline`/`remove_outline`, `jitter_vertices`, `move_modifier`.

**Merge rules:**
- Merge SAME VERB, DIFFERENT SCOPE into one tool with a scope enum:
  `select(scope="ring"|"boundary"|"by_axis"|...)`. The enum is the namespace —
  the docstring must list every scope value with a one-line description, since
  that listing replaces eleven separate schemas as the driver's directory.
- NEVER merge distinct verbs (`extrude` and `bevel` stay separate forever).
- No mega-tools: if a merge forces unrelated params into one schema or pushes
  it past ~8 params, don't merge.
- Server-side only where possible: a merged server tool dispatches to the
  existing extension handlers over the socket — extension code and the
  1-tool-call-=-1-undo-step invariant untouched. Cuts remove both sides.

**Prefix discipline for the residual flat list:** read-only starts `get_`/
`check_`, creation starts `add_`. Break up the `set_*` junk drawer (19 tools,
nothing in common but the verb) only where a rename fixes a real findability
problem — renames churn tests and priors, so no cosmetic renames.

**Do NOT cut:** the tactile-introspection suite (`check_resting`, `is_aligned`,
`gap_between`, `parts_in`, ...) — low frequency but zero collision, and it's
the project thesis. Likewise history/undo.

**Acceptance:** tool count ≤ ~100; the audit table proves every removed
capability is reachable on the new surface (old name → new call mapping);
merged docstrings enumerate their scopes; e2e suite asserts each scope value
routes to the right handler and the legacy e2e batches still pass.
Implementation will likely take several batches — audit table first, then
merges, then cuts, then renames. Get the table reviewed before writing code.

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

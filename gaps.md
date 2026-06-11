# MCP gaps

## Production-asset gaps (U1–U11) — driving the Blender Studio "Spring" rig, 2026-06-11

Everything before this series was authoring: build the asset, then introspect
what we built. Spring (BlenRig character, ~400 objects, mesh-deform cages, face
lattices, particle hair, linked widget meshes) tests the opposite workflow —
*operate on a complex asset someone else made*. The creation verbs held up
(nothing crashed; `get_object_info` listed a 32-modifier stack cleanly). The
introspection layer is what thins out: the toolset can author a rig but cannot
discover one.

- **U1 — armatures cannot be discovered, only authored.** `pose_bone` expects
  bone names "from create_armature" — the toolset assumes WE built the rig.
  Against RIG-Spring there is no way to learn a single bone name: no bone-tree
  tool, no bone-level describe. Posing the character fails at step zero.
  Primitive: armature introspection — a bone hierarchy tree (filterable, like
  U4; this rig has hundreds of bones) and a per-bone describe (parent, head/tail
  in scene vocabulary, deform flag, locks, constraints with their targets).
  The read-side complement of `create_armature`.
- **U2 — no custom-property access.** Production rigs are driven through custom
  props — IK/FK switches, the whole `cs_properties_*` panel family. We have no
  get/set for custom properties on objects, bones, or pose bones. General
  Blender primitive (any addon/rig/game-export metadata lives there), not a
  rig-specific one.
- **U3 — `pose_bone` only rotates, with replace semantics.** Production rigs
  are posed mostly by *translating* IK controls (hand/foot targets, pole
  vectors); a rotation-only verb can't drive an IK chain at all. Primitive:
  bone location alongside rotation (and an additive option — replace semantics
  forces re-deriving the full pose to nudge one axis).
- **U4 — `get_scene_tree` doesn't scale.** On Spring it dumped ~400 objects —
  300 of them `cs_*` bone-shape widgets — and the output the agent received
  cut off mid-tree (lights/cameras/world never appeared). Verified against the
  code: there is NO cap or truncation in `get_scene_tree` itself — the clamp
  happened in the agent harness swallowing a payload that size. So this is an
  output-volume/scalability gap, not a no-silent-caps bug: at production scale
  the full dump is unreadable by the consumer regardless of who truncates it.
  Primitive: depth limit, type/name filters, and collection summarization
  ("spring.rig.widgets/ — 310 meshes") with full expansion on request.
- **U5 — Principled-slot material summaries are actively WRONG on node-graph
  materials.** `MAT_spring.head` — the skin — reports base_color black,
  emission_strength 1.0: the real shading lives in the node tree and the
  unused Principled defaults get reported as truth. An agent would conclude
  the face is black and glowing. T3's big sibling (T3: overrides invisible;
  U5: values misleading). Minimum fix: detect that the summarized sockets are
  link-driven and say `nodegraph-driven (summary unreliable)` instead of
  reporting numbers; the full fix is the long-term node-graph item.
- **U6 — `describe()` has no vocabulary for non-mesh types.** "RIG-Spring:
  freestanding (origin -0.435m above floor); no material" — technically true,
  useless, and 'no material' is noise on an armature. Lattices, empties, and
  armatures need their own relational sentences (an armature's is U1's bone
  summary; a lattice's is what objects it deforms; an empty's is what uses it
  as a target).
- **U7 — particle systems are invisible and undrivable.** Spring's hair is 6+
  PARTICLE_SYSTEM modifier entries; we can see the names via `list_modifiers`
  and nothing else — can't toggle viewport display (they bury the head in
  strands), can't read counts/types, can't convert to mesh (`convert_to_mesh`
  bakes curves, not particles). Even just display-toggle + a describe line
  would make hair-bearing assets workable.
- **U8 — shape keys don't exist in the toolset.** No list, no get/set value.
  Any character face (and plenty of hard-surface assets) carries them;
  they're also the natural target of a future corrective-sculpt workflow.
- **U9 — constraints and drivers are invisible.** Bone constraints (IK chains,
  copy-transforms, the entire BlenRig control graph) and drivers can't be
  listed on anything. Consequence for U3: `pose_bone` may silently fight a
  constraint and report success while the bone didn't visibly move. Read-only
  listing (constraint type + target + influence per bone/object) is the
  primitive; mutation can wait.
- **U10 — linked library data is undefined territory.** The scene tree marks
  dozens of objects `(linked)` but no tool knows the difference: what happens
  when `move_vertices` or `set_material` hits a linked datablock is untested —
  likely an opaque error, possibly a silent no-op. Primitive: surface
  linked/override status in describe + scene tree, and fail loudly with a
  "linked data — needs a library override" message on mutation attempts.
- **U11 — externally-opened files leave stale server state.** Spring was
  opened by hand (File → Open); the status block still reports
  `last_action: 'Final game ready overview render'` from the previous
  catapult session. History, `diff_since` snapshots, and undo bookkeeping all
  describe a scene that no longer exists — `undo()` here would try to "verify
  against history snapshot" from another file. `new_scene` clears
  bookkeeping; a manual file load bypasses it. Fix: a load-file handler
  (`bpy.app.handlers.load_post`) that resets history state, the same reset
  `new_scene` already does.

## Presentation-pass gaps (T1–T8) — texturing/lighting the catapult for a showcase, 2026-06-11

Dressing a finished multi-material asset for hero renders. The build was done;
every gap below is about *changing how it looks* without rebuilding it.

- **T1 — materials are only addressable through an object's slot 0.**
  `set_material` / `set_textured_material` always write the target's first
  material slot. A multi-slot mesh (wheel: wood faces + iron rim faces) can't
  have its secondary material changed at all, and a material shared across many
  objects (`iron_mat` on 4 wheels + arm + drum) can't be restyled in one call —
  the tools have no way to say "update the material *named* iron_mat".
  Workaround that worked: add a throwaway box, apply with
  `material_name="iron_mat"` (reuse-rewires the shared datablock in place, so
  every slot-1 user updates), delete the box. That's three calls and a trick;
  the primitive is one: address a material by NAME with no target object
  (`set_material(material="iron_mat", ...)`), leaving slot assignments alone.
  Slot-index targeting (`target="wheel_FL", slot=1`) is the same gap from the
  other side.
- **T2 — `set_camera_dof(focus_object=...)` focuses on the rest-pose origin.**
  Object origins don't move under armature deform, so focusing on the posed
  boulder (riding the cocked arm, ~1m from where its origin says it is) needed
  hand-computed `focus_distance`. The fix mirrors R4's lesson: evaluate the
  posed geometry — focus on the evaluated-bbox center, not the object origin.
- **T3 — texture tint/override values are invisible to introspection.**
  `describe` lists each slot's material with base color + roughness +
  `texture(asset@res)`, but a `tint`/`base_color` override applied by
  `set_textured_material` lives inside the node tree and is not reported — after
  retinting the shared `rope_mat`, nothing deterministic could confirm the
  change propagated (describe still showed the unused BSDF default
  `[0.8, 0.8, 0.8]`); only a render could. Tactile-introspection hole: the
  material line should read `texture(cotton_jersey@1k tint=[0.45,0.33,0.2])`.
- **T4 — the agent can't see what the user's viewport is showing.** A whole
  texture pass happened while the user's viewport sat in SOLID shading — they
  watched gray blockout and reported "zero textures" while renders were fully
  dressed. `get_viewport_screenshot` returns the shading mode in its metadata,
  but the status block (the instrument panel every mutating call returns) does
  not. One `viewport: SOLID` line in the status block would have flagged the
  mismatch at the first `set_textured_material` call.

- **T5 — viewport overlays are screenshot-only configurable.**
  `get_viewport_screenshot(hide_overlays=True)` cleans up the agent's view, but
  nothing can clean up the USER's live viewport: with a rigged, scattered scene
  the armature draws white octahedral bones over the meshes and every linked
  instance draws a dashed relationship line — the textured model reads as gray
  blockout to the person watching. T4's other half: the agent could *see* the
  problem (after T4 lands) but still can't *fix* it. Primitive: a
  `set_viewport_overlays(relationship_lines=, bones=, gizmos=, ...)` verb (or
  per-object viewport visibility, e.g. hide the armature object from the
  viewport without unbinding it).

- **T6 — no posed-position query for deformed meshes.** Object origins and
  `describe`/`get_object_info` report REST placement; while the rig was cocked,
  framing the camera on the relocated cup meant hand-deriving the bone pivot
  from two measured point pairs and rotating the rest position by hand (the
  exact dead-reckoning GUIDANCE_FOR_LLMS warns about). The armature object's
  status-block bounds DO update with pose, but per-mesh evaluated bounds don't
  exist as a query. Primitive: `describe(name, posed=True)` (or a
  `where_is(name)`) returning evaluated-geometry bounds/center under current
  modifiers — one call instead of trigonometry. Would also fix T2's DOF case.
- **T7 — deleted-object names stay claimed after a boolean.** Sequence:
  `boolean(..., hide_cutter=True)` → `delete_object(cutter)` reports deleted →
  `add_sphere(name=<same name>)` fails with "already exists". Workaround: pick
  a fresh name. **ROOT CAUSE (live repro 2026-06-11): `delete_object` silently
  no-ops on hidden objects.** Control (add → delete → re-add, never hidden)
  is clean; with `hide_cutter=True` the delete reports "Deleted 't7_cutter'"
  but the post-call status block still shows `active: t7_cutter` with readable
  dims — the object never left `bpy.data`. Hidden objects can't be selected,
  so a select-by-name → `bpy.ops.object.delete()` path deletes nothing; the
  tool doesn't verify and reports success anyway (a silent-success violation,
  T8's sibling). Not undo snapshots, not orphaned mesh data. Fix: delete via
  `bpy.data.objects.remove(obj, do_unlink=True)` (ignores visibility/selection
  entirely), or unhide before the ops path — and assert
  `name not in bpy.data.objects` afterward, failing loudly if it survived.

- **T8 — `boolean` reports success when the result is an empty mesh.** A
  DIFFERENCE slab cut against a joined mesh whose islands interpenetrate (arm
  shaft poking into the bowl shell) returned "applied (baked)" — and the target
  collapsed to zero verts. Only the status-block bounds (`dims: [0,0,0]`)
  betrayed it; one render later it would have been "where did the throw arm
  go". `undo()` recovered (E1's full-context fix verified in real anger), and
  cutting the SPLIT-OFF island alone worked, so the rule is "split before you
  boolean a multi-island mesh" — but the tool should catch the catastrophic
  outcome itself: if the result has 0 verts (or loses >X% of input verts on a
  DIFFERENCE), fail loudly and leave the modifier unapplied, the same way
  apply-failure already does.

## S1b-residual — lint skip-report is bypassed by GROUP expansion, 2026-06-11

`audit_asset("throw_arm,winch_rope")` correctly prints `(skipped 1 non-mesh:
winch_rope)`, but `audit_asset("catapult")` — a 9-part group containing the
same curve — reports `8 object(s)` with no skip line (same for
`validate_scene`). The group→objects resolution filters to meshes BEFORE the
tools' `excluded_non_mesh` accounting, so the no-silent-caps fix only covers
explicitly named targets. Fix where the group expands: pass non-mesh members
through to the tool's exclusion accounting instead of dropping them at
expansion.

## Tactile introspection — the design principle

The guiding principle for P4–P12, kept here because it governs all future
introspection work: the agent's vision can *judge* but cannot *measure*. These
tools convert geometry into short semantic verdicts in scene vocabulary (object
names, mm/deg deltas, frame %) — never coordinate dumps, which the agent cannot
reason over. Region words ("top-left-front") locate things without leaking
coordinates. BVHTree makes the proximity queries milliseconds-cheap at hobby poly counts.

---

# Recently closed

## Live-curve delivery gaps (S1–S2) — finishing the catapult rope, 2026-06-11

R4 made the beveled live curve a first-class deliverable (the rig-following
rope); these two close the gap between "the curve follows the rig" and "the
curve is a textured, exportable deliverable". e2e in `tests/e2e_curve_delivery.py`
(19 checks).

- **S1 — material tools accept any material-slot object, not just meshes.**
  `set_material`, `set_textured_material`, and `set_toon_material` now filter on
  `has_material_slots(obj)` (new `common.py` helper: `obj.data` carries a
  `materials` collection — MESH, CURVE, SURFACE, FONT, META) instead of
  `type == 'MESH'`. A beveled curve renders as a solid tube with ordinary slots,
  so it materializes directly — no more baking throwaway `spline_tube` stand-ins
  per pose to texture a rope. Extended to `set_toon_material` too (same
  assign-to-slots family; leaving it mesh-only would just be the same gap one
  tool over). `add_outline`/`remove_outline` stay mesh-only — they build an
  inverted-hull solidify shell, which is genuine mesh geometry, not a slot
  assignment. **S1b:** `audit_asset` and `validate_scene` genuinely can't lint a
  curve (no faces), but they no longer *silently* drop them — both return
  `excluded_non_mesh` and the server prints "(skipped N non-mesh: …)", per the
  no-silent-caps principle.
- **S2 — `convert_to_mesh(name)` bakes a live curve into a real mesh.** New
  general verb (Object > Convert > Mesh) in `finishes.py`. `bpy.ops.object.convert(target='MESH')`
  evaluates the FULL result — modifiers, the curve's bevel, AND the hooks — in
  one call, so the R4 following-rope delivery is now a single
  `convert_to_mesh("rope")` after posing (not apply-then-convert). Chose a
  dedicated verb over auto-converting inside `apply_modifiers`: silently changing
  an object's type would surprise callers and break "apply a hook but keep
  editing the spline". Verified headless: a posed, hooked, beveled POLY curve
  converts to a MESH whose baked verts keep the hook-deformed shape and then
  takes `set_textured_material` with no complaint. R4 delivery docstrings
  (server `add_curve`, extension `add_curve`) updated to point at it.

## Siege-catapult rigging gaps (R1–R5) — mechanical-prop rigging, 2026-06-11

Rigid-assembly rigging + set-dressing. Armature work in `extension/armature.py`,
the following rope on `add_curve` (`extension/curves.py`), exclusion zone on
`scatter_on_surface` (`extension/scatter.py`); all mirrored server-side. e2e in
`tests/e2e_rigging.py` (25 checks).

- **R1 — `weight_to_bone(mesh, armature, bone)`** — rigid bind: 100% weight on
  every vertex to ONE bone, strips this armature's other deform groups so the
  bone is the sole influence, creates/reuses the Armature modifier. The
  deterministic alternative to `auto_weight`'s heat solve for hard-surface parts
  (wheels, doors, levers, throwing arms). Added an `armature` param the gap's
  `(mesh, bone)` shorthand omitted — a bone name alone can't say which armature
  owns the modifier. Verified headless: posing the bone deforms the bound mesh.
- **R2 — `auto_weight` coverage verdict** — now reports `weighted/total` and
  clusters orphaned (unweighted) verts into connected islands by mesh edges,
  located by region word: `96/128 weighted — 32 orphaned in 2 islands: 18 verts
  top-front, 14 verts bottom-back`. WARNs like the zero-weight case and points at
  `weight_to_bone` for rigid parts. (`_orphan_islands` unit-tested directly,
  since the heat solve won't deterministically orphan a simple test mesh.)
- **R3 — `deform: false` bone flag** — `create_armature` bone spec accepts
  `"deform": false` → `edit_bone.use_deform`, excluding root/control bones from
  the heat solve. Replaces the bury-the-bone-below-the-floor hack. Result lists
  `non_deform_bones`.
- **R4 — anchored following curve** — landed on `add_curve` (not `spline_tube`):
  a baked mesh can only drag its endpoint vertex rings (shear/tear), so the tube
  must stay a LIVE curve whose spline re-solves between hooked control points.
  Any control point can carry `"anchor": {"object": "winch_drum"}` or
  `{"bone": "rig/arm_swing"}` → a Hook modifier; the curve follows when the
  target moves/poses (rope, cable, hose, chain). Per-point (not endpoint-only) so
  a sag midpoint can stay in world space. `spline_tube` keeps its pure
  bake-to-mesh contract. Traps handled: hook captures the point in the bone's
  REST space (anchor in rest pose), and add_curve's identity object transform
  makes `matrix_inverse = target_world⁻¹` the correct no-jump bind. Delivery:
  pose the rig, then `apply_modifiers` to bake the curve to a game-ready mesh.
- **R5 — `scatter_on_surface` exclusion zone** — `avoid` (object/collection) +
  `avoid_margin` rejection-samples instances out of the avoid's world XY
  footprint; instances that can't clear it after 20 tries are dropped and
  reported. Set-dressing around a hero asset in one call.

## Pocket-watch gaps + tactile introspection (P1–P12)

Manipulation (`relational.py`, `transforms.py`) and two new analysis modules
(`extension/lint.py`, `extension/introspect.py`, mirrored server-side). All
read-only tools are in `NON_UNDOABLE_TOOLS`; e2e in `tests/e2e_introspect.py`.

- **P1 — `array_radial`** — circular/arc duplication around a center (point or object), optional `align_to_tangent`. Full 360 span = no overlapping seam (`step=span/count`); any other span = arc, inclusive of both ends. Built with `matrix_world` composition so orientation rides the orbit only when tangent-aligned. Clock markers, bolt circles, gear teeth, chain links on an arc.
- **P2 — `rotate_object(pivot=…)`** — optional `pivot=[x,y,z]` / `pivot="<object>"`. Rigid `T(pivot)·R·T(−pivot)·matrix_world` swing (position + orientation) for clock hands about the dial, a door about its hinge. No pivot → unchanged own-origin spin.
- **P3 — `find_coplanar_overlaps(targets?, epsilon)`** — collapses each object's axis-aligned faces into merged "panels" (axis, outward-sign, plane-coord) and reports cross-object coplanar panels overlapping in-plane, with overlap size in mm. Same-sign requirement avoids flagging legitimate flush stacking. Also reused inside P5.
- **P4 — `check_contacts(targets?)`** — per part: connected / floating(gap mm) / penetrating(depth mm) vs its nearest neighbour. Gap from BVH nearest-vert; penetration from all-axis bbox overlap (robust for matched footprints where vertex-inside tests fail). Reports facts, no judgement.
- **P5 — `validate_scene(targets?)`** — compiler-style lint: cross-object z-fights (P3), likely-inverted normals (centroid-facing heuristic), zero-area faces, objects below the floor. "PASS" or one finding per line. (Authoring-time lint-on-write left for later; standalone tool shipped.)
- **P6 — `check_mesh(target)`** — non-manifold edges, self-intersections (BVH self-overlap minus shared-vert adjacency), zero-area faces, thinnest wall (inward ray "pinch test"). **Deviation from the original note:** Blender 5.1 does *not* bundle the 3D-Print Toolbox (it moved to the extensions platform in 4.2+ and isn't installed), so the metrics are computed directly with bmesh+BVH — no add-on dependency, more robust.
- **P7 — `trace_profile(target, axis, sections)`** — per-section radius + centre drift, plus a feature narrative (rise / taper / flat / crease / bulge with mm-over-trend). Object-mode, evaluated geometry. Needs ≥3 populated sections (cones with only base+apex verts are correctly rejected).
- **P8 — `check_symmetry`** now dual-level + server-exposed. Single mesh → mesh-level BVH mirror-deviation (max/mean mm + worst region); multiple/collection → the existing object-pairing logic. Defaults: 0.5mm mesh, 10mm object.
- **P9 — `check_framing(targets?, camera?)`** — frame coverage %, clipped edges (+ overflow %), behind-camera, and % occluded by other objects (scene ray casts from the camera). Pure matrix math + raycasts; the deterministic answer to "is it still cropped?".
- **P10 — `check_resting(targets?)`** — support (floor or object below), contact-point count, float/sink mm, and whether the COM sits over the contact footprint (else tip direction).
- **P11 — `diff_since(checkpoint?)`** — narrates added/deleted and per-object moved(mm)/rotated(deg)/scaled/deformed(max mm + where). Backed by a cheap per-op geometry snapshot in `state.log_operation` (loc/rot/scale + a capped *local* vertex sample, so rigid motion and real deformation are told apart). Defaults to the first recorded op.
- **P12 — `audit_asset(group, tri_budget)`** — missing material slots, tri counts (with on-screen coverage % when a camera exists, to flag overbuilt parts), unapplied scale/rotation, loose verts.


- **Live-session undo (E1-residual)** — `bpy.ops.ed.undo` was a no-op in the live socket→timer context. Root cause: `temp_override(window=wins[0])` REPLACES the context with only the window, dropping the screen/area the global-undo operator resolves against, so it ran as a silent no-op. (Headless passed because with no windows it took the bare `bpy.ops.ed.undo()` path.) Fix: `state.ui_override()` builds a full VIEW_3D context (window + screen + area + region), used by both `_step_op` (history.py) and `push_undo_step` (state.py); returns None in headless so that path is unchanged. Verified live: `undo(2)` / `redo(2)` actually revert/replay with `✓ scene verified against history snapshot` and no POST-UNDO MISMATCH. Headless e2e still green (no regression).
- **`new_scene(empty=False)`** — File → New → General in one call. Wraps `bpy.ops.wm.read_homefile(app_template="")` (resets world / color-management / render settings with it), clears the history bookkeeping, and re-registers the persistent queue timer defensively. `empty=True` additionally wipes the startup cube/camera/light for a bare modelling slate. The daemon socket thread + `persistent=True` timer both survive the reload, so no full re-arm was needed. Replaces the `open_design("_empty_general")` workaround. Verified live + e2e.

- **E4** — `boolean(target, cutter, op, solver, apply, hide_cutter)` MCP wrapper. Keyholes, mortises, split-lid chests, half-barrels.
- **E5** — `band_around(name, targets, axis, at, width, thickness)`: a strap/hoop/belt following the convex-hull silhouette of the combined targets (bridges gaps between parts).
- **E6** — `set_material(hex="#RRGGBB")`: sRGB → scene-linear so reference colors render true.
- **E7** — `orbit_viewport(auto_frame=True)`: aim at the selection/scene bbox and pull back to fit — one-call three-quarter hero shot.
- **E8** — `taper_end` warns when the extreme ring is a bevel sliver (< 2% of the axis extent) and points at `taper_section`.
- **E9** — primitive `rot_*` docstrings corrected: placement resolves against the post-rotation bounding box.
- **E10** — `set_color_management(view_transform, look, exposure, gamma)`; current values in `get_blender_status` under `render:`. `set_toon_material` recommends `Standard`.
- **E11** — `set_render_quality(raytracing, ao, shadows, samples)` toggles the Eevee features off by default (metals reflect instead of looking plastic).
- **duplicate_mirrored** — bake a static mirrored copy across a world axis (normals recalculated, transform applied).
- **Render to file** — `render_to_file(filepath, resolution, samples, engine, format, transparent)`; per-call `timeout` threaded through the socket protocol so long renders aren't cut at 30s. (Synchronous — the viewport freezes during the render.)
- **Curve datablocks** — `add_curve(name, points, type, cyclic, resolution, bevel_depth)`: live Bézier/NURBS/POLY curve objects (dolly paths, bevel profiles).
- **Sculpt brushes** — semantic sculpt verbs (`sculpt_draw/inflate/grab/smooth/pinch/flatten/crease`) already shipped.
- **Armature + rigging (Tier C beachhead)** — `create_armature(name, bones)` builds a skeleton from named head/tail joints + parenting; `auto_weight(mesh, armature)` binds with automatic weights (warns if weighting comes back empty); `pose_bone(armature, bone, rot)` articulates a joint. End-to-end deform verified.

---

# Long-term (character quality finish line)

- Rigify control-rig generation (the generic armature layer is in; this adds IK/FK controls on top)
- Multires + dyntopo wrappers
- Retopology — auto-retopo or guided
- UV unwrap with seam control
- Material node graph beyond Principled BSDF
- Hair card system
- Face topology: eyes/nose/mouth loops with subsurf-correct flow
- Camera path animation (Follow Path constraint + keyframed eval over `add_curve` paths)

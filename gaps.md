# MCP gaps

_No open gaps._ (P1–P12 shipped — see Recently closed.)

## Tactile introspection — the design principle

The guiding principle for P4–P12, kept here because it governs all future
introspection work: the agent's vision can *judge* but cannot *measure*. These
tools convert geometry into short semantic verdicts in scene vocabulary (object
names, mm/deg deltas, frame %) — never coordinate dumps, which the agent cannot
reason over. Region words ("top-left-front") locate things without leaking
coordinates. BVHTree makes the proximity queries milliseconds-cheap at hobby poly counts.

---

# Recently closed

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

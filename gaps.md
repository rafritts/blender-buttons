# MCP gaps

- **P1 — no radial array primitive.** Placing 12 hour markers and 17 chain links on the pocket-watch build required computing every sin/cos position + tangent rotation by hand outside Blender. Blender's native idiom is an Array modifier around an empty (or dupli-rotate about the 3D cursor). Want: `array_radial(source, count, center, axis, start_angle, end_angle, align_to_tangent)` — circular/arc duplication around a point, optionally orienting each copy along the tangent. Covers clock markers, bolt circles, chain links on an arc, spokes, petals, gear teeth.
- **P2 — `rotate_object` has no pivot override.** It rotates around each object's own origin only, so anything that must pivot around a shared point (clock hands around the dial center, a door around its hinge) has to be created pre-rotated with the world position computed by hand. Want: optional `pivot=[x,y,z]` (or `pivot="<object>"`) on `rotate_object`. Same root cause as the known group-rotate disassembly gap.
- **P3 — coplanar-face z-fighting is invisible until a render.** The watch caseband's solid top cap was exactly coplanar with the dial's top face; viewport + renders showed brown triangular mottling on the dial that looked exactly like a material/normal bug, and it cost three diagnostic Cycles renders + a lift-the-crystal experiment to isolate. Want: `find_coplanar_overlaps(targets?, epsilon=1e-4)` — report pairs of faces from different objects that are coplanar and XY-overlapping, so an agent can lint the scene before rendering.

## Tactile introspection ("braille for the agent")

Design principle for all of these: the agent's vision can *judge* but cannot *measure*. These tools convert geometry into short semantic verdicts in scene vocabulary (object names, mm deltas) — never coordinate dumps, which the agent cannot reason over. Support zoom levels (scene → object → region) so a coarse answer is one line and detail is opt-in. BVHTree makes all of the proximity queries milliseconds-cheap at hobby poly counts.

- **P4 — `check_contacts(targets?)`** — per part: `connected` (surfaces touch/overlap), `floating` (nearest neighbor + gap in mm), `penetrating` (depth). E.g. `"fob_bar: floating — nearest link_16, gap 19mm"`. Reports facts, doesn't judge: interpenetration is *correct* for chain links and sunk markers. The pocket-watch fob bar drifted 14cm from dead-reckoned coordinates and three other gaps were eyeballed from screenshots; this is one call each.
- **P5 — `validate_scene()` + lint-on-write** — pre-render lint: coplanar overlapping faces across objects (P3's z-fight), inverted normals, degenerate faces, objects below the floor plane. Compiler-style output: `"PASS"` or one line per finding. Higher-leverage variant: the placement resolver already holds every bbox at `add_*` time — append `⚠ top face coplanar with caseband top (Δz=0.0)` to the status block so the lint runs at authoring time, zero extra calls.
- **P6 — wrap Blender's bundled 3D-Print Toolbox as the analysis engine** — `bpy.ops.mesh.print3d_check_all` (enable addon programmatically) already computes: non-manifold edges, intersecting faces, zero-area faces/edges, thin walls (thickness probe), distorted faces, sharp edges, overhangs. Harvest its results into a semantic report instead of reimplementing. Thickness is the "pinch test" — directly useful before booleans and for game-asset shell soundness.
- **P7 — `trace_profile(target, axis|path)`** — run a fingertip along a line: sample a cross-section sweep and return a *feature narrative*, not points: `"smooth rise 0–38%, sharp crease at 42% (concave 78°), bulge apex 60% (+12mm over trend), flat 70–100%"`. Pairs with `get_rings`/`get_mesh_profile` (the calipers) by adding per-section verdicts: center drift, radius, roundness. This is how a blind sculptor reads form — curvature sequence, not position.
- **P8 — `check_symmetry(target, axis, epsilon)`** — mirror the mesh across the axis and report max/mean deviation and *where*: `"asymmetric: +X shoulder region bulges 8mm beyond mirrored −X"`. Cheap with BVH nearest-point queries. Prerequisite for character work — symmetry is the first thing human eyes catch and the agent's screenshots reliably miss.

---

# Recently closed

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

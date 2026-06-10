# MCP gaps

## Render to file

`bpy.ops.render.render(write_still=True)` blocks the main thread for the full render duration. Our socket handler has `result_event.wait(timeout=30)` — anything > 30s silently times out. Needs async dispatch (fire-and-forget + a poll tool) or a per-call timeout override.

## Curve objects (live datablocks)

`spline_tube` covers interpolating curves swept as mesh in one call. What's unbuilt: Bézier/NURBS curve datablocks as live scene objects (camera dolly paths, particle distribution controls).

## Live-session undo is a no-op (E1-residual)

`bpy.ops.ed.undo` does nothing in the live socket→timer context even with `temp_override(window=...)`. The headless e2e passes because it pushes undo through a different path. Needs investigation in a live session specifically. Current state: undo is fail-loud (reports POST-UNDO MISMATCH instead of silently destroying the scene), but it doesn't actually revert. Practical workaround: `save_design` / `open_design`.

## `band_around` (E5)

Gold straps wrapping a composite silhouette (body + lid) had to be hand-assembled from mismatched parts. `band_around(targets, axis, at, width, thickness)` — extract combined cross-section silhouette at the given axis position, offset outward, sweep wide. Covers chest straps, barrel hoops, belts, pipe clamps. **File:** new module. Effort: medium (silhouette extraction is the design work).

---

# Recently closed

- **E4** — `boolean(target, cutter, op, solver, apply, hide_cutter)` MCP wrapper now exposes the existing extension handler. Covers keyholes, mortises, split-lid chests, half-barrels.
- **E6** — `set_material(hex="#RRGGBB")` converts sRGB → scene-linear so reference colors render true instead of pale.
- **E7** — `orbit_viewport(auto_frame=True)` aims at the selection/scene bbox center and pulls back to fit — a one-call three-quarter hero shot.
- **E8** — `taper_end` warns when the extreme ring is a bevel sliver (< 2% of the axis extent from its neighbor) and points at `taper_section`.
- **E9** — primitive `rot_*` docstrings corrected: placement resolves against the post-rotation bounding box.
- **E10** — `set_color_management(view_transform, look, exposure, gamma)`; current values surfaced in `get_blender_status` under `render:`. `set_toon_material` now recommends `Standard`.
- **E11** — `set_render_quality(raytracing, ao, shadows, samples)` toggles the Eevee features that are off by default (metals reflect instead of looking plastic).
- **duplicate_mirrored** — bake a static mirrored copy across a world axis (normals recalculated, transform applied).
- **Sculpt brushes** — semantic sculpt verbs (`sculpt_draw/inflate/grab/smooth/pinch/flatten/crease`) already shipped.

---

# Long-term (character quality finish line)

- Armature creation + auto-weight (rigify target)
- Pose mode — `pose_bone(name, rot=[x,y,z])`
- Multires + dyntopo wrappers
- Retopology — auto-retopo or guided
- UV unwrap with seam control
- Material node graph beyond Principled BSDF
- Hair card system
- Face topology: eyes/nose/mouth loops with subsurf-correct flow
- Render to file (see above)

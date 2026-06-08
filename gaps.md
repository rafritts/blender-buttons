# MCP gaps surfaced by the donut tutorial

A live attempt at the Blender Guru donut tutorial via the MCP server.
Each entry: what the tutorial calls for, the closest tool we have, and what's missing.

## 1. Organic deformation — IMPLEMENTED

Two complementary tools:

- `jitter_vertices(amount, axis=NORMAL|X|Y|Z|XYZ, seed, only_positive)` —
  random per-vertex displacement. Covers "lumpy dough".
- `proportional_move(x, y, z, radius, falloff=SMOOTH|LINEAR|SPHERE|SHARP|ROOT|CONSTANT)` —
  move selected verts with a falloff that drags nearby verts along. The
  donut-tutorial proportional-editing equivalent — gives bulbous icing drips
  when applied to sparse boundary handles.

## 2. Sculpt-mode brushes

**Tutorial step:** alternative path to organic deform — use Sculpt mode with Grab/Inflate/Smooth brushes.

**What we have:** `set_mode SCULPT` enters the mode; no brush dispatch.

**Why deferred:** sculpt brushes work on screen-space strokes — they take a list of (x, y, pressure) viewport samples. Driving them from MCP means either (a) scripting `bpy.ops.sculpt.brush_stroke` with a synthesized stroke list (works but coordinate space is gnarly — viewport vs. world) or (b) skipping brushes entirely and exposing direct mesh deformations like "inflate this vertex set by N along normals". (b) is the saner MCP shape but it's a real design exercise.

## 3. Delete in edit mode (verts / edges / faces) — IMPLEMENTED

`delete_geometry(mode: VERT | EDGE | FACE | ONLY_FACE | EDGE_FACE)` —
`extension/editmode.py:delete_geometry`, MCP wrapper in `server/main.py:delete_geometry`.

## 4. Separate by selection (P key) — IMPLEMENTED

`separate_selection(new_name?)` — `extension/editmode.py:separate_selection`,
MCP wrapper in `server/main.py:separate_selection`. Returns the new object's name.

## 5. Shrinkwrap modifier — IMPLEMENTED

`add_modifier(type='SHRINKWRAP', target=..., offset=..., wrap_method=...)` —
extended in `extension/finishes.py:add_modifier`. `wrap_method` defaults to
`NEAREST_SURFACEPOINT`; pass `target` (object to wrap onto), optional `offset` (skin distance).

## 6. Sprinkles / surface scatter — IMPLEMENTED

`scatter_on_surface(target, source, count, scale_min, scale_max, align_normal,
rotate_z, parent_to_target, seed, name_prefix)` — new module
`extension/scatter.py`, MCP wrapper in `server/main.py:scatter_on_surface`.

Area-weighted triangle sampling on the target's *evaluated* mesh (so sprinkles
land on the visible post-subsurf/shrinkwrap surface). All instances share the
source's mesh data so memory stays cheap. Capped at 5000 per call.

**Small remaining quirks** (left as polish, not gaps):
- Source object's origin must be set so the source sits "on top" of its base — otherwise instances get half-embedded in the target surface. We don't have an origin-set tool yet (`bpy.ops.object.origin_set`).
- No way to filter by normal direction (e.g. "scatter only on upward-facing faces"). Sprinkles can land inside the donut hole.

## 7. Render (image output)

**Tutorial step:** F12 to render the final frame.

**What we have:** nothing. `get_viewport_screenshot` is a viewport grab, not a render.

**Why deferred:** `bpy.ops.render.render(write_still=True)` blocks the main thread for the full render duration. Our socket handler has `result_event.wait(timeout=30)` — anything > 30s silently times out and leaves Blender mid-render. Needs either async dispatch (fire-and-forget + a poll tool for "is the render done?") or a per-call timeout override. Same shape would help any other long-running op (heavy remesh, heavy subsurf bake, etc.).

## 8. Viewport shading mode (see your materials) — IMPLEMENTED

`set_viewport_shading(mode: WIREFRAME | SOLID | MATERIAL | RENDERED)` —
`extension/viewport.py:set_viewport_shading`, MCP wrapper in
`server/main.py:set_viewport_shading`. Call before `get_viewport_screenshot`
to see materials/lighting in the captured image.

## 9. Curve objects (Bézier / NURBS)

**Tutorial step:** Andrew uses a Bézier circle as a particle distribution control / for camera dolly paths.

**What we have:** nothing. All primitives are meshes.

**Why deferred:** curves are their own datablock type with control points, handles, bevel objects, taper objects. A first-class `add_bezier_circle` / `add_bezier_path` is doable but it's a new module (`curves.py`), not a one-tool addition.

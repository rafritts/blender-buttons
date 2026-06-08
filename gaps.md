# MCP gaps surfaced by the donut tutorial

A live attempt at the Blender Guru donut tutorial via the MCP server.
Each entry: what the tutorial calls for, the closest tool we have, and what's missing.

## 1. Proportional editing on transforms

**Tutorial step:** sculpt the torus into an organic, slightly-deformed donut shape — push a vertex and have the surrounding area follow with a falloff.

**What we have:** `move_vertices` and `scale_vertices` (bmesh-based), `grow_selection`. Neither honors a falloff.

**Why deferred:** `bpy.ops.transform.translate(..., use_proportional_edit=True, proportional_size=R)` only works in an operator context driven from `bpy.ops`. Our bmesh path bypasses it. Implementing the falloff ourselves means picking a curve (smooth/sphere/root/sharp/linear/constant/random), computing per-vertex distance to each selected vertex, and weighting the translation. Doable, but a real design decision: do we want falloff per-handle (each selected vert pulls its neighborhood) or per-selection-set (a centroid)? Blender does per-handle.

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

## 6. Particle systems / hair particles

**Tutorial step:** sprinkles. Distribute thousands of small instanced meshes across the icing's surface with random rotation.

**What we have:** `array_at_corners` (4 instances at bbox corners), `array_along` (linear array between two points). Nothing surface-based.

**Why deferred:** this is the "scatter_on_surface" tool that was already discussed. Real design questions: instance-vs-real-mesh, RNG seed semantics, alignment (align-to-normal vs. random), density (count vs. area), per-instance scale jitter. A worthwhile tool but the surface-of-a-thing is the right shape, not a hack-shaped `scatter`.

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

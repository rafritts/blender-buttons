# blender-buttons

An MCP server that lets an LLM drive Blender like a human would — selecting objects, editing meshes, taking screenshots, and reading scene state.

## Architecture

```
Agent / LLM harness
      │  MCP over stdio (JSON-RPC)
      ▼
server/main.py          ← FastMCP server, one @mcp.tool() per capability
      │  TCP socket, localhost:8765, newline-delimited JSON
      ▼
extension/__init__.py   ← Blender addon, runs inside Blender's Python interpreter
      │  bpy / bmesh
      ▼
Blender 4.2+
```

The MCP server is a thin wrapper. All logic runs inside Blender on the main thread via a queue; the addon enforces this so Blender's API is never called from a background thread.

## Connecting

**stdio transport** (standard MCP):

```json
{
  "mcpServers": {
    "blender-buttons": {
      "command": "/path/to/repo/.venv/bin/python",
      "args": ["/path/to/repo/server/main.py"]
    }
  }
}
```

Works in: Claude Code (`.mcp.json`), Claude Desktop, Cursor, Windsurf, or any MCP-compatible harness.

**Prerequisites:**
1. Blender 4.2+ running with the addon installed (`blender_buttons.zip`)
2. Addon server started: Properties panel → Scene → Blender Buttons → Start Server
3. Server listens on `localhost:8765`

**Install the addon:**
```bash
cd extension && zip ../blender_buttons.zip __init__.py blender_manifest.toml
```
Then install the zip via Edit → Preferences → Add-ons → Install from Disk.

## Auto-status

Every state-modifying tool appends a `── blender status ──` block to its return string. You do not need to call `get_blender_status` manually after every operation — it fires automatically. The block contains:

```
── blender status ──────────────────────────────
  mode:        OBJECT | EDIT | SCULPT
  active:      <object name> (<type>)
  selected:    [<names>]
  z_range:     [min_z, max_z]  ← world space bounding box Z extent
  dims:        [x, y, z]       ← world space dimensions
  rot_deg:     [rx, ry, rz]    ← Euler rotation in degrees
  last_action: {id, label, tool}
  ── edit ──                   ← only present in Edit Mode
  component:   VERT | EDGE | FACE
  selected:    {verts, edges, faces}  /  total: {verts, edges, faces}
  sel_z:       [min_z, max_z]  ← world space Z range of selected verts
────────────────────────────────────────────────
```

Read-only / image tools (`get_blender_status`, `get_viewport_screenshot`, `get_viewport_collage`, `get_scene_tree`, `get_history`) do not append a status block.

## Tool Reference

### Scene inspection

| Tool | Description |
|------|-------------|
| `get_scene_tree()` | All objects in the scene as an ASCII tree, with active/selected markers |
| `get_blender_status()` | Full context snapshot: mode, active object, dims, Z range, edit-mode selection counts |
| `get_object_info()` | Active object: location, scale, rotation, world bounding box, vert/edge/face counts |
| `get_mesh_profile(axis="Z")` | Slice the active mesh into rings along an axis; reports min/max/width at each ring. Use before editing to know actual geometry. |
| `get_history()` | Full operation log with IDs. Use with `undo_to`. |

### Viewport

| Tool | Description |
|------|-------------|
| `get_viewport_screenshot(width=960, height=540)` | Returns `Image`. Captures the 3D viewport as-is. A "+Z up" label is baked into the bottom-left corner. |
| `get_viewport_collage(target="ALL", zoom=1.0)` | Returns `[Image, text]`. 6-panel grid: FRONT \| RIGHT \| TOP (row 1), BACK \| LEFT \| PERSP (row 2). Each panel auto-frames on `target` (`ALL` / `SELECTED` / object name) AND is baked with a corner label naming the visible plane (e.g. `FRONT X-Z plane (+Y into screen)`). Text line reports the framed bbox. |
| `set_viewport_angle(angle)` | `FRONT \| BACK \| LEFT \| RIGHT \| TOP \| BOTTOM \| CAMERA` |
| `orbit_viewport(azimuth, elevation, distance, target_x, target_y, target_z)` | Position the viewport perspective camera by orbit angles. Prefer this over `set_viewport_angle(CAMERA)` — it avoids the camera border crop. azimuth=0 is front, positive = right. |
| `frame_scene()` | Fit all objects in the viewport |
| `zoom_to_selected()` | Zoom viewport to the active object |

### Object operations (Object Mode)

| Tool | Description |
|------|-------------|
| `add_cube(name, size, x, y, z, rot_x, rot_y, rot_z)` | Add a cube. `size` = edge length (default 2). |
| `add_plane(name, size, x, y, z, rot_x, rot_y, rot_z)` | Add a single-quad plane. |
| `add_cylinder(name, vertices, radius, depth, cap_fill, x, y, z, rot_x, rot_y, rot_z)` | Cylinder aligned to Z. `vertices` = circumference resolution. `cap_fill`: `NOTHING \| NGON \| TRIFAN`. |
| `add_sphere(name, segments, rings, radius, x, y, z, rot_x, rot_y, rot_z)` | UV sphere. `segments`/`rings` control resolution. |
| `add_cone(name, vertices, radius1, radius2, depth, cap_fill, x, y, z, rot_x, rot_y, rot_z)` | Cone or truncated cone. `radius1`=base, `radius2`=top (0 = point). |
| `select_object(name)` | Select by name and make active |
| `rename_object(old_name, new_name)` | Rename object and its mesh data block |
| `delete_object(name, label)` | Delete by name |
| `move_object(x, y, z, label)` | Relative offset in world units |
| `rotate_object(angle, axis, label)` | Degrees, axis: `X \| Y \| Z` |
| `scale_object(x, y, z, label)` | Multipliers (1.0 = no change, 2.0 = double) |
| `snap_to(target, side, source_side, offset, label)` | Align active object's bbox face to a face of `target`. `side`: which face of target (`X_MIN`…`Z_MAX`). `source_side`: opposite face by default (`AUTO`), or explicit / `CENTER`. `offset` shifts along the same axis after alignment. Use for stacking and flush placement — no coordinate arithmetic. |
| `snap_to_grid(size, axes, label)` | Round the active object's origin to multiples of `size` on the chosen axes (e.g. `"XZ"`). Touches only the pivot — dims/rotation/geometry untouched. Opt-in per call. |
| `duplicate_object(name, new_name)` | Duplicate in place. `new_name` optional — if omitted Blender appends `.001`. Duplicate becomes the active object. |
| `join_objects(names)` | Join a list of objects into one. First name in the list is the surviving object. Minimum 2 names. |
| `apply_modifiers(name)` | Apply all modifiers on the named object (or active object if omitted), collapsing them into the base mesh. Required before export or boolean operations. |
| `set_camera_position(x, y, z, target_x, target_y, target_z)` | Move the scene camera |
| `add_modifier(type, name, levels, width, segments, label)` | type: `SUBSURF \| BEVEL \| SOLIDIFY \| MIRROR \| ARRAY \| SCREW` |

### Edit Mode operations

Must be in Edit Mode (`set_mode("EDIT")`) before calling these.

**Prefer ring-based addressing for shaping work.** LLMs are bad at picking the right world-space coordinate for "the second ring from the top." Address the mesh by topology (ring index) instead, using the macros below. Drop down to raw vertex ops only when you need something the macros don't cover.

#### Ring macros (preferred)

A "ring" is a set of vertices that share the same world-space coordinate on the given axis. After `loop_cut(Z, cuts=3)` on a cube, the blade has 5 rings along Z (index 0 = bottom, 4 = top). Operate on rings by index, not by coordinate.

| Tool | Description |
|------|-------------|
| `loop_cut(axis, cuts, label)` | Subdivide edges running along the given axis. Uses world-space edge direction, so works correctly on scaled/tapered objects. |
| `get_rings(axis)` | List all rings of the active mesh along an axis: index, world-space position, vert count. Call this to know what indices are available. |
| `select_ring(axis, index, action)` | Select all vertices belonging to a ring. `index` accepts negatives (-1 = last). `action`: `SELECT` (replace) \| `ADD` \| `DESELECT`. |
| `taper_end(axis, end, label)` | Collapse the extreme ring on an axis to a point. `end`: `MAX` \| `MIN`. Faster than select_ring + scale_vertices(x=0,y=0). |
| `taper_section(axis, from_ring, to_ring, x_start, x_end, y_start, y_end, label)` | Linearly interpolate scale across a span of rings. Each ring scales around its own centroid in the two non-axis directions. Use for tapers, bulges, pinches. |

#### Selection & topology

| Tool | Description |
|------|-------------|
| `set_mode(mode)` | `OBJECT \| EDIT \| SCULPT` |
| `set_component_mode(mode)` | Switch mesh select component type: `VERT \| EDGE \| FACE`. Call before selection operations that depend on component type. |
| `select_all(action)` | `SELECT \| DESELECT \| INVERT` |
| `grow_selection(direction, steps)` | Expand or contract the current selection by topology adjacency. `direction`: `GROW \| SHRINK`. `steps`: number of iterations (default 1). |
| `get_current_selection()` | Returns vert count, world-space centroid, and world-space bounding box of the current selection. Use before moving/scaling to verify what's actually selected. |

#### Raw vertex ops (escape hatch)

Use when ring macros don't fit — non-axis-aligned topology, arbitrary band selections, fine manual nudging.

| Tool | Description |
|------|-------------|
| `select_by_axis(axis, factor, comparison, action)` | Select/deselect verts by world-space position. `factor` maps 0.0→min extent, 1.0→max extent. |
| `select_between(axis, lo, hi, action)` | Select verts whose position on `axis` falls between `lo` and `hi` (both 0.0–1.0 factors). |
| `move_vertices(x, y, z, label)` | Move selected verts. x/y/z are fractions of the object's world-space dimension on that axis. |
| `scale_vertices(x, y, z, pivot, label)` | Scale selected verts. `pivot`: `SELECTION` (around centroid) \| `ORIGIN` (around object origin at local 0,0,0). |
| `extrude(x, y, z, label)` | Extrude and translate. x/y/z are fractions of object dimension. |
| `bevel(factor, segments, affect, label)` | `affect`: `EDGES \| VERTICES`. `factor` is a fraction of the object's smallest dimension. |

### History / undo

| Tool | Description |
|------|-------------|
| `get_history()` | List all logged operations with 8-char IDs |
| `undo(steps=1)` | Undo last N operations, syncs the history log |
| `undo_to(id)` | Undo everything after the named operation ID |

History is reset when Blender restarts. Each successful mutating tool pushes a checkpoint onto Blender's native undo stack (including bmesh operations like `loop_cut`, `taper_section`, `taper_end`, `move_vertices`, `scale_vertices` — these used to fall outside the undo stack), so `undo` / `undo_to` revert them cleanly. Use `get_blender_status` after undoing to verify the active object and mode.

## Key patterns

**Ring-based shaping** — preferred path for axis-aligned editing:
```
# 1. Add edge loops along Z (5 rings result: index 0..4)
loop_cut(axis=Z, cuts=3)

# 2. See what's there
get_rings(axis=Z)
# → 5 rings along Z:  [0] pos=-1.00 verts=4   [1] pos=-0.50 verts=4  ...

# 3. Collapse the top ring to a point — single call
taper_end(axis=Z, end=MAX)

# 4. Linear taper across rings 2..4
taper_section(axis=Z, from_ring=2, to_ring=4, x_end=0.4, y_end=0.4)

# 5. Address one specific ring manually
select_ring(axis=Z, index=-2)              # second from top
scale_vertices(x=0.85, y=0.85)
```

**Band selection (raw)** — when ring indexing doesn't fit:
```
select_between(axis=Z, lo=0.49, hi=0.51)
scale_vertices(x=0.5, y=0.5, pivot=SELECTION)
```

**Stacking objects with `snap_to`** — never compute coordinates by hand:
```
add_cube(name="Crossguard", z=1.42); scale_object(x=0.32, y=0.045, z=0.045)
add_cylinder(name="Grip", radius=0.028, depth=0.2)
snap_to(target="Crossguard", side="Z_MAX")            # grip-bottom flush with crossguard-top
add_cylinder(name="Pommel", radius=0.06, depth=0.04, rot_x=90)
snap_to(target="Grip", side="Z_MAX", offset=-0.04)    # pommel sinks 0.04 into grip
```
`snap_to` aligns one bbox face to another and only translates along that axis — other axes are preserved. Use `offset` for overlap or gap.

**Grid layout with `snap_to_grid`** — round positions to clean numbers:
```
add_cube(name="WallA", x=2.13, y=0.0, z=0.5)
snap_to_grid(size=0.5, axes="XY")                     # WallA snaps to nearest 0.5 multiple in X/Y
```
Useful for modular builds (walls, blocks, gridded layouts). Skip it for organic shapes.

**`taper_end` reports neighbors** — the result includes nearby mesh objects and their distance to the collapsed point. If you collapsed the wrong end, the report will surface that ("collapsed at z=1.4, nearby: Crossguard@0.02u") before you commit further work.

**Vertex move units** — `move_vertices` takes fractions of the object's world dimensions, not absolute units. `z=0.1` moves 10% of the object's total height. The returned `delta_world` is the actual world-space translation applied.

**loop_cut on tapered meshes** — cuts are placed at edge midpoints, not at uniform Z intervals. On a tapered cone/blade, new rings will already inherit the taper proportionally. To push rings to a specific width, select the ring after cutting and use `scale_vertices`.

**Screenshots** — `get_viewport_screenshot` captures whatever the viewport is showing right now. Call `orbit_viewport` or `set_viewport_angle` first to frame the shot you want. Do not use `set_viewport_angle(CAMERA)` for inspection — it shows the camera border crop and the camera object wireframe.

**Object names** — every `add_*` primitive tool requires a `name` argument and sets it immediately on the object and its mesh data. Blender may append `.001` if the name already exists; the actual name assigned is returned. Use `get_scene_tree` to verify.

**Edit mode context errors** — some Object Mode operators fail if called while in Edit Mode. Always call `set_mode("OBJECT")` before `delete_object`, `add_cube`/`add_cylinder`/etc., or `select_object`.

## File layout

```
server/main.py              MCP server (FastMCP, stdio transport)
extension/__init__.py       Blender addon (TCP socket, bmesh operations)
extension/blender_manifest.toml
blender_buttons.zip         Built addon — install this in Blender
```

## Rebuilding the addon

```bash
cd extension && zip ../blender_buttons.zip __init__.py blender_manifest.toml
```

After installing the updated zip in Blender: disable → re-enable the addon, then click Start Server.

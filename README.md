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
| `get_viewport_screenshot(width=960, height=540)` | Returns `Image`. Captures the 3D viewport as-is. |
| `get_viewport_collage(zoom=1.0)` | Returns `Image`. 6-panel grid: FRONT \| RIGHT \| TOP (row 1), BACK \| LEFT \| PERSP (row 2). |
| `set_viewport_angle(angle)` | `FRONT \| BACK \| LEFT \| RIGHT \| TOP \| BOTTOM \| CAMERA` |
| `orbit_viewport(azimuth, elevation, distance, target_x, target_y, target_z)` | Position the viewport perspective camera by orbit angles. Prefer this over `set_viewport_angle(CAMERA)` — it avoids the camera border crop. azimuth=0 is front, positive = right. |
| `frame_scene()` | Fit all objects in the viewport |
| `zoom_to_selected()` | Zoom viewport to the active object |

### Object operations (Object Mode)

| Tool | Description |
|------|-------------|
| `add_primitive(type, name, x, y, z, label)` | Add a mesh primitive. `name` is **required** — Blender's default names ("Cube", "Cylinder") are blocked. type: `CUBE \| SPHERE \| CYLINDER \| PLANE \| CONE` |
| `select_object(name)` | Select by name and make active |
| `rename_object(old_name, new_name)` | Rename object and its mesh data block |
| `delete_object(name, label)` | Delete by name |
| `move_object(x, y, z, label)` | Relative offset in world units |
| `rotate_object(angle, axis, label)` | Degrees, axis: `X \| Y \| Z` |
| `scale_object(x, y, z, label)` | Multipliers (1.0 = no change, 2.0 = double) |
| `set_camera_position(x, y, z, target_x, target_y, target_z)` | Move the scene camera |
| `add_modifier(type, name, levels, width, segments, label)` | type: `SUBSURF \| BEVEL \| SOLIDIFY \| MIRROR \| ARRAY \| SCREW` |

### Edit Mode operations

Must be in Edit Mode (`set_mode("EDIT")`) before calling these.

| Tool | Description |
|------|-------------|
| `set_mode(mode)` | `OBJECT \| EDIT \| SCULPT` |
| `select_all(action)` | `SELECT \| DESELECT \| INVERT` |
| `select_by_axis(axis, factor, comparison, action)` | Select/deselect verts by world-space position. `factor` maps 0.0→min extent, 1.0→max extent. `comparison`: `GREATER \| LESS`. `action`: `SELECT \| DESELECT`. Returns the actual world-space threshold used. |
| `loop_cut(axis, cuts, label)` | Subdivide edges running along the given axis. Uses world-space edge direction, so works correctly on scaled/tapered objects. |
| `move_vertices(x, y, z, label)` | Move selected verts. x/y/z are fractions of the object's world-space dimension on that axis. Handles object scale correctly. |
| `scale_vertices(x, y, z, pivot, label)` | Scale selected verts. `pivot`: `SELECTION` (around centroid) \| `ORIGIN` (around object origin at local 0,0,0). |
| `extrude(x, y, z, label)` | Extrude and translate. x/y/z are fractions of object dimension. |
| `bevel(factor, segments, affect, label)` | `affect`: `EDGES \| VERTICES`. `factor` is a fraction of the object's smallest dimension. |

### History / undo

| Tool | Description |
|------|-------------|
| `get_history()` | List all logged operations with 8-char IDs |
| `undo(steps=1)` | Undo last N operations, syncs the history log |
| `undo_to(id)` | Undo everything after the named operation ID |

History is reset when Blender restarts. The history log tracks only operations that went through this MCP server — Blender's internal undo stack may have additional entries (mode switches, etc.), which can cause `undo(N)` to overshoot. Use `get_blender_status` after undoing to verify the active object and mode.

## Key patterns

**Band selection** — select a ring of vertices at a specific height:
```
select_all(SELECT)
select_by_axis(Z, factor=0.49, comparison=LESS,    action=DESELECT)  # drop below
select_by_axis(Z, factor=0.51, comparison=GREATER, action=DESELECT)  # drop above
# now only the ring at Z=50% is selected
scale_vertices(x=0.5, y=0.5, pivot=SELECTION)
```

**Vertex move units** — `move_vertices` takes fractions of the object's world dimensions, not absolute units. `z=0.1` moves 10% of the object's total height. The returned `delta_world` is the actual world-space translation applied.

**loop_cut on tapered meshes** — cuts are placed at edge midpoints, not at uniform Z intervals. On a tapered cone/blade, new rings will already inherit the taper proportionally. To push rings to a specific width, select the ring after cutting and use `scale_vertices`.

**Screenshots** — `get_viewport_screenshot` captures whatever the viewport is showing right now. Call `orbit_viewport` or `set_viewport_angle` first to frame the shot you want. Do not use `set_viewport_angle(CAMERA)` for inspection — it shows the camera border crop and the camera object wireframe.

**Object names** — `add_primitive` requires a `name` argument and sets it immediately on the object and its mesh data. Blender may append `.001` if the name already exists; the actual name assigned is returned. Use `get_scene_tree` to verify.

**Edit mode context errors** — some Object Mode operators fail if called while in Edit Mode. Always call `set_mode("OBJECT")` before `delete_object`, `add_primitive`, or `select_object`.

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

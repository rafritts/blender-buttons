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
  dims:        [x, y, z]       ← world bbox dimensions (rotation-aware)
  bounds:      x=[..]  y=[..]  z=[..]   ← full world bbox
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
| `describe(name)` | Relational sentence about an object — what it rests on, what it's flush with, dimensions. **Prefer this over `get_object_info` for normal workflows.** |
| `get_scene_tree()` | All objects in the scene as an ASCII tree, with active/selected markers |
| `get_blender_status()` | Full context snapshot: mode, active object, dims, Z range, edit-mode selection counts |
| `get_object_info(name="")` | Coordinate dump (location, scale, rotation, world bounding box, vert/edge/face counts, material slots, modifier stack). Use when you actually need the raw numbers. |
| `get_mesh_profile(axis="Z")` | Slice the active mesh into rings along an axis; reports min/max/width at each ring. |
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

## Design principle: dimensions over coordinates

LLMs (and humans) are bad at carrying world-coordinate values across operations. So the API is built around **dimensions** (lengths, sizes) and **relational placement** (snap, on top of, between, at corners of). Raw `(x, y, z)` placement is available as a last resort but is never the default path.

The hierarchy:

1. **Dimensions** — `add_box(width=0.04, depth=0.04, height=0.45)`. The natural vocabulary.
2. **Relational placement** — `on={"at_corner": {"of": "seat", "corner": "front_left"}, "on_floor": True}`. The server computes the coordinate; you never see it.
3. **Relational verbs** — `array_at_corners`, `mirror_across`, `distribute_evenly`, `match_dimension`. One call replaces what would otherwise be a chain of coordinate math.
4. **Coordinates** — available via `nudge`, `snap_to_grid`, `raise_to`, and the edit-mode tools, but documented as the ripcord. Reach for them only when no relational framing fits.

Axis convention: **+X right, +Y back, +Z up**. "Front" of an object = its −Y side.

### Object operations (Object Mode)

#### Dimensional primitives — the way to create geometry

Every `add_*` takes exact world-space dimensions in meters plus an optional `on` placement spec. After creation, the object's scale is `[1, 1, 1]` so bevel and other width-based modifiers behave uniformly.

| Tool | Description |
|------|-------------|
| `add_box(name, width, depth, height, on=None, rot_x, rot_y, rot_z)` | Rectangular box of exact W × D × H meters. |
| `add_plane(name, width, depth, on=None, rot_x, rot_y, rot_z)` | Single-quad plane of exact W × D meters. |
| `add_cylinder(name, radius, height, on=None, vertices=32, cap_fill="NGON", rot_x, rot_y, rot_z)` | Cylinder aligned to Z. |
| `add_sphere(name, radius, on=None, segments=32, rings=16, rot_x, rot_y, rot_z)` | UV sphere of exact radius. |
| `add_cone(name, radius_bottom, height, radius_top=0.0, on=None, vertices=32, cap_fill="NGON", rot_x, rot_y, rot_z)` | Cone or truncated cone. |
| `spline_tube(name, points, radius=0.02, resolution=8, sides=4)` | Tube swept along an interpolating spline that passes THROUGH every control point (no Bezier handles). Points are `[x,y,z]` or `{"near": "obj", "offset": [dx,dy,dz]}` (anchored to an object's center, resolved once at creation). `radius` is a float or a per-point list for taper. Result is a plain capped mesh; `describe()` reports the through-points. Hair strands, cables, ribbons, branches. |

#### Placement DSL — the `on=` parameter

A dict combining one or more constraint keys:

| Key | Meaning |
|-----|---------|
| `{"on": "name"}` | New rests on top of target, centered XY |
| `{"under": "name"}` | New rests below target, centered XY |
| `{"between": ["a", "b"]}` | New is centered on midpoint of two object centers |
| `{"centered_on": "name"}` | Match XYZ centers |
| `{"at_corner": {"of": "name", "corner": "front_left"\|"front_right"\|"back_left"\|"back_right"}}` | Bottom-corner of new aligns with bottom-corner of target |
| `{"left_of": "name"}` / `right_of` / `in_front_of` / `behind` | Flush against the named side; remaining axes centered on target |
| `{"mirror_of": "name", "axis": "X"}` | Center copied from target with one axis flipped — symmetric placement |
| `{"at": [x, y, z]}` | Center at the literal world coordinate (full ripcord) |
| `{"x": 0.085}` / `{"y": ...}` / `{"z": ...}` | Override one center axis, applied after relational keys |
| `{"on_floor": True}` | Bottom of new = Z 0 (overrides Z from above keys) |
| `{"raise_to": 0.45}` | Bottom of new = Z 0.45 (literal Z value — ripcord) |
| `{"gap": 0.02}` | Spacing modifier for on/under/left_of/etc. (positive = farther apart; negative = overlap) |

Combine freely: `on={"at_corner": {"of": "seat", "corner": "front_left"}, "on_floor": True}`.
Unknown keys are rejected with an error listing the valid vocabulary — no silent ignores.

#### Relational queries — read scene state without coords

| Tool | Description |
|------|-------------|
| `describe(name)` | Relational sentence: what the object rests on, what it's flush with, its dimensions, and its material (name + Principled values). Spline tubes also report their through-points. Prefer over `get_object_info` for normal workflows. |
| `distance_between(a, b, axis="ANY")` | Center-to-center distance. `axis`: ANY \| X \| Y \| Z. |
| `gap_between(a, b)` | Empty space between bounding boxes per axis; negative = overlap. |
| `is_aligned(a, b, side="TOP", tolerance=0.001)` | True/False for face or center alignment. `side`: TOP \| BOTTOM \| LEFT \| RIGHT \| FRONT \| BACK \| CENTER_X \| CENTER_Y \| CENTER_Z. |
| `get_object_info(name="")` | Coordinate dump (location, scale, rotation, bbox). Use only when you actually need the underlying numbers. |
| `get_scene_tree()` | ASCII tree of objects and groups. |

#### Relational verbs — common multi-object operations

| Tool | Description |
|------|-------------|
| `match_dimension(target, reference, axis="Z")` | Resize `target` so its size on `axis` equals `reference`'s size. |
| `mirror_across(targets, plane="X", suffix="_mirror", replace=None)` | Duplicate parts and mirror copies across a world axis plane through origin. `replace=["_R", "_L"]` swaps the naming token (`eye_R` → `eye_L`) instead of appending the suffix. |
| `distribute_evenly(targets, between=[a, b], axis="X")` | Position parts evenly between two anchors. |
| `array_at_corners(prototype, of, standing_on_floor=True, keep_original=False, name_prefix="")` | Duplicate prototype to all 4 corners of target's footprint. Names: `<prefix>_front_left` etc. |
| `array_along(prototype, count, between=[a, b], axis="X", keep_original=False, name_prefix="")` | Duplicate prototype N times, evenly spaced between two anchors. Names: `<prefix>_1`..`_N`. |

#### Transforms

| Tool | Description |
|------|-------------|
| `nudge(targets="", right, left, up, down, back, forward)` | Relative offset in semantic directions (meters). Empty `targets` = active object. |
| `resize(targets="", width, depth, height)` | Absolute resize (any axis omitted preserves current size). Scale is baked after. Warns when a target is rotated (world-axis resize shears non-axis-aligned geometry). |
| `scale_group(targets, factor, pivot="center")` | Uniformly scale a whole assembly about a SHARED pivot, preserving relative layout. `pivot`: `center` \| `bottom_center` (keeps feet on floor) \| `origin` \| object name. What `resize` can't do: make a 12-part head assembly 8% bigger in place. |
| `rotate_object(angle, axis="Z", targets="")` | Rotate by degrees around axis. |
| `apply_transform(targets="", scale=True, rotation=False, location=False)` | Bake transforms into mesh data. |
| `snap_to(target, side, source_side="AUTO", offset=0.0)` | Move the active object so one of its bbox faces aligns with `target`'s named face. Lower-level than the placement DSL but still relational. |
| `snap_to_grid(size, axes="XYZ")` | Round the active object's origin to grid multiples. |

#### Groups (Blender collections)

| Tool | Description |
|------|-------------|
| `group(name, parts=[...])` | Create or extend a named group. Any tool that accepts `targets` can take the group name. |
| `parts_in(name)` | List objects in a group. |
| `ungroup(name)` | Remove a group; objects move back to scene root (NOT deleted). |

#### Finishes

| Tool | Description |
|------|-------------|
| `smooth_edges(targets="", width=0.002, segments=2, angle_limit=30.0)` | Round off sharp edges. Bundles BEVEL (angle-limited so coplanar edges are ignored) + shade_smooth + auto_smooth + apply. Use as the standard "make it look less blocky" verb. |
| `bend(targets, angle, axis="X", apply=True)` | Bend objects into an arc (SimpleDeform BEND, baked by default). `axis` is the axis to bend AROUND: a vertical object curls into a C in the perpendicular plane. Tapered cylinder + bend = hair lock / bent limb / rocker rail. Needs segments along the length (`loop_cut` first) to bend smoothly. |
| `add_modifier(type, name, levels, width, segments, limit_method="ANGLE", angle_limit=30.0)` | Lower-level modifier add. For BEVEL, `limit_method` and `angle_limit` are now exposed. |
| `apply_modifiers(name)` | Apply all modifiers on the named object (or active). |

#### Basics

| Tool | Description |
|------|-------------|
| `select_object(name)` | Select by name and make active. |
| `rename_object(old_name, new_name)` | Rename object and mesh data block. |
| `delete_object(name)` | Delete by name. |
| `duplicate_object(name, new_name="")` | Duplicate in place. |
| `join_objects(names=[...])` | Join into one object (minimum 2 names). |
| `set_camera_position(x, y, z, target_x, target_y, target_z)` | Move the scene camera. |

#### Persistence

Designs are saved as native `.blend` files in `~/blender-designs/`.

| Tool | Description |
|------|-------------|
| `save_design(name)` | Save the current scene to `~/blender-designs/<name>.blend`. |
| `open_design(name)` | Replace the current scene with a saved design. |
| `list_designs()` | List saved designs. |

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
| `select_rings(axis, indices, action)` | Select the union of multiple rings at once. `indices` is a list (negatives allowed). Replaces the verbose `select_ring` + `ADD` + `ADD` pattern for repeating detail. |
| `scale_rings(axis, indices, x, y, label)` | Scale each named ring around **its own centroid** in the two non-axis directions. Correct tool for bulge/pinch detail — avoids the pivot pitfalls of `scale_vertices` on multi-ring selections. |
| `taper_end(axis, end, scale, label)` | Scale the extreme ring on an axis toward its own centroid. `scale=0` (default) collapses to a point; `scale=0.5` leaves a partial taper. |
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

**Build a Mission chair — dimensions and relational verbs end-to-end:**
```
# 1. Seat (creates at origin — first piece needs an anchor)
add_box("seat", width=0.44, depth=0.40, height=0.03,
        on={"raise_to": 0.45})                                   # seat top at 0.48m

# 2. Four legs at the corners of the seat, standing on the floor
add_box("leg_proto", width=0.04, depth=0.04, height=0.45)
array_at_corners("leg_proto", of="seat", standing_on_floor=True,
                 name_prefix="leg")                              # → leg_front_left, leg_front_right, leg_back_left, leg_back_right

# 3. Back rails between the two back legs
add_box("back_rail_top", width=0.36, depth=0.04, height=0.05,
        on={"between": ["leg_back_left", "leg_back_right"], "raise_to": 0.90})
add_box("back_rail_bottom", width=0.36, depth=0.04, height=0.04,
        on={"between": ["leg_back_left", "leg_back_right"], "raise_to": 0.495})

# 4. Five slats evenly between the two rails along X
add_box("slat_proto", width=0.04, depth=0.015, height=0.365,
        on={"between": ["back_rail_top", "back_rail_bottom"]})
array_along("slat_proto", count=5,
            between=["leg_back_left", "leg_back_right"], axis="X",
            name_prefix="slat")

# 5. Stretchers across the bottom
add_box("stretcher_front", width=0.36, depth=0.025, height=0.04,
        on={"between": ["leg_front_left", "leg_front_right"], "raise_to": 0.08})
add_box("stretcher_back", width=0.36, depth=0.025, height=0.04,
        on={"between": ["leg_back_left", "leg_back_right"], "raise_to": 0.08})

# 6. Group and finish
group("chair", parts=["seat", "leg_front_left", "leg_front_right",
                       "leg_back_left", "leg_back_right",
                       "back_rail_top", "back_rail_bottom",
                       "slat_1", "slat_2", "slat_3", "slat_4", "slat_5",
                       "stretcher_front", "stretcher_back"])
smooth_edges("chair", width=0.003)                               # rounds every edge in one call
```
Zero raw `(x, y, z)` placements. Every position is expressed relative to existing parts.

**Lower-level snap with `snap_to`** — when the placement DSL doesn't fit:
```
add_box("Crossguard", width=0.32, depth=0.045, height=0.045, on={"raise_to": 1.4})
add_cylinder("Grip", radius=0.028, height=0.2)
snap_to(target="Crossguard", side="Z_MAX")                       # grip-bottom flush with crossguard-top
add_cylinder("Pommel", radius=0.06, height=0.04, rot_x=90)
snap_to(target="Grip", side="Z_MAX", offset=-0.04)               # pommel sinks 0.04 into grip
```

**Grid layout with `snap_to_grid`** — round positions to clean numbers:
```
add_box("WallA", width=0.5, depth=0.1, height=1.0, on={"raise_to": 0.0})
nudge("WallA", right=2.13)                                       # rough placement
snap_to_grid(size=0.5, axes="XY")                                # snap WallA to nearest 0.5m
```

**`taper_end` reports neighbors** — the result includes nearby mesh objects and their distance to the collapsed point. If you collapsed the wrong end, the report will surface that ("collapsed at z=1.4, nearby: Crossguard@0.02u") before you commit further work.

**Vertex move units** — `move_vertices` takes fractions of the object's world dimensions, not absolute units. `z=0.1` moves 10% of the object's total height. The returned `delta_world` is the actual world-space translation applied.

**loop_cut on tapered meshes** — cuts are placed at edge midpoints, not at uniform Z intervals. On a tapered cone/blade, new rings will already inherit the taper proportionally. To push rings to a specific width, select the ring after cutting and use `scale_vertices`.

**Screenshots** — `get_viewport_screenshot` captures whatever the viewport is showing right now. Call `orbit_viewport` or `set_viewport_angle` first to frame the shot you want. Do not use `set_viewport_angle(CAMERA)` for inspection — it shows the camera border crop and the camera object wireframe. Capture forces a depsgraph update + viewport redraw first, so material/geometry edits made since the last capture are always reflected (socket-driven edits don't generate the UI events that normally trigger redraws).

**Object names** — every `add_*` primitive tool requires a `name` argument and sets it immediately on the object and its mesh data. Blender may append `.001` if the name already exists; the actual name assigned is returned. Use `get_scene_tree` to verify.

**Edit mode context errors** — some Object Mode operators fail if called while in Edit Mode. Always call `set_mode("OBJECT")` before `delete_object`, `add_box`/`add_cylinder`/etc., or `select_object`.

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

import socket
import json
import base64
from mcp.server.fastmcp import FastMCP, Image

ADDON_HOST = "localhost"
ADDON_PORT = 8765

mcp = FastMCP("blender-buttons")


def call_blender(tool: str, params: dict = {}, label: str = "") -> dict:
    payload = json.dumps({"tool": tool, "params": params, "label": label}) + "\n"
    try:
        with socket.create_connection((ADDON_HOST, ADDON_PORT), timeout=30) as sock:
            sock.sendall(payload.encode())
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        return {"error": (
            f"Cannot reach Blender extension on {ADDON_HOST}:{ADDON_PORT} ({type(e).__name__}). "
            "Open Blender, enable the 'Blender Buttons' extension, and click 'Start Server' "
            "in the Scene properties panel."
        )}
    return json.loads(data.decode().strip())


def _status(result: dict) -> str:
    """Format the blender_status block that every tool response now carries."""
    s = result.get("blender_status")
    if not s:
        return ""
    wb = s.get("world_bounds") or {}
    lines = [
        "",
        "── blender status ──────────────────────────────",
        f"  mode:        {s['mode']}",
        f"  active:      {s['active_object']} ({s['active_type']})",
        f"  selected:    {s['selected_objects']}",
        f"  dims:        {s.get('dimensions')}     (world bbox, rotation-aware)",
        f"  bounds:      x={wb.get('x')}  y={wb.get('y')}  z={wb.get('z')}",
        f"  rot_deg:     {s.get('rotation_deg')}",
        f"  last_action: {s.get('last_action')}",
    ]
    if "edit" in s:
        e = s["edit"]
        lines += [
            f"  ── edit ──",
            f"  component:   {e['component_mode']}",
            f"  selected:    {e['selected']}  /  total: {e['total']}",
            f"  sel_z:       {e.get('selection_z_range', '—')}",
        ]
    lines.append("────────────────────────────────────────────────")
    return "\n".join(lines)


# --- Read-only tools (no status appended) ---

@mcp.tool()
def get_scene_tree() -> str:
    """List all objects in the Blender scene as a tree. Call this first to know what exists."""
    result = call_blender("get_scene_tree")
    return result.get("tree", result.get("error", "unknown error"))


@mcp.tool()
def get_viewport_screenshot(width: int = 960, height: int = 540) -> Image:
    """Capture the current 3D viewport. width/height default to 960x540 to keep context usage low."""
    result = call_blender("get_viewport_screenshot", {"width": width, "height": height})
    if "error" in result:
        raise RuntimeError(result["error"])
    return Image(data=base64.b64decode(result["image"]), format="png")


@mcp.tool()
def get_viewport_collage(target: str = "ALL", zoom: float = 1.0) -> list:
    """
    Capture 6 views in one image: FRONT | RIGHT | TOP (row 1), BACK | LEFT | PERSP (row 2).
    Each panel auto-frames on the target so the subject fills the view.

    target: ALL (all mesh objects, default) | SELECTED (currently selected mesh objects) | <object name>
    zoom: panel resolution scale. Base 320x180 per panel; zoom=2 → 640x360 per panel.

    Returns the image plus a text line with the framed world-space bbox.
    Selection state is preserved across the call.
    """
    result = call_blender("get_viewport_collage", {"target": target, "zoom": zoom})
    if "error" in result:
        raise RuntimeError(result["error"])
    img = Image(data=base64.b64decode(result["image"]), format="png")
    summary = (f"target={result['target']}  objects={result['target_objects']}  "
               f"bbox={result['framed_bbox']}")
    return [img, summary]


@mcp.tool()
def get_history() -> str:
    """
    Return the full operation history log. Each entry has:
    id (8-char hash), label (human name), tool, params.
    Use with undo_to(id) to roll back to any named point.
    """
    result = call_blender("get_history")
    entries = result.get("history", [])
    if not entries:
        return "No history yet."
    lines = [f"[{e['id']}] {e['label']}  ({e['tool']})" for e in entries]
    return "\n".join(lines)


@mcp.tool()
def get_blender_status() -> str:
    """
    Full Blender context snapshot. Returns mode, active + selected objects, dimensions,
    world Z range, last history action, and (in Edit Mode) component type, selection counts,
    and selection Z range. This is also automatically appended to every other tool's output.
    """
    result = call_blender("get_blender_status")
    if not result.get("success"):
        return result.get("error", "failed")
    s = result["status"]
    lines = [
        f"mode:           {s['mode']}",
        f"active_object:  {s['active_object']} ({s['active_type']})",
        f"selected:       {s['selected_objects']}",
        f"location:       {s.get('location')}",
        f"dimensions:     {s.get('dimensions')}     (world bbox)",
        f"rotation_deg:   {s.get('rotation_deg')}",
        f"world_bounds:   {s.get('world_bounds')}",
        f"history_depth:  {s['history_depth']}",
        f"last_action:    {s['last_action']}",
    ]
    if "edit" in s:
        e = s["edit"]
        lines += [
            f"--- edit mode ---",
            f"component_mode: {e['component_mode']}",
            f"selected:       {e['selected']}",
            f"total:          {e['total']}",
            f"sel_z_range:    {e.get('selection_z_range', 'none')}",
        ]
    return "\n".join(lines)


@mcp.tool()
def get_mesh_profile(axis: str = "Z") -> str:
    """
    Slice the active mesh into rings along an axis and report the width/extent at each ring.
    axis: X | Y | Z — the axis to slice along (default Z for vertical objects like blades)
    Returns a table: position along axis, plus min/max/width on the other two axes.
    Use this to understand actual geometry before making edits — no guessing needed.
    """
    result = call_blender("get_mesh_profile", {"axis": axis})
    if not result.get("success"):
        return result.get("error", "failed")
    profile = result["profile"]
    ax = result["axis"]
    other = [n for n in ['X', 'Y', 'Z'] if n != ax]
    lines = [f"{'':>8}  " + "  ".join(f"{n:>22}" for n in other)]
    for r in profile:
        cols = []
        for n in other:
            lo, hi = r[f"{n}_range"]
            w = r[f"{n}_width"]
            cols.append(f"{lo:+.4f}→{hi:+.4f} ({w:.4f})")
        lines.append(f"{ax}={r[ax]:+.4f}  " + "  ".join(cols))
    return f"{len(profile)} rings along {ax}:\n" + "\n".join(lines) + _status(result)


@mcp.tool()
def get_object_info(name: str = "") -> str:
    """
    Detailed state dump of an object: location, scale, rotation, dimensions, world bbox,
    and vertex/edge/face counts.

    Prefer `describe(name)` for normal workflows — it returns a relational sentence
    instead of raw coordinates. Use this when you specifically need the underlying
    coordinate/scale/rotation values (debugging, math).

    name: target object. If omitted, falls back to the active object.
    """
    params = {"name": name} if name else {}
    result = call_blender("get_object_info", params)
    if result.get("success"):
        return json.dumps(result["info"], indent=2) + _status(result)
    return result.get("error", "failed")


@mcp.tool()
def describe(name: str) -> str:
    """
    Describe an object in RELATIONAL terms — what it rests on, what it's flush with,
    and its dimensions. No raw world coordinates.

    Prefer this over get_object_info for normal workflows. Coords appear in get_object_info
    when you really need them; describe() is the everyday tool because relational
    descriptions are what you actually reason in.

    Example output:
        "leg_front_left: standing on floor; flush left of seat; size 0.04 × 0.04 × 0.45 m (W×D×H)"
    """
    result = call_blender("describe", {"name": name})
    if not result.get("success"):
        return result.get("error", "failed")
    return result["description"] + _status(result)


# --- State-modifying tools ---

@mcp.tool()
def set_viewport_angle(angle: str) -> str:
    """
    Set the viewport to a standard angle.
    angle: FRONT | BACK | LEFT | RIGHT | TOP | BOTTOM | CAMERA
    """
    result = call_blender("set_viewport_angle", {"angle": angle})
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


def _add_result(ptype: str, result: dict) -> str:
    if result.get("success"):
        dims = result.get("dimensions")
        bounds = result.get("world_bounds", {})
        bounds_str = (f" at x={bounds.get('x')} y={bounds.get('y')} z={bounds.get('z')}"
                      if bounds else "")
        return f"Added {ptype} as '{result['object_name']}' dims={dims}{bounds_str} [{result.get('op_id','')}]"
    return result.get("error", "failed")


# ─── PLACEMENT DSL ─────────────────────────────────────────────────────────────
#
# Every dimensional primitive (add_box / add_cylinder / add_sphere / add_cone /
# add_plane) takes an optional `on` parameter that describes WHERE the new object
# goes RELATIVE TO existing objects — instead of you computing world coordinates.
# This is the primary placement vocabulary. Use it.
#
# `on` is a dict that may combine several keys (combinations are useful):
#
#   Whole-object placements (set all 3 axes):
#     {"on":          "name"}          → resting on top of, centered XY
#     {"under":       "name"}          → resting underneath, centered XY
#     {"between":     ["a", "b"]}      → centered on midpoint of two
#     {"centered_on": "name"}          → match XYZ centers
#     {"at_corner":   {"of": "name", "corner": "front_left"|"front_right"|"back_left"|"back_right"}}
#                                      → bottom-corner of new = bottom-corner of target
#
#   Adjacency (1-axis flush + center the other 2):
#     {"left_of":     "name"}          → flush against target's −X side
#     {"right_of":    "name"}          → flush against target's +X side
#     {"in_front_of": "name"}          → flush against target's −Y side
#     {"behind":      "name"}          → flush against target's +Y side
#
#   Z overrides (applied last; win conflicts with the above):
#     {"on_floor":  true}              → bottom of new = Z 0
#     {"raise_to":  0.45}              → bottom of new = Z 0.45  (literal Z — ripcord)
#
#   Modifier:
#     {"gap": 0.01}                    → spacing for on/under/left_of/etc.
#
# Examples:
#   on={"at_corner": {"of": "seat", "corner": "front_left"}, "on_floor": True}
#   on={"between": ["leg_back_left", "leg_back_right"], "raise_to": 0.50}
#   on={"right_of": "leg_front_left", "gap": 0.36, "on_floor": True}
#
# Axis convention: +X = right, +Y = back, +Z = up. Front of an object is its −Y side.
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def add_box(name: str, width: float, depth: float, height: float,
            on: dict = None,
            rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
            label: str = "") -> str:
    """
    Add a rectangular box of exact world-space dimensions (W × D × H, in meters).
    The object's scale will be [1,1,1] after creation, so bevel / smooth_edges
    produce uniform results without any extra apply-scale step.

    name:   REQUIRED — object name (must be unique).
    width:  X extent in meters.   depth: Y extent.   height: Z extent.
    on:     placement spec — see PLACEMENT DSL at the top of this file.
            If omitted, the box is created at world origin.
    rot_x/y/z: optional rotation in degrees (applied after placement).
    """
    result = call_blender("add_box", {
        "name": name, "width": width, "depth": depth, "height": height,
        "on": on, "rotation_deg": [rot_x, rot_y, rot_z],
    }, label=label)
    return _add_result("BOX", result) + _status(result)


@mcp.tool()
def add_plane(name: str, width: float, depth: float,
              on: dict = None,
              rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
              label: str = "") -> str:
    """
    Add a flat plane (single quad) of exact W × D dimensions in meters.
    on: placement spec — see PLACEMENT DSL.
    """
    result = call_blender("add_plane", {
        "name": name, "width": width, "depth": depth,
        "on": on, "rotation_deg": [rot_x, rot_y, rot_z],
    }, label=label)
    return _add_result("PLANE", result) + _status(result)


@mcp.tool()
def add_cylinder(name: str, radius: float, height: float,
                 on: dict = None, vertices: int = 32, cap_fill: str = "NGON",
                 rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
                 label: str = "") -> str:
    """
    Add a cylinder aligned to Z. Exact radius and height in meters.
    vertices: edge count around the circumference (more = smoother).
    cap_fill: NGON | TRIFAN | NOTHING.
    on: placement spec — see PLACEMENT DSL.
    """
    result = call_blender("add_cylinder", {
        "name": name, "radius": radius, "height": height,
        "on": on, "vertices": vertices, "cap_fill": cap_fill,
        "rotation_deg": [rot_x, rot_y, rot_z],
    }, label=label)
    return _add_result("CYLINDER", result) + _status(result)


@mcp.tool()
def add_sphere(name: str, radius: float,
               on: dict = None, segments: int = 32, rings: int = 16,
               rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
               label: str = "") -> str:
    """
    Add a UV sphere of exact radius in meters.
    segments / rings: longitudinal / latitudinal divisions.
    on: placement spec — see PLACEMENT DSL.
    """
    result = call_blender("add_sphere", {
        "name": name, "radius": radius,
        "on": on, "segments": segments, "rings": rings,
        "rotation_deg": [rot_x, rot_y, rot_z],
    }, label=label)
    return _add_result("SPHERE", result) + _status(result)


@mcp.tool()
def add_cone(name: str, radius_bottom: float, height: float, radius_top: float = 0.0,
             on: dict = None, vertices: int = 32, cap_fill: str = "NGON",
             rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
             label: str = "") -> str:
    """
    Add a cone (or truncated cone) aligned to Z.
    radius_bottom: base radius in meters.   radius_top: top radius (0 = sharp point).
    height: total Z extent in meters.
    on: placement spec — see PLACEMENT DSL.
    """
    result = call_blender("add_cone", {
        "name": name, "radius_bottom": radius_bottom, "radius_top": radius_top,
        "height": height, "on": on, "vertices": vertices, "cap_fill": cap_fill,
        "rotation_deg": [rot_x, rot_y, rot_z],
    }, label=label)
    return _add_result("CONE", result) + _status(result)


@mcp.tool()
def rename_object(old_name: str, new_name: str) -> str:
    """
    Rename an object (and its mesh data) to a new name.
    Use get_scene_tree first to find current names.
    """
    result = call_blender("rename_object", {"old_name": old_name, "new_name": new_name})
    if result.get("success"):
        main = f"Renamed '{result['old_name']}' → '{result['new_name']}'"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_object(name: str) -> str:
    """Select an object by name and make it active. Use get_scene_tree first to find names."""
    result = call_blender("select_object", {"name": name})
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def nudge(targets: str = "", right: float = 0.0, left: float = 0.0,
          up: float = 0.0, down: float = 0.0,
          back: float = 0.0, forward: float = 0.0, label: str = "") -> str:
    """
    Move objects by a relative offset, in SEMANTIC directions instead of XYZ.
    right/left → ±X, back/forward → ±Y, up/down → ±Z. All in meters.

    Prefer placement spec (`on=` on add_*) for FIRST placement. Use nudge for fine
    adjustments after the fact (e.g. "shift this 1cm to the right to align with X").

    targets: single object name, a group name, or comma-separated list. Empty = active object.
    Example: nudge("seat", up=0.02) — raise the seat 2cm.
    """
    t = [s.strip() for s in targets.split(",")] if targets else None
    if t and len(t) == 1:
        t = t[0]
    result = call_blender("nudge", {
        "targets": t,
        "right": right, "left": left, "up": up, "down": down, "back": back, "forward": forward,
    }, label=label)
    if result.get("success"):
        main = f"nudged {result['moved']} by {result['delta']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def resize(targets: str = "", width: float = None, depth: float = None, height: float = None,
           label: str = "") -> str:
    """
    Resize objects to ABSOLUTE world-space dimensions (meters). Each axis is optional;
    omitted axes preserve their current size. Scale is baked after resize so modifiers
    (bevel etc.) behave uniformly.

    Prefer creating primitives at the right size up front (add_box etc.) — this is for
    after-the-fact corrections ("make the seat 5cm taller").

    targets: single object name, group name, or comma-separated list. Empty = active object.
    Example: resize("seat", height=0.04) — make the seat 4cm thick.
    """
    t = [s.strip() for s in targets.split(",")] if targets else None
    if t and len(t) == 1:
        t = t[0]
    params = {"targets": t}
    if width is not None:  params["width"] = width
    if depth is not None:  params["depth"] = depth
    if height is not None: params["height"] = height
    result = call_blender("resize", params, label=label)
    if result.get("success"):
        main = f"resized: {result['resized']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def apply_transform(targets: str = "", scale: bool = True,
                    rotation: bool = False, location: bool = False, label: str = "") -> str:
    """
    Bake an object's transform into its mesh data. After applying scale, obj.scale = [1,1,1]
    and bevels/modifiers behave uniformly. Apply rotation to clear rotation_euler. Apply
    location only if you really want the origin pinned at world (0,0,0) — usually unwanted.

    Primitives created with add_box etc. already have scale baked, so you rarely need this.
    Reach for it after `resize` if you bypass the built-in bake, or to fix imported objects.

    targets: single object name, group name, or comma-separated list. Empty = active object.
    """
    t = [s.strip() for s in targets.split(",")] if targets else None
    if t and len(t) == 1:
        t = t[0]
    result = call_blender("apply_transform", {
        "targets": t, "scale": scale, "rotation": rotation, "location": location,
    }, label=label)
    if result.get("success"):
        flags = [k for k in ("scale", "rotation", "location") if result.get(k)]
        main = f"applied {flags} on {result['applied_to']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def rotate_object(angle: float, axis: str = "Z", targets: str = "", label: str = "") -> str:
    """
    Rotate objects by `angle` degrees around `axis` (X | Y | Z).
    targets: single object name, group name, or comma-separated list. Empty = active object.
    """
    t = [s.strip() for s in targets.split(",")] if targets else None
    if t and len(t) == 1:
        t = t[0]
    result = call_blender("rotate_object", {
        "angle": angle, "axis": axis, "targets": t,
    }, label=label)
    if result.get("success"):
        main = f"rotated {result['rotated']} by {angle}° on {axis} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def snap_to(target: str, side: str = "Z_MAX", source_side: str = "AUTO",
            offset: float = 0.0, label: str = "") -> str:
    """
    Translate the active object so one of its bbox faces aligns with a face of `target`.

    side:        which face of TARGET to snap to.  X_MIN | X_MAX | Y_MIN | Y_MAX | Z_MIN | Z_MAX
    source_side: which face of ACTIVE to align there.
                 AUTO (default) = the opposite face on the same axis (so they touch flush).
                 CENTER = align active's center to target's chosen face.
                 explicit X_MIN..Z_MAX must be on the same axis as `side`.
    offset:      world-units along the side axis, applied AFTER alignment.
                 +ve = move active further in the +axis direction (more overlap when snapping to MAX-side).

    Examples:
      snap_to(target="Crossguard", side="Z_MAX")                          # grip bottom flush with crossguard top
      snap_to(target="Grip", side="Z_MAX", offset=-0.04)                  # pommel sinks 0.04 into grip
      snap_to(target="Wall", side="X_MAX", source_side="X_MAX")           # both right-faces align (flush, not next-to)
    """
    params = {"target": target, "side": side, "source_side": source_side, "offset": offset}
    result = call_blender("snap_to", params, label=label)
    if result.get("success"):
        main = (f"snap_to {target}.{side}: delta={result['delta']} "
                f"({result['source_side']}→{result['target_coord']})  [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def snap_to_grid(size: float = 0.1, axes: str = "XYZ", label: str = "") -> str:
    """
    Round the active object's location to multiples of `size` on the chosen axes.

    size: grid spacing in world units (e.g., 0.05, 0.1, 0.25, 1.0)
    axes: any of "X", "Y", "Z", or combinations like "XZ" — only these axes are snapped.

    Snaps the ORIGIN/pivot — does not change dims, rotation, or geometry.
    Pairs naturally with snap_to: free-place, snap-to-grid for alignment, snap-to for stacking.
    """
    params = {"size": size, "axes": axes}
    result = call_blender("snap_to_grid", params, label=label)
    if result.get("success"):
        moves = result.get("snapped", [])
        moved_summary = ", ".join(f"{m['axis']}:{m['from']}→{m['to']}" for m in moves if abs(m.get('moved', 0)) > 1e-9) or "no change"
        main = f"snap_to_grid {size} on {axes}: {moved_summary}  [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_mode(mode: str) -> str:
    """
    Switch the active object's interaction mode.
    mode: OBJECT | EDIT | SCULPT
    """
    result = call_blender("set_mode", {"mode": mode})
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def delete_object(name: str, label: str = "") -> str:
    """Delete an object by name. Use get_scene_tree to find object names."""
    result = call_blender("delete_object", {"name": name}, label=label)
    if result.get("success"):
        main = f"Deleted '{result['deleted']}' [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def frame_scene() -> str:
    """Fit all objects in the viewport."""
    result = call_blender("frame_scene")
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def zoom_to_selected() -> str:
    """Zoom the viewport to tightly frame the currently selected object."""
    result = call_blender("zoom_to_selected")
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def orbit_viewport(azimuth: float = 45.0, elevation: float = 25.0, distance: float = 8.0,
                   target_x: float = 0.0, target_y: float = 0.0, target_z: float = 1.0) -> str:
    """
    Position the viewport perspective camera using orbit controls.
    azimuth: horizontal angle in degrees (0=front, +right, -left)
    elevation: vertical angle in degrees (positive=from above)
    distance: distance from target
    """
    result = call_blender("orbit_viewport", {
        "azimuth": azimuth, "elevation": elevation, "distance": distance,
        "target_x": target_x, "target_y": target_y, "target_z": target_z,
    })
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_camera_position(x: float, y: float, z: float,
                        target_x: float = 0.0, target_y: float = 0.0, target_z: float = 0.0) -> str:
    """Move the scene camera to a position aimed at a target point."""
    result = call_blender("set_camera_position", {
        "x": x, "y": y, "z": z,
        "target_x": target_x, "target_y": target_y, "target_z": target_z,
    })
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def bevel(factor: float = 0.05, segments: int = 1, affect: str = "EDGES", label: str = "") -> str:
    """
    Bevel selected edges or vertices in edit mode.
    factor: bevel size as a fraction of the object's smallest dimension (0.05 = 5%)
    segments: edge loops added (more = smoother curve)
    affect: EDGES | VERTICES
    """
    result = call_blender("bevel", {"factor": factor, "segments": segments, "affect": affect}, label=label)
    if result.get("success"):
        main = f"ok (offset={result.get('offset_world')}) [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def extrude(x: float = 0.0, y: float = 0.0, z: float = 0.0, label: str = "") -> str:
    """
    Extrude selected geometry in edit mode and translate by a fraction of the object's dimensions.
    x/y/z: fraction of object dimension along that axis (0.5 = 50% of width/depth/height).
    Returns the actual world-space translation applied.
    """
    result = call_blender("extrude", {"x": x, "y": y, "z": z}, label=label)
    if result.get("success"):
        main = f"ok translation={result.get('translation_world')} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_all(action: str = "SELECT") -> str:
    """
    Select/deselect geometry in edit mode.
    action: SELECT | DESELECT | INVERT
    """
    result = call_blender("select_all", {"action": action})
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_by_axis(axis: str = "Z", factor: float = 0.5, comparison: str = "GREATER",
                   action: str = "SELECT") -> str:
    """
    Select or deselect vertices in edit mode by position along an axis.
    axis: X | Y | Z
    factor: 0.0 = min extent, 1.0 = max extent of object on this axis.
            e.g. factor=0.8 comparison=GREATER selects the top 20% of the mesh.
    comparison: GREATER | LESS
    action: SELECT (replace selection) | DESELECT (remove matching verts from selection)
            Use DESELECT to select a band: select_all → deselect left → deselect right = center band.
    Returns the actual world-space threshold used.
    """
    result = call_blender("select_by_axis", {"axis": axis, "factor": factor,
                                              "comparison": comparison, "action": action})
    if result.get("success"):
        main = f"ok (threshold_world={result.get('threshold_world')})"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def move_vertices(x: float = 0.0, y: float = 0.0, z: float = 0.0, label: str = "") -> str:
    """
    Translate selected vertices in edit mode using bmesh.
    x/y/z: fraction of object dimension along that axis (0.1 = 10% of width/depth/height).
    Negative values move in the opposite direction.
    Must be in edit mode with vertices selected.
    """
    result = call_blender("move_vertices", {"x": x, "y": y, "z": z}, label=label)
    if result.get("success"):
        main = f"Moved {result['verts_moved']} verts by {result['delta_world']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def scale_vertices(x: float = 1.0, y: float = 1.0, z: float = 1.0,
                   pivot: str = "SELECTION", label: str = "") -> str:
    """
    Scale selected vertices in edit mode using bmesh.
    x/y/z: scale multipliers per axis (0.5 = half, 2.0 = double)
    pivot: SELECTION (around selection center) | ORIGIN (around object origin)
    Must be in edit mode with vertices selected.
    """
    result = call_blender("scale_vertices", {"x": x, "y": y, "z": z, "pivot": pivot}, label=label)
    if result.get("success"):
        main = f"Scaled {result['verts_scaled']} verts [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def get_rings(axis: str = "Z") -> str:
    """
    List the edge-loop rings of the active mesh along an axis.

    A ring is a set of vertices that share the same world-space coordinate on the axis.
    Rings are returned sorted by position ascending; index 0 = lowest, last = highest.
    Use the index with select_ring / taper_end / taper_section to address geometry by topology,
    not by world coordinates.

    Must be in edit mode.
    """
    result = call_blender("get_rings", {"axis": axis})
    if not result.get("success"):
        return result.get("error", "failed")
    rings = result["rings"]
    lines = [f"{result['ring_count']} rings along {axis}:"]
    for r in rings:
        lines.append(f"  [{r['index']:>2}]  pos={r['position_world']:+.4f}  verts={r['verts']}")
    return "\n".join(lines) + _status(result)


@mcp.tool()
def select_ring(axis: str = "Z", index: int = 0, action: str = "SELECT") -> str:
    """
    Select the vertices belonging to a specific ring along an axis.

    index: 0 = first (lowest on axis), -1 = last (highest). Negative indices wrap.
    action: SELECT (replace current selection) | ADD (add to selection) | DESELECT (remove)

    Call get_rings first to see the available indices. Must be in edit mode.
    """
    result = call_blender("select_ring", {"axis": axis, "index": index, "action": action})
    if result.get("success"):
        main = (f"ring {result['ring_index']}/{result['ring_count']-1}  "
                f"pos={result['position_world']:+.4f}  verts={result['verts_in_ring']}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_rings(axis: str = "Z", indices: list = [], action: str = "SELECT") -> str:
    """
    Select the union of vertices belonging to MULTIPLE rings along an axis in one call.

    indices: list of ring indices (negatives wrap, so -1 = last).
             e.g. [2, 4, 6] for three alternating rings.
    action:  SELECT (replace) | ADD | DESELECT

    Replaces the verbose select_ring + ADD + ADD pattern when shaping repeated detail
    (alternating bulge/pinch on a grip wrap, fluting along a column).
    Pair with scale_rings to scale each selected ring around its own centroid.
    """
    result = call_blender("select_rings", {"axis": axis, "indices": indices, "action": action})
    if result.get("success"):
        main = f"selected rings {result['rings_selected']} of {result['ring_count']}  verts={result['verts_total']}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def scale_rings(axis: str = "Z", indices: list = [], x: float = 1.0, y: float = 1.0,
                label: str = "") -> str:
    """
    Scale each named ring around ITS OWN centroid in the two non-axis directions.

    indices: list of ring indices (negatives wrap, -1 = last)
    x, y:    scale multipliers on the two non-axis directions

    This is the correct tool for bulge/pinch detail on cylinders, repeating fluting, or any
    per-ring shaping. scale_vertices with pivot=SELECTION collapses all selected verts to
    one centroid (wrong for non-contiguous rings); pivot=ORIGIN only works when the object
    origin happens to lie on the cylinder axis. scale_rings always does the right thing.

    Example — alternating pinches on a grip:
      scale_rings(axis="Z", indices=[2, 4, 6], x=0.85, y=0.85)
    """
    result = call_blender("scale_rings", {
        "axis": axis, "indices": indices, "x": x, "y": y,
    }, label=label)
    if result.get("success"):
        main = (f"scaled rings {result['rings_scaled']} by (x={x}, y={y})  "
                f"{result['verts_affected']} verts  [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def taper_end(axis: str = "Z", end: str = "MAX", scale: float = 0.0, label: str = "") -> str:
    """
    Scale the extreme ring on an axis toward its own centroid in the two non-axis directions.

    end:   MAX (highest ring on axis) | MIN (lowest ring on axis)
    scale: 0.0 (default) collapses the ring fully to a point — same as before.
           0.5 leaves the ring at half its original spread (partial taper / chamfer).
           1.0 is a no-op.

    Use scale=0 for a sword tip; scale=0.4 for "narrow this end a bit" without committing
    to a single point. Faster than the two-ring taper_section equivalent.
    Must be in edit mode.
    """
    result = call_blender("taper_end", {"axis": axis, "end": end, "scale": scale}, label=label)
    if result.get("success"):
        verb = "collapsed" if scale == 0.0 else f"scaled→{scale}"
        main = (f"{verb} ring {result['ring_index']}/{result['ring_count']-1} "
                f"({result['end']} of {result['axis']})  "
                f"{result['collapsed_verts']} verts at world={result.get('collapsed_world')}")
        nearby = result.get("nearby_objects") or []
        if nearby:
            nearby_str = ", ".join(f"{n['name']}@{n['dist']}u" for n in nearby)
            main += f"\n  nearby: {nearby_str}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def taper_section(axis: str = "Z", from_ring: int = 0, to_ring: int = -1,
                  x_start: float = 1.0, x_end: float = 1.0,
                  y_start: float = 1.0, y_end: float = 1.0, label: str = "") -> str:
    """
    Linearly interpolate scale across a span of rings — sculpts taper, bulge, or pinch.

    Each ring in [from_ring, to_ring] is scaled around its own centroid in the two non-axis
    directions. The scale at the from_ring is (x_start, y_start); at the to_ring it is
    (x_end, y_end); intermediate rings interpolate linearly.

    Negative indices are allowed (Python-style, so -1 = last ring).

    Examples:
      taper_section(Z, from_ring=0, to_ring=-1, x_end=0.5, y_end=0.5)  → linear taper to 50% at top
      taper_section(Z, from_ring=2, to_ring=4, x_start=1, x_end=0)     → collapse rings 2..4 to a Y-edge

    Must be in edit mode.
    """
    result = call_blender("taper_section", {
        "axis": axis, "from_ring": from_ring, "to_ring": to_ring,
        "x_start": x_start, "x_end": x_end, "y_start": y_start, "y_end": y_end,
    }, label=label)
    if result.get("success"):
        main = (f"tapered rings {result['from_ring']}..{result['to_ring']} of {result['ring_count']} "
                f"({result['verts_affected']} verts)")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def loop_cut(axis: str = "Z", cuts: int = 1, label: str = "") -> str:
    """
    Add edge loop cuts perpendicular to the given axis using bmesh.
    Must be in edit mode. axis: X | Y | Z
    Finds all edges running along that axis and subdivides them.
    label: optional name for the history log
    """
    result = call_blender("loop_cut", {"axis": axis, "cuts": cuts}, label=label)
    if result.get("success"):
        main = f"Cut {result['edges_subdivided']} edges x{result['cuts']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def add_modifier(type: str, name: str = "", levels: int = 2, render_levels: int = 2,
                 width: float = 0.1, segments: int = 1, label: str = "") -> str:
    """
    Add a modifier to the active object.
    type: SUBSURF | BEVEL | SOLIDIFY | MIRROR | ARRAY | SCREW
    levels: subdivision levels (SUBSURF)  |  width/segments: bevel params
    """
    result = call_blender("add_modifier", {
        "type": type, "name": name or type.capitalize(),
        "levels": levels, "render_levels": render_levels,
        "width": width, "segments": segments,
    }, label=label)
    if result.get("success"):
        main = f"{result['modifier']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_component_mode(mode: str) -> str:
    """
    Switch the mesh select component mode in Edit Mode.
    mode: VERT | EDGE | FACE
    Must be in Edit Mode. Call this before selection operations that depend on component type.
    """
    result = call_blender("set_component_mode", {"mode": mode})
    main = f"component mode → {mode}" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def grow_selection(direction: str = "GROW", steps: int = 1) -> str:
    """
    Expand or contract the current selection by one topology step per step.
    direction: GROW (add adjacent elements) | SHRINK (remove boundary elements)
    steps: number of times to grow/shrink (default 1)
    Must be in Edit Mode with something selected.
    """
    result = call_blender("grow_selection", {"direction": direction, "steps": steps})
    main = f"{direction} x{steps}" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_between(axis: str = "Z", lo: float = 0.0, hi: float = 1.0,
                   action: str = "SELECT") -> str:
    """
    Select (or deselect) vertices whose world-space position on an axis falls between lo and hi.
    axis: X | Y | Z
    lo, hi: factors from 0.0 (min extent) to 1.0 (max extent) — same scale as select_by_axis.
            e.g. lo=0.4, hi=0.6 selects the middle 20% of the mesh along the axis.
    action: SELECT | DESELECT
    Returns the actual world-space thresholds and total selected vert count.
    Replaces the verbose select_all → deselect_below → deselect_above band pattern.
    """
    result = call_blender("select_between", {"axis": axis, "lo": lo, "hi": hi, "action": action})
    if result.get("success"):
        main = (f"ok  {axis}:[{result['lo_world']} → {result['hi_world']}]"
                f"  selected={result['selected_count']}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def get_current_selection() -> str:
    """
    Describe the current vertex selection in Edit Mode.
    Returns: selected vert count, world-space centroid, world-space bounding box.
    Use this to understand where your selection actually is before moving or scaling it.
    Must be in Edit Mode.
    """
    result = call_blender("get_current_selection")
    if not result.get("success"):
        return result.get("error", "failed")
    if result["selected_count"] == 0:
        return "No vertices selected." + _status(result)
    lines = [
        f"selected_verts: {result['selected_count']}",
        f"centroid_world: {result['centroid_world']}",
        f"bbox_world:",
        f"  x: {result['bbox_world']['x']}",
        f"  y: {result['bbox_world']['y']}",
        f"  z: {result['bbox_world']['z']}",
    ]
    return "\n".join(lines) + _status(result)


@mcp.tool()
def duplicate_object(name: str, new_name: str = "") -> str:
    """
    Duplicate an object in place. The duplicate becomes the active object.
    name: object to duplicate (must exist in the scene)
    new_name: name for the duplicate — if omitted, Blender appends .001
    Returns both the original and duplicate names.
    Must be in Object Mode.
    """
    result = call_blender("duplicate_object", {"name": name, "new_name": new_name})
    if result.get("success"):
        main = f"Duplicated '{result['original']}' → '{result['duplicate']}'"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def join_objects(names: list) -> str:
    """
    Join multiple objects into one. The first name in the list becomes the surviving object.
    names: list of object names to join (minimum 2)
    All objects must be the same type (MESH). The result keeps the first object's name.
    Must be in Object Mode.
    """
    result = call_blender("join_objects", {"names": names})
    if result.get("success"):
        main = f"Joined {result['joined']} → '{result['result_object']}'"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def apply_modifiers(name: str = "") -> str:
    """
    Apply all modifiers on an object, collapsing them into the base mesh.
    name: object name — if omitted, applies to the active object.
    Required before export, boolean operations, or manual mesh editing on a modified object.
    Must be in Object Mode.
    """
    result = call_blender("apply_modifiers", {"name": name})
    if result.get("success"):
        applied = result.get("applied", [])
        main = (f"Applied {len(applied)} modifier(s) on '{result['object']}': {applied}"
                if applied else f"No modifiers on '{result['object']}'")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def undo(steps: int = 1) -> str:
    """
    Undo the last N operations. Updates history log to match.
    Check get_history() first to see what will be undone.
    """
    result = call_blender("undo_steps", {"steps": steps})
    if result.get("success"):
        main = f"Undid {result['steps']} step(s). History remaining: {result['history_remaining']}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def undo_to(id: str) -> str:
    """
    Undo back to a specific operation by its ID (from get_history).
    Everything after that ID is undone. The target operation itself is kept.
    """
    result = call_blender("undo_to", {"id": id})
    if result.get("success"):
        main = f"Undid {result['steps']} step(s) to reach [{id}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


# --- Relational queries ---

@mcp.tool()
def distance_between(a: str, b: str, axis: str = "ANY") -> str:
    """
    Centre-to-centre distance between two objects, in meters.
    axis: ANY (3D Euclidean) | X | Y | Z (single-axis distance).

    Use this when you'd otherwise be tempted to fetch coords of both and subtract —
    let the server do the math so you don't carry numbers in your head.
    """
    result = call_blender("distance_between", {"a": a, "b": b, "axis": axis})
    if result.get("success"):
        return f"{a} ↔ {b} ({result['axis']}): {result['distance']} m" + _status(result)
    return result.get("error", "failed")


@mcp.tool()
def gap_between(a: str, b: str) -> str:
    """
    Smallest empty distance between two objects' bounding boxes, per axis.
    Negative = overlap. Useful for "are these touching?" and "how much room is left?"
    """
    result = call_blender("gap_between", {"a": a, "b": b})
    if not result.get("success"):
        return result.get("error", "failed")
    touching = result.get("touching_on_axes") or []
    touching_str = f" — touching on {touching}" if touching else ""
    main = (f"gap {a} ↔ {b}: x={result['gap_x']}  y={result['gap_y']}  z={result['gap_z']}"
            f"{touching_str}")
    return main + _status(result)


@mcp.tool()
def is_aligned(a: str, b: str, side: str = "TOP", tolerance: float = 0.001) -> str:
    """
    Check whether two objects share an aligned side / center.
    side: TOP | BOTTOM | LEFT | RIGHT | FRONT | BACK | CENTER_X | CENTER_Y | CENTER_Z

    Use this instead of fetching world-bounds for two objects and comparing.
    """
    result = call_blender("is_aligned", {"a": a, "b": b, "side": side, "tolerance": tolerance})
    if not result.get("success"):
        return result.get("error", "failed")
    verdict = "ALIGNED" if result["aligned"] else "NOT aligned"
    return f"{a} vs {b} on {side}: {verdict} (diff={result['difference']})" + _status(result)


# --- Relational verbs ---

@mcp.tool()
def match_dimension(target: str, reference: str, axis: str = "Z", label: str = "") -> str:
    """
    Resize `target` so its extent on `axis` equals `reference`'s extent on that axis.
    Bakes scale after resizing.

    Example: match_dimension("slat_3", "slat_1", axis="Z") — make slat 3 the same height as slat 1.
    """
    result = call_blender("match_dimension", {
        "target": target, "reference": reference, "axis": axis,
    }, label=label)
    if result.get("success"):
        return (f"{target}.{axis} → {result['new_size']} m (factor {result['factor_applied']}) "
                f"[{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def mirror_across(targets: str, plane: str = "X", suffix: str = "_mirror",
                  label: str = "") -> str:
    """
    Duplicate parts and mirror the copies across a world axis plane through origin.
    plane: 'X' mirrors across the YZ plane (flips +X ↔ −X); 'Y' and 'Z' analogous.

    The copies are independent objects (no live constraint). Useful for symmetric construction:
    build the left side, then mirror_across('X') to get the right side.

    targets: single object name, group name, or comma-separated list.
    Example: mirror_across("leg_front_left,leg_back_left", plane="X", suffix="_right")
    """
    t = [s.strip() for s in targets.split(",")] if targets else None
    if t and len(t) == 1:
        t = t[0]
    result = call_blender("mirror_across", {
        "targets": t, "plane": plane, "suffix": suffix,
    }, label=label)
    if result.get("success"):
        return (f"mirrored across {plane}: {result['mirrored_to']} "
                f"[{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def distribute_evenly(targets: str, between: list, axis: str = "X", label: str = "") -> str:
    """
    Position parts so their centers are evenly spaced strictly between two anchor objects' centers.
    Anchor positions themselves are NOT occupied.

    targets: comma-separated object names OR a group name.
    between: ["object_a", "object_b"] — the two anchors.
    axis: X | Y | Z — which axis to distribute along.

    Example: distribute_evenly("slat_1,slat_2,slat_3,slat_4,slat_5",
                              between=["leg_back_left", "leg_back_right"], axis="X")
             → 5 slats evenly spaced between the two back legs along X.
    """
    t = [s.strip() for s in targets.split(",")] if targets else None
    if t and len(t) == 1:
        t = t[0]
    result = call_blender("distribute_evenly", {
        "targets": t, "between": between, "axis": axis,
    }, label=label)
    if result.get("success"):
        names = [p["name"] for p in result["placed"]]
        return (f"distributed {len(names)} parts on {axis} (spacing {result['spacing']} m): "
                f"{names} [{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def array_at_corners(prototype: str, of: str, standing_on_floor: bool = True,
                     keep_original: bool = False, name_prefix: str = "",
                     label: str = "") -> str:
    """
    Duplicate a prototype object to all 4 corners of a target's footprint.
    The 4 copies are named "<prefix>_front_left", "<prefix>_front_right", etc.
    Prefix defaults to the prototype name.

    standing_on_floor: if True, copies sit at Z=0 regardless of where prototype was.
    keep_original: if False (default), the prototype is deleted after copying.

    Example: array_at_corners("leg", of="seat") — put four legs at the seat's corners.
    """
    result = call_blender("array_at_corners", {
        "prototype": prototype, "of": of,
        "standing_on_floor": standing_on_floor,
        "keep_original": keep_original,
        "name_prefix": name_prefix or prototype,
    }, label=label)
    if result.get("success"):
        return (f"placed at corners of {of}: {result['placed']} "
                f"[{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def array_along(prototype: str, count: int, between: list, axis: str = "X",
                keep_original: bool = False, name_prefix: str = "",
                label: str = "") -> str:
    """
    Duplicate a prototype N times, spacing copies evenly between two anchor centers.
    Like distribute_evenly but also creates the copies. Copies are named "<prefix>_1"..."_N".

    Example: array_along("slat", count=5,
                         between=["back_rail_bottom", "back_rail_top"], axis="Z")
             → 5 evenly spaced copies of "slat" between the two rails.
    """
    result = call_blender("array_along", {
        "prototype": prototype, "count": count, "between": between, "axis": axis,
        "keep_original": keep_original, "name_prefix": name_prefix or prototype,
    }, label=label)
    if result.get("success"):
        return (f"placed {count} copies on {axis} (spacing {result['spacing']} m): "
                f"{result['placed']} [{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


# --- Groups ---

@mcp.tool()
def group(name: str, parts: list, label: str = "") -> str:
    """
    Create (or extend) a named group containing the given parts.
    A group is a Blender collection — any tool that accepts `targets` can take the
    group name and act on all members.

    name: group name (unique).
    parts: list of object names to include.

    Example: group("chair", ["seat", "leg_front_left", "leg_front_right",
                              "leg_back_left", "leg_back_right", ...])
             then smooth_edges("chair") finishes every part in one call.
    """
    result = call_blender("group", {"name": name, "parts": parts}, label=label)
    if result.get("success"):
        return (f"group '{name}' now contains {len(result['members'])} parts "
                f"(added: {result['newly_added']}) [{result.get('op_id','')}]"
                + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def parts_in(name: str) -> str:
    """List the parts inside a named group."""
    result = call_blender("parts_in", {"name": name})
    if not result.get("success"):
        return result.get("error", "failed")
    return f"group '{name}': {result['parts']}" + _status(result)


@mcp.tool()
def ungroup(name: str, label: str = "") -> str:
    """Remove a group. Its objects move back to the scene root; they are NOT deleted."""
    result = call_blender("ungroup", {"name": name}, label=label)
    if result.get("success"):
        return (f"removed group '{name}'; freed {result['members_freed']} "
                f"[{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


# --- Bundled finishes ---

@mcp.tool()
def round_corners(target: str, corners: list, radius: float = 0.02,
                  segments: int = 6, label: str = "") -> str:
    """
    Round specific vertical corners of an object with a given world-space radius.

    Where `smooth_edges` does a small uniform bevel over every edge of an object,
    `round_corners` rounds ONLY the named corners — and by a real radius (e.g. 2cm),
    not the 1-3mm refinement that smooth_edges produces.

    target:   object name.
    corners:  list of "front_left" | "front_right" | "back_left" | "back_right".
              Each identifies a vertical edge at that XY corner of the bounding box.
    radius:   the rounding radius in meters. Default 0.02 (2cm — typical seat-front round).
    segments: smoothness of the curve. Default 6 (looks like a hand-routed roundover).

    Example: round_corners("seat", corners=["front_left", "front_right"], radius=0.025)
             → rounds just the two front corners of the seat by 25mm.

    Works on already-smoothed meshes: the corner matcher tolerates the small bevels
    left behind by smooth_edges. Re-applies shade_smooth so the new curve reads smooth.
    """
    result = call_blender("round_corners", {
        "target": target, "corners": corners, "radius": radius, "segments": segments,
    }, label=label)
    if result.get("success"):
        return (f"rounded {result['edges_beveled']} corner edge(s) of '{target}' "
                f"({corners}) by {radius}m [{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def smooth_edges(targets: str = "", width: float = 0.002, segments: int = 2,
                 angle_limit: float = 30.0, label: str = "") -> str:
    """
    Round off sharp edges on objects so they don't look blocky.
    Bundles BEVEL (with angle-limit so only sharp edges are beveled, not coplanar ones)
    + shade_smooth + auto_smooth + apply, in one call.

    targets: object name, group name, or comma-separated list. Empty = active object.
    width: bevel offset in meters (default 2mm — small, refined edge).
    segments: more = smoother curve (2 is a good default for furniture; 3+ for hero objects).
    angle_limit: only edges sharper than this (degrees) get beveled. Default 30°.

    Example: smooth_edges("chair", width=0.003) — round every edge in the chair group.
    """
    t = [s.strip() for s in targets.split(",")] if targets else None
    if t and len(t) == 1:
        t = t[0]
    result = call_blender("smooth_edges", {
        "targets": t, "width": width, "segments": segments, "angle_limit": angle_limit,
    }, label=label)
    if result.get("success"):
        return (f"smoothed: {result['smoothed']} (width={width}m, segs={segments}, "
                f"angle<{angle_limit}°) [{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def save_design(name: str) -> str:
    """
    Save the current Blender scene as a .blend file in ~/blender-designs/.
    Use to checkpoint a design so it can be reopened in a later session.

    name: design name. The .blend extension is added if omitted.
    """
    result = call_blender("save_design", {"name": name})
    if result.get("saved"):
        return f"saved: {result['saved']}"
    return result.get("error", "failed")


@mcp.tool()
def open_design(name: str) -> str:
    """
    Open a previously saved design from ~/blender-designs/. Replaces the
    current scene entirely.

    name: design name. The .blend extension is added if omitted.
    """
    result = call_blender("open_design", {"name": name})
    if result.get("opened"):
        return f"opened: {result['opened']}"
    return result.get("error", "failed")


@mcp.tool()
def list_designs() -> str:
    """List all saved designs in ~/blender-designs/."""
    result = call_blender("list_designs")
    designs = result.get("designs", [])
    if not designs:
        return f"No saved designs in {result.get('dir', '?')}."
    return f"{result['dir']}:\n" + "\n".join(f"  {d}" for d in designs)


if __name__ == "__main__":
    mcp.run()

import socket
import json
import base64
from mcp.server.fastmcp import FastMCP, Image

ADDON_HOST = "localhost"
ADDON_PORT = 8765

mcp = FastMCP("blender-buttons")


def call_blender(tool: str, params: dict = {}, label: str = "") -> dict:
    payload = json.dumps({"tool": tool, "params": params, "label": label}) + "\n"
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
    return json.loads(data.decode().strip())


def _status(result: dict) -> str:
    """Format the blender_status block that every tool response now carries."""
    s = result.get("blender_status")
    if not s:
        return ""
    lines = [
        "",
        "── blender status ──────────────────────────────",
        f"  mode:        {s['mode']}",
        f"  active:      {s['active_object']} ({s['active_type']})",
        f"  selected:    {s['selected_objects']}",
        f"  z_range:     {s.get('world_z_range')}",
        f"  dims:        {s.get('dimensions')}",
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
        f"dimensions:     {s.get('dimensions')}",
        f"rotation_deg:   {s.get('rotation_deg')}",
        f"world_z_range:  {s.get('world_z_range')}",
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
def get_object_info() -> str:
    """
    Return detailed state of the active object: location, scale, rotation, dimensions,
    world-space bounding box, and vertex/edge/face counts. Use this before making
    precise edits so you know actual coordinates and sizes.
    """
    result = call_blender("get_object_info")
    if result.get("success"):
        return json.dumps(result["info"], indent=2) + _status(result)
    return result.get("error", "failed")


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
        return f"Added {ptype} as '{result['object_name']}' dims={dims} [{result.get('op_id','')}]"
    return result.get("error", "failed")


@mcp.tool()
def add_cube(name: str, size: float = 2.0,
             x: float = 0, y: float = 0, z: float = 0,
             rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
             label: str = "") -> str:
    """
    Add a cube mesh. The cube's edge length equals `size` (default 2.0).
    name: REQUIRED — object name.
    x/y/z: world-space location.  rot_x/y/z: rotation in degrees.
    """
    result = call_blender("add_primitive", {
        "type": "CUBE", "name": name, "location": [x, y, z],
        "rotation_deg": [rot_x, rot_y, rot_z], "size": size,
    }, label=label)
    return _add_result("CUBE", result) + _status(result)


@mcp.tool()
def add_plane(name: str, size: float = 2.0,
              x: float = 0, y: float = 0, z: float = 0,
              rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
              label: str = "") -> str:
    """
    Add a plane mesh (single quad). Edge length = `size`.
    """
    result = call_blender("add_primitive", {
        "type": "PLANE", "name": name, "location": [x, y, z],
        "rotation_deg": [rot_x, rot_y, rot_z], "size": size,
    }, label=label)
    return _add_result("PLANE", result) + _status(result)


@mcp.tool()
def add_cylinder(name: str, vertices: int = 32, radius: float = 1.0, depth: float = 2.0,
                 cap_fill: str = "NGON",
                 x: float = 0, y: float = 0, z: float = 0,
                 rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
                 label: str = "") -> str:
    """
    Add a cylinder mesh aligned to Z.
    vertices: edges around the circumference (more = smoother)
    radius: circumference radius        depth: total Z height
    cap_fill: NOTHING | NGON | TRIFAN — how the caps are filled
    """
    result = call_blender("add_primitive", {
        "type": "CYLINDER", "name": name, "location": [x, y, z],
        "rotation_deg": [rot_x, rot_y, rot_z],
        "vertices": vertices, "radius": radius, "depth": depth, "cap_fill": cap_fill,
    }, label=label)
    return _add_result("CYLINDER", result) + _status(result)


@mcp.tool()
def add_sphere(name: str, segments: int = 32, rings: int = 16, radius: float = 1.0,
               x: float = 0, y: float = 0, z: float = 0,
               rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
               label: str = "") -> str:
    """
    Add a UV sphere mesh.
    segments: longitudinal divisions (around Z)
    rings: latitudinal divisions
    """
    result = call_blender("add_primitive", {
        "type": "SPHERE", "name": name, "location": [x, y, z],
        "rotation_deg": [rot_x, rot_y, rot_z],
        "segments": segments, "rings": rings, "radius": radius,
    }, label=label)
    return _add_result("SPHERE", result) + _status(result)


@mcp.tool()
def add_cone(name: str, vertices: int = 32, radius1: float = 1.0, radius2: float = 0.0,
             depth: float = 2.0, cap_fill: str = "NGON",
             x: float = 0, y: float = 0, z: float = 0,
             rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
             label: str = "") -> str:
    """
    Add a cone or truncated cone mesh aligned to Z.
    radius1: base (bottom) radius     radius2: top radius (0 = sharp point)
    cap_fill: NOTHING | NGON | TRIFAN
    """
    result = call_blender("add_primitive", {
        "type": "CONE", "name": name, "location": [x, y, z],
        "rotation_deg": [rot_x, rot_y, rot_z],
        "vertices": vertices, "radius1": radius1, "radius2": radius2,
        "depth": depth, "cap_fill": cap_fill,
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
def scale_object(x: float = 1.0, y: float = 1.0, z: float = 1.0, label: str = "") -> str:
    """
    Scale the active object. Values are multipliers (0.5 = half size, 2.0 = double).
    label: optional name for the history log
    """
    result = call_blender("scale_object", {"x": x, "y": y, "z": z}, label=label)
    main = f"ok [{result.get('op_id','')}]" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def move_object(x: float = 0.0, y: float = 0.0, z: float = 0.0, label: str = "") -> str:
    """
    Move the active object by a relative offset in world units.
    label: optional name for the history log
    """
    result = call_blender("move_object", {"x": x, "y": y, "z": z}, label=label)
    main = f"ok [{result.get('op_id','')}]" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def rotate_object(angle: float, axis: str = "Z", label: str = "") -> str:
    """
    Rotate the active object.
    angle: degrees  |  axis: X | Y | Z
    label: optional name for the history log
    """
    result = call_blender("rotate_object", {"angle": angle, "axis": axis}, label=label)
    main = f"ok [{result.get('op_id','')}]" if result.get("success") else result.get("error", "failed")
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
def taper_end(axis: str = "Z", end: str = "MAX", label: str = "") -> str:
    """
    Collapse the extreme ring on an axis to a single point (or thin edge).

    end: MAX (highest ring on axis) | MIN (lowest ring on axis)

    The verts at that ring all snap to the ring's centroid in the two non-axis dimensions.
    Result: a tapered tip. Faster than select_ring + scale_vertices(x=0,y=0).
    Must be in edit mode.
    """
    result = call_blender("taper_end", {"axis": axis, "end": end}, label=label)
    if result.get("success"):
        main = (f"tapered ring {result['ring_index']}/{result['ring_count']-1} "
                f"({result['end']} of {result['axis']})  "
                f"collapsed {result['collapsed_verts']} verts at world={result.get('collapsed_world')}")
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


if __name__ == "__main__":
    mcp.run()

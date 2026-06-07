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


# --- Read-only tools (no label needed) ---

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
def get_viewport_collage(zoom: float = 1.0) -> Image:
    """
    Capture 6 views in one image: FRONT | RIGHT | TOP (row 1), BACK | LEFT | PERSP (row 2).
    zoom: scale factor for panel resolution. Base is 320x180 per panel (960x360 total).
          zoom=2 gives 640x360 per panel. Use higher zoom for detail inspection.
    Does not affect or replace get_viewport_screenshot.
    """
    result = call_blender("get_viewport_collage", {"zoom": zoom})
    if "error" in result:
        raise RuntimeError(result["error"])
    return Image(data=base64.b64decode(result["image"]), format="png")


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


# --- State-modifying tools (accept label) ---

@mcp.tool()
def set_viewport_angle(angle: str) -> str:
    """
    Set the viewport to a standard angle.
    angle: FRONT | BACK | LEFT | RIGHT | TOP | BOTTOM | CAMERA
    """
    result = call_blender("set_viewport_angle", {"angle": angle})
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def add_primitive(type: str, x: float = 0, y: float = 0, z: float = 0, label: str = "") -> str:
    """
    Add a mesh primitive to the scene.
    type: CUBE | SPHERE | CYLINDER | PLANE | CONE
    x, y, z: location in world space
    label: optional name for the history log
    """
    result = call_blender("add_primitive", {"type": type, "location": [x, y, z]}, label=label)
    if result.get("success"):
        return f"Added {type} as '{result['object_name']}' [{result.get('op_id','')}]"
    return result.get("error", "failed")


@mcp.tool()
def select_object(name: str) -> str:
    """Select an object by name and make it active. Use get_scene_tree first to find names."""
    result = call_blender("select_object", {"name": name})
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def scale_object(x: float = 1.0, y: float = 1.0, z: float = 1.0, label: str = "") -> str:
    """
    Scale the active object. Values are multipliers (0.5 = half size, 2.0 = double).
    label: optional name for the history log
    """
    result = call_blender("scale_object", {"x": x, "y": y, "z": z}, label=label)
    return f"ok [{result.get('op_id','')}]" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def move_object(x: float = 0.0, y: float = 0.0, z: float = 0.0, label: str = "") -> str:
    """
    Move the active object by a relative offset in world units.
    label: optional name for the history log
    """
    result = call_blender("move_object", {"x": x, "y": y, "z": z}, label=label)
    return f"ok [{result.get('op_id','')}]" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def rotate_object(angle: float, axis: str = "Z", label: str = "") -> str:
    """
    Rotate the active object.
    angle: degrees  |  axis: X | Y | Z
    label: optional name for the history log
    """
    result = call_blender("rotate_object", {"angle": angle, "axis": axis}, label=label)
    return f"ok [{result.get('op_id','')}]" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def set_mode(mode: str) -> str:
    """
    Switch the active object's interaction mode.
    mode: OBJECT | EDIT | SCULPT
    """
    result = call_blender("set_mode", {"mode": mode})
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def delete_object(name: str, label: str = "") -> str:
    """Delete an object by name. Use get_scene_tree to find object names."""
    result = call_blender("delete_object", {"name": name}, label=label)
    if result.get("success"):
        return f"Deleted '{result['deleted']}' [{result.get('op_id','')}]"
    return result.get("error", "failed")


@mcp.tool()
def frame_scene() -> str:
    """Fit all objects in the viewport."""
    result = call_blender("frame_scene")
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def zoom_to_selected() -> str:
    """Zoom the viewport to tightly frame the currently selected object."""
    result = call_blender("zoom_to_selected")
    return "ok" if result.get("success") else result.get("error", "failed")


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
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def set_camera_position(x: float, y: float, z: float,
                        target_x: float = 0.0, target_y: float = 0.0, target_z: float = 0.0) -> str:
    """Move the scene camera to a position aimed at a target point."""
    result = call_blender("set_camera_position", {
        "x": x, "y": y, "z": z,
        "target_x": target_x, "target_y": target_y, "target_z": target_z,
    })
    return "ok" if result.get("success") else result.get("error", "failed")


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
        return f"ok (offset={result.get('offset_world')}) [{result.get('op_id','')}]"
    return result.get("error", "failed")


@mcp.tool()
def extrude(x: float = 0.0, y: float = 0.0, z: float = 0.0, label: str = "") -> str:
    """
    Extrude selected geometry in edit mode and translate by a fraction of the object's dimensions.
    x/y/z: fraction of object dimension along that axis (0.5 = 50% of width/depth/height).
    Returns the actual world-space translation applied.
    """
    result = call_blender("extrude", {"x": x, "y": y, "z": z}, label=label)
    if result.get("success"):
        return f"ok translation={result.get('translation_world')} [{result.get('op_id','')}]"
    return result.get("error", "failed")


@mcp.tool()
def select_all(action: str = "SELECT") -> str:
    """
    Select/deselect geometry in edit mode.
    action: SELECT | DESELECT | INVERT
    """
    result = call_blender("select_all", {"action": action})
    return "ok" if result.get("success") else result.get("error", "failed")


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
        return f"ok (threshold_world={result.get('threshold_world')})"
    return result.get("error", "failed")


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
        return f"Moved {result['verts_moved']} verts by {result['delta_world']} [{result.get('op_id','')}]"
    return result.get("error", "failed")


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
        return f"Scaled {result['verts_scaled']} verts [{result.get('op_id','')}]"
    return result.get("error", "failed")


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
    return f"{len(profile)} rings along {ax}:\n" + "\n".join(lines)


@mcp.tool()
def get_blender_status() -> str:
    """
    Full Blender context snapshot. Call this whenever you're unsure of the current state.
    Returns: mode, active object, all selected objects, world Z range, object dimensions,
    last history action, and (in Edit Mode) component type, selection counts, and
    the world Z range of the current selection.
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
def get_object_info() -> str:
    """
    Return detailed state of the active object: location, scale, rotation, dimensions,
    world-space bounding box, and vertex/edge/face counts. Use this before making
    precise edits so you know actual coordinates and sizes.
    """
    result = call_blender("get_object_info")
    if result.get("success"):
        import json
        return json.dumps(result["info"], indent=2)
    return result.get("error", "failed")


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
        return f"Cut {result['edges_subdivided']} edges x{result['cuts']} [{result.get('op_id','')}]"
    return result.get("error", "failed")


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
        return f"{result['modifier']} [{result.get('op_id','')}]"
    return result.get("error", "failed")


@mcp.tool()
def undo(steps: int = 1) -> str:
    """
    Undo the last N operations. Updates history log to match.
    Check get_history() first to see what will be undone.
    """
    result = call_blender("undo_steps", {"steps": steps})
    if result.get("success"):
        return f"Undid {result['steps']} step(s). History remaining: {result['history_remaining']}"
    return result.get("error", "failed")


@mcp.tool()
def undo_to(id: str) -> str:
    """
    Undo back to a specific operation by its ID (from get_history).
    Everything after that ID is undone. The target operation itself is kept.
    """
    result = call_blender("undo_to", {"id": id})
    if result.get("success"):
        return f"Undid {result['steps']} step(s) to reach [{id}]"
    return result.get("error", "failed")


if __name__ == "__main__":
    mcp.run()

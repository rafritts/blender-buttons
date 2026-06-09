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
def get_viewport_screenshot(width: int = 960, height: int = 540,
                            hide_overlays: bool = False) -> Image:
    """Capture the current 3D viewport. width/height default to 960x540 to keep context usage low.
    hide_overlays: turn off selection outlines, gizmos, axis overlay etc. for clean hero shots."""
    result = call_blender("get_viewport_screenshot",
                          {"width": width, "height": height, "hide_overlays": hide_overlays})
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


@mcp.tool()
def set_viewport_shading(mode: str = "MATERIAL") -> str:
    """
    Switch the 3D viewport shading mode.
    mode: WIREFRAME | SOLID | MATERIAL | RENDERED
      - SOLID: matcap default (no materials visible)
      - MATERIAL: previews materials with built-in studio lighting (fast)
      - RENDERED: full Eevee/Cycles preview using your scene lights + world
    Required before get_viewport_screenshot if you want to see materials/lighting —
    the screenshot tool captures whatever shading mode is currently active.
    """
    result = call_blender("set_viewport_shading", {"mode": mode})
    main = f"shading → {mode}" if result.get("success") else result.get("error", "failed")
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
def add_torus(name: str, major_radius: float, minor_radius: float,
              on: dict = None,
              major_segments: int = 48, minor_segments: int = 12,
              rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
              label: str = "") -> str:
    """
    Add a torus (donut/ring) aligned to Z. The hole faces along +Z.

    major_radius: center-of-tube radius (distance from origin to tube center).
    minor_radius: tube thickness radius. Outer diameter = (major+minor)*2.
    major_segments: ring resolution.   minor_segments: tube cross-section resolution.
    on: placement spec — see PLACEMENT DSL.

    Use cases: knocker rings, washers, handles, hoops, donuts.
    To stand a ring vertically (hole facing forward), pass rot_x=90.
    """
    result = call_blender("add_torus", {
        "name": name, "major_radius": major_radius, "minor_radius": minor_radius,
        "on": on, "major_segments": major_segments, "minor_segments": minor_segments,
        "rotation_deg": [rot_x, rot_y, rot_z],
    }, label=label)
    return _add_result("TORUS", result) + _status(result)


@mcp.tool()
def add_icosphere(name: str, radius: float,
                  on: dict = None, subdivisions: int = 2,
                  rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
                  label: str = "") -> str:
    """
    Add an icosphere of exact radius in meters.
    Icosphere topology (uniform triangles) deforms more cleanly under subdiv and
    sculpt than a UV sphere — prefer it when you'll add Subsurf or push verts around.

    subdivisions: 1 (20 faces) | 2 (80) | 3 (320) | 4 (1280) | 5 (5120). Default 2.
    on: placement spec — see PLACEMENT DSL.
    """
    result = call_blender("add_icosphere", {
        "name": name, "radius": radius,
        "on": on, "subdivisions": subdivisions,
        "rotation_deg": [rot_x, rot_y, rot_z],
    }, label=label)
    return _add_result("ICOSPHERE", result) + _status(result)


@mcp.tool()
def add_circle(name: str, radius: float,
               on: dict = None, vertices: int = 32, fill_type: str = "NOTHING",
               rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
               label: str = "") -> str:
    """
    Add a flat circle in the XY plane. Useful as a 2D profile (extrude later) or
    a thin disc.

    radius:    in meters.
    vertices:  edge count around the circumference.
    fill_type: NOTHING (open ring, vertices only) | NGON (filled disc) | TRIFAN.
    on: placement spec — see PLACEMENT DSL.
    """
    result = call_blender("add_circle", {
        "name": name, "radius": radius,
        "on": on, "vertices": vertices, "fill_type": fill_type,
        "rotation_deg": [rot_x, rot_y, rot_z],
    }, label=label)
    return _add_result("CIRCLE", result) + _status(result)


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
    """Delete an object OR a group by name. If `name` is a group, every part inside
    (recursively, through nested sub-groups) is deleted and the empty group is removed.
    Use get_scene_tree to see object/group names."""
    result = call_blender("delete_object", {"name": name}, label=label)
    if result.get("success"):
        if "deleted_group" in result:
            members = result["deleted_members"]
            main = (f"Deleted group '{result['deleted_group']}' and {len(members)} part(s) "
                    f"[{result.get('op_id','')}]")
        else:
            main = f"Deleted '{result['deleted']}' [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def frame_scene(targets: str = "", include_lights: bool = False) -> str:
    """Fit objects in the viewport.

    targets: object name, group name, or comma-separated list. Empty = all mesh objects.
    include_lights: include lights/cameras in the fit (default False — they usually
                    blow out the framing and leave the subject tiny).

    Example: frame_scene("body") frames just the character; frame_scene() frames all
    mesh objects with lights excluded.
    """
    params = {"include_lights": include_lights}
    if targets:
        params["targets"] = targets
    result = call_blender("frame_scene", params)
    if result.get("success"):
        framed = result.get("framed")
        main = f"framed {framed}" if framed else "ok"
    else:
        main = result.get("error", "failed")
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
def add_camera(name: str,
               x: float = 7.0, y: float = -7.0, z: float = 5.0,
               target: str = "",
               target_x: float = 0.0, target_y: float = 0.0, target_z: float = 0.0,
               lens: float = 50.0,
               label: str = "") -> str:
    """
    Create a new camera and set it as the active scene camera.

    name:    REQUIRED — unique object name.
    x, y, z: world position (default 7, -7, 5).
    target:  optional object name to aim at; overrides target_x/y/z.
    target_x, target_y, target_z: world point to aim at (default 0, 0, 0).
    lens:    focal length in mm (default 50). 35 = wide, 85 = portrait.

    Example: add_camera("cam", x=7, y=-7, z=5, target="donut")
    """
    params = {"name": name, "x": x, "y": y, "z": z, "lens": lens,
              "target_x": target_x, "target_y": target_y, "target_z": target_z}
    if target:
        params["target"] = target
    result = call_blender("add_camera", params, label=label)
    if result.get("success"):
        main = (f"Added camera '{result['camera']}' at {result['location']} "
                f"aimed at {result['target']} lens={result['lens']}mm [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
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
def proportional_move(x: float = 0.0, y: float = 0.0, z: float = 0.0,
                      radius: float = 0.01, falloff: str = "SMOOTH",
                      label: str = "") -> str:
    """
    Move selected verts with a falloff — drags nearby verts along (proportional editing).
    Selected verts move full amount; verts at radius edge don't move at all.

    x/y/z: translation as a fraction of object dims (same as move_vertices).
    radius: falloff radius in meters (default 1cm).
    falloff: SMOOTH (default — rounded shape) | LINEAR | SPHERE | SHARP | ROOT | CONSTANT.

    For icing drips: select sparse boundary verts, proportional_move(z=-0.5, radius=0.005)
    gives bulbous rounded drops instead of triangular spikes.
    """
    result = call_blender("proportional_move", {
        "x": x, "y": y, "z": z, "radius": radius, "falloff": falloff,
    }, label=label)
    if result.get("success"):
        main = (f"pulled {result['handles']} handles, dragged {result['affected']} verts "
                f"r={result['radius']}m {result['falloff']} delta_world={result['delta_world']} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def random_select(fraction: float = 0.2, seed: int = 0, label: str = "") -> str:
    """
    Randomly thin the current edit-mode selection: keep `fraction` of selected verts,
    deselect the rest. Use to turn a uniform ring/loop into a sparse pattern
    (e.g., pick a handful of boundary verts on the icing to pull down as drip points).
    fraction: 0..1. seed: RNG seed for reproducibility.
    """
    result = call_blender("random_select", {"fraction": fraction, "seed": seed}, label=label)
    if result.get("success"):
        main = f"kept {result['kept']}/{result['from']} verts (seed={result['seed']})"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def jitter_vertices(amount: float = 0.005, axis: str = "NORMAL", seed: int = 0,
                    only_positive: bool = False, label: str = "") -> str:
    """
    Randomly displace selected vertices in edit mode — organic lumpy geometry in one call.
    amount: max displacement in meters (default 5mm).
    axis: NORMAL (puffs along each vert's normal — best for organic dough) | X | Y | Z | XYZ.
    seed: RNG seed for reproducibility.
    only_positive: if true, only displace outward (default both directions).

    Tutorial uses: jitter donut with axis=NORMAL for lumpy dough; jitter icing's bottom ring
    with axis=Z + only_positive (negative amount) for drippy edges.
    """
    result = call_blender("jitter_vertices", {
        "amount": amount, "axis": axis, "seed": seed, "only_positive": only_positive,
    }, label=label)
    if result.get("success"):
        main = (f"Jittered {result['verts_jittered']} verts along {result['axis']} "
                f"±{result['amount']}m (seed={result['seed']}) [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def inflate_selection(amount: float = 0.003, label: str = "") -> str:
    """
    Push selected verts outward along their normals by a fixed amount (sculpt 'Inflate' brush, one-shot).
    amount: meters to move along normal. Positive = outward, negative = inward (deflate). Default 3mm.

    For bulbous drip tips: after pulling tips down with proportional_move,
    select just the tip verts and inflate_selection(amount=0.003) to swell them into teardrop bulbs.
    """
    result = call_blender("inflate_selection", {"amount": amount}, label=label)
    if result.get("success"):
        main = f"inflated {result['verts_inflated']} verts by {result['amount']}m along normals"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def delete_geometry(mode: str = "VERT", label: str = "") -> str:
    """
    Delete the current selection in edit mode.
    mode: VERT | EDGE | FACE | ONLY_FACE | EDGE_FACE
      - VERT       — delete selected verts (and faces/edges touching them)
      - FACE       — delete selected faces (and the edges/verts only used by them)
      - ONLY_FACE  — delete just the faces, leaving an open hole bounded by their edges
      - EDGE_FACE  — delete edges + faces, leave verts
    Must be in edit mode. Pairs with select_by_axis/select_between for "carve away half".
    """
    result = call_blender("delete_geometry", {"mode": mode}, label=label)
    if result.get("success"):
        main = f"deleted ({mode}) [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def separate_selection(new_name: str = "", label: str = "") -> str:
    """
    Split the current edit-mode selection out as a new object (the 'P → Selection' shortcut).
    new_name: optional name for the new object. If omitted, Blender appends '.001'.
    Returns the new object's name. The original stays in edit mode; the new object is in object mode.
    """
    params = {}
    if new_name:
        params["new_name"] = new_name
    result = call_blender("separate_selection", params, label=label)
    if result.get("success"):
        main = f"separated '{result['source']}' → '{result['new_object']}' [{result.get('op_id','')}]"
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
                  y_start: float = 1.0, y_end: float = 1.0,
                  curve: str = "linear", label: str = "") -> str:
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
        "curve": curve,
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
                 width: float = 0.1, segments: int = 1,
                 target: str = "", offset: float = None,
                 wrap_method: str = "NEAREST_SURFACEPOINT",
                 axis: str = "X", merge_threshold: float = None,
                 mirror_object: str = "",
                 label: str = "") -> str:
    """
    Add a modifier to the active object.
    type: SUBSURF | BEVEL | SOLIDIFY | MIRROR | ARRAY | SCREW | SHRINKWRAP
    levels: subdivision levels (SUBSURF)  |  width/segments: bevel params
    target: required for SHRINKWRAP — the object to wrap onto.
    offset: SHRINKWRAP only — surface offset in meters (skin distance).
    wrap_method: SHRINKWRAP only —
                 NEAREST_SURFACEPOINT (default) | PROJECT | NEAREST_VERTEX | TARGET_PROJECT.
    axis: MIRROR only — any combination of X, Y, Z (default "X"). E.g. "XY" mirrors on both.
    merge_threshold: MIRROR only — weld coincident verts at the mirror plane (typical 0.001).
    mirror_object: MIRROR only — use this object's local axes as the mirror plane (defaults to self).
    """
    params = {
        "type": type, "name": name or type.capitalize(),
        "levels": levels, "render_levels": render_levels,
        "width": width, "segments": segments,
        "wrap_method": wrap_method,
        "axis": axis,
    }
    if target:
        params["target"] = target
    if offset is not None:
        params["offset"] = offset
    if merge_threshold is not None:
        params["merge_threshold"] = merge_threshold
    if mirror_object:
        params["mirror_object"] = mirror_object
    result = call_blender("add_modifier", params, label=label)
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
def join_objects(names: list, merge_threshold: float = None) -> str:
    """
    Join multiple objects into one. The first name in the list becomes the surviving object.
    names: list of object names to join (minimum 2)
    merge_threshold: if set, weld coincident verts after joining (typical 0.001 = 1mm).
                     Eliminates seam-shading artifacts on a SubSurf'd joined mesh.
    All objects must be the same type (MESH). The result keeps the first object's name.
    Must be in Object Mode.
    """
    params = {"names": names}
    if merge_threshold is not None:
        params["merge_threshold"] = merge_threshold
    result = call_blender("join_objects", params)
    if result.get("success"):
        main = f"Joined {result['joined']} → '{result['result_object']}'"
        m = result.get("merged")
        if m:
            main += f"  merged {m['merged']} verts (welded to {m['verts_after']})"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def modify_modifier(target: str, modifier_name: str,
                    levels: int = None, render_levels: int = None,
                    width: float = None, segments: int = None,
                    thickness: float = None, offset: float = None,
                    angle_limit: float = None, count: int = None,
                    wrap_method: str = "", target_object: str = "",
                    label: str = "") -> str:
    """
    Tweak properties on an existing modifier without rebuilding it.
    Use this to dial in shrinkwrap offset, bevel width, subsurf levels, etc.

    target: object name. modifier_name: name of the modifier on that object.
    Each numeric param is optional — pass only the ones you want to change.
    angle_limit is in degrees (BEVEL). target_object re-points SHRINKWRAP/ARRAY to a different object.
    wrap_method (SHRINKWRAP): NEAREST_SURFACEPOINT | PROJECT | NEAREST_VERTEX | TARGET_PROJECT.
    """
    params = {"target": target, "modifier_name": modifier_name}
    for key, val in (("levels", levels), ("render_levels", render_levels),
                     ("width", width), ("segments", segments),
                     ("thickness", thickness), ("offset", offset),
                     ("angle_limit", angle_limit), ("count", count)):
        if val is not None:
            params[key] = val
    if wrap_method:
        params["wrap_method"] = wrap_method
    if target_object:
        params["target_object"] = target_object
    result = call_blender("modify_modifier", params, label=label)
    if result.get("success"):
        applied = result.get("applied", [])
        skipped = result.get("skipped", [])
        tail = f" (skipped: {skipped})" if skipped else ""
        main = f"{result['modifier']} ({result['type']}): {applied}{tail} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def remove_modifier(target: str, modifier_name: str, label: str = "") -> str:
    """
    Remove a modifier from an object by name. Pass modifier_name='ALL' to clear them all.
    Use list_modifiers first to see what's on the object.
    """
    result = call_blender("remove_modifier",
                          {"target": target, "modifier_name": modifier_name}, label=label)
    if result.get("success"):
        main = f"removed {result['removed']} from '{result['target']}' [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def list_modifiers(target: str) -> str:
    """
    List the modifier stack on an object (top → bottom = evaluation order).
    Each entry shows type, name, and the relevant numeric props.
    """
    result = call_blender("list_modifiers", {"target": target})
    if not result.get("success"):
        return result.get("error", "failed") + _status(result)
    mods = result["modifiers"]
    if not mods:
        return f"'{result['target']}': no modifiers" + _status(result)
    lines = [f"'{result['target']}' modifier stack ({len(mods)}):"]
    for i, m in enumerate(mods):
        extras = " ".join(f"{k}={v}" for k, v in m.items() if k not in ("name", "type"))
        lines.append(f"  {i}. {m['type']:12} '{m['name']}'  {extras}")
    return "\n".join(lines) + _status(result)


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


@mcp.tool()
def scatter_on_surface(target: str, source: str, count: int = 100,
                       scale_min: float = 0.8, scale_max: float = 1.2,
                       align_normal: bool = True, rotate_z: bool = True,
                       parent_to_target: bool = True, seed: int = 0,
                       name_prefix: str = "", label: str = "") -> str:
    """
    Scatter `count` copies of `source` randomly across `target`'s surface.
    The donut-tutorial sprinkles step.

    target / source: existing mesh object names (required).
    count: number of instances (capped at 5000).
    scale_min/max: per-instance scale jitter range.
    align_normal: rotate each copy's +Z to match the surface normal at its location.
    rotate_z: also apply random spin around that normal.
    parent_to_target: parent every instance to target so they move/animate with it.
    seed: RNG seed for reproducibility.
    name_prefix: name prefix for generated objects (default "<source>_inst").

    All instances share `source`'s mesh data — cheap memory-wise. Target's
    modifiers are evaluated, so sprinkles land on the visible (post-subsurf) surface.
    """
    result = call_blender("scatter_on_surface", {
        "target": target, "source": source, "count": count,
        "scale_min": scale_min, "scale_max": scale_max,
        "align_normal": align_normal, "rotate_z": rotate_z,
        "parent_to_target": parent_to_target, "seed": seed,
        "name_prefix": name_prefix,
    }, label=label)
    if result.get("success"):
        main = (f"scattered {result['scattered']} copies of '{result['source']}' "
                f"onto '{result['target']}' (mesh '{result['source_mesh']}') "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


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
def add_to_group(name: str, parts: list, label: str = "") -> str:
    """Add objects (or members of another group) to an existing group.

    Use this as the design grows so the group always represents the whole thing.
    Example: after adding a knocker_ring to a chest, call
    add_to_group("chest", ["knocker_plate", "knocker_ring"]) — then
    delete_object("chest") or nudge("chest", ...) acts on every part, not just the originals.

    name:  existing group name (create with `group` first).
    parts: list of object names or other group names (groups expand to their members).
    """
    result = call_blender("add_to_group", {"name": name, "parts": parts}, label=label)
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
def shade_smooth(targets: str = "", auto_smooth_angle: float = 30.0, label: str = "") -> str:
    """
    Toggle smooth shading on objects (the right-click "Shade Smooth" step from the donut tutorial).
    Edges sharper than auto_smooth_angle degrees stay faceted so corners read crisp.

    targets: object name, group name, comma-separated list, or empty (active object).
    """
    t = [s.strip() for s in targets.split(",")] if targets else None
    if t and len(t) == 1:
        t = t[0]
    result = call_blender("shade_smooth", {
        "targets": t, "auto_smooth_angle": auto_smooth_angle,
    }, label=label)
    if result.get("success"):
        main = f"shade_smooth: {result['smoothed']} (angle<{auto_smooth_angle}°) [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def shade_flat(targets: str = "", label: str = "") -> str:
    """
    Restore faceted (flat) shading on objects.
    targets: object name, group name, comma-separated list, or empty (active object).
    """
    t = [s.strip() for s in targets.split(",")] if targets else None
    if t and len(t) == 1:
        t = t[0]
    result = call_blender("shade_flat", {"targets": t}, label=label)
    if result.get("success"):
        main = f"shade_flat: {result['flattened']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_material(target: str,
                 base_color: list = None,
                 metallic: float = None,
                 roughness: float = None,
                 ior: float = None,
                 alpha: float = None,
                 emission_color: list = None,
                 emission_strength: float = None,
                 material_name: str = "",
                 label: str = "") -> str:
    """
    Create or update a Principled BSDF material and assign it to `target` (slot 0).
    Covers ~80% of real materials: color, metallic, roughness, IOR, alpha, emission.

    target:        REQUIRED — object to receive the material.
    base_color:    [r, g, b] or [r, g, b, a], floats 0..1.
    metallic:      0..1 (0 = dielectric, 1 = metal).
    roughness:     0..1 (0 = mirror, 1 = chalk).
    ior:           index of refraction. Glass ≈ 1.5, water ≈ 1.33. Default 1.45.
    alpha:         0..1. Values < 1 enable BLEND transparency.
    emission_color / emission_strength: glow color and intensity.
    material_name: name for the material; defaults to "<target>_mat". Reused if exists.

    Examples:
      set_material("donut", base_color=[0.8, 0.55, 0.35], roughness=0.6)   # dough
      set_material("icing", base_color=[1.0, 0.85, 0.92], roughness=0.3)   # pink frosting
      set_material("sprinkle_1", base_color=[1, 0.1, 0.1], roughness=0.4)
    """
    params = {"target": target}
    if material_name:        params["material_name"] = material_name
    if base_color is not None:        params["base_color"] = base_color
    if metallic is not None:          params["metallic"] = metallic
    if roughness is not None:         params["roughness"] = roughness
    if ior is not None:               params["ior"] = ior
    if alpha is not None:             params["alpha"] = alpha
    if emission_color is not None:    params["emission_color"] = emission_color
    if emission_strength is not None: params["emission_strength"] = emission_strength
    result = call_blender("set_material", params, label=label)
    if result.get("success"):
        main = (f"material '{result['material']}' on '{result['target']}': "
                f"{result['applied']} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def add_light(name: str, type: str = "POINT",
              x: float = 0.0, y: float = 0.0, z: float = 5.0,
              energy: float = None, color: list = None, size: float = 0.25,
              target: str = "", spot_angle: float = 45.0,
              label: str = "") -> str:
    """
    Add a light to the scene.

    name:    REQUIRED — unique object name.
    type:    POINT | SUN | SPOT | AREA  (default POINT)
    x, y, z: world position (meters). Default (0, 0, 5).
    energy:  light strength. Defaults: 1000 for POINT/SPOT/AREA (watts), 5 for SUN.
    color:   [r, g, b] floats 0..1. Default warm white [1, 0.95, 0.9].
    size:    soft-shadow radius / AREA quad side / SPOT radius. Default 0.25 m.
    target:  optional object name to aim the light at (its -Z axis points at the target).
    spot_angle: cone angle in degrees for SPOT lights. Default 45.

    Example: add_light("key", type="AREA", x=3, y=-3, z=4, size=2.0, energy=500, target="donut")
    """
    params = {"name": name, "type": type, "x": x, "y": y, "z": z, "size": size,
              "spot_angle": spot_angle}
    if energy is not None: params["energy"] = energy
    if color is not None:  params["color"] = color
    if target:             params["target"] = target
    result = call_blender("add_light", params, label=label)
    if result.get("success"):
        main = (f"Added {result['type']} light '{result['object_name']}' at "
                f"{result['location']} energy={result['energy']} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def modify_light(name: str, energy: float = None, color: list = None,
                 size: float = None, spot_angle: float = None,
                 x: float = None, y: float = None, z: float = None,
                 target: str = "", label: str = "") -> str:
    """
    Tweak an existing light without rebuilding it. Dial energy/color/size live.
    All params optional except `name`. x/y/z move the light; target re-aims it.
    """
    params = {"name": name}
    for key, val in (("energy", energy), ("color", color), ("size", size),
                     ("spot_angle", spot_angle), ("x", x), ("y", y), ("z", z)):
        if val is not None:
            params[key] = val
    if target:
        params["target"] = target
    result = call_blender("modify_light", params, label=label)
    if result.get("success"):
        main = (f"{result['light']} ({result['type']}): {result['applied']} "
                f"now energy={result['energy']} color={result['color']} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_world_background(color: list = None, strength: float = None,
                         hdri: str = "", label: str = "") -> str:
    """
    Set the world background. Either a solid color (cheap ambient) or an HDRI image
    (image-based lighting — gives free realistic environment light + reflections).

    color:    [r, g, b] solid color, floats 0..1. Ignored if `hdri` is set.
    strength: light intensity from the background. Default 1.0.
    hdri:     path to an HDRI/EXR file. Connected as an Environment Texture.

    Examples:
      set_world_background(color=[0.05, 0.05, 0.08], strength=0.3)         # dim blue room
      set_world_background(hdri="~/hdris/studio.exr", strength=1.0)        # studio lighting
    """
    params = {}
    if color is not None:    params["color"] = color
    if strength is not None: params["strength"] = strength
    if hdri:                 params["hdri"] = hdri
    result = call_blender("set_world_background", params, label=label)
    if result.get("success"):
        if result["mode"] == "hdri":
            main = f"world: hdri={result['hdri']} strength={result['strength']}"
        elif result["mode"] == "color":
            main = f"world: color={result['color']} strength={result['strength']}"
        else:
            main = f"world: unchanged (strength={result['strength']})"
        main += f" [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_camera_dof(focus_distance: float = None, aperture: float = None,
                   focus_object: str = "", camera: str = "", label: str = "") -> str:
    """
    Enable depth of field on the scene camera (the blurry-background look).

    focus_distance: meters from camera to focal plane. Ignored if focus_object is set.
    focus_object:   object to focus on (auto-tracks its distance).
    aperture:       f-stop. Lower = shallower DoF. 1.4 (very shallow) | 2.8 (portrait) | 8 (deep).
    camera:         camera object name. Empty = scene camera.

    Example: set_camera_dof(focus_object="donut", aperture=2.8)
    """
    params = {}
    if focus_distance is not None: params["focus_distance"] = focus_distance
    if aperture is not None:       params["aperture"] = aperture
    if focus_object:               params["focus_object"] = focus_object
    if camera:                     params["camera"] = camera
    result = call_blender("set_camera_dof", params, label=label)
    if result.get("success"):
        main = (f"DoF on '{result['camera']}': "
                f"focus_object={result['focus_object']} "
                f"focus_distance={result['focus_distance']} "
                f"f/{result['aperture_fstop']} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


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


@mcp.tool()
def mark_sharp(clear: bool = False, label: str = "") -> str:
    """Mark selected edges as sharp (or clear) in edit mode. Required after SubSurf so
    boxy details (hand/foot edges, jaw line) stay crisp instead of melting into blobs.
    Switch to EDGE component mode first."""
    result = call_blender("mark_sharp", {"clear": clear}, label=label)
    if result.get("success"):
        verb = "cleared" if clear else "marked"
        main = f"{verb} sharp on {result['edges_marked']} edge(s) [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_edge_crease(weight: float = 1.0, label: str = "") -> str:
    """Set the SubSurf edge-crease weight on selected edges in edit mode.
    weight: 0..1. 0 = no crease (smooth), 1 = perfectly sharp under SubSurf.
    Use to preserve hard edges on boxy hands/feet/jaws when a SubSurf modifier is active."""
    result = call_blender("set_edge_crease", {"weight": weight}, label=label)
    if result.get("success"):
        main = f"creased {result['edges_creased']} edge(s) at weight={result['weight']}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def merge_by_distance(threshold: float = 0.001, selected_only: bool = False,
                      label: str = "") -> str:
    """Weld coincident vertices in edit mode.
    After join_objects, run this to fuse the seams between formerly-separate meshes so
    SubSurf treats the result as one continuous skin instead of N disconnected pieces.
    threshold: weld distance in meters (default 1mm).
    selected_only: only merge currently-selected verts. Default: whole mesh."""
    result = call_blender("merge_by_distance",
                          {"threshold": threshold, "selected_only": selected_only}, label=label)
    if result.get("success"):
        main = (f"merged {result['merged']} verts (before={result['verts_before']} "
                f"after={result['verts_after']}, threshold={result['threshold']}m)")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_in_sphere(center_x: float, center_y: float, center_z: float, radius: float,
                     action: str = "SELECT") -> str:
    """Select edit-mode vertices inside a world-space sphere. The right tool for localized
    region edits on a joined mesh (push out the bust, inflate the brow ridge, etc.) when
    ring-based addressing won't reach the area.

    center_x/y/z: world coords. radius: meters. action: SELECT | ADD | DESELECT.
    Pair with proportional_move or inflate_selection to sculpt the region."""
    result = call_blender("select_in_sphere", {
        "center": [center_x, center_y, center_z], "radius": radius, "action": action,
    })
    if result.get("success"):
        main = (f"{action} {result['selected']} verts within {result['radius']}m of "
                f"{result['center']}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def split_by_part(label: str = "") -> str:
    """Split the active mesh into separate objects, one per connected component
    (P → By Loose Parts). Restores per-part addressability after a join_objects."""
    result = call_blender("split_by_part", {}, label=label)
    if result.get("success"):
        main = (f"split '{result['source']}' into {result['part_count']} parts; "
                f"new objects: {result['new_objects']}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def add_floor(name: str = "floor", size: float = 10.0, label: str = "") -> str:
    """Add a large ground plane at z=0 for character-modeling reference + shadow catching.
    name: object name (default 'floor'). size: side length in meters (default 10)."""
    result = call_blender("add_floor", {"name": name, "size": size}, label=label)
    return _add_result("FLOOR", result) + _status(result)


@mcp.tool()
def add_primitives(specs: list, label: str = "") -> str:
    """Bulk-add primitives in one call — collapses 16 round-trips into 1.
    Each spec is a dict: {"type": "box|plane|cylinder|sphere|cone|torus|icosphere|circle",
                          "name": "...", ...primitive-specific params...}.
    Param names match the single-primitive tools (width/depth/height, radius, on=..., etc.).

    Example:
      add_primitives(specs=[
        {"type": "box", "name": "torso", "width": 0.4, "depth": 0.2, "height": 0.6, "on": {"on_floor": True}},
        {"type": "sphere", "name": "head", "radius": 0.12, "on": {"on": "torso"}},
      ])
    """
    result = call_blender("add_primitives", {"specs": specs}, label=label)
    if result.get("success"):
        names = [c["name"] for c in result["created"]]
        main = f"added {result['count']} primitives: {names} [{result.get('op_id','')}]"
    else:
        partial = result.get("created", [])
        main = f"{result.get('error', 'failed')}  (created so far: {[c['name'] for c in partial]})"
    return main + _status(result)


# --- Sculpt brushes ---
# All sculpt_* tools accept a world-space brush center (at_x/y/z) and radius in
# meters, plus a falloff curve. They work on the named target object whether or
# not it's currently active — no need to be in edit mode. If the mesh is too
# coarse to register the brush, pass subdivide=True to add density first.


def _sculpt_result(brush: str, result: dict) -> str:
    if result.get("success"):
        sub = result.get("subdivided_edges", 0)
        sub_note = f" (+{sub} edges subdivided)" if sub else ""
        verts = result.get("verts_affected", result.get("verts_per_pass", "?"))
        if "iterations" in result and "verts_per_pass" in result:
            head = f"{brush}: {result['iterations']} iterations × {verts} verts{sub_note}"
        else:
            head = f"{brush}: affected {verts} verts{sub_note}"
        warn = result.get("warning")
        if warn:
            head += f"\n  ⚠ {warn}"
        return head
    return result.get("error", "failed")


@mcp.tool()
def sculpt_grab(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                to_x: float, to_y: float, to_z: float,
                falloff: str = "SMOOTH", subdivide: bool = False,
                label: str = "") -> str:
    """Pull a region of `target` toward a world-space point.

    Verts at the brush center (at_x, at_y, at_z) move by the full offset (to - at);
    verts at radius edge don't move; everything between interpolates by falloff.
    Use this to drag clay from one point to another — bulge a cheekbone, pull a
    handle outward, lift a brow.

    falloff: SMOOTH | LINEAR | SPHERE | SHARP | ROOT | CONSTANT.
    subdivide: if the mesh is too coarse in the brush region, set True to locally
               subdivide edges before sculpting.
    """
    result = call_blender("sculpt_grab", {
        "target": target, "at": [at_x, at_y, at_z], "to": [to_x, to_y, to_z],
        "radius": radius, "falloff": falloff, "subdivide": subdivide,
    }, label=label)
    return _sculpt_result("grab", result) + _status(result)


@mcp.tool()
def sculpt_inflate(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                   amount: float, falloff: str = "SMOOTH", subdivide: bool = False,
                   label: str = "") -> str:
    """Push verts along their OWN normals — organic bulge or deflate.

    amount: meters along each vert's normal. Positive = outward (bulge),
            negative = inward (deflate). Differs from sculpt_draw because each
            vert moves along its own surface normal, so curved areas bulge
            outward in their natural direction.
    """
    result = call_blender("sculpt_inflate", {
        "target": target, "at": [at_x, at_y, at_z], "radius": radius,
        "amount": amount, "falloff": falloff, "subdivide": subdivide,
    }, label=label)
    return _sculpt_result("inflate", result) + _status(result)


@mcp.tool()
def sculpt_draw(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                amount: float, normal_x: float = 0.0, normal_y: float = 0.0,
                normal_z: float = 0.0, falloff: str = "SMOOTH",
                subdivide: bool = False, label: str = "") -> str:
    """Push verts along a SINGLE averaged normal — uniform-direction ridge or dent.

    amount: meters along the averaged normal. Signed.
    normal_x/y/z: optional world-space normal override. If all three are 0, the
                  average of vert normals in the region is used. Override when
                  the surface is curved enough that the average is unstable, or
                  when you want a specific direction (e.g. [0, 0, 1] to push up).
    """
    normal = [normal_x, normal_y, normal_z] if any([normal_x, normal_y, normal_z]) else None
    params = {"target": target, "at": [at_x, at_y, at_z], "radius": radius,
              "amount": amount, "falloff": falloff, "subdivide": subdivide}
    if normal is not None:
        params["normal"] = normal
    result = call_blender("sculpt_draw", params, label=label)
    return _sculpt_result("draw", result) + _status(result)


@mcp.tool()
def sculpt_smooth(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                  iterations: int = 1, falloff: str = "SMOOTH",
                  subdivide: bool = False, label: str = "") -> str:
    """Laplacian relax — pull each vert toward the centroid of its neighbors.

    iterations: how many smoothing passes. More iterations = more relaxation.
                There's no `amount` parameter — strength is iterations × falloff.
    """
    result = call_blender("sculpt_smooth", {
        "target": target, "at": [at_x, at_y, at_z], "radius": radius,
        "iterations": iterations, "falloff": falloff, "subdivide": subdivide,
    }, label=label)
    return _sculpt_result("smooth", result) + _status(result)


@mcp.tool()
def sculpt_crease(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                  amount: float, falloff: str = "SHARP", subdivide: bool = False,
                  label: str = "") -> str:
    """Pull verts toward the brush center — sharp folds, valleys, seams.

    Default falloff is SHARP because the whole point is a tight fold; pass
    falloff='SMOOTH' for a softer crease.

    amount: meters of pull toward center. Positive = pull in (valley),
            negative = push out (ridge).
    """
    result = call_blender("sculpt_crease", {
        "target": target, "at": [at_x, at_y, at_z], "radius": radius,
        "amount": amount, "falloff": falloff, "subdivide": subdivide,
    }, label=label)
    return _sculpt_result("crease", result) + _status(result)


@mcp.tool()
def sculpt_pinch(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                 amount: float, falloff: str = "SMOOTH", subdivide: bool = False,
                 label: str = "") -> str:
    """Pull verts radially inward in their TANGENT PLANE — tightens without raising.

    Unlike crease (which moves verts toward the center directly), pinch projects
    the toward-center direction onto each vert's tangent plane. The surface
    puckers without changing its average height — good for tightening features
    like lip corners, fabric folds, or pinching a sphere into a teardrop.

    amount: meters of in-plane pull. Positive = inward, negative = outward.
    """
    result = call_blender("sculpt_pinch", {
        "target": target, "at": [at_x, at_y, at_z], "radius": radius,
        "amount": amount, "falloff": falloff, "subdivide": subdivide,
    }, label=label)
    return _sculpt_result("pinch", result) + _status(result)


@mcp.tool()
def sculpt_flatten(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                   amount: float = 1.0,
                   plane_normal_x: float = 0.0, plane_normal_y: float = 0.0,
                   plane_normal_z: float = 0.0,
                   falloff: str = "SMOOTH", subdivide: bool = False,
                   label: str = "") -> str:
    """Project verts toward an average plane through the brush center — smooth out bumps.

    amount: 0..1 blend toward the plane (default 1.0 = fully flatten).
            Negative values push AWAY from the plane (amplify bumps).
    plane_normal_x/y/z: optional world-space plane normal override. If all three
                        are 0, the average of vert normals in the region is used.
                        Pass an override for "flatten against THIS plane"
                        (e.g. [0, 0, 1] to flatten against the ground plane).
    """
    plane = [plane_normal_x, plane_normal_y, plane_normal_z] \
        if any([plane_normal_x, plane_normal_y, plane_normal_z]) else None
    params = {"target": target, "at": [at_x, at_y, at_z], "radius": radius,
              "amount": amount, "falloff": falloff, "subdivide": subdivide}
    if plane is not None:
        params["plane_normal"] = plane
    result = call_blender("sculpt_flatten", params, label=label)
    return _sculpt_result("flatten", result) + _status(result)


if __name__ == "__main__":
    mcp.run()

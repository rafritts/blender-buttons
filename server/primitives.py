from server._core import mcp, call_blender, _status, _add_result


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

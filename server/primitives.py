from typing import Union

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
#   Mirror (center copied from another object, one axis flipped):
#     {"mirror_of": "thigh_R", "axis": "X"}  → center = thigh_R's center with X negated
#
#   Absolute coordinates (the ripcord — prefer relational keys when an anchor exists):
#     {"at": [x, y, z]}                → center at the literal world coordinate
#     {"x": 0.085} / {"y": ...} / {"z": ...}  → override just that center axis,
#                                       applied AFTER relational keys (combine freely)
#
#   Z overrides (applied last; win conflicts with the above):
#     {"on_floor":  true}              → bottom of new = Z 0
#     {"raise_to":  0.45}              → bottom of new = Z 0.45  (literal Z — ripcord)
#
#   Modifier:
#     {"gap": 0.01}                    → spacing for on/under/left_of/etc.
#
#   Unknown keys are rejected with an error (no silent ignores).
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
    rot_x/y/z: optional rotation in degrees. Placement is rotation-aware: a
            rotated primitive still rests/sits flush where the `on` spec says
            (the post-rotation bounding box is what gets placed).
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
    rot_x/y/z: rotation in degrees; placement stays flush (resolved against the
            post-rotation bounding box, not the unrotated one).
    """
    result = call_blender("add_plane", {
        "name": name, "width": width, "depth": depth,
        "on": on, "rotation_deg": [rot_x, rot_y, rot_z],
    }, label=label)
    return _add_result("PLANE", result) + _status(result)


@mcp.tool()
def add_cylinder(name: str, radius: float, height: float,
                 on: dict = None, segments: int = None, vertices: int = 32,
                 cap_fill: str = "NGON",
                 rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
                 label: str = "") -> str:
    """
    Add a cylinder aligned to Z. Exact radius and height in meters.
    For a TAPERED cylinder (different top/bottom radii) use add_cone(radius_top=...).
    segments: edge count around the circumference (more = smoother). Default 32.
            `vertices` is accepted as an alias.
    cap_fill: NGON | TRIFAN | NOTHING.
    on: placement spec — see PLACEMENT DSL.
    rot_x/y/z: rotation in degrees; placement stays flush (resolved against the
            post-rotation bounding box, not the unrotated one).
    """
    params = {
        "name": name, "radius": radius, "height": height,
        "on": on, "vertices": vertices, "cap_fill": cap_fill,
        "rotation_deg": [rot_x, rot_y, rot_z],
    }
    if segments is not None:
        params["segments"] = segments
    result = call_blender("add_cylinder", params, label=label)
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
    rot_x/y/z: rotation in degrees; placement stays flush (resolved against the
            post-rotation bounding box, not the unrotated one).
    """
    result = call_blender("add_sphere", {
        "name": name, "radius": radius,
        "on": on, "segments": segments, "rings": rings,
        "rotation_deg": [rot_x, rot_y, rot_z],
    }, label=label)
    return _add_result("SPHERE", result) + _status(result)


@mcp.tool()
def add_cone(name: str, radius_bottom: float, height: float, radius_top: float = 0.0,
             on: dict = None, segments: int = None, vertices: int = 32,
             cap_fill: str = "NGON",
             rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
             label: str = "") -> str:
    """
    Add a cone (or truncated cone) aligned to Z.
    radius_bottom: base radius in meters.   radius_top: top radius (0 = sharp point).
    height: total Z extent in meters.
    segments: edge count around the circumference (more = smoother). Default 32.
            `vertices` is accepted as an alias.
    on: placement spec — see PLACEMENT DSL.
    rot_x/y/z: rotation in degrees; placement stays flush (resolved against the
            post-rotation bounding box, not the unrotated one).
    """
    params = {
        "name": name, "radius_bottom": radius_bottom, "radius_top": radius_top,
        "height": height, "on": on, "vertices": vertices, "cap_fill": cap_fill,
        "rotation_deg": [rot_x, rot_y, rot_z],
    }
    if segments is not None:
        params["segments"] = segments
    result = call_blender("add_cone", params, label=label)
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
    To stand a ring vertically (hole facing forward), pass rot_x=90. Placement
    stays flush — it resolves against the post-rotation bounding box.
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
    rot_x/y/z: rotation in degrees; placement stays flush (resolved against the
            post-rotation bounding box, not the unrotated one).
    """
    result = call_blender("add_icosphere", {
        "name": name, "radius": radius,
        "on": on, "subdivisions": subdivisions,
        "rotation_deg": [rot_x, rot_y, rot_z],
    }, label=label)
    return _add_result("ICOSPHERE", result) + _status(result)


@mcp.tool()
def add_circle(name: str, radius: float,
               on: dict = None, segments: int = None, vertices: int = 32,
               fill_type: str = "NOTHING",
               rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
               label: str = "") -> str:
    """
    Add a flat circle in the XY plane. Useful as a 2D profile (extrude later) or
    a thin disc.

    radius:    in meters.
    segments:  edge count around the circumference. Default 32. `vertices` is
               accepted as an alias.
    fill_type: NOTHING (open ring, vertices only) | NGON (filled disc) | TRIFAN.
    on: placement spec — see PLACEMENT DSL.
    rot_x/y/z: rotation in degrees; placement stays flush (resolved against the
            post-rotation bounding box, not the unrotated one).
    """
    params = {
        "name": name, "radius": radius,
        "on": on, "vertices": vertices, "fill_type": fill_type,
        "rotation_deg": [rot_x, rot_y, rot_z],
    }
    if segments is not None:
        params["segments"] = segments
    result = call_blender("add_circle", params, label=label)
    return _add_result("CIRCLE", result) + _status(result)


@mcp.tool()
def spline_tube(name: str, points: list, radius: Union[float, list] = 0.02,
                resolution: int = 8, sides: int = 4, label: str = "") -> str:
    """
    Create a tube mesh swept along a smooth curve that passes THROUGH every
    control point (interpolating spline — no Bezier handles). The go-to tool for
    hair strands, cables, ribbons, handles, branches, and any curved organic shape.

    name:    REQUIRED — object name (must be unique).
    points:  2–32 control points the curve passes through. Each is either
             [x, y, z] world coords (ripcord), or
             {"near": "object_name", "offset": [dx, dy, dz]} — anchored to an
             existing object's bbox center, resolved once at creation.
    radius:  tube radius in meters. A single number, OR a list with one radius
             per control point for taper (e.g. [0.03, 0.02, 0.005] = thick root
             to thin tip — a hair strand).
    resolution: curve samples per segment (default 8; raise for tight bends).
    sides:   cross-section smoothness (default 4 ≈ 16-sided tube).

    The result is a normal mesh object — group it, material it, mirror it like
    any primitive. describe() reports the through-points for later adjustment.

    Example — hair strand from scalp to shoulder, curving outward:
      spline_tube("hair_strand_R",
                  points=[{"near": "head", "offset": [0.08, 0, 0.05]},
                          [0.14, -0.02, 1.35],
                          [0.11, -0.04, 1.15]],
                  radius=[0.025, 0.018, 0.004])
    """
    result = call_blender("spline_tube", {
        "name": name, "points": points, "radius": radius,
        "resolution": resolution, "sides": sides,
    }, label=label)
    if result.get("success"):
        main = (f"Added SPLINE_TUBE as '{result['object_name']}' through "
                f"{len(result['points'])} points, length={result['length']}m, "
                f"radii={result['radii']}, dims={result.get('dimensions')} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def add_curve(name: str, points: list, type: str = "BEZIER", cyclic: bool = False,
              resolution: int = 12, bevel_depth: float = 0.0, label: str = "") -> str:
    """
    Create a LIVE curve object (a real Bézier/NURBS/POLY datablock), not a baked
    mesh. Use this when you need an editable curve in the scene: a camera DOLLY
    PATH (set it as a Follow Path constraint target), a bevel/taper profile, or a
    distribution control for scattering. For a one-shot swept TUBE MESH (hair,
    cable, handle), use spline_tube instead — that bakes straight to geometry.

    name:        object name (required, unique).
    points:      2+ control points. Each is [x, y, z] world coords,
                 {"near": "object", "offset": [dx, dy, dz]} (positioned once at
                 creation), or a dict carrying a live ANCHOR:
                   {"at": [x,y,z], "anchor": {"object": "winch_drum"}}
                   {"anchor": {"bone": "catapult_rig/arm_swing"}}   # pos = bone head
                 An anchored point gets a Hook modifier and FOLLOWS that object/bone
                 when it moves or poses — a rope/cable/hose/chain that stretches
                 between a drum and a swinging arm. Anchor any point (both ends, a
                 sag midpoint, or just one). Unanchored points stay in world space
                 and the curve interpolates through them. IMPORTANT: create the
                 curve with the rig in its REST pose — the hook captures each point
                 in the bone's rest space, so anchoring while posed bakes in an
                 offset. Add bevel_depth to give the rope thickness.
    type:        BEZIER (default — smooth, auto-handles pass through each point) |
                 NURBS (smooth, approximating) | POLY (straight line segments).
    cyclic:      True closes the curve into a loop.
    resolution:  eval subdivisions per segment (default 12; raise for smoother).
    bevel_depth: round-bevel radius in meters. >0 gives the curve thickness so it
                 renders as a solid tube; 0 (default) leaves a zero-width path.

    An anchored curve is a LIVE rig accessory. For a game-ready mesh, pose the rig
    then bake it with convert_to_mesh(this curve) — one call evaluates the hooks
    AND the bevel into texturable geometry. (apply_modifiers alone leaves it a
    CURVE, which set_textured_material still can't UV cleanly.)

    Example — camera dolly arc: add_curve("dolly", points=[[6,-6,3],[0,-8,3],[-6,-6,3]],
                                          type="BEZIER")
    Example — catapult rope (drum→arm), 2cm thick:
      add_curve("rope", type="NURBS", bevel_depth=0.02, points=[
        {"anchor": {"object": "winch_drum"}},
        {"at": [0, 0.5, 1.2]},                          # sag midpoint, stays put
        {"anchor": {"bone": "catapult_rig/arm_swing"}}])
    """
    result = call_blender("add_curve", {
        "name": name, "points": points, "type": type, "cyclic": cyclic,
        "resolution": resolution, "bevel_depth": bevel_depth,
    }, label=label)
    if result.get("success"):
        main = (f"Added {result['type']} curve '{result['object_name']}' "
                f"({result['control_points']} pts"
                f"{', cyclic' if result['cyclic'] else ''}"
                f"{', bevel ' + str(result['bevel_depth']) + 'm' if result['bevel_depth'] else ''}) "
                f"dims={result['dimensions']} [{result.get('op_id','')}]")
        for a in result.get("anchored", []):
            tgt = f"{a['target']}/{a['bone']}" if a.get("bone") else a["target"]
            main += f"\n  ⚓ point {a['point']} hooked to {tgt} (follows when posed)"
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

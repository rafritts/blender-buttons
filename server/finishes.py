from server._core import mcp, call_blender, _status, _targets


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
    result = call_blender("smooth_edges", {
        "targets": _targets(targets), "width": width, "segments": segments, "angle_limit": angle_limit,
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
    result = call_blender("shade_smooth", {
        "targets": _targets(targets), "auto_smooth_angle": auto_smooth_angle,
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
    result = call_blender("shade_flat", {"targets": _targets(targets)}, label=label)
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

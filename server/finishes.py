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
def bend(targets: str, angle: float, axis: str = "X", apply: bool = True,
         label: str = "") -> str:
    """
    Bend objects into an arc — the one-call curving verb. Tapered cylinder + bend
    = curved hair lock, bent limb, banana, rocker rail.

    targets: object name, group name, or comma-separated list.
    angle:   bend angle in degrees. 30–60 = gentle arc, 90 = quarter turn,
             180 = U shape. Negative flips direction.
    axis:    the axis to bend AROUND (X | Y | Z, local). A vertical object bends
             into a C in the plane perpendicular to this axis: X curls it
             forward/back, Y left/right.
    apply:   bake into the mesh (default True). False keeps the modifier live
             so modify_modifier can adjust the angle later. (apply=True forces
             OBJECT mode — handy as an escape hatch out of Edit mode.)

    PIVOT: the bend pivots about the object's ORIGIN and is SYMMETRIC about it —
    geometry on both sides curls equally, growing with distance from the origin.
    A part centred on its origin humps both ways (the "mustache"), NOT a single
    tilted arc; move the origin to one end first for a clean one-way crescent.

    Bending needs segments along the length to look smooth — if the result is
    faceted, run loop_cut(axis=Z, cuts=8, target=<name>) first and bend again.

    Example: bend("hair_lock_R", angle=40, axis="Y") — curl a hair strand outward.
    """
    result = call_blender("bend", {
        "targets": _targets(targets), "angle": angle, "axis": axis, "apply": apply,
    }, label=label)
    if result.get("success"):
        main = (f"bent {[b['name'] for b in result['bent']]} by {angle}° around {axis}"
                f"{' (applied)' if result.get('applied') else ' (live modifier)'} "
                f"[{result.get('op_id','')}]")
        for warning in result.get("warnings", []):
            main += f"\n⚠ {warning}"
        return main + _status(result)
    return result.get("error", "failed")


@mcp.tool()
def noise_displace(target: str = "", strength: float = 0.05, scale: float = 0.5,
                   detail: int = 2, direction: str = "NORMAL", apply: bool = True,
                   label: str = "") -> str:
    """
    Coherent organic surface noise (G55) — break a soft form up into LUMPS with a
    DISPLACE modifier driven by a procedural noise texture.

    The difference from edit op=jitter: jitter is per-vertex WHITE noise (each vert
    hops on its own → spiky, incoherent), this samples a SMOOTH noise field so
    neighbouring verts move together → real lumps. The move for foliage canopies,
    terrain, bark, rock. Noise is sampled in WORLD space, so copies at different
    positions break up differently for free (scattered bushes won't look identical).

    target:    mesh to break up (empty = active).
    strength:  ≈ peak displacement in meters (default 0.05). The amount.
    scale:     feature size (default 0.5). Larger = bigger, broader lumps; smaller =
               finer, busier detail.
    detail:    extra octaves of finer noise on top of the big lumps (default 2).
    direction: NORMAL (default — push along each vert's normal, the organic puff) |
               X | Y | Z.
    apply:     bake into the mesh (default True). False keeps the modifier live.

    NEEDS RESOLUTION: displacement only moves existing verts — a coarse primitive
    barely ripples. remesh / loop_cut / subdivide first. Rigged/keyed meshes refused
    when apply=True (duplicate + strip first, or apply=False).
    """
    result = call_blender("noise_displace", {
        "target": target, "strength": strength, "scale": scale, "detail": detail,
        "direction": direction, "apply": apply,
    }, label=label)
    if result.get("success"):
        state = "baked" if result.get("applied") else f"live modifier '{result.get('modifier')}'"
        return (f"noise_displace '{result['object']}' strength={strength}m scale={scale} "
                f"dir={result['direction']} ({state}): dims {result['dims_before']} → "
                f"{result['dims_after']} [{result.get('op_id','')}]" + _status(result))
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
def set_material(target: str = "",
                 base_color: list = None,
                 hex: str = "",
                 metallic: float = None,
                 roughness: float = None,
                 ior: float = None,
                 alpha: float = None,
                 emission_color: list = None,
                 emission_strength: float = None,
                 material_name: str = "",
                 material: str = "",
                 slot: int = None,
                 label: str = "") -> str:
    """
    Create or update a Principled BSDF material and assign it. Covers ~80% of real
    materials: color, metallic, roughness, IOR, alpha, emission.

    target:        object OR group name. Group expands to every mesh inside
                   (recursively). Material is assigned to slot 0 by default.
    material:      address an EXISTING material datablock by NAME, with NO target —
                   restyle a shared material everywhere it's used in one call
                   (e.g. material="iron_mat" recolors all 4 wheels + arm at once).
    slot:          with a target, operate on this material SLOT index instead of 0.
                   Without material_name this edits the material already in that slot
                   in place — the way to change a multi-slot mesh's SECONDARY
                   material (wheel: wood in slot 0, iron rim in slot 1).
    base_color:    [r, g, b] or [r, g, b, a], floats 0..1 (scene-linear).
    hex:           "#RRGGBB" or "#RRGGBBAA" sRGB color (as picked from a
                   reference image / color picker). Converted to scene-linear
                   internally — use this instead of base_color when matching a
                   reference, or the color renders far too pale. Overrides base_color.
    metallic:      0..1 (0 = dielectric, 1 = metal).
    roughness:     0..1 (0 = mirror, 1 = chalk).
    ior:           index of refraction. Glass ≈ 1.5, water ≈ 1.33. Default 1.45.
    alpha:         0..1. Values < 1 enable BLEND transparency.
    emission_color / emission_strength: glow color and intensity.
    material_name: name for the material; defaults to "<target>_mat". Reused if exists.

    Examples:
      set_material("donut", base_color=[0.8, 0.55, 0.35], roughness=0.6)   # dough
      set_material(material="iron_mat", roughness=0.25, metallic=1.0)       # restyle shared
      set_material("wheel_FL", slot=1, hex="#3a3a40")                       # the iron rim
    """
    params = {}
    # Route `target` through the shared parser so a comma list / group name expands
    # like every other verb (G27) — "a,b,c" → ["a","b","c"], "" → omitted.
    tgt = _targets(target)
    if tgt is not None:      params["target"] = tgt
    if material:             params["material"] = material
    if slot is not None:     params["slot"] = slot
    if material_name:        params["material_name"] = material_name
    if hex:                  params["hex"] = hex
    if base_color is not None:        params["base_color"] = base_color
    if metallic is not None:          params["metallic"] = metallic
    if roughness is not None:         params["roughness"] = roughness
    if ior is not None:               params["ior"] = ior
    if alpha is not None:             params["alpha"] = alpha
    if emission_color is not None:    params["emission_color"] = emission_color
    if emission_strength is not None: params["emission_strength"] = emission_strength
    result = call_blender("set_material", params, label=label)
    if result.get("success"):
        if result.get("edited_in_place"):
            where = "in place (all users updated)"
        else:
            slot_str = f" slot {result['slot']}" if result.get("slot") is not None else ""
            where = f"on '{result.get('target')}'{slot_str}"
        main = (f"material '{result['material']}' {where}: "
                f"{result['applied']} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)

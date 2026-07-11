from server._core import mcp, call_blender, _status, _targets


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
                 transmission: float = None,
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
    alpha:         0..1. Values < 1 enable BLEND transparency (flat, non-refracting).
    transmission:  0..1. The refractive-SOLID dial — glass, gems, lenses, water that
                   BEND light (unlike alpha). Pair with `ior`; `roughness` blurs it
                   (frosted glass). >0 auto-enables the material's refraction flags;
                   the engine still needs raytracing on to show it in the render.
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
    if transmission is not None:      params["transmission"] = transmission
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


def assign_material(target: str = "", material: str = "", base_color: list = None,
                    hex: str = "", metallic: float = None, roughness: float = None,
                    material_name: str = "", label: str = "") -> str:
    """
    Paint a material onto the LIVE edit-mode FACE SELECTION of `target` — the per-region
    primitive `set_material` isn't (it colours a whole object/slot). Select the faces
    first (any `select` op), then assign. The material is either an EXISTING one named
    by `material=`, or a fresh one minted from `base_color`/`hex` (+ metallic/roughness/
    material_name). A slot is reused if the material is already on the mesh, else appended
    — other slots and their faces are left alone.

    Example — a brown rim band on a plate:
      select(op="by_radius", target="plate", ...)        # grab the rim ring
      material(op="assign", target="plate", hex="#5a3a22", material_name="rim_brown")
    """
    params = {"target": target}
    if material:                params["material"] = material
    if material_name:           params["material_name"] = material_name
    if hex:                     params["hex"] = hex
    if base_color is not None:  params["base_color"] = base_color
    if metallic is not None:    params["metallic"] = metallic
    if roughness is not None:   params["roughness"] = roughness
    result = call_blender("assign_material", params, label=label)
    if result.get("success"):
        slot = ("minted slot %d" % result["slot"]) if result.get("slot_minted") \
            else ("slot %d" % result.get("slot"))
        main = (f"assigned '{result['material']}' to {result['faces_assigned']} face(s) "
                f"of '{result.get('target')}' ({slot}) [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)

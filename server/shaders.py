from server._core import mcp, call_blender, _status


@mcp.tool()
def set_toon_material(target: str,
                      base_color: list = None,
                      shadow_color: list = None,
                      bands: int = 2,
                      shadow_softness: float = 0.05,
                      rim_color: list = None,
                      rim_width: float = 0.2,
                      gradient_top: list = None,
                      gradient_bottom: list = None,
                      material_name: str = "",
                      label: str = "") -> str:
    """
    Apply an anime/cel-shaded material — flat color quantized into hard shading
    bands, the Genshin/Wuthering-Waves look. Built as one fixed node graph.

    EEVEE ONLY: uses a Shader-to-RGB node, which Cycles does not support — Cycles
    renders of this material will look wrong. Colors are scene-linear floats 0..1
    (same convention as set_material).

    target:          object OR group name (group expands to every mesh inside).
    base_color:      [r,g,b(,a)] flat surface color. Required unless BOTH
                     gradient_top and gradient_bottom are supplied.
    shadow_color:    darkest band color. Default = base scaled ~0.55, biased cool
                     (anime shadows are cool, not black).
    bands:           number of hard shading steps (>=1). 2-3 reads cleanest.
    shadow_softness: 0..1, widens the darkest band (hard cel banding can't do a
                     true soft terminator, so this just nudges the boundary).
    rim_color:       optional rim-light color added at grazing silhouette edges.
    rim_width:       0..1 fraction of the silhouette the rim covers (default 0.2).
    gradient_top /   optional vertical object-space gradient that REPLACES the
    gradient_bottom: flat base color (e.g. brighter hair toward the tips).
    material_name:   defaults to "<target>_toon"; reused/updated in place if present.

    Pair with add_outline() for the full inked-cartoon look. Also run
    set_color_management(view_transform="Standard") — the default AgX transform
    filmically mutes these flat colors and the cel banding, so toon work looks
    washed out until you switch to Standard.
    Example: set_toon_material("hair", base_color=[0.55,0.2,0.6], bands=3, rim_color=[1,1,1])
    """
    params = {"target": target, "bands": bands, "shadow_softness": shadow_softness,
              "rim_width": rim_width}
    if base_color is not None:      params["base_color"] = base_color
    if shadow_color is not None:    params["shadow_color"] = shadow_color
    if rim_color is not None:       params["rim_color"] = rim_color
    if gradient_top is not None:    params["gradient_top"] = gradient_top
    if gradient_bottom is not None: params["gradient_bottom"] = gradient_bottom
    if material_name:               params["material_name"] = material_name
    result = call_blender("set_toon_material", params, label=label)
    if result.get("success"):
        main = (f"toon material '{result['material']}' on '{result['target']}' "
                f"({result['bands']} bands) → {result['assigned_to']} "
                f"[{result.get('op_id','')}]\n⚠ {result['note']}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def add_outline(target: str, thickness: float = 0.01, color: list = None,
                label: str = "") -> str:
    """
    Add a cartoon outline by the inverted-hull method — a flipped-normal,
    backface-culled emission shell grown off the object's own geometry. No
    duplicate object is created. Pair with set_toon_material for the full
    inked-cartoon look.

    target:    object OR group name (group expands to every mesh inside).
    thickness: outline width in WORLD meters. On a ~1m prop, 0.005-0.015 is the
               sane range. Default 0.01 (1cm).
    color:     [r,g,b(,a)] outline color, scene-linear floats. Default black.

    The outline is APPENDED as a new material slot, so an existing slot-0
    material (e.g. a toon material) is left untouched. Idempotent. Undo with
    remove_outline.
    """
    params = {"target": target, "thickness": thickness}
    if color is not None:
        params["color"] = color
    result = call_blender("add_outline", params, label=label)
    if result.get("success"):
        main = (f"outlined {result['outlined']} (thickness={result['thickness']}m) "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def remove_outline(target: str, label: str = "") -> str:
    """
    Remove the inverted-hull outline added by add_outline — deletes the Solidify
    modifier and the material slot it appended, nothing else.

    target: object OR group name.
    """
    result = call_blender("remove_outline", {"target": target}, label=label)
    if result.get("success"):
        main = f"removed outline from {result['removed']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)

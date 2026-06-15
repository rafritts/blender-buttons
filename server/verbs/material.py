"""material — Material Properties / shading (SPEC-05).

Assign and tune materials (PBR, toon, textured), shade smooth/flat, outlines, and
search the Poly Haven texture/HDRI libraries. `op` selects the operation.
"""

from server._core import mcp
from server import finishes, shaders, textures, scene
from ._common import unknown

_OPS = ["set", "toon", "textured", "outline", "remove_outline", "shade_smooth",
        "shade_flat", "search_textures", "search_hdris"]


@mcp.tool(name="material")
def material(
    op: str,
    target: str = "",
    # PBR (set)
    base_color: list = None, hex: str = "",
    metallic: float = None, roughness: float = None, ior: float = None,
    alpha: float = None, emission_color: list = None, emission_strength: float = None,
    material_name: str = "", material: str = "", slot: int = None,
    # toon
    shadow_color: list = None, bands: int = 2, shadow_softness: float = 0.05,
    rim_color: list = None, rim_width: float = 0.2,
    gradient_top: list = None, gradient_bottom: list = None,
    # textured
    asset_id: str = "", scale: float = 1.0, resolution: str = "1k", tint: list = None,
    # outline
    thickness: float = 0.01, color: list = None,
    # shade_smooth
    auto_smooth_angle: float = 30.0,
    # search
    query: str = "", limit: int = 10,
    label: str = "",
) -> str:
    """
    Materials & shading — **Material Properties**. `op` selects:

      set       — PBR material   (target, base_color|hex, metallic, roughness, ior,
                  alpha, emission_color/strength, material_name|material, slot)
      toon      — flat cel material (target, base_color|hex, shadow_color, bands,
                  shadow_softness, rim_color/width, gradient_top/bottom)
      textured  — Poly Haven PBR texture set (target, asset_id, scale, resolution,
                  base_color/tint, metallic, roughness, slot)
      outline   — add an inverted-hull outline (target, thickness, color)
      remove_outline — strip it                (target)
      shade_smooth — smooth shading            (target(s), auto_smooth_angle)
      shade_flat   — flat shading              (target(s))
      search_textures — find PBR texture ids   (query, limit)
      search_hdris    — find HDRI ids for lighting (query, limit)

    (HDRI is applied to the world via `scene` world; here you just search ids.)
    """
    o = op.lower().strip()
    if o == "set":
        return finishes.set_material(target, base_color, hex, metallic, roughness,
                                     ior, alpha, emission_color, emission_strength,
                                     material_name, material, slot, label)
    if o == "toon":
        return shaders.set_toon_material(target, base_color, hex, shadow_color, bands,
                                         shadow_softness, rim_color, rim_width,
                                         gradient_top, gradient_bottom, material_name, label)
    if o == "textured":
        return textures.set_textured_material(target, asset_id, scale, resolution,
                                              base_color, tint, metallic, roughness,
                                              material_name, slot, label)
    if o == "outline":
        return shaders.add_outline(target, thickness, color, label)
    if o == "remove_outline":
        return shaders.remove_outline(target, label)
    if o == "shade_smooth":
        return finishes.shade_smooth(target, auto_smooth_angle, label)
    if o == "shade_flat":
        return finishes.shade_flat(target, label)
    if o == "search_textures":
        return textures.search_textures(query, limit)
    if o == "search_hdris":
        return scene.search_hdris(query, limit)
    return unknown("material", "op", op, _OPS)

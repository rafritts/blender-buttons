"""material — Material Properties / shading (SPEC-05).

Assign and tune materials (PBR, toon, textured), shade smooth/flat, outlines, and
search the Poly Haven texture/HDRI libraries. `op` selects the operation.
"""

from typing import Literal

from server._core import mcp
from server import finishes, shaders, textures, scene
from ._common import tag, unknown

_OPS = ["set", "assign", "toon", "textured", "pbr", "outline", "remove_outline",
        "remove_slot", "remove_unused_slots",
        "shade_smooth", "shade_flat", "search_textures", "search_hdris"]


@mcp.tool(name="material")
def material(
    op: Literal["set", "assign", "toon", "textured", "pbr", "outline", "remove_outline",
                "remove_slot", "remove_unused_slots",
                "shade_smooth", "shade_flat", "search_textures", "search_hdris"],
    target: tag(str, "object(s) to shade: 'name', group, or 'a,b,c'") = "",
    # PBR (set)
    base_color: tag(list, "[set/toon/textured] [r,g,b] 0..1") = None,
    hex: tag(str, "[set/toon] #RRGGBB color") = "",
    metallic: tag(float, "[set/textured] metallic 0..1") = None,
    roughness: tag(float, "[set/textured] roughness 0..1") = None,
    ior: tag(float, "[set] index of refraction (glass≈1.5, water≈1.33)") = None,
    alpha: tag(float, "[set] opacity 0..1 (flat see-through)") = None,
    transmission: tag(float, "[set] 0..1 refractive solid — glass/gem/lens/water; pair with ior, roughness frosts it") = None,
    emission_color: tag(list, "[set] emission [r,g,b]") = None,
    emission_strength: tag(float, "[set] emission strength") = None,
    material_name: tag(str, "[set/toon/textured] name for the material") = "",
    material: tag(str, "[set/assign] reuse an existing material by name") = "",
    slot: tag(int, "[set/textured/remove_slot] material slot index") = None,
    # toon
    shadow_color: tag(list, "[toon] shadow band [r,g,b]") = None,
    bands: tag(int, "[toon] number of shading bands") = 2,
    shadow_softness: tag(float, "[toon] band edge softness") = 0.05,
    rim_color: tag(list, "[toon] rim light [r,g,b]") = None,
    rim_width: tag(float, "[toon] rim width") = 0.2,
    gradient_top: tag(list, "[toon] gradient top [r,g,b]") = None,
    gradient_bottom: tag(list, "[toon] gradient bottom [r,g,b]") = None,
    # textured (Poly Haven) + pbr (local folder)
    asset_id: tag(str, "[textured] Poly Haven texture id") = "",
    scale: tag(float, "[textured/pbr] unitless UV/texture scale (ignored if physical_size set)") = 1.0,
    physical_size: tag(float, "[textured/pbr] real-world metres ONE texture tile should cover — "
                              "derives the box-projection scale from the object's measured size "
                              "so grain reads at a true physical scale (G141)") = 0.0,
    space: tag(str, "[textured/pbr] box (default) | uv. box = object-coordinate box "
                    "projection, needs NO unwrap (the default for blockout/portfolio). "
                    "uv = read the mesh's active UV layer (run `uv op=unwrap` first) — "
                    "only when grain must follow a curved surface. In uv mode physical_size "
                    "is ignored and `scale` means UV tiling.") = "box",
    resolution: tag(str, "[textured] 1k|2k|4k") = "1k",
    tint: tag(list, "[textured/pbr] tint [r,g,b]") = None,
    folder: tag(str, "[pbr] local texture-set folder (Poliigon/Megascans/etc.) — maps auto-detected by filename") = "",
    size: tag(str, "[pbr] resolution subfolder/token to pick, e.g. 4K (default: largest present)") = "",
    displacement: tag(float, "[pbr] bump-displacement strength from the height map (0=off)") = 0.0,
    use_alpha: tag(bool, "[pbr/textured] wire a detected alpha/opacity map into transparency. "
                         "Default False — an alpha channel in a surface scan is usually a "
                         "mask, not whole-material transparency (auto-wiring it made an opaque "
                         "material render invisible, G126). Set True for a real cutout.") = False,
    # outline
    thickness: tag(float, "[outline] outline thickness (m)") = 0.01,
    color: tag(list, "[outline] outline [r,g,b]") = None,
    # shade_smooth
    auto_smooth_angle: tag(float, "[shade_smooth] auto-smooth angle (deg)") = 30.0,
    # search
    query: tag(str, "[search_textures/search_hdris] search keywords") = "",
    limit: tag(int, "[search_textures/search_hdris] max results") = 10,
    label: str = "",
) -> str:
    """
    Materials & shading — **Material Properties**. `op` selects:

      set       — PBR material on a whole object/slot (target, base_color|hex, metallic,
                  roughness, ior, alpha, transmission, emission_color/strength,
                  material_name|material, slot)
      assign    — paint a material onto the LIVE edit-mode FACE SELECTION only — rim
                  bands, label patches, wainscot (select faces first, then: target,
                  material=<existing> | base_color|hex [+metallic/roughness/material_name])
      toon      — flat cel material (target, base_color|hex, shadow_color, bands,
                  shadow_softness, rim_color/width, gradient_top/bottom)
      textured  — Poly Haven PBR texture set (target, asset_id, scale, resolution,
                  base_color/tint, metallic, roughness, slot)
      pbr       — PBR material from a LOCAL texture-set folder, maps auto-detected by
                  filename — vendor-neutral (Poliigon/Megascans/ambientCG/loose folders),
                  no addon or login needed (target, folder, size, scale, displacement,
                  base_color/tint, metallic, roughness, slot)

      textured/pbr take space=box|uv: box (default) projects off object coordinates and
      needs NO unwrap; uv reads the mesh's active UV layer (run `uv op=unwrap` first) for
      grain that must follow a curved surface (a mug belly, a plate rim). SPEC-18.
      outline   — add an inverted-hull outline (target, thickness, color)
      remove_outline — strip it                (target)
      remove_slot — remove one material slot by index — reassign its faces FIRST
                  (Blender re-homes orphaned faces to slot 0)  (target, slot)
      remove_unused_slots — drop every slot with no faces — trim a consolidated
                  mesh to its real slot count               (target)
      shade_smooth — smooth shading            (target(s), auto_smooth_angle)
      shade_flat   — flat shading              (target(s))
      search_textures — find PBR texture ids   (query, limit)
      search_hdris    — find HDRI ids for lighting (query, limit)

    (HDRI is applied to the world via `scene` world; here you just search ids.)
    """
    o = op.lower().strip()
    if o == "set":
        return finishes.set_material(target, base_color, hex, metallic, roughness,
                                     ior, alpha, transmission, emission_color,
                                     emission_strength, material_name, material, slot, label)
    if o == "assign":
        return finishes.assign_material(target, material, base_color, hex, metallic,
                                        roughness, material_name, label)
    if o == "toon":
        return shaders.set_toon_material(target, base_color, hex, shadow_color, bands,
                                         shadow_softness, rim_color, rim_width,
                                         gradient_top, gradient_bottom, material_name, label)
    if o == "textured":
        return textures.set_textured_material(target, asset_id, scale, resolution,
                                              base_color, tint, metallic, roughness,
                                              material_name, slot, use_alpha,
                                              physical_size, space, label)
    if o == "pbr":
        return textures.set_pbr_material(target, folder, size, scale, displacement,
                                         base_color, tint, metallic, roughness,
                                         material_name, slot, use_alpha,
                                         physical_size, space, label)
    if o == "outline":
        return shaders.add_outline(target, thickness, color, label)
    if o == "remove_outline":
        return shaders.remove_outline(target, label)
    if o == "remove_slot":
        return shaders.remove_material_slot(target, slot, label)
    if o == "remove_unused_slots":
        return shaders.remove_unused_material_slots(target, label)
    if o == "shade_smooth":
        return finishes.shade_smooth(target, auto_smooth_angle, label)
    if o == "shade_flat":
        return finishes.shade_flat(target, label)
    if o == "search_textures":
        return textures.search_textures(query, limit)
    if o == "search_hdris":
        return scene.search_hdris(query, limit)
    return unknown("material", "op", op, _OPS)

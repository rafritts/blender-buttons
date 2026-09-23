"""material — Material Properties / shading (SPEC-05).

Assign and tune materials, shade smooth/flat, and search the Poly Haven texture/HDRI
libraries. `op` selects the operation.

SPEC-22: `set`/`assign` use the stock Principled BSDF (native single operations —
input writes + slot assign). The multi-node shader-graph builders (textured/pbr/toon)
and the inverted-hull outline composite were stripped. Two thin exceptions remain:
`op=image` (G230) binds one packed image to Base Color and/or Emission, and
`op=texture` (G239) wires a Poly Haven id's diffuse, roughness, and normal with
box projection. Texture/HDRI SEARCH stays (it's a read).
"""

from typing import Literal

from server._core import mcp
from server import finishes, shaders, textures, scene
from ._common import tag, unknown

_OPS = ["set", "assign", "image", "texture", "remove_slot", "remove_unused_slots",
        "shade_smooth", "shade_flat", "search_textures", "search_hdris"]


@mcp.tool(name="material")
def material(
    op: Literal["set", "assign", "image", "texture", "remove_slot", "remove_unused_slots",
                "shade_smooth", "shade_flat", "search_textures", "search_hdris"],
    target: tag(str, "object(s) to shade: 'name', group, or 'a,b,c'") = "",
    # PBR (set)
    base_color: tag(list, "[set] [r,g,b] 0..1") = None,
    hex: tag(str, "[set] #RRGGBB color") = "",
    metallic: tag(float, "[set] metallic 0..1") = None,
    roughness: tag(float, "[set] roughness 0..1") = None,
    ior: tag(float, "[set] index of refraction (glass≈1.5, water≈1.33)") = None,
    alpha: tag(float, "[set] opacity 0..1 (flat see-through)") = None,
    transmission: tag(float, "[set] 0..1 refractive solid — glass/gem/lens/water; pair with ior, roughness frosts it") = None,
    emission_color: tag(list, "[set] emission [r,g,b]") = None,
    emission_strength: tag(float, "[set] emission strength") = None,
    subsurface_weight: tag(float, "[set] subsurface 0..1 (dough, wax, skin)") = None,
    subsurface_radius: tag(list, "[set] subsurface radius [r,g,b], or one number for all") = None,
    subsurface_scale: tag(float, "[set] subsurface scale, metres") = None,
    coat_weight: tag(float, "[set] clearcoat weight 0..1") = None,
    coat_roughness: tag(float, "[set] clearcoat roughness 0..1") = None,
    material_name: tag(str, "[set] name for the material") = "",
    material: tag(str, "[set/assign] reuse an existing material by name") = "",
    slot: tag(int, "[set/remove_slot] material slot index") = None,
    # shade_smooth
    auto_smooth_angle: tag(float, "[shade_smooth] auto-smooth angle (deg)") = 30.0,
    # search
    query: tag(str, "[search_textures/search_hdris] search keywords") = "",
    limit: tag(int, "[search_textures/search_hdris] max results") = 10,
    source: tag(str, "[search_textures] library: 'polyhaven' (default, CC0) | 'poliigon'") = "polyhaven",
    # image (G230)
    image: tag(str, "[image] filesystem path or packed image name") = "",
    bind: tag(str, "[image] which Principled input: 'base' | 'emission' | 'both'") = "base",
    space: tag(str, "[image] 'uv' (needs uv op=unwrap) or 'box' (object projection)") = "box",
    label: str = "",
    # texture (G239)
    id: tag(str, "[texture] Poly Haven texture id from search_textures") = "",
    resolution: tag(str, "[texture] map resolution: 1k (default) | 2k | 4k | 8k") = "1k",
    scale: tag(float, "[texture] uniform object-space mapping scale") = 1.0,
) -> str:
    """
    Materials & shading — **Material Properties**. `op` selects:

      set       — PBR material on a whole object/slot (target, base_color|hex, metallic,
                  roughness, ior, alpha, transmission, emission_color/strength,
                  subsurface_weight/radius/scale, coat_weight/roughness,
                  material_name|material, slot). A Principled socket this Blender
                  doesn't have is reported as skipped, not silently dropped.
      image     — bind a packed image to Principled Base Color and/or Emission
                  (target, image=<path or packed name>, bind=base|emission|both,
                  space=uv|box, emission_strength, material_name). Thin bind, not
                  the retired PBR graph. space=uv needs `uv op=unwrap` first.
      texture   — wear a Poly Haven texture (id from search_textures, resolution,
                  scale). Wires diffuse, roughness, and normal with box projection.
                  One call, one material.
      assign    — paint a material onto the LIVE edit-mode FACE SELECTION only — rim
                  bands, label patches, wainscot (select faces first, then: target,
                  material=<existing> | base_color|hex [+metallic/roughness/material_name])
      remove_slot — remove one material slot by index — reassign its faces FIRST
                  (Blender re-homes orphaned faces to slot 0)  (target, slot)
      remove_unused_slots — drop every slot with no faces — trim a consolidated
                  mesh to its real slot count               (target)
      shade_smooth — Object ▸ Shade Smooth (Face ▸ Shade Smooth) · smooth shading
                    (target(s), auto_smooth_angle)
      shade_flat   — Object ▸ Shade Flat (Face ▸ Shade Flat) · flat shading   (target(s))
      search_textures — find PBR texture ids   (query, limit)
      search_hdris    — find HDRI ids for lighting (query, limit)

    (HDRI is applied to the world via `scene` world; here you just search ids.)
    """
    o = op.lower().strip()
    if o == "set":
        return finishes.set_material(
            target, base_color, hex, metallic, roughness,
            ior, alpha, transmission, emission_color,
            emission_strength, material_name, material, slot, label,
            subsurface_weight=subsurface_weight,
            subsurface_radius=subsurface_radius,
            subsurface_scale=subsurface_scale,
            coat_weight=coat_weight,
            coat_roughness=coat_roughness)
    if o == "image":
        return finishes.bind_image(target, image, bind, space, emission_strength,
                                   material_name, material, slot, label)
    if o == "texture":
        return finishes.apply_texture(target, id, resolution, scale,
                                      material_name, material, slot, label)
    if o == "assign":
        return finishes.assign_material(target, material, base_color, hex, metallic,
                                        roughness, material_name, label)
    if o == "remove_slot":
        return shaders.remove_material_slot(target, slot, label)
    if o == "remove_unused_slots":
        return shaders.remove_unused_material_slots(target, label)
    if o == "shade_smooth":
        return finishes.shade_smooth(target, auto_smooth_angle, label)
    if o == "shade_flat":
        return finishes.shade_flat(target, label)
    if o == "search_textures":
        return textures.search_textures(query, limit, source)
    if o == "search_hdris":
        return scene.search_hdris(query, limit)
    return unknown("material", "op", op, _OPS)

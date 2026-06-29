"""buttons-npr-macro — non-photoreal LOOK macros (SPEC-20 §3, II.2).

blender-buttons MACROS that build a whole NPR look (a cel node graph, an inverted-hull
outline) — not a single native node — grouped by purpose with an R1 native-cousin tag.
Dispatch to the same flat handlers (shaders.*).

  toon           — cel/anime shader graph (Shader-to-RGB → ramp → bands)
  outline        — inverted-hull silhouette outline
  remove_outline — strip it

(The PBR node-graph builders `material op=textured` / `material op=pbr` are also composite,
but their purpose-outcome is material application — you reach for them by "texture this" —
so they stay under `material`, tagged as composite. This bucket is the NPR LOOK only.)
"""

from typing import Literal

from server._core import mcp
from server import shaders
from ._common import tag, unknown


@mcp.tool(name="buttons-npr-macro")
def buttons_npr_macro(
    op: Literal["toon", "outline", "remove_outline"],
    target: tag(str, "object(s) to apply the look to: 'name', group, or 'a,b,c'") = "",
    # toon
    base_color: tag(list, "[toon] [r,g,b] 0..1") = None,
    hex: tag(str, "[toon] #RRGGBB color") = "",
    shadow_color: tag(list, "[toon] shadow band [r,g,b]") = None,
    bands: tag(int, "[toon] number of shading bands") = 2,
    shadow_softness: tag(float, "[toon] band edge softness") = 0.05,
    rim_color: tag(list, "[toon] rim light [r,g,b]") = None,
    rim_width: tag(float, "[toon] rim width") = 0.2,
    gradient_top: tag(list, "[toon] gradient top [r,g,b]") = None,
    gradient_bottom: tag(list, "[toon] gradient bottom [r,g,b]") = None,
    material_name: tag(str, "[toon] name for the material") = "",
    # outline
    thickness: tag(float, "[outline] outline thickness (m)") = 0.01,
    color: tag(list, "[outline] outline [r,g,b]") = None,
    label: str = "",
) -> str:
    """
    Non-photoreal LOOK macros (blender-buttons composites). `op` selects:

      toon           — flat cel material (target, base_color|hex, shadow_color, bands,
                       shadow_softness, rim_color/width, gradient_top/bottom)
      outline        — add an inverted-hull outline (target, thickness, color)
      remove_outline — strip it                     (target)

    NATIVE COUSINS (R1):
      • toon ≈ the native **Shader to RGB** node (EEVEE-only — Cycles doesn't support it)
        + ColorRamp. Blender ships NO stock toon/NPR shader or preset; toon assembles that
        graph for you. (Known EEVEE-Next quirk: a Shader-to-RGB toon chain ignores object
        emission, blender #119828.)
      • outline ≈ three native paths — **Line Art** (Grease Pencil; the real-time "real"
        line renderer, but emits GP strokes, not mesh), **Freestyle** (render-only, no
        longer maintained), and the **Solidify** flipped-normal inverted-hull (native
        machinery the macro automates into a baked mesh silhouette). For true line
        rendering reach for Line Art; outline is the one-call baked-hull convenience.
    """
    o = op.lower().strip()
    if o == "toon":
        return shaders.set_toon_material(target, base_color, hex, shadow_color, bands,
                                         shadow_softness, rim_color, rim_width,
                                         gradient_top, gradient_bottom, material_name, label)
    if o == "outline":
        return shaders.add_outline(target, thickness, color, label)
    if o == "remove_outline":
        return shaders.remove_outline(target, label)
    return unknown("buttons-npr-macro", "op", op, ["toon", "outline", "remove_outline"])

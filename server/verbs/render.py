"""render — the Render menu (SPEC-05).

Produce the image and control render quality / color management. `op` selects.
render(op="image") is the only user-facing image producer (see its warning).
"""

from typing import Literal

from server._core import mcp
from server import scene
from ._common import tag, unknown

_OPS = ["image", "settings", "quality", "cycles", "color"]


@mcp.tool(name="render")
def render(
    op: Literal["image", "settings", "quality", "cycles", "color"],
    # image (render_to_file)
    filepath: tag(str, "[image] output path (~ expanded)") = "",
    resolution_x: tag(int, "[image] pixel width") = None,
    resolution_y: tag(int, "[image] pixel height") = None,
    engine: tag(str, "[image] engine id — `render op=settings` lists this build's (e.g. CYCLES, BLENDER_EEVEE); empty=keep current") = "",
    format: tag(str, "[image] PNG|JPEG|OPEN_EXR|TIFF|WEBP") = "PNG",
    transparent: tag(bool, "[image] transparent background") = None,
    timeout: tag(float, "[image] seconds before giving up") = 300,
    # quality (Eevee) + shared
    raytracing: tag(bool, "[quality] Eevee screen-space ray tracing (metal reflections)") = None,
    ao: tag(bool, "[quality] ambient occlusion") = None,
    shadows: tag(bool, "[quality] soft shadows") = None,
    samples: tag(int, "[image/quality/cycles] sample count") = None,
    # cycles
    device: tag(str, "[cycles] GPU | CPU") = "",
    backend: tag(str, "[cycles] OPTIX|CUDA|HIP|ONEAPI|METAL (GPU backend)") = "",
    denoise: tag(bool, "[cycles] denoise the final image") = None,
    denoiser: tag(str, "[cycles] OPTIX | OPENIMAGEDENOISE") = "",
    adaptive_threshold: tag(float, "[cycles] adaptive-sampling noise floor, e.g. 0.01") = None,
    # color management
    view_transform: tag(str, "[color] Standard|AgX|Filmic|Raw") = "",
    look: tag(str, "[color] contrast look") = "",
    exposure: tag(float, "[color] stops of exposure") = None,
    gamma: tag(float, "[color] display gamma") = None,
    label: str = "",
) -> str:
    """
    Render & look — the **Render** menu. `op` selects:

      image   — render the scene camera to a file (filepath, resolution_x/y, samples,
                engine, format, transparent, timeout)
                (engine: the build's id, NOT a hardcoded name — Blender 5.x Eevee is
                `BLENDER_EEVEE`, not `_NEXT`; `render op=settings` lists what's real.)

                ⚠ THE IMAGE IS FOR THE HUMAN, NOT THE AGENT. Do NOT read it back.
                Why this is a hard rule, not a style note:
                  • LLM vision is unreliable at this level of precision, and it
                    *self-confirms* — you will look at the render, see what you
                    expected to see, and report success whether or not it's true.
                    The render cannot catch your own mistake; it launders it.
                  • A render is a lossy, ambiguous 2D view of hidden 3D state.
                  • Reading it back lights tokens on fire for that false comfort.
                Verify with GROUND TRUTH instead — `feel` (topology/measurements),
                `object info`, modifier lists, the status block. Those are
                depsgraph-exact and can't be gaslit. Render only when the user asks
                for a picture, then hand them the path.
                (engine: builds vary — CYCLES may be absent, Eevee's id shifts by
                version. `render op=settings` reports this build's real list.)
      settings— READ the render config / PREFLIGHT: available engines (the build's
                own list, dynamically-registered engines included), current engine,
                resolution/format, color management, the active engine's params, and
                for Cycles the GPU preflight — compute backend, per-device enabled
                flags, and the EFFECTIVE device (catches a device=GPU that silently
                falls back to CPU). The read half of this verb.                (—)
      quality — Eevee quality toggles (raytracing, ao, shadows, samples)
      cycles  — Cycles controls (device=GPU|CPU, backend=OPTIX|CUDA|…, denoise,
                denoiser, adaptive_threshold, samples)
      color   — color management (view_transform=Standard|AgX|…, look, exposure, gamma)
    """
    o = op.lower().strip()
    if o == "image":
        return scene.render_to_file(filepath, resolution_x, resolution_y, samples,
                                    engine, format, transparent, timeout, label)
    if o == "settings":
        return scene.render_settings()
    if o == "quality":
        return scene.set_render_quality(raytracing, ao, shadows, samples, label)
    if o == "cycles":
        return scene.set_cycles_quality(device, backend, denoise, denoiser,
                                        adaptive_threshold, samples, label)
    if o == "color":
        return scene.set_color_management(view_transform, look, exposure, gamma, label)
    return unknown("render", "op", op, _OPS)

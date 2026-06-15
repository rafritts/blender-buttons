"""render — the Render menu (SPEC-05).

Produce the image and control render quality / color management. `op` selects.
render(op="image") is the only user-facing image producer (see its warning).
"""

from server._core import mcp
from server import scene
from ._common import unknown

_OPS = ["image", "quality", "cycles", "color"]


@mcp.tool(name="render")
def render(
    op: str,
    # image (render_to_file)
    filepath: str = "",
    resolution_x: int = None, resolution_y: int = None,
    engine: str = "", format: str = "PNG", transparent: bool = None,
    timeout: float = 300,
    # quality (Eevee) + shared
    raytracing: bool = None, ao: bool = None, shadows: bool = None, samples: int = None,
    # cycles
    device: str = "", backend: str = "", denoise: bool = None, denoiser: str = "",
    adaptive_threshold: float = None,
    # color management
    view_transform: str = "", look: str = "", exposure: float = None, gamma: float = None,
    label: str = "",
) -> str:
    """
    Render & look — the **Render** menu. `op` selects:

      image   — render the scene camera to a file (filepath, resolution_x/y, samples,
                engine=CYCLES|BLENDER_EEVEE_NEXT, format, transparent, timeout)
                ⚠ FOR THE HUMAN — the agent never reads these back; use `feel`/reads
                to understand the model.
      quality — Eevee quality toggles (raytracing, ao, shadows, samples)
      cycles  — Cycles controls (device=GPU|CPU, backend=OPTIX|CUDA|…, denoise,
                denoiser, adaptive_threshold, samples)
      color   — color management (view_transform=Standard|AgX|…, look, exposure, gamma)
    """
    o = op.lower().strip()
    if o == "image":
        return scene.render_to_file(filepath, resolution_x, resolution_y, samples,
                                    engine, format, transparent, timeout, label)
    if o == "quality":
        return scene.set_render_quality(raytracing, ao, shadows, samples, label)
    if o == "cycles":
        return scene.set_cycles_quality(device, backend, denoise, denoiser,
                                        adaptive_threshold, samples, label)
    if o == "color":
        return scene.set_color_management(view_transform, look, exposure, gamma, label)
    return unknown("render", "op", op, _OPS)

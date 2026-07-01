"""scene — the Outliner + scene-level Properties (SPEC-05).

Scene-level state only: the collection tree, the world background, and starting a
new scene. Per-object Properties (modifier/material/object data) belong to their
own verbs; producing the image is `render`.
"""

from typing import Literal

from server._core import mcp
from server import queries, scene as _scene, designs
from ._common import tag, unknown

_OPS = ["tree", "world", "atmosphere", "new", "frame", "bake_physics"]


@mcp.tool(name="scene")
def scene(
    op: Literal["tree", "world", "atmosphere", "new", "frame", "bake_physics"],
    # tree
    filter: tag(str, "[tree] name-substring filter") = "",
    type: tag(str, "[tree] type filter, e.g. MESH") = "",
    max_depth: tag(int, "[tree] max tree depth") = None,
    summarize: tag(int, "[tree] collapse collections over N objects (0 = expand all)") = 20,
    parts_only: tag(bool, "[tree] show only real renderable geometry — hide bone-shape widgets + render-hidden helpers") = False,
    # world
    color: tag(list, "[world] solid background [r,g,b] 0..1") = None,
    hex: tag(str, "[world] solid background #RRGGBB") = "",
    strength: tag(float, "[world] background light strength") = None,
    hdri: tag(str, "[world] HDRI id or path (image-based lighting)") = "",
    resolution: tag(str, "[world] HDRI fetch resolution (1k|2k|4k|8k)") = "2k",
    # atmosphere
    density: tag(float, "[atmosphere] scattering coeff: 0.01 haze, 0.05 mist, 0.1 fog") = None,
    absorption: tag(float, "[atmosphere] extra extinction (smoke vs clean mist); omit for pure scatter") = None,
    anisotropy: tag(float, "[atmosphere] -1..1 scatter dir; ~0.6 = tighter beams toward the light") = None,
    clear: tag(bool, "[atmosphere] True = remove the medium (clear air)") = False,
    # new
    empty: tag(bool, "[new] True = a truly empty scene") = False,
    # frame / bake_physics (G196)
    frame: tag(int, "[frame] jump to absolute frame N") = None,
    step: tag(int, "[frame] advance N frames (negative to rewind)") = None,
    start: tag(int, "[frame/bake_physics] first frame of the playback range / bake") = None,
    end: tag(int, "[frame] last frame of the playback range") = None,
    frames: tag(int, "[bake_physics] number of frames to simulate from start") = None,
    label: str = "",
) -> str:
    """
    Scene-level state — the **Outliner** + scene Properties. `op` selects:

      tree   — the scene collection tree   (filter, type, max_depth, summarize=N,
               parts_only=True for just the real renderable parts on a busy rig)
      world  — set the world background    (color|hex + strength, OR hdri id/path +
               resolution)  — image-based lighting
      atmosphere — fill the air with a scattering medium: haze/fog/mist AND the
               volumetric god-ray (density, color|hex, absorption, anisotropy;
               clear=True to remove). A bright shadow-casting spot/sun then shafts
               through it for free.
      new    — start a fresh scene         (empty=True for a truly empty one)
      frame  — move the timeline playhead   (frame=N absolute | step=±N; start/end set
               the playback range) — physics/animation evaluate as frames advance
      bake_physics — RUN the sim: bake every cloth/soft-body/particle point cache and
               leave the scene on the settled last frame (frames=N, start=F). Pair with
               modifier op=add type=CLOTH pin_group=… / type=COLLISION.

    (Render/output/color settings are the `render` verb; render quality lives there
    too. Per-object tabs are `modifier` / `material` / `object`.)
    """
    o = op.lower().strip()
    if o == "tree":
        return queries.get_scene_tree(filter, type, max_depth, summarize, parts_only)
    if o == "world":
        return _scene.set_world_background(color, hex, strength, hdri, resolution, label)
    if o == "atmosphere":
        return _scene.set_atmosphere(density, color, hex, absorption, anisotropy, clear, label)
    if o == "new":
        return designs.new_scene(empty)
    if o == "frame":
        return _scene.set_frame(frame, step, start, end, label)
    if o == "bake_physics":
        return _scene.bake_physics(frames, start, label=label)
    return unknown("scene", "op", op, _OPS)

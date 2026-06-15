"""scene — the Outliner + scene-level Properties (SPEC-05).

Scene-level state only: the collection tree, the world background, and starting a
new scene. Per-object Properties (modifier/material/object data) belong to their
own verbs; producing the image is `render`.
"""

from server._core import mcp
from server import queries, scene as _scene, designs
from ._common import unknown

_OPS = ["tree", "world", "new"]


@mcp.tool(name="scene")
def scene(
    op: str,
    # tree
    filter: str = "", type: str = "", max_depth: int = None, summarize: int = 20,
    # world
    color: list = None, hex: str = "", strength: float = None,
    hdri: str = "", resolution: str = "2k",
    # new
    empty: bool = False,
    label: str = "",
) -> str:
    """
    Scene-level state — the **Outliner** + scene Properties. `op` selects:

      tree   — the scene collection tree   (filter, type, max_depth, summarize=N)
      world  — set the world background    (color|hex + strength, OR hdri id/path +
               resolution)  — image-based lighting
      new    — start a fresh scene         (empty=True for a truly empty one)

    (Render/output/color settings are the `render` verb; render quality lives there
    too. Per-object tabs are `modifier` / `material` / `object`.)
    """
    o = op.lower().strip()
    if o == "tree":
        return queries.get_scene_tree(filter, type, max_depth, summarize)
    if o == "world":
        return _scene.set_world_background(color, hex, strength, hdri, resolution, label)
    if o == "new":
        return designs.new_scene(empty)
    return unknown("scene", "op", op, _OPS)

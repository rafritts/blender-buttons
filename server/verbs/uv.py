"""uv — UV unwrap & texture-space mapping (SPEC-18).

UV is a distinct coordinate space (the 2D map a texture lives in). Box projection
(`material` without space=uv) needs no UVs and is the default; reach here only when
texture grain must follow a curved surface — a mug belly, a plate rim, wood edge grain.
`op` selects the operation.

Phase 1 (this build): `unwrap` — the no-seam parametric/auto projections. Seam marking
+ seam-driven methods and the deterministic `uv op=check` verdict are later phases.
"""

from typing import Literal

from server._core import mcp
from server import uv as _uv
from ._common import tag, unknown, teach

_OPS = ["unwrap"]


@mcp.tool(name="uv")
def uv(
    op: Literal["unwrap"],
    target: tag(str, "object, group/collection, or 'a,b,c' — each mesh unwrapped "
                     "INDEPENDENTLY (UVs are per-mesh)") = "",
    method: tag(str, "[unwrap] smart (default, hard-surface) | cube (boxy) | "
                     "cylinder (mugs/bottles/columns) | sphere (balls/domes)") = "smart",
    angle_limit: tag(float, "[unwrap/smart] degrees; split islands where faces bend "
                            "past this (66 default)") = 66.0,
    island_margin: tag(float, "[unwrap/smart] gap between islands, UV units (0.02)") = 0.02,
    scale_to_bounds: tag(bool, "[unwrap] stretch the result to fill the [0,1] square") = False,
    label: str = "",
) -> str:
    """
    UV unwrap & texture-space mapping — the 2D map textures read. `op` selects:

      unwrap — flatten a mesh's UVs with a parametric / auto projection (no seams):
               method=smart|cube|cylinder|sphere, target, angle_limit, island_margin,
               scale_to_bounds. Then consume it with `material op=pbr/textured space=uv`.

    Box projection (`material` without space=uv) is the default and needs NO unwrap —
    use this only when grain must follow a curved surface. The unwrap is mechanical: it
    flattens; whether the seams land well is taste (render a checker for the human).
    """
    o = op.lower().strip()
    if o == "unwrap":
        bad = teach("uv", "op", o, {
            "unwrap": (bool(target), "target=<object/group/'a,b,c'>",
                       "uv op=unwrap target=Mug method=cylinder")})
        if bad:
            return bad
        return _uv.uv_unwrap(target, method, angle_limit, island_margin,
                             scale_to_bounds, label)
    return unknown("uv", "op", op, _OPS)

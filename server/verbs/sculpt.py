"""sculpt — Sculpt Mode brushes (SPEC-05).

Stroke a brush at a world point on a mesh. `brush` selects which brush; every
brush shares the at_x/at_y/at_z + radius targeting. Auto-enters Sculpt Mode.
"""

from server._core import mcp
from server import sculpt as _s
from ._common import unknown

_BRUSHES = ["grab", "draw", "inflate", "smooth", "crease", "pinch", "flatten"]


@mcp.tool(name="sculpt")
def sculpt(
    brush: str,
    target: str,
    at_x: float, at_y: float, at_z: float, radius: float,
    # amount (draw/inflate/crease/pinch/flatten)
    amount: float = 1.0,
    # grab displacement — absolute to_* OR relative directions
    to_x: float = None, to_y: float = None, to_z: float = None,
    out: float = 0.0, inward: float = 0.0, up: float = 0.0, down: float = 0.0,
    left: float = 0.0, right: float = 0.0, forward: float = 0.0, back: float = 0.0,
    # draw direction / flatten plane
    normal_x: float = 0.0, normal_y: float = 0.0, normal_z: float = 0.0,
    plane_normal_x: float = 0.0, plane_normal_y: float = 0.0, plane_normal_z: float = 0.0,
    # smooth
    iterations: int = 1,
    falloff: str = "SMOOTH", subdivide: bool = False, label: str = "",
) -> str:
    """
    Sculpt a mesh — **Sculpt Mode** brushes. Strokes at a world point (at_x/y/z)
    within `radius`. `brush` selects:

      grab    — drag verts   (to_x/y/z absolute, OR out/up/left/.. relative)
      draw    — raise/lower along a normal  (amount, normal_x/y/z)
      inflate — push along per-vert normals (amount)
      smooth  — relax surface               (iterations)
      crease  — pull into a sharp ridge     (amount; falloff defaults SHARP)
      pinch   — pull verts together         (amount)
      flatten — flatten toward a plane      (amount, plane_normal_x/y/z)

    falloff: SMOOTH|SHARP|… subdivide=True adds resolution under the brush first.
    """
    b = brush.lower().strip()
    if b == "grab":
        return _s.sculpt_grab(target, at_x, at_y, at_z, radius, to_x, to_y, to_z,
                              out, inward, up, down, left, right, forward, back,
                              falloff, subdivide, label)
    if b == "draw":
        return _s.sculpt_draw(target, at_x, at_y, at_z, radius, amount,
                              normal_x, normal_y, normal_z, falloff, subdivide, label)
    if b == "inflate":
        return _s.sculpt_inflate(target, at_x, at_y, at_z, radius, amount,
                                 falloff, subdivide, label)
    if b == "smooth":
        return _s.sculpt_smooth(target, at_x, at_y, at_z, radius, iterations,
                                falloff, subdivide, label)
    if b == "crease":
        return _s.sculpt_crease(target, at_x, at_y, at_z, radius, amount,
                                falloff if falloff != "SMOOTH" else "SHARP",
                                subdivide, label)
    if b == "pinch":
        return _s.sculpt_pinch(target, at_x, at_y, at_z, radius, amount,
                               falloff, subdivide, label)
    if b == "flatten":
        return _s.sculpt_flatten(target, at_x, at_y, at_z, radius, amount,
                                 plane_normal_x, plane_normal_y, plane_normal_z,
                                 falloff, subdivide, label)
    return unknown("sculpt", "brush", brush, _BRUSHES)

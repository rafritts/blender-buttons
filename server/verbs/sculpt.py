"""sculpt — Sculpt Mode brushes (SPEC-05).

Stroke a brush at a world point on a mesh. `brush` selects which brush; every
brush shares the at_x/at_y/at_z + radius targeting. Auto-enters Sculpt Mode.
"""

from typing import Literal

from server._core import mcp
from server import sculpt as _s
from ._common import tag, unknown

_BRUSHES = ["grab", "draw", "inflate", "smooth", "crease", "pinch", "flatten"]


@mcp.tool(name="sculpt")
def sculpt(
    brush: Literal["grab", "draw", "inflate", "smooth", "crease", "pinch", "flatten"],
    target: tag(str, "mesh to sculpt"),
    at_x: tag(float, "brush world X"), at_y: tag(float, "brush world Y"),
    at_z: tag(float, "brush world Z"), radius: tag(float, "brush radius (m)"),
    # amount (draw/inflate/crease/pinch/flatten)
    amount: tag(float, "[draw/inflate/crease/pinch/flatten] strength") = 1.0,
    # grab displacement — absolute to_* OR relative directions
    to_x: tag(float, "[grab] drag to world X") = None,
    to_y: tag(float, "[grab] drag to world Y") = None,
    to_z: tag(float, "[grab] drag to world Z") = None,
    out: tag(float, "[grab] drag outward (m)") = 0.0,
    inward: tag(float, "[grab] drag inward (m)") = 0.0,
    up: tag(float, "[grab] drag +Z (m)") = 0.0,
    down: tag(float, "[grab] drag -Z (m)") = 0.0,
    left: tag(float, "[grab] drag -X (m)") = 0.0,
    right: tag(float, "[grab] drag +X (m)") = 0.0,
    forward: tag(float, "[grab] drag -Y (m)") = 0.0,
    back: tag(float, "[grab] drag +Y (m)") = 0.0,
    # draw direction / flatten plane
    normal_x: tag(float, "[draw] push direction X") = 0.0,
    normal_y: tag(float, "[draw] push direction Y") = 0.0,
    normal_z: tag(float, "[draw] push direction Z") = 0.0,
    plane_normal_x: tag(float, "[flatten] plane normal X") = 0.0,
    plane_normal_y: tag(float, "[flatten] plane normal Y") = 0.0,
    plane_normal_z: tag(float, "[flatten] plane normal Z") = 0.0,
    # smooth
    iterations: tag(int, "[smooth] relax iterations") = 1,
    falloff: tag(str, "brush falloff SMOOTH|SHARP|…") = "SMOOTH",
    subdivide: tag(bool, "add resolution under the brush first") = False,
    label: str = "",
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

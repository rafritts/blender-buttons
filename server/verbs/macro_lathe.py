"""buttons-lathe-macro — surface-of-revolution / ring-family macros (SPEC-20 §3, II.2).

blender-buttons MACROS (composite ring-deformers with no single native operator), grouped
by purpose with an R1 native-cousin tag. Dispatch to the same flat handlers (rings.*).

  taper_end / taper_section / scale_rings — relative ring scaling
  shape_profile — absolute-radius lathe (goblet/hourglass/baluster)
  flute — meridional corrugation (flutes / gadroons)
"""

from typing import Literal

from server._core import mcp
from server import rings
from ._common import tag, unknown, teach


@mcp.tool(name="buttons-lathe-macro")
def buttons_lathe_macro(
    op: Literal["taper_end", "taper_section", "shape_profile", "flute", "scale_rings"],
    target: tag(str, "mesh object to shape (empty=active)") = "",
    axis: tag(str, "[all] lathe axis X|Y|Z") = "Z",
    # taper_end
    end: tag(str, "[taper_end] which end MAX|MIN") = "MAX",
    scale: tag(float, "[taper_end] end scale: 0=collapse to a point, <1 taper, 1 no-op, >1 flare (e.g. 1.5=bell lip)") = 0.0,
    # taper_section
    from_ring: tag(int, "[taper_section] first ring") = 0,
    to_ring: tag(int, "[taper_section] last ring (-1 = end)") = -1,
    x_start: tag(float, "[taper_section] X scale at from_ring") = 1.0,
    x_end: tag(float, "[taper_section] X scale at to_ring") = 1.0,
    y_start: tag(float, "[taper_section] Y scale at from_ring") = 1.0,
    y_end: tag(float, "[taper_section] Y scale at to_ring") = 1.0,
    curve_shape: tag(str, "[taper_section] interpolation: linear|ease_in|ease_out|ease_in_out|smoothstep") = "linear",
    # shape_profile (G92) — absolute-radius lathe
    points: tag(list, "[shape_profile] control points [[ring_index, radius_m], ...]; rings between interpolate, outside untouched") = None,
    # flute (G94) — meridional corrugation
    flute_count: tag(int, "[flute] number of flutes/lobes around the axis (>=1)") = 0,
    flute_depth: tag(float, "[flute] radial depth of each flute (m, >0)") = 0.0,
    flute_profile: tag(str, "[flute] convex (lobes bulge out — gadroons) | concave (grooves cut in — flutes)") = "convex",
    phase: tag(float, "[flute] rotate the lobe pattern (deg)") = 0.0,
    # scale_rings
    indices: tag(list, "[scale_rings] ring indices to scale") = None,
    ring_x: tag(float, "[scale_rings] X scale of the rings") = 1.0,
    ring_y: tag(float, "[scale_rings] Y scale of the rings") = 1.0,
    label: str = "",
) -> str:
    """
    Surface-of-revolution / ring macros (blender-buttons composites). `op` selects:

      taper_end     — taper one end to a scale     (axis, end=MAX|MIN, scale)
      taper_section — taper a ring range (axis, from_ring, to_ring, x_start/x_end/
                      y_start/y_end, curve_shape)
      shape_profile — LATHE: set ring radii in ABSOLUTE meters and interpolate between
                      control points (axis, points=[[ring,radius],…]). Seam-safe and
                      idempotent (unlike taper_section's relative scale). The surface-of-
                      revolution shaper (goblet, hourglass, baluster).
      flute         — corrugate a surface of revolution with N vertical flutes/lobes by
                      modulating radius vs azimuth — flutes (concave), gadroons (convex).
                      (axis, flute_count, flute_depth, flute_profile, phase)
      scale_rings   — scale specific rings   (axis, indices=[...], ring_x, ring_y)

    NATIVE COUSIN (R1): these are per-ring **Transform scale** with an Individual-Origins
    pivot — but there is **no native lathe/turning operator** that sets per-ring radii
    along an axis with interpolation. The macros author that profile directly on the mesh;
    natively it's a hand loop of select-ring → scale-to-point, per ring.
    """
    o = op.lower().strip()
    bad = teach("buttons-lathe-macro", "op", o, {
        "shape_profile": (bool(points), "points=[[ring_index, radius_m], ...]",
                    "buttons-lathe-macro op=shape_profile axis=Z points=[[0,0.05],[11,0.009],[22,0.06]]"),
        "flute": (bool(flute_count >= 1 and flute_depth > 0),
                    "flute_count=N (>=1) and flute_depth=<m> (>0)",
                    "buttons-lathe-macro op=flute axis=Z flute_count=12 flute_depth=0.004 flute_profile=concave"),
    })
    if bad:
        return bad
    if o == "taper_end":
        return rings.taper_end(axis, end, scale, label, target)
    if o == "taper_section":
        return rings.taper_section(axis, from_ring, to_ring, x_start, x_end,
                                   y_start, y_end, curve_shape, label, target)
    if o == "shape_profile":
        return rings.shape_profile(axis, points or [], label, target)
    if o == "flute":
        return rings.flute(axis, flute_count, flute_depth, flute_profile, phase,
                           label, target)
    if o == "scale_rings":
        return rings.scale_rings(axis, indices or [], ring_x, ring_y, label, target)
    return unknown("buttons-lathe-macro", "op", op,
                   ["taper_end", "taper_section", "shape_profile", "flute", "scale_rings"])

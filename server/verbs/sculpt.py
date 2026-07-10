"""sculpt — Sculpt Mode brushes (SPEC-05).

Stroke a brush at a measured point on a mesh. `brush` selects which brush; every
brush shares the at=selection / handle= + radius targeting (no typed coordinates).
Auto-enters Sculpt Mode.
"""

from typing import Literal

from server._core import mcp
from server import sculpt as _s, handles, queries
from ._common import tag, unknown

_BRUSHES = ["grab", "draw", "inflate", "smooth", "crease", "pinch", "flatten", "gravity"]

# Organic-deform ops that live on OTHER verbs — agents reach for these as "sculpt
# brushes" (tutorial language calls noise an "inflate brush"), so when one shows up
# as a brush=, redirect to where it actually lives instead of a bare "unknown brush".
_ELSEWHERE = {
    "noise_displace": "edit op=noise_displace (coherent organic surface break-up)",
    "noise":          "edit op=noise_displace (coherent organic surface break-up)",
    "displace":       "edit op=noise_displace, or modifier op=add type=displace",
    "proportional":   "edit op=proportional_move (soft directional bulge)",
    "proportional_move": "edit op=proportional_move (soft directional bulge)",
}


@mcp.tool(name="sculpt")
def sculpt(
    brush: Literal["grab", "draw", "inflate", "smooth", "crease", "pinch", "flatten", "gravity"],
    target: tag(str, "mesh to sculpt"),
    radius: tag(float, "brush radius (m); optional for gravity (omit = whole mesh)") = None,
    at: tag(str, "WHERE to brush — 'selection' uses the LIVE edit-mode selection's "
                 "surface-snapped centroid (the measured, no-coordinate default; "
                 "SPEC-09).") = "",
    handle: tag(str, "brush at a named handle's live point (recomputed)") = "",
    # amount (draw/inflate/crease/pinch/flatten)
    amount: tag(float, "[draw/inflate/crease/pinch/flatten] strength") = 1.0,
    # grab displacement — relative directions (m)
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
    # gravity (region-parametric drape)
    strength: tag(float, "[gravity] metres the free (bottom) end falls") = 0.02,
    pin: tag(float, "[gravity] 0..1 top fraction frozen as the attachment") = 0.25,
    falloff: tag(str, "brush falloff SMOOTH|SHARP|…") = "SMOOTH",
    subdivide: tag(bool, "force extra resolution under the brush first (a coarse footprint "
                         "auto-densifies to detail= anyway — G213; this adds a pass on top)") = False,
    detail: tag(float, "target edge length (m) the footprint is densified to before the "
                       "stroke (default radius/4) so the falloff can actually appear on a "
                       "coarse mesh (G213)") = None,
    connected: tag(bool, "scope GEODESICALLY along the surface instead of a euclidean "
                         "sphere — on a thin shell this walks ONE wall instead of grabbing "
                         "the opposing wall and shredding it (G215)") = False,
    label: str = "",
) -> str:
    """
    Sculpt a mesh — **Sculpt Mode** brushes. WHERE to stroke: at='selection' (the
    live selection's surface-snapped centroid — measured, no coordinate) or
    handle=<name> (a named anchor's live point). Strokes within `radius`. `brush`
    selects:

      grab    — drag verts   (out/up/left/.. relative)
      draw    — raise/lower along a normal  (amount, normal_x/y/z)
      inflate — push along per-vert normals (amount)
      smooth  — relax surface               (iterations)
      crease  — pull into a sharp ridge     (amount; falloff defaults SHARP)
      pinch   — pull verts together         (amount)
      flatten — flatten toward a plane      (amount, plane_normal_x/y/z)
      gravity — DRAPE a soft form: pin the top, let the lower mass fall →
                a hanging/teardrop shape by construction (strength, pin). Scope
                with at=selection/handle + radius, or omit the point to drape the
                whole mesh.

    falloff: SMOOTH|SHARP|… subdivide=True adds resolution under the brush first.

    NOT a sculpt brush: organic surface BREAK-UP (lumpy noise, glaze drips) is
    `edit op=noise_displace`; a soft directional bulge on a dense/irregular mesh is
    `edit op=proportional_move` (a uniform normal-push `inflate` lumps it — see
    guidance). Pass either of those to `brush=` and you'll be pointed back here.
    """
    b = brush.lower().strip()
    note = ""
    at_x = at_y = at_z = None
    if at.strip().lower() == "selection":
        pt, nrm, sugg_r, err = queries.resolve_selection_anchor(target)
        if err:
            return err
        at_x, at_y, at_z = pt
        # Phase 3 — the selection is a bundle of affordances: source the brush RADIUS
        # from its extent and the push DIRECTION from its normal when not given.
        if radius is None and sugg_r:
            radius = sugg_r
            note += f"radius {round(sugg_r,4)}m from selection extent\n"
        if b == "draw" and (normal_x, normal_y, normal_z) == (0.0, 0.0, 0.0) and nrm:
            normal_x, normal_y, normal_z = nrm
    elif handle:
        pt, err, drift = handles.resolve_point(handle)
        if err:
            return err
        note = drift or ""
        at_x, at_y, at_z = pt
    # gravity is region-parametric, not a stroke: it allows no point (whole mesh).
    if b == "gravity":
        return note + _s.sculpt_gravity(target, at_x, at_y, at_z, radius,
                                        strength, pin, falloff, subdivide,
                                        detail, connected, label)
    if at_x is None or at_y is None or at_z is None:
        return "sculpt: need a brush point — pass at=selection or handle=<name>"
    if radius is None:
        return "sculpt: 'radius' is required for this brush"
    if b == "grab":
        result = _s.sculpt_grab(target, at_x, at_y, at_z, radius, None, None, None,
                                out, inward, up, down, left, right, forward, back,
                                falloff, subdivide, detail, connected, label)
    elif b == "draw":
        result = _s.sculpt_draw(target, at_x, at_y, at_z, radius, amount,
                                normal_x, normal_y, normal_z, falloff, subdivide,
                                detail, connected, label)
    elif b == "inflate":
        result = _s.sculpt_inflate(target, at_x, at_y, at_z, radius, amount,
                                   falloff, subdivide, detail, connected, label)
    elif b == "smooth":
        result = _s.sculpt_smooth(target, at_x, at_y, at_z, radius, iterations,
                                  falloff, subdivide, detail, connected, label)
    elif b == "crease":
        result = _s.sculpt_crease(target, at_x, at_y, at_z, radius, amount,
                                  falloff if falloff != "SMOOTH" else "SHARP",
                                  subdivide, detail, connected, label)
    elif b == "pinch":
        result = _s.sculpt_pinch(target, at_x, at_y, at_z, radius, amount,
                                 falloff, subdivide, detail, connected, label)
    elif b == "flatten":
        result = _s.sculpt_flatten(target, at_x, at_y, at_z, radius, amount,
                                   plane_normal_x, plane_normal_y, plane_normal_z,
                                   falloff, subdivide, detail, connected, label)
    else:
        where = _ELSEWHERE.get(b)
        if where:
            return (f"sculpt has no '{b}' brush — that's {where}. "
                    f"sculpt brushes are: {' | '.join(_BRUSHES)}.")
        return unknown("sculpt", "brush", brush, _BRUSHES)
    return note + result

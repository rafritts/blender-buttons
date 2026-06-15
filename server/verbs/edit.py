"""edit — Edit Mode / the Mesh menu (SPEC-05).

Mesh-editing operations on the active object's geometry (its current selection):
extrude, bevel, loop cut, merge, delete, mark sharp, taper, bend, boolean, … `op`
selects the operation. The flat handlers manage entering Edit Mode on `target`.
"""

from server._core import mcp
from server import editmode, finishes, rings, bands, introspect, modifiers
from ._common import unknown

_OPS = ["extrude", "bevel", "loop_cut", "merge", "delete", "separate",
        "mark_sharp", "crease", "inflate", "jitter", "proportional_move",
        "extrude_along_curve", "round", "bend", "smooth_edges", "taper_end",
        "taper_section", "scale_rings", "band", "trace", "boolean"]


@mcp.tool(name="edit")
def edit(
    op: str,
    target: str = "",
    # directional amounts (extrude / move-style ops; meters, local frame)
    out: float = 0.0, inward: float = 0.0, up: float = 0.0, down: float = 0.0,
    left: float = 0.0, right: float = 0.0, forward: float = 0.0, back: float = 0.0,
    until_contact: str = "", until_length: float = 0.0,
    x: float = 0.0, y: float = 0.0, z: float = 0.0,
    # bevel
    width: float = 0.0, factor: float = 0.05, segments: int = 1, affect: str = "EDGES",
    # loop_cut / axis-based
    axis: str = "Z", cuts: int = 1,
    # merge / delete / sharp / crease
    threshold: float = 0.001, selected_only: bool = False,
    mode: str = "VERT", clear: bool = False, weight: float = 1.0,
    # inflate / jitter / proportional
    amount: float = 0.003, seed: int = 0, only_positive: bool = False,
    radius: float = 0.01, falloff: str = "SMOOTH",
    # separate
    new_name: str = "",
    # extrude_along_curve
    curve: str = "", taper: float = 1.0,
    # round_corners
    corners: list = None,
    # bend
    angle: float = 0.0, apply: bool = True,
    # smooth_edges
    angle_limit: float = 30.0,
    # taper / rings
    end: str = "MAX", scale: float = 0.0, indices: list = None,
    from_ring: int = 0, to_ring: int = -1,
    x_start: float = 1.0, x_end: float = 1.0, y_start: float = 1.0, y_end: float = 1.0,
    curve_shape: str = "linear",
    # ring scale (op=scale_rings uses x/y as ring-plane scale factors)
    ring_x: float = 1.0, ring_y: float = 1.0,
    # band_around
    name: str = "", at: float = None, thickness: float = 0.02,
    # trace_profile
    sections: int = 24,
    # boolean
    cutter: str = "", bool_op: str = "DIFFERENCE", solver: str = "EXACT",
    hide_cutter: bool = True,
    label: str = "",
) -> str:
    """
    Mesh editing — **Edit Mode / Mesh** menu. Operates on the active object's
    current selection. `op` selects:

      extrude     — push the selection out (out/inward/up/down/left/right/forward/back
                    meters, or until_contact=obj / until_length)
      bevel       — round edges/verts   (width OR factor, segments, affect=EDGES|VERTICES)
      loop_cut    — add edge loops       (axis, cuts)
      merge       — merge by distance    (threshold, selected_only)
      delete      — delete geometry      (mode=VERT|EDGE|FACE|ONLY_FACE|EDGE_FACE)
      separate    — split selection into a new object   (new_name)
      mark_sharp  — mark/clear sharp edges               (clear)
      crease      — set edge crease weight               (weight)
      inflate     — push verts along normals             (amount)
      jitter      — randomize verts        (amount, axis, seed, only_positive)
      proportional_move — soft move with falloff (directional + radius, falloff)
      extrude_along_curve — sweep selection along a curve (curve, segments, taper)
      round       — round named corners    (corners=[...], radius→width, segments)
      bend        — bend the object        (angle, axis, apply)
      smooth_edges— bevel+shade for soft edges  (width, segments, angle_limit)
      taper_end   — taper one end to a scale     (axis, end=MAX|MIN, scale)
      taper_section — taper a ring range (axis, from_ring, to_ring, x_start/x_end/
                    y_start/y_end, curve_shape)
      scale_rings — scale specific rings   (axis, indices=[...], ring_x, ring_y)
      band        — wrap a raised band     (name, target(s), axis, at, width, thickness)
      trace       — trace a cross-section profile  (target, axis, sections)
      boolean     — boolean with a cutter  (cutter, bool_op=DIFFERENCE|UNION|
                    INTERSECT, solver, apply, hide_cutter)
    """
    o = op.lower().strip()
    if o == "extrude":
        return editmode.extrude(out, inward, up, down, left, right, forward, back,
                                until_contact, until_length, x, y, z, label, target)
    if o == "bevel":
        return editmode.bevel(width, factor, segments, affect, label, target)
    if o == "loop_cut":
        return editmode.loop_cut(axis, cuts, label, target)
    if o == "merge":
        return editmode.merge_by_distance(threshold, selected_only, label, target)
    if o == "delete":
        return editmode.delete_geometry(mode, label, target)
    if o == "separate":
        return editmode.separate_selection(new_name, label)
    if o == "mark_sharp":
        return editmode.mark_sharp(clear, label, target)
    if o == "crease":
        return editmode.set_edge_crease(weight, label, target)
    if o == "inflate":
        return editmode.inflate_selection(amount, label)
    if o == "jitter":
        return editmode.jitter_vertices(amount, axis, seed, only_positive, label)
    if o == "proportional_move":
        return editmode.proportional_move(out, inward, up, down, left, right,
                                          forward, back, x, y, z, radius, falloff, label)
    if o == "extrude_along_curve":
        return editmode.extrude_along_curve(curve, segments, taper, label)
    if o == "round":
        return finishes.round_corners(target, corners or [], width or 0.02, segments, label)
    if o == "bend":
        return finishes.bend(target, angle, axis, apply, label)
    if o == "smooth_edges":
        return finishes.smooth_edges(target, width or 0.002, segments, angle_limit, label)
    if o == "taper_end":
        return rings.taper_end(axis, end, scale, label, target)
    if o == "taper_section":
        return rings.taper_section(axis, from_ring, to_ring, x_start, x_end,
                                   y_start, y_end, curve_shape, label, target)
    if o == "scale_rings":
        return rings.scale_rings(axis, indices or [], ring_x, ring_y, label, target)
    if o == "band":
        return bands.band_around(name, target, axis, at, width or 0.05, thickness, label)
    if o == "trace":
        return introspect.trace_profile(target, axis, sections)
    if o == "boolean":
        return modifiers.boolean(target, cutter, bool_op, solver, apply, hide_cutter, label)
    return unknown("edit", "op", op, _OPS)

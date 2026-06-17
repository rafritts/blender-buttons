"""edit — Edit Mode / the Mesh menu (SPEC-05).

Mesh-editing operations on the active object's geometry (its current selection):
extrude, bevel, loop cut, merge, delete, mark sharp, taper, bend, boolean, … `op`
selects the operation. The flat handlers manage entering Edit Mode on `target`.
"""

from typing import Literal

from server._core import mcp
from server import editmode, finishes, rings, bands, introspect, modifiers
from ._common import tag, unknown

_OPS = ["extrude", "bevel", "loop_cut", "merge", "delete", "separate",
        "mark_sharp", "crease", "inflate", "jitter", "proportional_move",
        "extrude_along_curve", "round", "bend", "smooth_edges", "taper_end",
        "taper_section", "scale_rings", "band", "trace", "boolean", "subdivide", "bridge"]


@mcp.tool(name="edit")
def edit(
    op: Literal["extrude", "bevel", "loop_cut", "merge", "delete", "separate",
                "mark_sharp", "crease", "inflate", "jitter", "proportional_move",
                "extrude_along_curve", "round", "bend", "smooth_edges", "taper_end",
                "taper_section", "scale_rings", "band", "trace", "boolean", "subdivide",
                "bridge"],
    target: tag(str, "mesh object to edit (empty=active)") = "",
    # bridge — weld two boundary handles (SPEC-07 Phase 5 / G10)
    a: tag(str, "[bridge] first boundary handle to weld (order-independent)") = "",
    b: tag(str, "[bridge] second boundary handle to weld") = "",
    # directional amounts (extrude / move-style ops; meters, local frame)
    out: tag(float, "[extrude/proportional_move] push out along normal (m)") = 0.0,
    inward: tag(float, "[extrude/proportional_move] push inward (m)") = 0.0,
    up: tag(float, "[extrude/proportional_move] +Z (m)") = 0.0,
    down: tag(float, "[extrude/proportional_move] -Z (m)") = 0.0,
    left: tag(float, "[extrude/proportional_move] -X (m)") = 0.0,
    right: tag(float, "[extrude/proportional_move] +X (m)") = 0.0,
    forward: tag(float, "[extrude/proportional_move] -Y (m)") = 0.0,
    back: tag(float, "[extrude/proportional_move] +Y (m)") = 0.0,
    until_contact: tag(str, "[extrude] extrude until hitting this object") = "",
    until_length: tag(float, "[extrude] extrude to this total length (m)") = 0.0,
    x: tag(float, "[extrude/proportional_move] explicit X amount (m)") = 0.0,
    y: tag(float, "[extrude/proportional_move] explicit Y amount (m)") = 0.0,
    z: tag(float, "[extrude/proportional_move] explicit Z amount (m)") = 0.0,
    # bevel
    width: tag(float, "[bevel/round/smooth_edges] bevel width (m)") = 0.0,
    factor: tag(float, "[bevel] bevel amount as a factor (alt to width)") = 0.05,
    segments: tag(int, "[bevel/round/smooth_edges] bevel segments") = 1,
    affect: tag(str, "[bevel] EDGES | VERTICES") = "EDGES",
    # loop_cut / axis-based
    axis: tag(str, "[loop_cut/taper_end/taper_section/scale_rings/band/trace] axis X|Y|Z") = "Z",
    cuts: tag(int, "[loop_cut/subdivide] number of cuts to add") = 1,
    subdivide_smooth: tag(float, "[subdivide] 0=flat (denser cage) … ~1=round toward limit surface") = 0.0,
    # merge / delete / sharp / crease
    threshold: tag(float, "[merge] merge-by-distance threshold (m)") = 0.001,
    selected_only: tag(bool, "[merge] merge only within the selection") = False,
    mode: tag(str, "[delete] VERT|EDGE|FACE|ONLY_FACE|EDGE_FACE") = "VERT",
    clear: tag(bool, "[mark_sharp] clear instead of mark") = False,
    weight: tag(float, "[crease] crease weight 0..1") = 1.0,
    # inflate / jitter / proportional
    amount: tag(float, "[inflate/jitter] displacement amount (m)") = 0.003,
    seed: tag(int, "[jitter] random seed") = 0,
    only_positive: tag(bool, "[jitter] jitter outward only") = False,
    radius: tag(float, "[proportional_move] falloff radius (m)") = 0.01,
    falloff: tag(str, "[proportional_move] SMOOTH|SHARP|…") = "SMOOTH",
    # separate
    new_name: tag(str, "[separate] name for the split-off object") = "",
    # extrude_along_curve
    curve: tag(str, "[extrude_along_curve] curve to sweep along") = "",
    taper: tag(float, "[extrude_along_curve] end scale (taper)") = 1.0,
    # round_corners
    corners: tag(list, "[round] named corners to round") = None,
    # bend
    angle: tag(float, "[bend] bend angle (deg)") = 0.0,
    apply: tag(bool, "[bend] apply the bend modifier") = True,
    # smooth_edges
    angle_limit: tag(float, "[smooth_edges] shade-smooth angle limit (deg)") = 30.0,
    # taper / rings
    end: tag(str, "[taper_end] which end MAX|MIN") = "MAX",
    scale: tag(float, "[taper_end] end scale factor") = 0.0,
    indices: tag(list, "[scale_rings] ring indices to scale") = None,
    from_ring: tag(int, "[taper_section] first ring") = 0,
    to_ring: tag(int, "[taper_section] last ring (-1 = end)") = -1,
    x_start: tag(float, "[taper_section] X scale at from_ring") = 1.0,
    x_end: tag(float, "[taper_section] X scale at to_ring") = 1.0,
    y_start: tag(float, "[taper_section] Y scale at from_ring") = 1.0,
    y_end: tag(float, "[taper_section] Y scale at to_ring") = 1.0,
    curve_shape: tag(str, "[taper_section] interpolation: linear|ease_in|ease_out|ease_in_out|smoothstep") = "linear",
    # ring scale (op=scale_rings uses x/y as ring-plane scale factors)
    ring_x: tag(float, "[scale_rings] X scale of the rings") = 1.0,
    ring_y: tag(float, "[scale_rings] Y scale of the rings") = 1.0,
    # band_around
    name: tag(str, "[band] name for the new band object") = "",
    at: tag(float, "[band] position along axis (0..1)") = None,
    thickness: tag(float, "[band] band thickness (m)") = 0.02,
    # trace_profile
    sections: tag(int, "[trace] number of cross-sections") = 24,
    # boolean
    cutter: tag(str, "[boolean] cutter object") = "",
    bool_op: tag(str, "[boolean] DIFFERENCE|UNION|INTERSECT") = "DIFFERENCE",
    solver: tag(str, "[boolean] EXACT|FAST") = "EXACT",
    hide_cutter: tag(bool, "[boolean] hide the cutter afterward") = True,
    label: str = "",
) -> str:
    """
    Mesh editing — **Edit Mode / Mesh** menu. Operates on the active object's
    current selection. `op` selects:

      extrude     — push the selection out (out/inward/up/down/left/right/forward/back
                    meters, or until_contact=obj / until_length)
      bevel       — round edges/verts   (width OR factor, segments, affect=EDGES|VERTICES)
      loop_cut    — add edge loops       (axis, cuts)
      subdivide   — densify the SELECTED patch locally — sculptable resolution where
                    you select, no global loops, no shape-key block  (cuts, subdivide_smooth)
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
      bend        — bend the object into an arc  (angle, axis, apply). Pivots about
                    the object ORIGIN and is SYMMETRIC about it — a bar centred on its
                    origin humps both ways ("mustache"); move the origin to one end
                    for a one-way crescent. apply=True forces OBJECT mode.
      smooth_edges— bevel+shade for soft edges  (width, segments, angle_limit)
      taper_end   — taper one end to a scale     (axis, end=MAX|MIN, scale)
      taper_section — taper a ring range (axis, from_ring, to_ring, x_start/x_end/
                    y_start/y_end, curve_shape)
      scale_rings — scale specific rings   (axis, indices=[...], ring_x, ring_y)
      band        — wrap a raised band     (name, target(s), axis, at, width, thickness)
      trace       — trace a cross-section profile  (target, axis, sections)
      boolean     — boolean with a cutter  (cutter, bool_op=DIFFERENCE|UNION|
                    INTERSECT, solver, apply, hide_cutter)
      bridge      — weld two open boundary loops into a continuous surface (the
                    bridge-edge-loops primitive). a/b are two boundary handles (mint
                    with feel op=assembly); their rims get bridged. SAME-OBJECT only —
                    join cross-object parts first (object op=join), then bridge on the
                    joined mesh. Keyed/rigged meshes refused (topology change corrupts
                    the deform). Order-independent.     (a, b)
    """
    o = op.lower().strip()
    if o == "extrude":
        return editmode.extrude(out, inward, up, down, left, right, forward, back,
                                until_contact, until_length, x, y, z, label, target)
    if o == "bevel":
        return editmode.bevel(width, factor, segments, affect, label, target)
    if o == "loop_cut":
        return editmode.loop_cut(axis, cuts, label, target)
    if o == "subdivide":
        return editmode.subdivide_selection(cuts, subdivide_smooth, label, target)
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
        return editmode.jitter_vertices(amount, axis, seed, only_positive, label, target)
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
    if o == "bridge":
        return editmode.bridge(a, b, label)
    return unknown("edit", "op", op, _OPS)

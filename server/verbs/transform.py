"""transform — move / rotate / scale / snap / mirror / array (SPEC-05).

Mode-agnostic transforms: relocate, resize, rotate, snap, mirror, distribute,
array, scatter — plus vertex-level move/scale. `op` selects the operation;
`targets` is "" (active), one name, or "a,b,c".
"""

from typing import Literal

from server._core import mcp
from server import transforms, relational, editmode, handles
from ._common import tag, unknown

_OPS = ["nudge", "move_to", "rotate_to", "resize", "scale", "rotate", "apply",
        "snap", "snap_grid", "match_dim", "mirror", "distribute", "array_corners",
        "array_along", "array_radial", "scatter", "move_verts", "scale_verts",
        "snap_loop"]


@mcp.tool(name="transform")
def transform(
    op: Literal["nudge", "move_to", "rotate_to", "resize", "scale", "rotate", "apply",
                "snap", "snap_grid", "match_dim", "mirror", "distribute",
                "array_corners", "array_along", "array_radial", "scatter",
                "move_verts", "scale_verts", "snap_loop"],
    targets: tag(str, "object(s): '' active, 'name', or 'a,b,c'") = "",
    # nudge (relative meters)
    right: tag(float, "[nudge] +X (m)") = 0.0,
    left: tag(float, "[nudge] -X (m)") = 0.0,
    up: tag(float, "[nudge/move_verts] +Z (m)") = 0.0,
    down: tag(float, "[nudge/move_verts] -Z (m)") = 0.0,
    back: tag(float, "[nudge/move_verts] +Y (m)") = 0.0,
    forward: tag(float, "[nudge/move_verts] -Y (m)") = 0.0,
    inward: tag(float, "[move_verts] inward along normal (m)") = 0.0,
    out: tag(float, "[move_verts] outward along normal (m)") = 0.0,
    # move_to (absolute world position; omitted axis preserved)
    to_x: tag(float, "[move_to] absolute world X (m)") = None,
    to_y: tag(float, "[move_to] absolute world Y (m)") = None,
    to_z: tag(float, "[move_to] absolute world Z (m)") = None,
    # rotate_to (absolute euler degrees; omitted axis preserved). Separate from to_*
    # so no field means two things (G23): a param's meaning is clear from its name.
    deg_x: tag(float, "[rotate_to] absolute X euler (deg)") = None,
    deg_y: tag(float, "[rotate_to] absolute Y euler (deg)") = None,
    deg_z: tag(float, "[rotate_to] absolute Z euler (deg)") = None,
    handle: tag(str, "[move_to/snap_loop] a named handle: move_to moves a whole object "
                     "TO its point; snap_loop seats the selected loop ONTO it") = "",
    # resize (absolute meters)
    width: tag(float, "[resize] absolute X extent (m)") = None,
    depth: tag(float, "[resize] absolute Y extent (m)") = None,
    height: tag(float, "[resize] absolute Z extent (m)") = None,
    # scale / rotate
    factor: tag(float, "[scale] multiply size by") = 1.0,
    pivot: tag(str, "[scale/rotate] pivot: center (default; scale=bbox centre, rotate=own origin) | bbox_center | cursor | origin") = "center",
    pivot_object: tag(str, "[scale/rotate] object to pivot around") = "",
    angle: tag(float, "[rotate] degrees") = 0.0,
    axis: tag(str, "[rotate/match_dim/array_*] axis X|Y|Z") = "Z",
    # apply
    scale: tag(bool, "[apply] bake scale into mesh data") = True,
    rotation: tag(bool, "[apply] bake rotation") = False,
    location: tag(bool, "[apply] bake location") = False,
    # snap
    target: tag(str, "[snap/match_dim] object to snap/measure against") = "",
    side: tag(str, "[snap] target side, e.g. Z_MAX") = "Z_MAX",
    source_side: tag(str, "[snap] moved-object side (AUTO infers)") = "AUTO",
    offset: tag(float, "[snap] gap along the snap axis (m)") = 0.0,
    # snap_grid
    size: tag(float, "[snap_grid] grid size (m)") = 0.1,
    axes: tag(str, "[snap_grid] axes to snap, e.g. XYZ") = "XYZ",
    # match_dim
    reference: tag(str, "[match_dim] object whose extent to match") = "",
    # mirror
    plane: tag(str, "[mirror] mirror plane X|Y|Z") = "X",
    suffix: tag(str, "[mirror] suffix for the mirrored copy") = "_mirror",
    replace: tag(bool, "[mirror] replace existing mirror") = None,
    # distribute / array
    between: tag(list, "[distribute/array_along] two endpoint objects [a,b]") = None,
    prototype: tag(str, "[array_*] object to copy") = "",
    of: tag(str, "[array_corners] target whose 4 corners to fill") = "",
    count: tag(int, "[array_along/array_radial] number of copies") = 0,
    standing_on_floor: tag(bool, "[array_corners] keep copies on the floor") = True,
    keep_original: tag(bool, "[array_*] keep the prototype") = False,
    name_prefix: tag(str, "[array_*/scatter] name prefix for copies") = "",
    center: tag(list, "[array_radial] ring center [x,y,z]") = None,
    center_object: tag(str, "[array_radial] object at the ring center") = "",
    start_angle: tag(float, "[array_radial] start angle (deg)") = 0.0,
    end_angle: tag(float, "[array_radial] end angle (deg)") = 360.0,
    radius: tag(float, "[array_radial] ring radius (m)") = None,
    align_to_tangent: tag(bool, "[array_radial] rotate copies to the ring tangent") = False,
    # scatter
    source: tag(str, "[scatter] surface object to scatter onto") = "",
    scale_min: tag(float, "[scatter] min random scale") = 0.8,
    scale_max: tag(float, "[scatter] max random scale") = 1.2,
    align_normal: tag(bool, "[scatter] align copies to surface normal") = True,
    rotate_z: tag(bool, "[scatter] random Z rotation") = True,
    parent_to_target: tag(bool, "[scatter] parent copies to the surface") = True,
    seed: tag(int, "[scatter] random seed") = 0,
    avoid: tag(str, "[scatter] object/region to avoid") = "",
    avoid_margin: tag(float, "[scatter] avoidance margin (m)") = 0.0,
    # move_verts / scale_verts (edit-mode component transforms)
    x: tag(float, "[move_verts] explicit X amount (m)") = 0.0,
    y: tag(float, "[move_verts] explicit Y amount (m)") = 0.0,
    z: tag(float, "[move_verts] explicit Z amount (m)") = 0.0,
    sx: tag(float, "[scale_verts] X scale factor") = 1.0,
    sy: tag(float, "[scale_verts] Y scale factor") = 1.0,
    sz: tag(float, "[scale_verts] Z scale factor") = 1.0,
    in_plane: tag(float, "[scale_verts] in-plane scale (flatten)") = 0.0,
    vert_pivot: tag(str, "[scale_verts] SELECTION|CURSOR|…") = "SELECTION",
    # snap_loop
    fit_scale: tag(bool, "[snap_loop] scale the loop rim→rim to the target (False=keep size)") = True,
    fit_rotation: tag(bool, "[snap_loop] tilt the loop's plane parallel to the target") = False,
    label: str = "",
) -> str:
    """
    Transform objects (or verts) — the **transform** tools. `op` selects:

      nudge    — relative move in meters  (right/left/up/down/back/forward/inward/out)
      move_to  — set ABSOLUTE world position (to_x/to_y/to_z; omitted axis preserved) —
                 drop at a computed point, e.g. a feel op=aim hit, or handle=<name>
                 to move TO a handle's live point
      rotate_to— set ABSOLUTE euler rotation in degrees (deg_x/deg_y/deg_z; omitted
                 kept). Distinct param names from move_to's to_*, so no field is
                 polymorphic — meaning is unambiguous from the name alone.
      resize   — set absolute dims         (width, depth, height)
      scale    — multiply size             (factor, pivot=center|.., pivot_object)
      rotate   — rotate degrees            (angle, axis, pivot, pivot_object)
      apply    — bake transform to data    (scale, rotation, location)
      snap     — snap flush to a target    (target, side, source_side, offset)
      snap_grid— round origin to a grid    (size, axes)
      match_dim— match one object's extent (target, reference, axis)
      mirror   — mirrored copy across a plane (targets, plane=X|Y|Z, suffix, replace)
      distribute — space evenly between two (targets, between=[a,b], axis)
      array_corners — copy to a target's 4 corners (prototype, of, standing_on_floor)
      array_along  — N copies between two   (prototype, count, between=[a,b], axis)
      array_radial — N copies in a ring (prototype, count, center|center_object, axis,
                   start_angle, end_angle, radius, align_to_tangent)
      scatter  — scatter copies on a surface (target, source, count, scale_min/max, …)
      move_verts — move selected verts (edit) (out/up/.. or x/y/z, target)
      scale_verts— scale selected verts (edit) (sx/sy/sz, in_plane, vert_pivot, target)
      snap_loop  — seat the SELECTED boundary loop onto a target opening (handle):
                   translate centre→centre, optional scale rim→rim (fit_scale) and
                   tilt plane→plane (fit_rotation). The action half of feel op=assembly
                   — fit, then `edit op=bridge` welds. Be in edit mode, loop selected.
    """
    o = op.lower().strip()
    if o == "nudge":
        return transforms.nudge(targets, right, left, up, down, back, forward, label)
    if o == "move_to":
        note = ""
        if handle:
            pt, err, drift = handles.resolve_point(handle)
            if err:
                return err
            note = drift or ""
            to_x = pt[0] if to_x is None else to_x
            to_y = pt[1] if to_y is None else to_y
            to_z = pt[2] if to_z is None else to_z
        return note + transforms.move_to(targets, to_x, to_y, to_z, label)
    if o == "rotate_to":
        # deg_* is the correct field; fall back to the old to_* only if deg_* unset,
        # so pre-G23 callers still work while the schema steers to the clear name.
        rx = deg_x if deg_x is not None else to_x
        ry = deg_y if deg_y is not None else to_y
        rz = deg_z if deg_z is not None else to_z
        return transforms.rotate_to(targets, rx, ry, rz, label)
    if o == "resize":
        return transforms.resize(targets, width, depth, height, label)
    if o == "scale":
        return transforms.scale_group(targets, factor, pivot, label)
    if o == "rotate":
        return transforms.rotate_object(angle, axis, targets, pivot, pivot_object, label)
    if o == "apply":
        return transforms.apply_transform(targets, scale, rotation, location, label)
    if o == "snap":
        return transforms.snap_to(target, side, source_side, offset, label)
    if o == "snap_grid":
        return transforms.snap_to_grid(size, axes, label)
    if o == "match_dim":
        return relational.match_dimension(target, reference, axis, label)
    if o == "mirror":
        return relational.mirror_across(targets, plane, suffix, replace, label)
    if o == "distribute":
        return relational.distribute_evenly(targets, between or [], axis, label)
    if o == "array_corners":
        return relational.array_at_corners(prototype, of, standing_on_floor,
                                           keep_original, name_prefix, label)
    if o == "array_along":
        return relational.array_along(prototype, count, between or [], axis,
                                      keep_original, name_prefix, label)
    if o == "array_radial":
        return relational.array_radial(prototype, count, center, center_object, axis,
                                       start_angle, end_angle, radius, align_to_tangent,
                                       keep_original, name_prefix, label)
    if o == "scatter":
        return relational.scatter_on_surface(target, source, count or 100, scale_min,
                                             scale_max, align_normal, rotate_z,
                                             parent_to_target, seed, name_prefix,
                                             avoid, avoid_margin, label)
    if o == "move_verts":
        return editmode.move_vertices(out, inward, up, down, left, right, forward,
                                      back, x, y, z, label, target)
    if o == "scale_verts":
        return editmode.scale_vertices(in_plane, sx, sy, sz, vert_pivot, label, target)
    if o == "snap_loop":
        return editmode.snap_loop(handle, fit_scale, fit_rotation, label)
    return unknown("transform", "op", op, _OPS)

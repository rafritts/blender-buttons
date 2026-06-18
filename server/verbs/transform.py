"""transform — move / rotate / scale / snap / mirror / array (SPEC-05).

Mode-agnostic transforms: relocate, resize, rotate, snap, mirror, distribute,
array, scatter — plus vertex-level move/scale. `op` selects the operation;
`targets` is "" (active), one name, or "a,b,c".
"""

from typing import Literal

from server._core import mcp
from server import transforms, relational, editmode, handles
from ._common import tag, unknown, teach

_OPS = ["nudge", "place", "move_to", "rotate_to", "aim_axis", "rest_on", "resize", "scale",
        "rotate", "apply", "snap", "snap_grid", "match_dim", "mirror", "distribute",
        "array_corners", "array_along", "array_radial", "scatter", "move_verts",
        "scale_verts", "snap_loop"]


@mcp.tool(name="transform")
def transform(
    op: Literal["nudge", "place", "move_to", "rotate_to", "aim_axis", "rest_on", "resize",
                "scale", "rotate", "apply", "snap", "snap_grid", "match_dim", "mirror",
                "distribute", "array_corners", "array_along", "array_radial", "scatter",
                "move_verts", "scale_verts", "snap_loop"],
    targets: tag(str, "object(s): '' active, 'name', or 'a,b,c'") = "",
    # place (relational re-placement — same DSL as add's on=)
    on: tag(dict, "[place] placement spec — {\"left_of\":\"base\",\"gap\":0}, {\"on\":\"seat\"}, …") = None,
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
    # aim_axis (orient a local axis down a from→to segment)
    aim_from: tag(list, "[aim_axis] start point [x,y,z]") = None,
    aim_to: tag(list, "[aim_axis] end point [x,y,z]") = None,
    from_handle: tag(str, "[aim_axis] start handle (instead of aim_from)") = "",
    to_handle: tag(str, "[aim_axis] end handle (instead of aim_to)") = "",
    # resize (absolute meters)
    width: tag(float, "[resize] absolute X extent (m)") = None,
    depth: tag(float, "[resize] absolute Y extent (m)") = None,
    height: tag(float, "[resize] absolute Z extent (m)") = None,
    # scale / rotate
    factor: tag(float, "[scale] multiply size by") = 1.0,
    pivot: tag(str, "[scale/rotate] pivot: center (default; scale=bbox centre, rotate=own origin) | bbox_center | cursor | origin") = "center",
    pivot_object: tag(str, "[scale/rotate] object to pivot around") = "",
    angle: tag(float, "[rotate] degrees") = 0.0,
    axis: tag(str, "[rotate/match_dim/array_*] axis X|Y|Z; [aim_axis] local axis (signed ok, e.g. -Z); [rest_on] drop axis") = "Z",
    # apply
    scale: tag(bool, "[apply] bake scale into mesh data") = True,
    rotation: tag(bool, "[apply] bake rotation") = False,
    location: tag(bool, "[apply] bake location") = False,
    # snap
    target: tag(str, "[snap/match_dim] object to snap/measure against; [rest_on] surface to rest on; [scatter] the SURFACE to scatter onto") = "",
    side: tag(str, "[snap] target side, e.g. Z_MAX") = "Z_MAX",
    source_side: tag(str, "[snap] moved-object side (AUTO infers)") = "AUTO",
    offset: tag(float, "[snap] gap along the snap axis (m); [rest_on] clearance after contact (m)") = 0.0,
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
    source: tag(str, "[scatter] the object to instance across the surface (copies share its mesh data); the surface is target=") = "",
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
      place    — RE-place an existing object with the relational DSL (on=) — the same
                 vocabulary as add's on=, but for objects already in the scene. Seat
                 left_of/on/under/at_corner another without raw coordinates. Resolves
                 against the object's own dims; place one object at a time.
      move_to  — set ABSOLUTE world position (to_x/to_y/to_z; omitted axis preserved) —
                 drop at a computed point, e.g. a feel op=aim hit, or handle=<name>
                 to move TO a handle's live point
      rotate_to— set ABSOLUTE euler rotation in degrees (deg_x/deg_y/deg_z; omitted
                 kept). Distinct param names from move_to's to_*, so no field is
                 polymorphic — meaning is unambiguous from the name alone.
      aim_axis — orient a LOCAL axis down a from→to segment (aim_from/aim_to points or
                 from_handle/to_handle; axis=Z default, signed ok). The orient-along-
                 an-edge primitive for solids that don't self-orient like type=tube —
                 lay a coil/bolt/strut along a direction without hand-trig. Rotation
                 only; pair with move_to to position.
      rest_on  — drop along −axis until the object's REAL geometry rests on `target`
                 (axis=Z default, offset=clearance). BVH from the source's own verts,
                 so tilted/irregular parts seat by their true lowest point — the action
                 half of feel op=contacts 'floating Xmm'.
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
    # G23 move 3 — teaching errors: a valid op missing a structurally-required param
    # (a destination, a target, a prototype, two endpoints) gets the requirement named
    # + a canonical call, instead of a silent no-op or a deep crash.
    bad = teach("transform", "op", o, {
        "place":         (bool(on),
                          "on=<placement spec> (same DSL as add's on=)",
                          "transform op=place targets=cup on={\"left_of\":\"base\",\"gap\":0}"),
        "move_to":       (bool(handle) or any(v is not None for v in (to_x, to_y, to_z)),
                          "to_x/to_y/to_z (any) or handle=<name>",
                          "transform op=move_to targets=cap to_z=1.2"),
        "rotate_to":     (any(v is not None for v in (deg_x, deg_y, deg_z, to_x, to_y, to_z)),
                          "deg_x/deg_y/deg_z (any)",
                          "transform op=rotate_to targets=guide deg_z=25"),
        "aim_axis":      ((aim_from and aim_to) or (from_handle and to_handle),
                          "aim_from+aim_to (points) or from_handle+to_handle",
                          "transform op=aim_axis targets=bolt aim_from=[0,0,0] aim_to=[1,0,0] axis=Z"),
        "rest_on":       (bool(target),
                          "target=<surface to rest on>",
                          "transform op=rest_on targets=crate target=floor axis=Z"),
        "resize":        (any(v is not None for v in (width, depth, height)),
                          "width/depth/height (any)",
                          "transform op=resize targets=box width=0.5"),
        "snap":          (bool(target),
                          "target=<object to snap against>",
                          "transform op=snap targets=lid target=jar side=Z_MAX"),
        "match_dim":     (bool(target and reference),
                          "target and reference",
                          "transform op=match_dim target=shelf reference=wall axis=X"),
        "distribute":    (bool(between) and len(between or []) == 2,
                          "between=[a,b] (two endpoint objects)",
                          "transform op=distribute targets=a,b,c between=[left,right] axis=X"),
        "array_corners": (bool(prototype and of),
                          "prototype and of=<target whose 4 corners to fill>",
                          "transform op=array_corners prototype=leg of=tabletop"),
        "array_along":   (bool(prototype and count) and len(between or []) == 2,
                          "prototype, count, between=[a,b]",
                          "transform op=array_along prototype=picket count=5 between=[postL,postR]"),
        "array_radial":  (bool(prototype and count and (center or center_object)),
                          "prototype, count, center=[x,y,z] or center_object",
                          "transform op=array_radial prototype=spoke count=8 center_object=hub axis=Z"),
        "scatter":       (bool(target and source),
                          "target=<prototype> and source=<surface to scatter onto>",
                          "transform op=scatter target=rock source=terrain count=50"),
        "snap_loop":     (bool(handle),
                          "handle=<target opening> (be in edit mode, loop selected)",
                          "transform op=snap_loop handle=jar.rim"),
    })
    if bad:
        return bad
    if o == "nudge":
        return transforms.nudge(targets, right, left, up, down, back, forward, label)
    if o == "place":
        return transforms.place(targets, on, label)
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
    if o == "aim_axis":
        frm, to = aim_from, aim_to
        if from_handle:
            pt, err, drift = handles.resolve_point(from_handle)
            if err:
                return err
            frm = pt
        if to_handle:
            pt, err, drift = handles.resolve_point(to_handle)
            if err:
                return err
            to = pt
        return transforms.aim_axis(targets, frm, to, axis, label)
    if o == "rest_on":
        return transforms.rest_on(targets, target, axis, offset, label)
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

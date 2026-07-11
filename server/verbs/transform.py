"""transform — move / rotate / scale / snap / distribute (SPEC-05).

Object-mode relational transforms: relocate, resize, rotate, snap, distribute.
`op` selects the operation; `targets` is "" (active), one name, or "a,b,c".

SPEC-22: this verb is the relational-placement SUBSTRATE (the mouse the agent lacks).
Edit-mode geometry transforms are native hands and live on `edit` now (grab/scale/
lattice/shrink_fatten). The dup-and-place array/mirror composites were stripped — the
native single-operation equivalents are the Mirror and Array MODIFIERS (`modifier op=add`
/ `modifier op=add_asset asset="Array"` — Blender 5.0's GN Array has a native Circular
mode; surface scatter is asset="Scatter on Surface").
"""

from typing import Literal

from server._core import mcp
from server import transforms, relational, editmode, handles
from ._common import tag, unknown, teach

_OPS = ["nudge", "place", "move_to", "rotate_to", "aim_axis", "rest_on", "seat", "resize",
        "scale", "rotate", "apply", "snap", "snap_grid", "match_dim", "distribute",
        "snap_loop"]


@mcp.tool(name="transform")
def transform(
    op: Literal["nudge", "place", "move_to", "rotate_to", "aim_axis", "rest_on", "seat",
                "resize", "scale", "rotate", "apply", "snap", "snap_grid", "match_dim",
                "distribute", "snap_loop"],
    targets: tag(str, "object(s): '' active, 'name', or 'a,b,c'") = "",
    # place (relational re-placement — same DSL as add's on=)
    on: tag(dict, "[place] placement spec — {\"left_of\":\"base\",\"gap\":0}, {\"on\":\"seat\"}, …") = None,
    # nudge (relative meters)
    right: tag(float, "[nudge] +X (m)") = 0.0,
    left: tag(float, "[nudge] -X (m)") = 0.0,
    up: tag(float, "[nudge] +Z (m)") = 0.0,
    down: tag(float, "[nudge] -Z (m)") = 0.0,
    back: tag(float, "[nudge] +Y (m)") = 0.0,
    forward: tag(float, "[nudge] -Y (m)") = 0.0,
    # rotate_to (absolute euler degrees; omitted axis preserved). An ANGLE, not a
    # position — intrinsic orientation, no world coordinate involved.
    deg_x: tag(float, "[rotate_to] absolute X euler (deg)") = None,
    deg_y: tag(float, "[rotate_to] absolute Y euler (deg)") = None,
    deg_z: tag(float, "[rotate_to] absolute Z euler (deg)") = None,
    handle: tag(str, "[move_to/snap_loop] a named handle: move_to moves a whole object "
                     "TO its point; snap_loop seats the selected loop ONTO it") = "",
    # aim_axis (orient a local axis down a from→to segment, by named handles)
    from_handle: tag(str, "[aim_axis] start handle") = "",
    to_handle: tag(str, "[aim_axis] end handle") = "",
    # resize (absolute meters)
    width: tag(float, "[resize] absolute X extent (m)") = None,
    depth: tag(float, "[resize] absolute Y extent (m)") = None,
    height: tag(float, "[resize] absolute Z extent (m)") = None,
    # scale / rotate
    factor: tag(float, "[scale] multiply size by") = 1.0,
    pivot: tag(str, "[scale/rotate] pivot point. rotate: self=own origin (default — each target spins about ITSELF; with several targets use assembly instead) | assembly/bbox_center=shared centre of ALL targets (rigid group turn) | world=world 0,0,0 | cursor. (legacy aliases: center→self, origin→world — named backwards vs Blender, prefer self/world.) scale: center=bbox centre (default) | bottom_center | world | object name") = "center",
    pivot_object: tag(str, "[scale/rotate] object to pivot around") = "",
    angle: tag(float, "[rotate] degrees") = 0.0,
    axis: tag(str, "[rotate/match_dim] axis X|Y|Z; [aim_axis] local axis (signed ok, e.g. -Z); [rest_on/seat] drop axis") = "Z",
    # apply
    scale: tag(bool, "[apply] bake scale into mesh data") = True,
    rotation: tag(bool, "[apply] bake rotation") = False,
    location: tag(bool, "[apply] bake location") = False,
    # snap
    target: tag(str, "[snap/match_dim] object to snap/measure against; [rest_on] surface to rest on; [seat] cavity to seat into") = "",
    side: tag(str, "[snap] target side, e.g. Z_MAX") = "Z_MAX",
    source_side: tag(str, "[snap] moved-object side (AUTO infers)") = "AUTO",
    offset: tag(float, "[snap] gap along the snap axis (m); [rest_on/seat] clearance after contact (m)") = 0.0,
    # snap_grid
    size: tag(float, "[snap_grid] grid size (m)") = 0.1,
    axes: tag(str, "[snap_grid] axes to snap, e.g. XYZ") = "XYZ",
    # match_dim
    reference: tag(str, "[match_dim] object whose extent to match") = "",
    # distribute
    between: tag(list, "[distribute] two endpoint objects [a,b]") = None,
    # snap_loop
    fit_scale: tag(bool, "[snap_loop] scale the loop rim→rim to the target (False=keep size)") = True,
    fit_rotation: tag(bool, "[snap_loop] tilt the loop's plane parallel to the target") = False,
    label: str = "",
) -> str:
    """
    Transform objects — the **transform** tools. `op` selects:

      nudge    — relative move in meters  (right/left/up/down/back/forward)
      place    — RE-place an existing object with the relational DSL (on=) — the same
                 vocabulary as add's on=, but for objects already in the scene. Seat
                 left_of/on/under/at_corner another without raw coordinates. Resolves
                 against the object's own dims; place one object at a time.
      move_to  — move a whole object TO a named handle's live point (handle=<name>) —
                 the relational re-locate: address the destination by name, never by
                 typed coordinate.
      rotate_to— set ABSOLUTE euler rotation in degrees (deg_x/deg_y/deg_z; omitted
                 kept). An angle, not a position — intrinsic orientation only.
      aim_axis — orient a LOCAL axis down a from→to segment (from_handle/to_handle;
                 axis=Z default, signed ok). The orient-along-an-edge primitive for
                 solids that don't self-orient — lay a coil/bolt/strut
                 along a direction without hand-trig. Rotation only; pair with move_to
                 to position.
      rest_on  — drop along −axis until the object's REAL geometry rests on `target`
                 (axis=Z default, offset=clearance). BVH from the source's own verts,
                 so tilted/irregular parts seat by their true lowest point — the action
                 half of feel op=contacts 'floating Xmm'.
      seat     — seat the object DOWN INTO a cavity: lower along −axis onto the highest
                 INTERIOR floor of `target` under its footprint (dial in a bezel well,
                 gem in a setting, lens in a barrel). Unlike rest_on it ignores the
                 cavity's rim/walls (keeps only up-facing floors), so the part sinks in
                 instead of catching on the lip.  (targets, target, axis, offset)
      resize   — set absolute dims         (width, depth, height)
      scale    — multiply size             (factor, pivot=center|.., pivot_object)
      rotate   — rotate degrees            (angle, axis, pivot, pivot_object)
      apply    — bake transform to data    (scale, rotation, location)
      snap     — snap flush to a target    (target, side, source_side, offset)
      snap_grid— round origin to a grid    (size, axes)
      match_dim— match one object's extent (target, reference, axis)
      distribute — space evenly between two (targets, between=[a,b], axis)
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
        "move_to":       (bool(handle),
                          "handle=<name> (a named landmark to move TO)",
                          "transform op=move_to targets=cap handle=jar.rim"),
        "rotate_to":     (any(v is not None for v in (deg_x, deg_y, deg_z)),
                          "deg_x/deg_y/deg_z (any)",
                          "transform op=rotate_to targets=guide deg_z=25"),
        "aim_axis":      (bool(from_handle and to_handle),
                          "from_handle+to_handle (two named handles)",
                          "transform op=aim_axis targets=bolt from_handle=base to_handle=tip axis=Z"),
        "rest_on":       (bool(target),
                          "target=<surface to rest on>",
                          "transform op=rest_on targets=crate target=floor axis=Z"),
        "seat":          (bool(target),
                          "target=<cavity to seat into>",
                          "transform op=seat targets=dial target=case axis=Z"),
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
        pt, err, drift = handles.resolve_point(handle)
        if err:
            return err
        note = drift or ""
        return note + transforms.move_to(targets, pt[0], pt[1], pt[2], label)
    if o == "rotate_to":
        return transforms.rotate_to(targets, deg_x, deg_y, deg_z, label)
    if o == "aim_axis":
        frm, err, _ = handles.resolve_point(from_handle)
        if err:
            return err
        to, err, _ = handles.resolve_point(to_handle)
        if err:
            return err
        return transforms.aim_axis(targets, frm, to, axis, label)
    if o == "rest_on":
        return transforms.rest_on(targets, target, axis, offset, label)
    if o == "seat":
        return transforms.seat_into(targets, target, axis, offset, label)
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
    if o == "distribute":
        return relational.distribute_evenly(targets, between or [], axis, label)
    if o == "snap_loop":
        return editmode.snap_loop(handle, fit_scale, fit_rotation, label)
    return unknown("transform", "op", op, _OPS)

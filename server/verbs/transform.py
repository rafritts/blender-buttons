"""transform — move / rotate / scale / snap / mirror / array (SPEC-05).

Mode-agnostic transforms: relocate, resize, rotate, snap, mirror, distribute,
array, scatter — plus vertex-level move/scale. `op` selects the operation;
`targets` is "" (active), one name, or "a,b,c".
"""

from server._core import mcp
from server import transforms, relational, editmode
from ._common import unknown

_OPS = ["nudge", "resize", "scale", "rotate", "apply", "snap", "snap_grid",
        "match_dim", "mirror", "distribute", "array_corners", "array_along",
        "array_radial", "scatter", "move_verts", "scale_verts"]


@mcp.tool(name="transform")
def transform(
    op: str,
    targets: str = "",
    # nudge (relative meters)
    right: float = 0.0, left: float = 0.0, up: float = 0.0, down: float = 0.0,
    back: float = 0.0, forward: float = 0.0, inward: float = 0.0, out: float = 0.0,
    # resize (absolute meters)
    width: float = None, depth: float = None, height: float = None,
    # scale / rotate
    factor: float = 1.0, pivot: str = "center", pivot_object: str = "",
    angle: float = 0.0, axis: str = "Z",
    # apply
    scale: bool = True, rotation: bool = False, location: bool = False,
    # snap
    target: str = "", side: str = "Z_MAX", source_side: str = "AUTO",
    offset: float = 0.0,
    # snap_grid
    size: float = 0.1, axes: str = "XYZ",
    # match_dim
    reference: str = "",
    # mirror
    plane: str = "X", suffix: str = "_mirror", replace: bool = None,
    # distribute / array
    between: list = None, prototype: str = "", of: str = "", count: int = 0,
    standing_on_floor: bool = True, keep_original: bool = False, name_prefix: str = "",
    center: list = None, center_object: str = "",
    start_angle: float = 0.0, end_angle: float = 360.0, radius: float = None,
    align_to_tangent: bool = False,
    # scatter
    source: str = "", scale_min: float = 0.8, scale_max: float = 1.2,
    align_normal: bool = True, rotate_z: bool = True, parent_to_target: bool = True,
    seed: int = 0, avoid: str = "", avoid_margin: float = 0.0,
    # move_verts / scale_verts (edit-mode component transforms)
    x: float = 0.0, y: float = 0.0, z: float = 0.0,
    sx: float = 1.0, sy: float = 1.0, sz: float = 1.0,
    in_plane: float = 0.0, vert_pivot: str = "SELECTION",
    label: str = "",
) -> str:
    """
    Transform objects (or verts) — the **transform** tools. `op` selects:

      nudge    — relative move in meters  (right/left/up/down/back/forward/inward/out)
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
    """
    o = op.lower().strip()
    if o == "nudge":
        return transforms.nudge(targets, right, left, up, down, back, forward, label)
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
    return unknown("transform", "op", op, _OPS)

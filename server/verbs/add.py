"""add — the Blender Add menu (SPEC-05).

One verb for everything you can add to the scene. `type` is the Add-menu category;
the shape's own params are flat, optional fields — use the ones your `type` needs
(the table below says which). Placement (`on`) and rotation (`rot_*`) are shared
across the dimensional primitives, exactly as in the Add menu.
"""

from typing import Union

from server._core import mcp
from server import primitives, scene
from ._common import unknown

_TYPES = ["box", "plane", "cylinder", "sphere", "cone", "torus", "icosphere",
          "circle", "tube", "curve", "floor", "light", "camera"]


@mcp.tool(name="add")
def add(
    type: str,
    name: str = "",
    # ── placement & orientation (the dimensional primitives) ──
    on: dict = None,
    rot_x: float = 0, rot_y: float = 0, rot_z: float = 0,
    # ── dimensions (use the ones your `type` needs — see table) ──
    width: float = 0, depth: float = 0, height: float = 0,
    radius: float = 0, radius_top: float = 0, radius_bottom: float = 0,
    major_radius: float = 0, minor_radius: float = 0,
    size: float = 0,
    # ── resolution / topology ──
    segments: int = 0, rings: int = 0, subdivisions: int = 0,
    major_segments: int = 0, minor_segments: int = 0,
    cap_fill: str = "", fill_type: str = "",
    # ── curve / tube (type=curve|tube) ──
    points: list = None, subtype: str = "", cyclic: bool = False,
    resolution: int = 0, sides: int = 0, bevel_depth: float = 0,
    tube_radius: Union[float, list] = None,
    # ── light / camera (type=light|camera) ──
    energy: float = 0, color: list = None, hex: str = "",
    target: str = "", spot_angle: float = 0, lens: float = 0,
    x: float = 0, y: float = 0, z: float = 0,
    target_x: float = 0, target_y: float = 0, target_z: float = 0,
    label: str = "",
) -> str:
    """
    Add something to the scene — the Blender **Add** menu. Auto-enters Object Mode.
    `type` picks the category; fill only the params that category uses.

    type = one of:
      MESH PRIMITIVES (take name, on=placement DSL, rot_x/y/z):
        box        — width, depth, height               (W×D×H meters)
        plane      — width, depth
        cylinder   — radius, height, segments, cap_fill  (NGON|TRIFAN|NOTHING)
        sphere     — radius, segments, rings             (UV sphere)
        cone       — radius_bottom, height, radius_top(=0 sharp), segments, cap_fill
        torus      — major_radius, minor_radius, major_segments, minor_segments
        icosphere  — radius, subdivisions                (uniform tris; prefer for sculpt)
        circle     — radius, segments, fill_type         (NOTHING|NGON|TRIFAN)
        floor      — size                                (ground plane at z=0)
      CURVES (take name, points):
        tube       — points + tube_radius (float OR per-point list for taper),
                     resolution, sides    (baked tube MESH — hair/cable/handle)
        curve      — points + subtype (BEZIER|NURBS|POLY), cyclic, resolution,
                     bevel_depth          (LIVE curve datablock — dolly path, rope)
      OBJECTS:
        light      — subtype (POINT|SUN|SPOT|AREA), x/y/z, energy, color|hex,
                     size, target, spot_angle
        camera     — x/y/z, target|target_x/y/z, lens   (focal mm; 35 wide, 85 portrait)

    name: REQUIRED for everything except floor (defaults to 'floor').
    on:   placement DSL for mesh primitives — {"on":"seat"}, {"between":[...]},
          {"at_corner":{...}}, {"on_floor":true}, {"gap":0.01}, … (see primitives.py).
    """
    t = type.lower().strip()
    r = [rot_x, rot_y, rot_z]

    if t == "box":
        return primitives.add_box(name, width, depth, height, on, *r, label)
    if t == "plane":
        return primitives.add_plane(name, width, depth, on, *r, label)
    if t == "cylinder":
        return primitives.add_cylinder(
            name, radius, height, on, segments or None, segments or 32,
            cap_fill or "NGON", *r, label)
    if t == "sphere":
        return primitives.add_sphere(
            name, radius, on, segments or 32, rings or 16, *r, label)
    if t == "cone":
        return primitives.add_cone(
            name, radius_bottom, height, radius_top, on, segments or None,
            segments or 32, cap_fill or "NGON", *r, label)
    if t == "torus":
        return primitives.add_torus(
            name, major_radius, minor_radius, on, major_segments or 48,
            minor_segments or 12, *r, label)
    if t == "icosphere":
        return primitives.add_icosphere(
            name, radius, on, subdivisions or 2, *r, label)
    if t == "circle":
        return primitives.add_circle(
            name, radius, on, segments or None, segments or 32,
            fill_type or "NOTHING", *r, label)
    if t == "floor":
        return primitives.add_floor(name or "floor", size or 10.0, label)
    if t == "tube":
        return primitives.spline_tube(
            name, points or [], tube_radius if tube_radius is not None else 0.02,
            resolution or 8, sides or 4, label)
    if t == "curve":
        return primitives.add_curve(
            name, points or [], subtype or "BEZIER", cyclic, resolution or 12,
            bevel_depth, label)
    if t == "light":
        return scene.add_light(
            name, subtype or "POINT", x, y, z or 5.0, energy or None, color,
            hex, size or 0.25, target, spot_angle or 45.0, label)
    if t == "camera":
        return scene.add_camera(
            name, x or 7.0, y or -7.0, z or 5.0, target, target_x, target_y,
            target_z, lens or 50.0, label)
    return unknown("add", "type", type, _TYPES)

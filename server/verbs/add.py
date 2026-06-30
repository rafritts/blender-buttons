"""add — the Blender Add menu (SPEC-05).

One verb for everything you can add to the scene. `type` is the Add-menu category;
the shape's own params are flat, optional fields — use the ones your `type` needs
(the table below says which). Placement (`on`) and rotation (`rot_*`) are shared
across the dimensional primitives, exactly as in the Add menu.
"""

from typing import Literal, Union

from server._core import mcp
from server import primitives, scene
from ._common import tag, unknown, teach

_TYPES = ["box", "plane", "cylinder", "sphere", "cone", "torus", "icosphere",
          "circle", "grid", "tube", "helix", "curve", "text", "floor", "light", "camera"]


@mcp.tool(name="add")
def add(
    type: Literal["box", "plane", "cylinder", "sphere", "cone", "torus",
                  "icosphere", "circle", "grid", "tube", "helix", "curve", "text", "floor",
                  "light", "camera"],
    name: tag(str, "object name (required except floor)") = "",
    # ── placement & orientation (the dimensional primitives) ──
    on: tag(dict, "[mesh primitives] placement DSL — {\"on\":\"seat\"}, {\"on_floor\":true}, …") = None,
    rot_x: tag(float, "[mesh primitives] rotation X (deg)") = 0,
    rot_y: tag(float, "[mesh primitives] rotation Y (deg)") = 0,
    rot_z: tag(float, "[mesh primitives] rotation Z (deg)") = 0,
    # ── dimensions (use the ones your `type` needs — see table) ──
    width: tag(float, "[box/plane] X extent (m)") = 0,
    depth: tag(float, "[box/plane] Y extent (m); [text] extrude thickness (m)") = 0,
    # ── text (type=text) ──
    body: tag(str, "[text] the characters to render (e.g. 'XII', '12', a maker's name)") = "",
    bevel: tag(float, "[text] round-bevel radius on the extruded edges (m; 0=sharp)") = 0,
    height: tag(float, "[box/plane/cylinder/cone] Z extent (m)") = 0,
    radius: tag(float, "[sphere/cylinder/icosphere/circle] radius (m)") = 0,
    radius_top: tag(float, "[cone] top radius (0 = sharp)") = 0,
    radius_bottom: tag(float, "[cone] base radius (m)") = 0,
    major_radius: tag(float, "[torus] center-to-tube radius (m)") = 0,
    minor_radius: tag(float, "[torus] tube radius (m)") = 0,
    size: tag(float, "[floor/light] floor side length / light size (m); [text] cap height (m)") = 0,
    # ── resolution / topology ──
    segments: tag(int, "[cylinder/cone/sphere/circle] segments around") = 0,
    rings: tag(int, "[sphere] latitudinal rings") = 0,
    subdivisions: tag(int, "[icosphere] subdivisions 1..5") = 0,
    major_segments: tag(int, "[torus] ring resolution") = 0,
    minor_segments: tag(int, "[torus] tube resolution") = 0,
    cap_fill: tag(str, "[cylinder/cone] NGON|TRIFAN|NOTHING") = "",
    fill_type: tag(str, "[circle] NOTHING|NGON|TRIFAN") = "",
    # ── grid (type=grid): a subdivided plane in quad topology ──
    x_subdivisions: tag(int, "[grid] cuts across X (default 10; more = denser)") = 0,
    y_subdivisions: tag(int, "[grid] cuts across Y (default 10; more = denser)") = 0,
    # ── curve / tube (type=curve|tube) ──
    points: tag(list, "[tube/curve] control points the curve passes through") = None,
    between: tag(list, "[tube] connect two anchors [A,B] — straight tube, nearest-surface endpoints (alt to points)") = None,
    subtype: tag(str, "[light] POINT|SUN|SPOT|AREA · [curve] BEZIER|NURBS|POLY") = "",
    cyclic: tag(bool, "[curve] close the curve into a loop") = False,
    resolution: tag(int, "[tube/curve] samples per segment") = 0,
    sides: tag(int, "[tube/helix] cross-section smoothness") = 0,
    bevel_depth: tag(float, "[curve] round-bevel radius → solid tube (m)") = 0,
    tube_radius: tag(Union[float, list], "[tube] radius float OR per-point list for taper; [helix] wire radius (float)") = None,
    # ── helix / coil (type=helix) ──
    turns: tag(float, "[helix] number of full revolutions") = 0,
    taper: tag(float, "[helix] end/start wire-thickness ratio (1=uniform)") = 0,
    handedness: tag(str, "[helix] right (default) | left") = "",
    axis: tag(str, "[helix] coil axis X|Y|Z (default Z)") = "",
    segments_per_turn: tag(int, "[helix] samples per revolution (default 24)") = 0,
    # ── light / camera (type=light|camera) ──
    energy: tag(float, "[light] strength (watts; SUN ~5)") = 0,
    color: tag(list, "[light] [r,g,b] 0..1") = None,
    hex: tag(str, "[light] #RRGGBB color") = "",
    target: tag(str, "[light/camera] object to aim at") = "",
    spot_angle: tag(float, "[light] SPOT cone angle (deg)") = 0,
    lens: tag(float, "[camera] focal length (mm; 35 wide, 85 portrait)") = 0,
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
        grid       — width, depth, x_subdivisions, y_subdivisions  (a flat subdivided
                     PLANE: a width×depth rectangle of verts already wired into quad
                     topology. Native Add > Mesh > Grid. The substrate you lay down and
                     then deform/sculpt into a surface — push its verts after.)
      CURVES (take name, points)  — tube/helix are composite MACROS (SPEC-20): they kept
      their home under `add` because their purpose IS construction, but each carries an
      R1 native-cousin note below:
        tube       — points + tube_radius (float OR per-point list for taper),
                     resolution, sides    (baked tube MESH — hair/cable/handle).
                     OR between=[A,B] to strut/connect two objects (nearest-surface
                     endpoints — no coordinates).  MACRO ≈ a Curve + Bevel / Blender 5.0's
                     native "Curve to Tube" modifier; tube bakes the swept mesh in one call.
        helix      — turns, height, radius, tube_radius, taper, handedness, axis,
                     segments_per_turn, sides  (continuous coil MESH — wire wrap,
                     spring, screw thread, coiled rope; no point cap). Spawns at the
                     origin — re-seat it relationally with transform op=place.
                     MACRO ≈ the native Screw modifier / a swept curve.
        curve      — points + subtype (BEZIER|NURBS|POLY), cyclic, resolution,
                     bevel_depth          (LIVE curve datablock — dolly path, rope)
        text       — body=<string>, size (cap height), depth (extrude), bevel
                     (converted to a real editable MESH — dial numerals, maker's
                     marks, gauge labels, keycaps, signage). Placeable with on=.
      OBJECTS (spawn at a default viewpoint — re-seat relationally with
      transform op=place / op=nudge, or aim with target=<object>):
        light      — subtype (POINT|SUN|SPOT|AREA), energy, color|hex,
                     size, target, spot_angle
        camera     — target=<object>, lens   (focal mm; 35 wide, 85 portrait)

    name: REQUIRED for everything except floor (defaults to 'floor').
    on:   placement DSL for mesh primitives — {"on":"seat"}, {"between":[...]},
          {"at_corner":{...}}, {"on_floor":true}, {"gap":0.01}, … (see primitives.py).
    """
    t = type.lower().strip()
    r = [rot_x, rot_y, rot_z]

    # G23 move 3 — teaching errors. name is required for everything but floor; the
    # curve types are inert without the points they pass through.
    if t != "floor" and t in _TYPES and not name:
        return (f"add type={t}: needs name=<object name> — got none. "
                f"e.g. add type={t} name=my_{t}")
    bad = teach("add", "type", t, {
        "tube":  (bool(points) or bool(between), "points=[...] the tube passes through, or between=[A,B]",
                  "add type=tube name=cable points=[[0,0,0],[0,0,1]] tube_radius=0.02"),
        "curve": (bool(points), "points=[...] control points",
                  "add type=curve name=path points=[[0,0,0],[1,0,0]] subtype=BEZIER"),
        "text":  (bool(body), "body=<string> the characters to render",
                  "add type=text name=numeral body=\"XII\" size=0.02 depth=0.004"),
    })
    if bad:
        return bad

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
    if t == "grid":
        return primitives.add_grid(
            name, width or 1.0, depth or 1.0,
            x_subdivisions or 10, y_subdivisions or 10, on, *r, label)
    if t == "tube":
        return primitives.spline_tube(
            name, points or [], tube_radius if tube_radius is not None else 0.02,
            resolution or 8, sides or 4, label, between)
    if t == "helix":
        return primitives.helix_coil(
            name, turns or 3, height or 0.2, radius or 0.05,
            (tube_radius if isinstance(tube_radius, (int, float)) else None) or 0.02,
            taper or 1.0, handedness or "right", axis or "Z", None,
            segments_per_turn or 24, sides or 4, label)
    if t == "curve":
        return primitives.add_curve(
            name, points or [], subtype or "BEZIER", cyclic, resolution or 12,
            bevel_depth, label)
    if t == "text":
        return primitives.add_text(name, body, size or 0.1, depth, bevel, on, *r, label)
    if t == "light":
        # Spawns above the origin; re-seat relationally (transform op=place/nudge).
        return scene.add_light(
            name, subtype or "POINT", 0.0, 0.0, 5.0,
            energy or None, color, hex, size or 0.25, target, spot_angle or 45.0, label)
    if t == "camera":
        # Spawns at a default 3/4 viewpoint; re-seat relationally (view op=orbit,
        # transform op=place) and aim with target=<object>.
        return scene.add_camera(
            name, 7.0, -7.0, 5.0, target, 0.0, 0.0, 0.0, lens or 50.0, label)
    return unknown("add", "type", type, _TYPES)

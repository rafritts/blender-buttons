"""view — the 3D Viewport View menu + camera viewpoint (SPEC-05).

How the scene is looked at: viewport shading/angle/overlays, orbit, zoom, frame,
and the scene camera as a viewpoint. `op` selects.
"""

from server._core import mcp
from server import viewport, introspect, scene
from ._common import unknown

_OPS = ["shading", "angle", "overlays", "orbit", "zoom", "frame", "check_framing",
        "camera_position", "camera_dof"]


@mcp.tool(name="view")
def view(
    op: str,
    # shading / angle
    mode: str = "MATERIAL", angle: str = "",
    # overlays
    relationship_lines: bool = None, floor: bool = None, cursor: bool = None,
    wireframes: bool = None, text_info: bool = None, axes: bool = None,
    overlays: bool = None,
    # orbit
    azimuth: float = 45.0, elevation: float = 25.0, distance: float = 8.0,
    target_x: float = 0.0, target_y: float = 0.0, target_z: float = 1.0,
    auto_frame: bool = False,
    # frame / check_framing
    targets: str = "", include_lights: bool = False, camera: str = "",
    # camera_position
    x: float = 0.0, y: float = 0.0, z: float = 0.0,
    # camera_dof
    focus_distance: float = None, aperture: float = None, focus_object: str = "",
) -> str:
    """
    Look at the scene — the **View** menu + camera viewpoint. `op` selects:

      shading   — viewport shading mode  (mode=WIREFRAME|SOLID|MATERIAL|RENDERED)
      angle     — snap to a standard view (angle=FRONT|BACK|TOP|… or persp/ortho)
      overlays  — toggle overlays (relationship_lines/floor/cursor/wireframes/
                  text_info/axes, or overlays=False to hide all)
      orbit     — orbit the viewport camera (azimuth, elevation, distance,
                  target_x/y/z, auto_frame)
      zoom      — zoom to the current selection (—)
      frame     — frame objects in view  (targets, include_lights)
      check_framing — is everything in the camera frame? (targets, camera)
      camera_position — move the scene camera to a point aimed at a target
                  (x/y/z, target_x/y/z)
      camera_dof — depth of field on the camera (focus_distance OR focus_object,
                  aperture f-stop, camera)
    """
    o = op.lower().strip()
    if o == "shading":
        return viewport.set_viewport_shading(mode)
    if o == "angle":
        return viewport.set_viewport_angle(angle)
    if o == "overlays":
        return viewport.set_viewport_overlays(relationship_lines, floor, cursor,
                                              wireframes, text_info, axes, overlays)
    if o == "orbit":
        return viewport.orbit_viewport(azimuth, elevation, distance, target_x,
                                       target_y, target_z, auto_frame)
    if o == "zoom":
        return viewport.zoom_to_selected()
    if o == "frame":
        return viewport.frame_scene(targets, include_lights)
    if o == "check_framing":
        return introspect.check_framing(targets, camera)
    if o == "camera_position":
        return scene.set_camera_position(x, y, z, target_x, target_y, target_z)
    if o == "camera_dof":
        return scene.set_camera_dof(focus_distance, aperture, focus_object, camera)
    return unknown("view", "op", op, _OPS)

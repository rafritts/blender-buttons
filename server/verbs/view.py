"""view — the 3D Viewport View menu + camera viewpoint (SPEC-05).

How the scene is looked at: viewport shading/angle/overlays, orbit, zoom, frame,
and the scene camera as a viewpoint. `op` selects.
"""

from typing import Literal

from server._core import mcp
from server import viewport, introspect, scene
from ._common import tag, unknown

_OPS = ["shading", "angle", "overlays", "orbit", "zoom", "frame", "check_framing",
        "camera_dof", "active_camera"]


@mcp.tool(name="view")
def view(
    op: Literal["shading", "angle", "overlays", "orbit", "zoom", "frame",
                "check_framing", "camera_dof", "active_camera"],
    # shading / angle
    mode: tag(str, "[shading] WIREFRAME|SOLID|MATERIAL|RENDERED") = "MATERIAL",
    angle: tag(str, "[angle] FRONT|BACK|TOP|… or persp/ortho") = "",
    # overlays
    relationship_lines: tag(bool, "[overlays] show relationship lines") = None,
    floor: tag(bool, "[overlays] show the floor grid") = None,
    cursor: tag(bool, "[overlays] show the 3D cursor") = None,
    wireframes: tag(bool, "[overlays] show wireframes") = None,
    text_info: tag(bool, "[overlays] show text info") = None,
    axes: tag(bool, "[overlays] show axes") = None,
    overlays: tag(bool, "[overlays] master toggle (False hides all)") = None,
    # orbit
    azimuth: tag(float, "[orbit] horizontal angle (deg)") = 45.0,
    elevation: tag(float, "[orbit] vertical angle (deg)") = 25.0,
    distance: tag(float, "[orbit] camera distance (m)") = 8.0,
    auto_frame: tag(bool, "[orbit] auto-fit the scene") = False,
    # frame / check_framing
    targets: tag(str, "[frame/check_framing] objects to frame/check") = "",
    include_lights: tag(bool, "[frame] include lights in the frame") = False,
    camera: tag(str, "[check_framing/camera_dof] camera name (empty=scene cam)") = "",
    aspect: tag(str, "[check_framing] target frame 'WxH'|'W:H' to validate against (empty=scene resolution)") = "",
    # active_camera — camera= names which camera to act on (empty=scene cam)
    # camera_dof
    focus_distance: tag(float, "[camera_dof] focus distance (m)") = None,
    aperture: tag(float, "[camera_dof] f-stop (lower = shallower)") = None,
    focus_object: tag(str, "[camera_dof] object to focus on") = "",
) -> str:
    """
    Look at the scene — the **View** menu + camera viewpoint. `op` selects:

      shading   — viewport shading mode  (mode=WIREFRAME|SOLID|MATERIAL|RENDERED)
      angle     — snap to a standard view (angle=FRONT|BACK|TOP|… or persp/ortho)
      overlays  — toggle overlays (relationship_lines/floor/cursor/wireframes/
                  text_info/axes, or overlays=False to hide all)
      orbit     — orbit the viewport camera (azimuth, elevation, distance,
                  auto_frame) — relational viewpoint, no typed coordinates
      zoom      — zoom to the current selection (—)
      frame     — frame objects in view  (targets, include_lights)
      check_framing — is everything in the camera frame? Coverage % is relative to
                  the frame aspect, so each reading states the reference resolution;
                  aspect='WxH'|'W:H' validates against an intended output. (targets,
                  camera, aspect)
      camera_dof — depth of field on the camera (focus_distance OR focus_object,
                  aperture f-stop, camera)
      active_camera — make an existing camera the active scene/render camera (camera)
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
        return viewport.orbit_viewport(azimuth, elevation, distance, 0.0, 0.0, 1.0,
                                       auto_frame)
    if o == "zoom":
        return viewport.zoom_to_selected()
    if o == "frame":
        return viewport.frame_scene(targets, include_lights)
    if o == "check_framing":
        return introspect.check_framing(targets, camera, aspect)
    if o == "camera_dof":
        return scene.set_camera_dof(focus_distance, aperture, focus_object, camera)
    if o == "active_camera":
        return scene.set_active_camera(camera)
    return unknown("view", "op", op, _OPS)

"""view — the 3D Viewport View menu + camera viewpoint (SPEC-05).

How the scene is looked at: viewport shading/angle/overlays, orbit, zoom, frame,
and the scene camera as a viewpoint. `op` selects.
"""

from typing import Literal

from server._core import mcp
from server import viewport, introspect, scene
from ._common import tag, unknown

_OPS = ["shading", "angle", "overlays", "orbit", "rig", "zoom", "frame", "check_framing",
        "check_focus", "check_visible", "check_exposure", "check_lighting", "camera_dof",
        "camera_lens", "active_camera"]


@mcp.tool(name="view")
def view(
    op: Literal["shading", "angle", "overlays", "orbit", "rig", "zoom", "frame",
                "check_framing", "check_focus", "check_visible", "check_exposure",
                "check_lighting", "camera_dof", "camera_lens", "active_camera"],
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
    # orbit / rig
    azimuth: tag(float, "[orbit/rig] horizontal angle (deg; 0=front −Y, 90=+X right)") = 45.0,
    elevation: tag(float, "[orbit/rig] vertical angle above horizon (deg)") = 25.0,
    distance: tag(float, "[orbit/rig] distance from the subject/target (m)") = 8.0,
    auto_frame: tag(bool, "[orbit] auto-fit the scene") = False,
    target: tag(str, "[orbit] named object to orbit the viewport around (empty=fixed datum)") = "",
    rig: tag(str, "[rig] the object (light/camera) to position+aim around the subject (camera= is accepted as an alias)") = "",
    subject: tag(str, "[rig] the subject(s) the rigged light/camera orbits and aims at — "
                      "one object, a comma-list ('donut,plate,mug'), or a group name") = "",
    fit: tag(bool, "[rig] auto-derive distance to frame the WHOLE subject set (camera: "
                   "from its FOV; light: from extent) — no hand-tuning to stop clipping") = False,
    # frame / check_framing
    targets: tag(str, "[frame/check_framing] objects to frame/check") = "",
    include_lights: tag(bool, "[frame] include lights in the frame") = False,
    camera: tag(str, "[check_framing/camera_dof] camera name (empty=scene cam)") = "",
    aspect: tag(str, "[check_framing] target frame 'WxH'|'W:H' to validate against (empty=scene resolution)") = "",
    # active_camera — camera= names which camera to act on (empty=scene cam)
    # camera_dof
    focus_distance: tag(float, "[camera_dof] focus distance (m)") = None,
    aperture: tag(float, "[camera_dof] f-stop (lower = shallower)") = None,
    focus_object: tag(str, "[camera_dof/check_focus] object to focus on") = "",
    resolve_for: tag(str, "[check_focus] object to solve the sharp-keeping aperture for; "
                          "[check_exposure] light to solve the ~0-stop energy for") = "",
    # camera_lens
    lens: tag(float, "[camera_lens] focal length mm (24 wide · 50 neutral · 85 portrait · 135 hero)") = None,
) -> str:
    """
    Look at the scene — the **View** menu + camera viewpoint. `op` selects:

      shading   — viewport shading mode  (mode=WIREFRAME|SOLID|MATERIAL|RENDERED)
      angle     — snap to a standard view (angle=FRONT|BACK|TOP|… or persp/ortho)
      overlays  — toggle overlays (relationship_lines/floor/cursor/wireframes/
                  text_info/axes, or overlays=False to hide all)
      orbit     — orbit the viewport camera (azimuth, elevation, distance, auto_frame,
                  target=<object to orbit around>) — relational viewpoint, no coordinates
      rig       — position+aim a light or camera around a subject: rig=<light/camera>,
                  subject=<object|comma-list|group>, azimuth/elevation/distance. The
                  relational key/fill/rim or hero-camera rig (spherical analogue of
                  array_radial); aims the object's -Z at the subject(s)' union centre.
                  fit=True auto-frames the whole subject set from the camera's FOV (or a
                  light's extent). (re-aim only → object op=aim)
      zoom      — zoom to the current selection (—)
      frame     — frame objects in view  (targets, include_lights)
      check_framing — is everything in the camera frame? Coverage % is relative to
                  the frame aspect, so each reading states the reference resolution;
                  aspect='WxH'|'W:H' validates against an intended output. (targets,
                  camera, aspect)
      check_focus — VALIDATE depth of field (G115): near/far sharp limits at the current
                  (or hypothetical aperture/focus_distance/focus_object) settings, and
                  whether each target's full depth is inside the in-focus slab — the
                  sharpness check you can't get from a render you're told not to read.
                  resolve_for=<obj> also solves the widest aperture that keeps it sharp.
      check_visible — would a viewer SEE this surface from the camera? (G131) yes/no +
                  % of FRONT-FACING surface unoccluded. For a recessed part (liquid in a
                  vessel, a gem in a setting) whose whole-bbox occlusion reads ~100% even
                  though its visible face is the point. (targets, camera)
      check_exposure — is there too much / too little light? (SPEC-17) A deterministic
                  irradiance estimate per target: stops over/under, key:fill ratio, % in
                  shadow — flags GROSS over/under-exposure (whether it LOOKS right is your
                  call). resolve_for=<light> solves the ~0-stop energy. (targets, resolve_for)
      check_lighting — the lighting roll-up: exposure + focus in one read, no render.
                  (targets, camera)
      camera_dof — depth of field on the camera (focus_distance OR focus_object,
                  aperture f-stop, camera)
      camera_lens — retune the focal length of an existing camera (lens mm, camera) —
                  the wide-vs-compressed dial, no longer write-once at add
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
                                       auto_frame, target)
    if o == "rig":
        # G158: the rigged object is rig=, but camera= is a natural guess (and a valid
        # key elsewhere on this verb) — accept it as an alias instead of failing.
        rigged = rig or camera
        if not rigged:
            return ("rig needs rig=<light/camera to position+aim> (and "
                    "subject=<object/group to orbit around>). "
                    "Example: view op=rig rig=HeroCamera subject=donut,plate fit=true")
        return scene.rig_object(rigged, subject, azimuth, elevation, distance, fit)
    if o == "zoom":
        return viewport.zoom_to_selected()
    if o == "frame":
        return viewport.frame_scene(targets, include_lights)
    if o == "check_framing":
        return introspect.check_framing(targets, camera, aspect)
    if o == "check_focus":
        return introspect.check_focus(targets, camera, aperture, focus_distance,
                                      focus_object, resolve_for)
    if o == "check_visible":
        return introspect.check_visible(targets, camera)
    if o == "check_exposure":
        return introspect.check_exposure(targets, resolve_for)
    if o == "check_lighting":
        return introspect.check_lighting(targets, camera)
    if o == "camera_dof":
        return scene.set_camera_dof(focus_distance, aperture, focus_object, camera)
    if o == "camera_lens":
        return scene.set_camera_lens(lens, camera)
    if o == "active_camera":
        return scene.set_active_camera(camera)
    return unknown("view", "op", op, _OPS)

from server._core import mcp, call_blender, _status


@mcp.tool()
def set_viewport_angle(angle: str) -> str:
    """
    Set the viewport to a standard angle.
    angle: FRONT | BACK | LEFT | RIGHT | TOP | BOTTOM | CAMERA
    """
    result = call_blender("set_viewport_angle", {"angle": angle})
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_viewport_shading(mode: str = "MATERIAL") -> str:
    """
    Switch the 3D viewport shading mode.
    mode: WIREFRAME | SOLID | MATERIAL | RENDERED
      - SOLID: matcap default (no materials visible)
      - MATERIAL: previews materials with built-in studio lighting (fast)
      - RENDERED: full Eevee/Cycles preview using your scene lights + world
    Affects the user's live viewport and render_to_file output, which capture
    whatever shading mode is currently active.
    """
    result = call_blender("set_viewport_shading", {"mode": mode})
    main = f"shading → {mode}" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_viewport_overlays(relationship_lines: bool = None, floor: bool = None,
                          cursor: bool = None, wireframes: bool = None,
                          text_info: bool = None, axes: bool = None,
                          overlays: bool = None) -> str:
    """
    Toggle the USER's live 3D-viewport overlays — clean up what the PERSON watching
    sees, not just the agent's screenshot. On a rigged, scattered scene the dashed
    relationship lines and grid clutter make a fully textured model read as gray
    blockout to whoever's looking.

    Pass any of (bool each): relationship_lines, floor, cursor, wireframes,
    text_info, axes, overlays (master on/off). To hide an armature's BONES from the
    user, hide the armature object with set_object_visibility (the Armature modifier
    keeps deforming the mesh).

    Example: set_viewport_overlays(relationship_lines=False, cursor=False)
    """
    params = {k: v for k, v in {
        "relationship_lines": relationship_lines, "floor": floor, "cursor": cursor,
        "wireframes": wireframes, "text_info": text_info, "axes": axes,
        "overlays": overlays,
    }.items() if v is not None}
    result = call_blender("set_viewport_overlays", params)
    if result.get("success"):
        return f"overlays updated: {result['changed']}"
    return result.get("error", "failed")


@mcp.tool()
def frame_scene(targets: str = "", include_lights: bool = False) -> str:
    """Fit objects in the viewport.

    targets: object name, group name, or comma-separated list. Empty = all mesh objects.
    include_lights: include lights/cameras in the fit (default False — they usually
                    blow out the framing and leave the subject tiny).

    Example: frame_scene("body") frames just the character; frame_scene() frames all
    mesh objects with lights excluded.
    """
    params = {"include_lights": include_lights}
    if targets:
        params["targets"] = targets
    result = call_blender("frame_scene", params)
    if result.get("success"):
        framed = result.get("framed")
        main = f"framed {framed}" if framed else "ok"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def zoom_to_selected() -> str:
    """Zoom the viewport to tightly frame the currently selected object."""
    result = call_blender("zoom_to_selected")
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def orbit_viewport(azimuth: float = 45.0, elevation: float = 25.0, distance: float = 8.0,
                   target_x: float = 0.0, target_y: float = 0.0, target_z: float = 1.0,
                   auto_frame: bool = False, target: str = "") -> str:
    """
    Position the viewport perspective camera using orbit controls.
    azimuth: horizontal angle in degrees (0=front, +right, -left)
    elevation: vertical angle in degrees (positive=from above)
    distance: distance from target
    target: orbit around this NAMED object's centre (G79); empty = the fixed datum point.
    auto_frame: if True, ignore target_*/distance and auto-frame the scene — aims
                at the bounding-box center of the selection (or all visible meshes
                if nothing is selected) and pulls back to fit. The default
                azimuth=45/elevation=25 then gives a clean three-quarter "hero"
                shot of whatever's in the scene, no distance-eyeballing.

    Example: orbit_viewport(auto_frame=True)  # framed 3/4 view of the whole model
    """
    result = call_blender("orbit_viewport", {
        "azimuth": azimuth, "elevation": elevation, "distance": distance,
        "target_x": target_x, "target_y": target_y, "target_z": target_z,
        "auto_frame": auto_frame, "target": target,
    })
    if result.get("success"):
        af = result.get("auto_framed")
        main = (f"orbit: framed {af['target']} @ distance {af['distance']}"
                if af else "ok")
    else:
        main = result.get("error", "failed")
    return main + _status(result)

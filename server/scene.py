from server._core import mcp, call_blender, _status


@mcp.tool()
def add_light(name: str, type: str = "POINT",
              x: float = 0.0, y: float = 0.0, z: float = 5.0,
              energy: float = None, color: list = None, size: float = 0.25,
              target: str = "", spot_angle: float = 45.0,
              label: str = "") -> str:
    """
    Add a light to the scene.

    name:    REQUIRED — unique object name.
    type:    POINT | SUN | SPOT | AREA  (default POINT)
    x, y, z: world position (meters). Default (0, 0, 5).
    energy:  light strength. Defaults: 1000 for POINT/SPOT/AREA (watts), 5 for SUN.
    color:   [r, g, b] floats 0..1. Default warm white [1, 0.95, 0.9].
    size:    soft-shadow radius / AREA quad side / SPOT radius. Default 0.25 m.
    target:  optional object name to aim the light at (its -Z axis points at the target).
    spot_angle: cone angle in degrees for SPOT lights. Default 45.

    Example: add_light("key", type="AREA", x=3, y=-3, z=4, size=2.0, energy=500, target="donut")
    """
    params = {"name": name, "type": type, "x": x, "y": y, "z": z, "size": size,
              "spot_angle": spot_angle}
    if energy is not None: params["energy"] = energy
    if color is not None:  params["color"] = color
    if target:             params["target"] = target
    result = call_blender("add_light", params, label=label)
    if result.get("success"):
        main = (f"Added {result['type']} light '{result['object_name']}' at "
                f"{result['location']} energy={result['energy']} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def modify_light(name: str, energy: float = None, color: list = None,
                 size: float = None, spot_angle: float = None,
                 x: float = None, y: float = None, z: float = None,
                 target: str = "", label: str = "") -> str:
    """
    Tweak an existing light without rebuilding it. Dial energy/color/size live.
    All params optional except `name`. x/y/z move the light; target re-aims it.
    """
    params = {"name": name}
    for key, val in (("energy", energy), ("color", color), ("size", size),
                     ("spot_angle", spot_angle), ("x", x), ("y", y), ("z", z)):
        if val is not None:
            params[key] = val
    if target:
        params["target"] = target
    result = call_blender("modify_light", params, label=label)
    if result.get("success"):
        main = (f"{result['light']} ({result['type']}): {result['applied']} "
                f"now energy={result['energy']} color={result['color']} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_world_background(color: list = None, strength: float = None,
                         hdri: str = "", label: str = "") -> str:
    """
    Set the world background. Either a solid color (cheap ambient) or an HDRI image
    (image-based lighting — gives free realistic environment light + reflections).

    color:    [r, g, b] solid color, floats 0..1. Ignored if `hdri` is set.
    strength: light intensity from the background. Default 1.0.
    hdri:     path to an HDRI/EXR file. Connected as an Environment Texture.

    Examples:
      set_world_background(color=[0.05, 0.05, 0.08], strength=0.3)         # dim blue room
      set_world_background(hdri="~/hdris/studio.exr", strength=1.0)        # studio lighting
    """
    params = {}
    if color is not None:    params["color"] = color
    if strength is not None: params["strength"] = strength
    if hdri:                 params["hdri"] = hdri
    result = call_blender("set_world_background", params, label=label)
    if result.get("success"):
        if result["mode"] == "hdri":
            main = f"world: hdri={result['hdri']} strength={result['strength']}"
        elif result["mode"] == "color":
            main = f"world: color={result['color']} strength={result['strength']}"
        else:
            main = f"world: unchanged (strength={result['strength']})"
        main += f" [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_camera_position(x: float, y: float, z: float,
                        target_x: float = 0.0, target_y: float = 0.0, target_z: float = 0.0) -> str:
    """Move the scene camera to a position aimed at a target point."""
    result = call_blender("set_camera_position", {
        "x": x, "y": y, "z": z,
        "target_x": target_x, "target_y": target_y, "target_z": target_z,
    })
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def add_camera(name: str,
               x: float = 7.0, y: float = -7.0, z: float = 5.0,
               target: str = "",
               target_x: float = 0.0, target_y: float = 0.0, target_z: float = 0.0,
               lens: float = 50.0,
               label: str = "") -> str:
    """
    Create a new camera and set it as the active scene camera.

    name:    REQUIRED — unique object name.
    x, y, z: world position (default 7, -7, 5).
    target:  optional object name to aim at; overrides target_x/y/z.
    target_x, target_y, target_z: world point to aim at (default 0, 0, 0).
    lens:    focal length in mm (default 50). 35 = wide, 85 = portrait.

    Example: add_camera("cam", x=7, y=-7, z=5, target="donut")
    """
    params = {"name": name, "x": x, "y": y, "z": z, "lens": lens,
              "target_x": target_x, "target_y": target_y, "target_z": target_z}
    if target:
        params["target"] = target
    result = call_blender("add_camera", params, label=label)
    if result.get("success"):
        main = (f"Added camera '{result['camera']}' at {result['location']} "
                f"aimed at {result['target']} lens={result['lens']}mm [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_camera_dof(focus_distance: float = None, aperture: float = None,
                   focus_object: str = "", camera: str = "", label: str = "") -> str:
    """
    Enable depth of field on the scene camera (the blurry-background look).

    focus_distance: meters from camera to focal plane. Ignored if focus_object is set.
    focus_object:   object to focus on (auto-tracks its distance).
    aperture:       f-stop. Lower = shallower DoF. 1.4 (very shallow) | 2.8 (portrait) | 8 (deep).
    camera:         camera object name. Empty = scene camera.

    Example: set_camera_dof(focus_object="donut", aperture=2.8)
    """
    params = {}
    if focus_distance is not None: params["focus_distance"] = focus_distance
    if aperture is not None:       params["aperture"] = aperture
    if focus_object:               params["focus_object"] = focus_object
    if camera:                     params["camera"] = camera
    result = call_blender("set_camera_dof", params, label=label)
    if result.get("success"):
        main = (f"DoF on '{result['camera']}': "
                f"focus_object={result['focus_object']} "
                f"focus_distance={result['focus_distance']} "
                f"f/{result['aperture_fstop']} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)

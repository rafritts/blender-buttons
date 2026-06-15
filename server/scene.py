import os

from server._core import mcp, call_blender, _status
from server import polyhaven


@mcp.tool()
def add_light(name: str, type: str = "POINT",
              x: float = 0.0, y: float = 0.0, z: float = 5.0,
              energy: float = None, color: list = None, hex: str = "",
              size: float = 0.25,
              target: str = "", spot_angle: float = 45.0,
              label: str = "") -> str:
    """
    Add a light to the scene.

    name:    REQUIRED — unique object name.
    type:    POINT | SUN | SPOT | AREA  (default POINT). DIRECTIONAL is accepted
             as an alias for SUN.
    x, y, z: world position (meters). Default (0, 0, 5).
    energy:  light strength. Defaults: 1000 for POINT/SPOT/AREA (watts), 5 for SUN.
    color:   [r, g, b] floats 0..1 (scene-linear). Default warm white [1, 0.95, 0.9].
    hex:     "#RRGGBB" sRGB color, converted to scene-linear (same convention as
             set_material). Overrides color.
    size:    soft-shadow radius / AREA quad side / SPOT radius. Default 0.25 m.
    target:  optional object name to aim the light at (its -Z axis points at the target).
    spot_angle: FULL cone (apex) angle in degrees for SPOT lights. Default 45.

    Example: add_light("key", type="AREA", x=3, y=-3, z=4, size=2.0, energy=500, target="donut")
    """
    params = {"name": name, "type": type, "x": x, "y": y, "z": z, "size": size,
              "spot_angle": spot_angle}
    if energy is not None: params["energy"] = energy
    if color is not None:  params["color"] = color
    if hex:                params["hex"] = hex
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
                 hex: str = "", size: float = None, spot_angle: float = None,
                 x: float = None, y: float = None, z: float = None,
                 target: str = "", label: str = "") -> str:
    """
    Tweak an existing light without rebuilding it. Dial energy/color/size live.
    All params optional except `name`. x/y/z move the light; target re-aims it.
    hex: "#RRGGBB" sRGB color, converted to scene-linear (overrides color).
    spot_angle is the FULL cone (apex) angle in degrees.
    """
    params = {"name": name}
    for key, val in (("energy", energy), ("color", color), ("size", size),
                     ("spot_angle", spot_angle), ("x", x), ("y", y), ("z", z)):
        if val is not None:
            params[key] = val
    if hex:
        params["hex"] = hex
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
def set_world_background(color: list = None, hex: str = "", strength: float = None,
                         hdri: str = "", resolution: str = "2k", label: str = "") -> str:
    """
    Set the world background. Either a solid color (cheap ambient) or an HDRI
    (image-based lighting — free realistic environment light + reflections).

    color:    [r, g, b] solid color, floats 0..1. Ignored if `hdri` is set.
    hex:      "#RRGGBB" sRGB solid color, converted to scene-linear (same
              convention as set_material). Overrides color; ignored if `hdri` is set.
    strength: light intensity from the background. Default 1.0.
    hdri:     EITHER a path to a local HDRI/EXR file, OR a Poly Haven HDRI asset id
              (from search_hdris, e.g. "studio_small_03"). If it isn't an existing
              file, it's fetched from Poly Haven (CC0) and cached.
    resolution: Poly Haven HDRI resolution when fetching by id — "1k", "2k" (default),
              "4k", "8k".

    Examples:
      set_world_background(color=[0.05, 0.05, 0.08], strength=0.3)     # dim blue room
      set_world_background(hdri="~/hdris/studio.exr")                  # local file
      set_world_background(hdri="studio_small_03", resolution="2k")    # Poly Haven id
    """
    params = {}
    if color is not None:    params["color"] = color
    if hex:                  params["hex"] = hex
    if strength is not None: params["strength"] = strength
    if hdri:
        # A local file passes straight through; anything else is a Poly Haven id
        # resolved + cached to a local path here (the addon never hits the network).
        if os.path.isfile(os.path.expanduser(hdri)):
            params["hdri"] = hdri
        else:
            try:
                params["hdri"] = polyhaven.ensure_hdri(hdri, resolution)
            except polyhaven.PolyHavenError as e:
                return f"could not fetch HDRI '{hdri}': {e}. World unchanged."
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
def search_hdris(query: str, limit: int = 10) -> str:
    """
    Search Poly Haven's CC0 HDRI library by keyword (lighting mood / place —
    e.g. "studio", "sunset", "overcast", "night city"). Returns asset ids to pass
    to set_world_background(hdri=...). Cached 24h, so it works offline after first use.
    """
    try:
        results = polyhaven.search(query, "hdris", limit)
    except polyhaven.PolyHavenError as e:
        return f"HDRI search failed: {e}"
    if not results:
        return f"No HDRIs match '{query}'."
    return "\n".join(f"{r['id']}  [{', '.join(r['tags'][:6])}]" for r in results)


@mcp.tool()
def set_color_management(view_transform: str = "", look: str = "",
                         exposure: float = None, gamma: float = None,
                         label: str = "") -> str:
    """
    Control the scene's view transform / look / exposure / gamma — how Blender
    tone-maps the render, independent of the materials and lights.

    Blender 4.x defaults to the AgX view transform: filmic, it lifts and
    desaturates midtones. Great for realistic PBR, but it MUTES flat toon/NPR
    colors and emission glow. If a toon scene or saturated color renders washed
    out and grey, this is usually why.

    view_transform: 'Standard' (no tone-mapping — use for cel/NPR work) |
                    'AgX' (filmic, default — use for PBR/realism) | 'Filmic' | 'Raw'.
    look:           contrast look, e.g. 'None', 'Medium Contrast', 'AgX - Punchy'.
    exposure:       stops of exposure (default 0).
    gamma:          display gamma (default 1.0).

    Current values are reported in get_blender_status under `render:`.
    Recommendation: set_toon_material scenes want view_transform='Standard'.

    Example: set_color_management(view_transform="Standard")  # un-mute toon colors
    """
    params = {}
    if view_transform: params["view_transform"] = view_transform
    if look:           params["look"] = look
    if exposure is not None: params["exposure"] = exposure
    if gamma is not None:    params["gamma"] = gamma
    result = call_blender("set_color_management", params, label=label)
    if result.get("success"):
        main = (f"color management: {result['applied']} "
                f"(now view_transform={result['view_transform']}, look={result['look']}, "
                f"exposure={result['exposure']}, gamma={result['gamma']}) [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_render_quality(raytracing: bool = None, ao: bool = None,
                       shadows: bool = None, samples: int = None,
                       label: str = "") -> str:
    """
    Toggle Eevee render-quality features that are OFF by default in Blender 4.x.

    raytracing: screen-space ray tracing. REQUIRED for crisp metal reflections
                and sharp specular highlights — without it, metallic=1 reflects
                only the low-res world probe and looks like plastic. Turn this on
                whenever a scene has metal or glass.
    ao:         ambient occlusion (contact shadows in crevices/seams).
    shadows:    soft shadows.
    samples:    render sample count (higher = less noise, slower). Try 64–128.

    Pairs with set_color_management: together they're "control how Blender draws
    the asset" vs. just modelling it. (No effect under Cycles — it ray-traces always.)

    Example: set_render_quality(raytracing=True, ao=True)  # make metals reflect
    """
    params = {}
    if raytracing is not None: params["raytracing"] = raytracing
    if ao is not None:         params["ao"] = ao
    if shadows is not None:    params["shadows"] = shadows
    if samples is not None:    params["samples"] = samples
    result = call_blender("set_render_quality", params, label=label)
    if result.get("success"):
        tail = f" (skipped: {result['skipped']})" if result.get("skipped") else ""
        main = (f"render quality [{result['engine']}]: {result['applied']}{tail} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_cycles_quality(device: str = "", backend: str = "",
                       denoise: bool = None, denoiser: str = "",
                       adaptive_threshold: float = None, samples: int = None,
                       label: str = "") -> str:
    """
    Cycles-specific render controls — the Cycles counterpart to set_render_quality
    (which only affects Eevee). Persists on the scene, so set it once and every
    render_to_file afterward uses it.

    device:   'GPU' | 'CPU'. 'GPU' also enables the card in Cycles addon
              preferences, so a .blend saved as CPU starts using the GPU — THE fix
              when renders crawl on CPU.
    backend:  GPU backend when device='GPU': 'OPTIX' (NVIDIA RTX — fastest, adds
              hardware denoising) | 'CUDA' | 'HIP' (AMD) | 'ONEAPI' (Intel) |
              'METAL' (Apple). Empty = auto-pick the best backend that has a device.
    denoise:  True/False — denoise the final image. The single biggest win against
              grain: a denoised 64-sample frame beats a noisy 512-sample one.
    denoiser: 'OPTIX' (GPU, NVIDIA) | 'OPENIMAGEDENOISE' (works anywhere). Empty =
              leave as-is.
    adaptive_threshold: noise floor for adaptive sampling, e.g. 0.01. Lower =
              cleaner + slower. Enables adaptive sampling; Cycles stops refining a
              pixel once it converges, so a high `samples` ceiling stays cheap.
    samples:  max render sample count.

    Example: set_cycles_quality(device="GPU", backend="OPTIX", denoise=True,
                                denoiser="OPTIX", samples=128)
    """
    params = {}
    if device:                         params["device"] = device
    if backend:                        params["backend"] = backend
    if denoise is not None:            params["denoise"] = denoise
    if denoiser:                       params["denoiser"] = denoiser
    if adaptive_threshold is not None: params["adaptive_threshold"] = adaptive_threshold
    if samples is not None:            params["samples"] = samples
    result = call_blender("set_cycles_quality", params, label=label)
    if result.get("success"):
        tail = f" (skipped: {result['skipped']})" if result.get("skipped") else ""
        main = (f"cycles quality [device={result['device']}]: {result['applied']}{tail} "
                f"(denoise={result['denoise']}/{result['denoiser']}, samples={result['samples']}) "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def render_to_file(filepath: str,
                   resolution_x: int = None, resolution_y: int = None,
                   samples: int = None, engine: str = "",
                   format: str = "PNG", transparent: bool = None,
                   timeout: float = 300, label: str = "") -> str:
    """
    Render the scene camera to an image file on disk. Requires a camera — add_camera first.

    ⚠ THIS IS FOR THE HUMAN USER, NOT THE AGENT. It produces a picture for a person
    to look at. The agent does NOT see these images and must NOT read them back —
    doing so burns tokens and has repeatedly led to wrong conclusions (an image is a
    lossy, ambiguous view of hidden state). Call this ONLY when the user explicitly
    asks for a rendered image, then hand them the path.

    To understand the model yourself, use the introspection/topology tools instead —
    they are precise and cheap: get_topology, describe, get_object_info, check_mesh,
    list_modifiers, get_scene_tree, diff_since. Those are almost always what you want.

    filepath:     output path (~ expanded; extension auto-added to match format).
    resolution_x/y: pixel dimensions (default: keep the scene's current).
    samples:      render sample count (higher = cleaner + slower).
    engine:       'BLENDER_EEVEE_NEXT' | 'CYCLES' (default: keep current).
    format:       PNG (default) | JPEG | OPEN_EXR | TIFF | WEBP.
    transparent:  True → transparent background (alpha in PNG/EXR).
    timeout:      seconds to allow the render to run before giving up (default 300).
                  Raise it for heavy Cycles renders.

    SYNCHRONOUS: this blocks Blender's main thread (the viewport freezes) for the
    whole render. Keep samples modest for interactive sessions.

    Example: render_to_file("~/renders/hero.png", resolution_x=1920, resolution_y=1080,
                            samples=128, transparent=True)
    """
    params = {"filepath": filepath, "format": format}
    if resolution_x is not None: params["resolution_x"] = resolution_x
    if resolution_y is not None: params["resolution_y"] = resolution_y
    if samples is not None:      params["samples"] = samples
    if engine:                   params["engine"] = engine
    if transparent is not None:  params["transparent"] = transparent
    result = call_blender("render_to_file", params, label=label, timeout=timeout)
    if result.get("success"):
        kb = result["bytes"] / 1024.0
        main = (f"rendered {result['resolution']} [{result['engine']}, {result['format']}] "
                f"→ {result['filepath']} ({kb:.0f} KB) [{result.get('op_id','')}]")
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

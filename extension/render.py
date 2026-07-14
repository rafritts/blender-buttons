"""Render the scene camera to an image file.

render_to_file is SYNCHRONOUS: bpy.ops.render.render(write_still=True) blocks
Blender's main thread for the whole render. The socket protocol carries a
per-call `timeout` (see server.handle_client) so long renders don't get cut off
at the default 30s — but the live viewport will freeze until the render finishes.
Keep sample counts modest for interactive use.
"""

import os

import bpy


_FORMATS = {"PNG", "JPEG", "OPEN_EXR", "TIFF", "WEBP"}


def _available_engines():
    """The engines this build can ACTUALLY render with (G24).

    The `engine` RNA enum's static items can MISS dynamically-registered engines —
    CYCLES is a Python RenderEngine subclass, so it isn't always in the enum items
    (the same dynamic-enum gotcha that empties compute_device_type's items). That
    produced the self-contradicting read `engine: CYCLES  available: BLENDER_EEVEE`.
    Union three authoritative sources: the enum items, the registered RenderEngine
    subclasses, and the currently-set engine (valid by definition — Blender refuses
    to assign an engine it can't provide)."""
    scene = bpy.context.scene
    names = set()
    try:
        names.update(e.identifier for e in
                     type(scene.render).bl_rna.properties["engine"].enum_items)
    except Exception:
        pass
    for cls in bpy.types.RenderEngine.__subclasses__():
        bl_idname = getattr(cls, "bl_idname", None)
        if bl_idname:
            names.add(bl_idname)
    names.add(scene.render.engine)
    return sorted(names)


def _cycles_preflight():
    """The Cycles GPU/compute layer — which lives in ADDON PREFERENCES, not the scene
    (G24). Lets the agent tell 'GPU' from 'silent CPU fallback' before a render crawls
    or OOMs. Reports addon-enabled, the compute backend, and every device with its
    enabled flag."""
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        return {"addon_enabled": False,
                "note": "Cycles addon not enabled in this build — GPU rendering "
                        "unavailable (CPU only)."}
    prefs = addon.preferences
    # The device list is populated lazily; refresh it (API name varies by version).
    for refresh in ("refresh_devices", "get_devices"):
        fn = getattr(prefs, refresh, None)
        if fn is not None:
            try:
                fn()
                break
            except Exception:
                pass
    devices = [{"name": d.name, "type": d.type, "enabled": bool(d.use)}
               for d in getattr(prefs, "devices", [])]
    gpu_on = [d["name"] for d in devices if d["enabled"] and d["type"] != 'CPU']
    return {
        "addon_enabled": True,
        "compute_device_type": getattr(prefs, "compute_device_type", None),
        "devices": devices,
        "gpu_devices_enabled": gpu_on,
    }


def render_to_file(params):
    """Render the active scene camera to an image file.

    Experimental agent sight: the agent may open the returned path for appearance /
    presentation. Geometry still comes from feel/status (vision is recognition-biased).

    filepath:   output path (required). ~ is expanded. Extension is set to match
                the format if missing.
    resolution_x / resolution_y: pixel dims (default: keep the scene's current).
    samples:    render sample count (optional; higher = cleaner + slower).
    engine:     'BLENDER_EEVEE' | 'CYCLES' | ... (default: keep current). Note: Blender
                5.0 renamed Eevee's id 'BLENDER_EEVEE_NEXT' -> 'BLENDER_EEVEE'; the engine
                is validated against the build, so pass the build's real id.
    format:     PNG (default) | JPEG | OPEN_EXR | TIFF | WEBP.
    transparent: True → render film with a transparent background (PNG/EXR alpha).
    """
    filepath = params.get("filepath")
    if not filepath:
        return {"error": "'filepath' is required"}
    scene = bpy.context.scene

    if scene.camera is None:
        from .common import resolve_camera
        cam, err = resolve_camera(None, scene)
        if err:
            return {"error": err}
        scene.camera = cam

    engine = params.get("engine")
    if engine:
        # Authoritative check: try to SET it and catch the TypeError an invalid engine
        # raises. The old pre-validation read a static enum list that could omit a
        # genuinely-renderable engine (CYCLES), forcing callers to drop engine= to
        # bypass a false rejection (G24). Assignment can't be fooled.
        try:
            scene.render.engine = engine
        except TypeError:
            return {"error": f"render engine '{engine}' not available in this build; "
                             f"available: {_available_engines()}"}

    fmt = (params.get("format") or "PNG").upper()
    if fmt not in _FORMATS:
        return {"error": f"format must be one of {sorted(_FORMATS)}"}
    scene.render.image_settings.file_format = fmt

    rx = params.get("resolution_x")
    ry = params.get("resolution_y")
    if rx is not None:
        scene.render.resolution_x = int(rx)
    if ry is not None:
        scene.render.resolution_y = int(ry)
    scene.render.resolution_percentage = 100

    samples = params.get("samples")
    if samples is not None:
        eevee = getattr(scene, "eevee", None)
        if scene.render.engine == 'CYCLES':
            scene.cycles.samples = int(samples)
        elif eevee is not None and hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = int(samples)

    if params.get("transparent") is not None:
        scene.render.film_transparent = bool(params.get("transparent"))

    ext = {"PNG": ".png", "JPEG": ".jpg", "OPEN_EXR": ".exr",
           "TIFF": ".tif", "WEBP": ".webp"}[fmt]
    path = os.path.expanduser(filepath)
    if not os.path.splitext(path)[1]:
        path += ext
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    scene.render.filepath = path

    bpy.ops.render.render(write_still=True)

    if not os.path.isfile(path):
        return {"error": f"render reported success but no file at {path}"}
    return {
        "success": True,
        "filepath": path,
        "bytes": os.path.getsize(path),
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "engine": scene.render.engine,
        "format": fmt,
        "camera": scene.camera.name,
    }


def render_settings(params):
    """G11 — READ the render config (the missing half: the verb could only set).
    Reports the build's available engines (so the schema never hardcodes them), the
    current engine, output resolution/format, color management, and the active engine's
    own params. Stops 'discovery-by-exception' — no need to send a bad engine to learn
    the list from the error."""
    scene = bpy.context.scene
    r = scene.render
    vs = scene.view_settings

    available = _available_engines()

    out = {
        "success": True,
        "engine": r.engine,
        "available_engines": available,
        "resolution": [r.resolution_x, r.resolution_y],
        "resolution_percentage": r.resolution_percentage,
        "pixel_aspect": [round(r.pixel_aspect_x, 4), round(r.pixel_aspect_y, 4)],
        "format": r.image_settings.file_format,
        "film_transparent": r.film_transparent,
        "color": {
            "view_transform": vs.view_transform,
            "look": vs.look,
            "exposure": round(vs.exposure, 4),
            "gamma": round(vs.gamma, 4),
        },
    }

    if r.engine == 'CYCLES' and hasattr(scene, "cycles"):
        c = scene.cycles
        cy = {"samples": getattr(c, "samples", None),
              "device": getattr(c, "device", None),
              "use_denoising": getattr(c, "use_denoising", None),
              "denoiser": getattr(c, "denoiser", None)}
        if getattr(c, "use_adaptive_sampling", False):
            cy["adaptive_threshold"] = round(getattr(c, "adaptive_threshold", 0.0), 5)
        cyc = {k: v for k, v in cy.items() if v is not None}
        # The preference-layer preflight: backend + per-device enabled flags, and the
        # EFFECTIVE device (so 'device=GPU' that will silently fall back to CPU shows it).
        pre = _cycles_preflight()
        cyc["compute"] = pre
        wants_gpu = getattr(c, "device", "CPU") == 'GPU'
        has_gpu = pre.get("addon_enabled") and pre.get("gpu_devices_enabled")
        cyc["effective_device"] = "GPU" if (wants_gpu and has_gpu) else "CPU"
        if wants_gpu and not has_gpu:
            cyc["warning"] = ("device=GPU but no GPU device is enabled in Cycles "
                              "preferences — this render falls back to CPU.")
        out["cycles"] = cyc
    else:
        eevee = getattr(scene, "eevee", None)
        if eevee is not None:
            ev = {}
            if hasattr(eevee, "taa_render_samples"):
                ev["samples"] = eevee.taa_render_samples
            if hasattr(eevee, "use_raytracing"):
                ev["raytracing"] = eevee.use_raytracing
            if hasattr(eevee, "use_gtao"):
                ev["ao"] = eevee.use_gtao
            if hasattr(eevee, "use_shadows"):
                ev["shadows"] = eevee.use_shadows
            out["eevee"] = ev

    return out


def set_render_engine(params):
    """G187 — set the active render engine as STATE, no frame rendered.

    Choosing Eevee vs Cycles is scene CONFIGURATION an artist sets once and leaves —
    it belongs with quality/cycles/color. But the only other path that assigns
    scene.render.engine is render_to_file, which flips the engine AND immediately
    renders. That trapped a piece of config behind a render ACTION (and collided with
    the 'don't render to self-confirm' rule). This sets it standalone, so look-dev on
    Cycles (SSS, caustics, the GPU preflight render_settings already reports) needs no
    throwaway render.

    name: the build's engine id — e.g. 'CYCLES', 'BLENDER_EEVEE'. Validated by trying
          the assignment (Blender refuses an engine it can't provide), so an invalid id
          returns the build's real available list instead of crashing — same
          authoritative check render_to_file uses.
    """
    name = params.get("name") or params.get("engine")
    if not name:
        return {"error": "'name' is required — the engine id to activate "
                         f"(available: {_available_engines()})"}
    scene = bpy.context.scene
    previous = scene.render.engine
    if name == previous:
        return {"success": True, "engine": previous, "previous": previous,
                "available_engines": _available_engines(), "unchanged": True}
    try:
        scene.render.engine = name
    except TypeError:
        return {"error": f"render engine '{name}' not available in this build; "
                         f"available: {_available_engines()}"}
    return {"success": True, "engine": scene.render.engine, "previous": previous,
            "available_engines": _available_engines()}


TOOLS = {
    "render_to_file": render_to_file,
    "render_settings": render_settings,
    "set_render_engine": set_render_engine,
}

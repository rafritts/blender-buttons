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


def render_to_file(params):
    """Render the active scene camera to an image file.

    FOR THE HUMAN USER, NOT THE AGENT — produces a picture for a person to look at.
    The agent never sees these images; to understand the model it uses the
    introspection/topology tools (get_topology, describe, check_mesh, etc.).

    filepath:   output path (required). ~ is expanded. Extension is set to match
                the format if missing.
    resolution_x / resolution_y: pixel dims (default: keep the scene's current).
    samples:    render sample count (optional; higher = cleaner + slower).
    engine:     'BLENDER_EEVEE_NEXT' | 'CYCLES' | ... (default: keep current).
    format:     PNG (default) | JPEG | OPEN_EXR | TIFF | WEBP.
    transparent: True → render film with a transparent background (PNG/EXR alpha).
    """
    filepath = params.get("filepath")
    if not filepath:
        return {"error": "'filepath' is required"}
    scene = bpy.context.scene

    if scene.camera is None:
        cam = next((o for o in scene.objects if o.type == 'CAMERA'), None)
        if cam is None:
            return {"error": "No camera in scene — add_camera first."}
        scene.camera = cam

    engine = params.get("engine")
    if engine:
        avail = [e.identifier for e in
                 type(scene.render).bl_rna.properties["engine"].enum_items]
        if engine not in avail:
            return {"error": f"render engine '{engine}' not available in this build; "
                             f"available: {avail}"}
        scene.render.engine = engine

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

    available = [e.identifier for e in
                 type(r).bl_rna.properties["engine"].enum_items]

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
        out["cycles"] = {k: v for k, v in cy.items() if v is not None}
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


TOOLS = {
    "render_to_file": render_to_file,
    "render_settings": render_settings,
}

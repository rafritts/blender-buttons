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
        try:
            scene.render.engine = engine
        except TypeError:
            return {"error": f"render engine '{engine}' not available in this build"}

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


TOOLS = {
    "render_to_file": render_to_file,
}

"""Save/open/list .blend design files in ~/blender-designs, plus new_scene."""

import os

import bpy

from . import state

DESIGNS_DIR = os.path.expanduser("~/blender-designs")


def _designs_dir():
    os.makedirs(DESIGNS_DIR, exist_ok=True)
    return DESIGNS_DIR


def save_design(params):
    name = params.get("name", "").strip()
    if not name:
        return {"error": "name is required"}
    if not name.endswith(".blend"):
        name += ".blend"
    path = os.path.join(_designs_dir(), name)
    # Pack external files (e.g. cached Poly Haven texture/HDRI images) into the
    # .blend so saved designs are self-contained and don't dangle on cache paths.
    packed = False
    try:
        bpy.ops.file.pack_all()
        packed = True
    except Exception:
        pass
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    return {"saved": path, "packed": packed}


def open_design(params):
    name = params.get("name", "").strip()
    if not name:
        return {"error": "name is required"}
    if not name.endswith(".blend"):
        name += ".blend"
    path = os.path.join(_designs_dir(), name)
    if not os.path.isfile(path):
        return {"error": f"no design at {path}"}
    bpy.ops.wm.open_mainfile(filepath=path)
    return {"opened": path}


def list_designs(params):
    d = _designs_dir()
    files = sorted(f for f in os.listdir(d) if f.endswith(".blend"))
    return {"dir": d, "designs": files}


def new_scene(params):
    """Reset to a fresh scene — the equivalent of File > New > General.

    Loads Blender's startup file (default cube/camera/light) and with it resets
    world background, color management, and render settings to defaults — the
    one-call "start over" that otherwise meant deleting every object by hand and
    un-doing earlier world/render tweaks. `empty=True` additionally clears the
    startup cube/camera/light for a bare modelling slate.

    The socket server runs in a daemon thread and the queue processor is a
    persistent timer, so both survive the reload; we re-register the timer only
    in the (not-expected) case Blender dropped it.
    """
    empty = bool(params.get("empty", False))
    bpy.ops.wm.read_homefile(app_template="")

    removed = []
    if empty:
        for obj in list(bpy.data.objects):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)

    # The reload wiped Blender's undo stack and replaced the scene; drop our
    # parallel bookkeeping so the history log can't desync from the now-fresh
    # undo stack (the 1:1 invariant in state.py / gaps.md E1).
    state._history.clear()
    state._redo_stack.clear()
    state._undo_baseline = None
    state._snapshots.clear()

    # Defensive: persistent=True timers survive file loads, but if a future
    # Blender ever drops it, re-arm so the server keeps draining the queue.
    if state._running:
        from . import server
        if not bpy.app.timers.is_registered(server.process_queue):
            bpy.app.timers.register(server.process_queue, persistent=True)

    return {"success": True,
            "reset_to": "empty scene" if empty else "File > New > General",
            "objects": state.scene_object_names(),
            "removed": removed}


TOOLS = {
    "save_design":  save_design,
    "open_design":  open_design,
    "list_designs": list_designs,
    "new_scene":    new_scene,
}

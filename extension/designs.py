"""Save/open/list .blend design files in ~/blender-designs."""

import os

import bpy

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
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    return {"saved": path}


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


TOOLS = {
    "save_design":  save_design,
    "open_design":  open_design,
    "list_designs": list_designs,
}

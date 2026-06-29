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


def _imp_stl(p):
    try:
        bpy.ops.wm.stl_import(filepath=p)
    except AttributeError:
        bpy.ops.import_mesh.stl(filepath=p)


def _imp_ply(p):
    try:
        bpy.ops.wm.ply_import(filepath=p)
    except AttributeError:
        bpy.ops.import_mesh.ply(filepath=p)


def _imp_fbx(p):
    # Blender 5.0 made the C++ importer (wm.fbx_import) the default and demoted the
    # Python add-on (import_scene.fbx) to legacy — it is OFF by default, so its operator
    # is usually unregistered. Prefer the C++ op; fall back only if it's absent.
    try:
        bpy.ops.wm.fbx_import(filepath=p)
    except AttributeError:
        bpy.ops.import_scene.fbx(filepath=p)


_IMPORTERS = {
    ".obj":  lambda p: bpy.ops.wm.obj_import(filepath=p),
    ".stl":  _imp_stl,
    ".ply":  _imp_ply,
    ".glb":  lambda p: bpy.ops.import_scene.gltf(filepath=p),
    ".gltf": lambda p: bpy.ops.import_scene.gltf(filepath=p),
    ".fbx":  _imp_fbx,
}


def _append_blend(path, name_filter, link):
    """Append (or link) objects out of a saved .blend — the File > Append path,
    which `bpy.ops.wm.<format>_import` can't reach. Uses bpy.data.libraries.load
    to pull the Object datablocks, then links them into the active scene
    collection (load alone brings the data in but puts nothing in the scene).

    name_filter: case-insensitive substring; only matching object names are
                 appended (default: every object in the file).
    link:        True = library-LINK (read-only, tracks the source file) instead
                 of a local APPEND copy. Default False (append).
    """
    with bpy.data.libraries.load(path, link=link) as (data_from, data_to):
        names = list(data_from.objects)
        if name_filter:
            nf = name_filter.lower()
            names = [n for n in names if nf in n.lower()]
        if not names:
            return {"error": f"no objects in '{path}'"
                             + (f" matching '{name_filter}'" if name_filter else "")}
        data_to.objects = names
    appended = [ob for ob in data_to.objects if ob is not None]
    coll = bpy.context.scene.collection
    linked_in = []
    for ob in appended:
        try:
            coll.objects.link(ob)
            linked_in.append(ob.name)
        except RuntimeError:
            pass  # already present in a scene collection
    meshes = [{"name": ob.name,
               "verts": len(ob.data.vertices),
               "faces": len(ob.data.polygons),
               "edges": len(ob.data.edges)}
              for ob in appended if ob.type == 'MESH']
    return {"imported": [ob.name for ob in appended], "meshes": meshes,
            "path": path, "mode": "link" if link else "append"}


def import_mesh(params):
    """Import a mesh file into the current scene (File > Import). Generic over
    the common formats; the importer is chosen by file extension. A `.blend`
    path is APPENDED (File > Append) rather than format-imported — its objects
    are pulled in with their wired/packed materials intact."""
    path = os.path.expanduser(params.get("path", "").strip())
    if not path:
        return {"error": "path is required"}
    if not os.path.isfile(path):
        return {"error": f"no file at {path}"}
    ext = os.path.splitext(path)[1].lower()
    if ext == ".blend":
        try:
            return _append_blend(path, params.get("name", "").strip(),
                                 bool(params.get("link", False)))
        except Exception as e:
            return {"error": f"append failed: {e}"}
    imp = _IMPORTERS.get(ext)
    if imp is None:
        return {"error": f"unsupported format '{ext}'; supported: "
                         f"{', '.join(sorted(_IMPORTERS))}, .blend"}
    before = set(bpy.data.objects.keys())
    try:
        imp(path)
    except Exception as e:  # missing io addon, malformed file, ...
        return {"error": f"import failed: {e}"}
    new = [n for n in bpy.data.objects.keys() if n not in before]
    meshes = []
    for n in new:
        ob = bpy.data.objects.get(n)
        if ob is not None and ob.type == 'MESH':
            meshes.append({"name": n,
                           "verts": len(ob.data.vertices),
                           "faces": len(ob.data.polygons),
                           "edges": len(ob.data.edges)})
    return {"imported": new, "meshes": meshes, "path": path}


TOOLS = {
    "save_design":  save_design,
    "open_design":  open_design,
    "list_designs": list_designs,
    "new_scene":    new_scene,
    "import_mesh":  import_mesh,
}

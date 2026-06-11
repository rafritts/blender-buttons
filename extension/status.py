"""Snapshot tools: get_scene_tree, get_blender_status. These run on demand and after every mutating tool."""

import math

import bpy

from . import state
from .common import world_bbox


def get_scene_tree(params=None):
    """Scene hierarchy. On production scenes (Spring: ~400 objects, 300 of them
    bone-shape widgets) the full dump is unreadable, so big collections collapse
    to per-type counts and the tree is filterable (gaps.md U4).

    filter:    substring — show only objects whose name contains it.
    type:      object type (MESH/ARMATURE/EMPTY/…) — show only that type.
    max_depth: cap collection nesting depth.
    summarize: collapse any collection holding more than this many objects into a
               per-type count line (default 20; 0 disables). Filtering disables it
               (you asked for specific objects).
    """
    from collections import Counter
    params = params or {}
    flt = (params.get("filter") or "").lower()
    type_filter = (params.get("type") or "").upper()
    md = params.get("max_depth")
    max_depth = int(md) if md is not None else None
    try:
        summarize = int(params.get("summarize", 20))
    except (TypeError, ValueError):
        summarize = 20
    filtering = bool(flt or type_filter)

    mesh_count = Counter(
        obj.data.name for obj in bpy.context.scene.objects
        if obj.type == 'MESH' and obj.data
    )
    from .common import linked_status

    def matches(obj):
        if flt and flt not in obj.name.lower():
            return False
        if type_filter and obj.type != type_filter:
            return False
        return True

    def obj_line(obj, pad=""):
        active = " ● active" if obj == bpy.context.active_object else ""
        sel = " ◆" if obj.select_get() else ""
        instanced = " (instanced)" if obj.type == 'MESH' and obj.data and mesh_count[obj.data.name] > 1 else ""
        lib = linked_status(obj)
        lib_tag = f" [{lib}]" if lib else ""
        return f"{pad}├── {obj.name} [{obj.type}]{instanced}{lib_tag}{active}{sel}"

    shown = [0]
    hidden = [0]

    def emit_objects(objs, pad, lines):
        # Summarize a big collection to per-type counts — unless filtering (then the
        # caller wants the matching objects listed).
        if not filtering and summarize and len(objs) > summarize:
            counts = Counter(o.type for o in objs)
            summary = ", ".join(f"{n} {t}" for t, n in counts.most_common())
            lines.append(f"{pad}├── … {len(objs)} objects ({summary}) — "
                         f"filter=/type= to drill in, summarize=0 to expand")
            hidden[0] += len(objs)
        else:
            for obj in objs:
                if matches(obj):
                    lines.append(obj_line(obj, pad))
                    shown[0] += 1

    def fmt_collection(col, depth=0):
        pad = "│   " * depth
        lines = [f"{pad}├── {col.name}/"]
        emit_objects(list(col.objects), pad + "│   ", lines)
        if max_depth is None or depth < max_depth:
            for child in col.children:
                lines += fmt_collection(child, depth + 1)
        elif col.children:
            lines.append(f"{pad}│   ├── … {len(col.children)} sub-collection(s) (max_depth={max_depth})")
        return lines

    lines = ["Scene Collection"]
    for col in bpy.context.scene.collection.children:
        lines += fmt_collection(col)
    emit_objects(list(bpy.context.scene.collection.objects), "", lines)

    result = {"tree": "\n".join(lines), "shown": shown[0]}
    if hidden[0]:
        result["summarized"] = hidden[0]
    return result


def _viewport_shading():
    """Shading mode of the user's first 3D viewport — 'SOLID', 'MATERIAL',
    'RENDERED', or 'WIREFRAME'. Returns None in headless/windowless contexts."""
    wm = bpy.context.window_manager
    for win in (wm.windows if wm else []):
        screen = getattr(win, "screen", None)
        if not screen:
            continue
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = next((s for s in area.spaces if s.type == 'VIEW_3D'), None)
                if space:
                    return space.shading.type
    return None


def get_blender_status(params):
    import bmesh as _bmesh
    # Force depsgraph evaluation so matrix_world / bound_box reflect any location, rotation,
    # or scale changes from the just-finished tool. Without this, status reads return
    # the pre-mutation state and the appended status block lies.
    bpy.context.view_layer.update()
    obj = bpy.context.active_object

    status = {
        "mode": obj.mode if obj else "OBJECT",
        "active_object": obj.name if obj else None,
        "active_type": obj.type if obj else None,
        "selected_objects": [o.name for o in bpy.context.selected_objects],
        "last_action": (
            {"id": state._history[-1]["id"], "label": state._history[-1]["label"],
             "tool": state._history[-1]["tool"]}
            if state._history else None
        ),
        "history_depth": len(state._history),
    }

    # Render/display settings — an agent can't diagnose washed-out (AgX) or
    # plastic-metal (no raytracing) renders without seeing these.
    scene = bpy.context.scene
    vs = scene.view_settings
    render = {
        "engine": scene.render.engine,
        "view_transform": vs.view_transform,
        "look": vs.look,
        "exposure": round(vs.exposure, 4),
        "gamma": round(vs.gamma, 4),
    }
    eevee = getattr(scene, "eevee", None)
    if eevee is not None and hasattr(eevee, "use_raytracing"):
        render["raytracing"] = eevee.use_raytracing
    status["render"] = render

    # The shading mode the USER is looking at. A texture pass run while their
    # viewport sits in SOLID reads as gray blockout to them even as renders come
    # out fully dressed (gaps.md T4) — surfacing it lets the agent catch the
    # mismatch at the first material call. None in headless.
    vp = _viewport_shading()
    if vp is not None:
        status["viewport"] = vp

    if obj:
        status["location"] = [round(v, 4) for v in obj.location]
        status["rotation_deg"] = [round(math.degrees(v), 2) for v in obj.rotation_euler]
        # World-space bbox dims (rotation-aware). obj.dimensions is local-bbox × scale and
        # ignores rotation — wrong for any rotated object.
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
        status["dimensions"] = [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)]
        status["world_bounds"] = {
            "x": [round(xmin, 4), round(xmax, 4)],
            "y": [round(ymin, 4), round(ymax, 4)],
            "z": [round(zmin, 4), round(zmax, 4)],
        }
        status["world_z_range"] = status["world_bounds"]["z"]

    if obj and obj.mode == 'EDIT' and obj.type == 'MESH':
        bm = _bmesh.from_edit_mesh(obj.data)
        sel_verts  = [v for v in bm.verts if v.select]
        sel_edges  = [e for e in bm.edges if e.select]
        sel_faces  = [f for f in bm.faces if f.select]
        status["edit"] = {
            "component_mode": (
                "VERT"  if bpy.context.tool_settings.mesh_select_mode[0] else
                "EDGE"  if bpy.context.tool_settings.mesh_select_mode[1] else
                "FACE"
            ),
            "selected":  {"verts": len(sel_verts),  "edges": len(sel_edges),  "faces": len(sel_faces)},
            "total":     {"verts": len(bm.verts),    "edges": len(bm.edges),   "faces": len(bm.faces)},
        }
        if sel_verts:
            world_sel = [(obj.matrix_world @ v.co) for v in sel_verts]
            status["edit"]["selection_z_range"] = [
                round(min(v.z for v in world_sel), 4),
                round(max(v.z for v in world_sel), 4),
            ]

    return {"success": True, "status": status}


TOOLS = {
    "get_scene_tree":     get_scene_tree,
    "get_blender_status": get_blender_status,
}

"""Snapshot tools: get_scene_tree, get_blender_status. These run on demand and after every mutating tool."""

import math

import bpy

from . import state
from .common import world_bbox


def get_scene_tree():
    def fmt_collection(col, depth=0):
        pad = "│   " * depth
        lines = [f"{pad}├── {col.name}/"]
        for obj in col.objects:
            active = " ● active" if obj == bpy.context.active_object else ""
            sel = " ◆" if obj.select_get() else ""
            lines.append(f"{pad}│   ├── {obj.name} [{obj.type}]{active}{sel}")
        for child in col.children:
            lines += fmt_collection(child, depth + 1)
        return lines

    lines = ["Scene Collection"]
    for col in bpy.context.scene.collection.children:
        lines += fmt_collection(col)
    for obj in bpy.context.scene.collection.objects:
        active = " ● active" if obj == bpy.context.active_object else ""
        sel = " ◆" if obj.select_get() else ""
        lines.append(f"├── {obj.name} [{obj.type}]{active}{sel}")
    return {"tree": "\n".join(lines)}


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
    "get_scene_tree":     lambda p: get_scene_tree(),
    "get_blender_status": get_blender_status,
}

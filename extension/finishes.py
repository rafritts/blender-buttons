"""Bundled finishes: smooth_edges, round_corners, add_modifier, apply_modifiers."""

import math

import bpy

from .common import activate, resolve_targets, world_bbox
from .state import push_undo


def smooth_edges(params):
    """Round off the sharp edges of one or more objects.
    Adds a BEVEL modifier with angle-limit (only sharp edges get beveled, not coplanar ones),
    then shade_smooth + auto_smooth so the rounded edges read as smooth, not faceted.
    width: bevel offset in world units (default 2mm). segments: more = smoother curve.
    angle_limit: edges sharper than this (degrees) get beveled. Default 30°."""
    targets = params.get("targets")
    width = params.get("width", 0.002)
    segments = params.get("segments", 2)
    angle_limit_deg = params.get("angle_limit", 30.0)
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    processed = []
    for o in objs:
        if o.type != 'MESH':
            continue
        activate(o)
        if any(abs(s - 1.0) > 1e-4 for s in o.scale):
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        for m in list(o.modifiers):
            if m.name == "Smooth_Bevel":
                o.modifiers.remove(m)

        mod = o.modifiers.new(name="Smooth_Bevel", type='BEVEL')
        mod.width = width
        mod.segments = segments
        mod.limit_method = 'ANGLE'
        mod.angle_limit = math.radians(angle_limit_deg)
        mod.miter_outer = 'MITER_ARC'
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.ops.object.shade_smooth()
        if hasattr(o.data, "use_auto_smooth"):
            o.data.use_auto_smooth = True
            o.data.auto_smooth_angle = math.radians(angle_limit_deg)
        processed.append(o.name)

    return {"success": True, "smoothed": processed, "width": width,
            "segments": segments, "angle_limit": angle_limit_deg}


def round_corners(params):
    """Round specific vertical corner edges of an object by a real-world radius.

    target:   object name.
    corners:  list of "front_left" | "front_right" | "back_left" | "back_right".
    radius:   bevel offset in meters (the rounding radius). Default 0.02 (2cm).
    segments: number of segments in the round; more = smoother curve. Default 6.
    """
    import bmesh
    target = params.get("target")
    corners = params.get("corners", [])
    radius = params.get("radius", 0.02)
    segments = params.get("segments", 6)

    obj = bpy.data.objects.get(target) if target else None
    if obj is None:
        return {"error": f"Object '{target}' not found"}
    if obj.type != 'MESH':
        return {"error": f"'{target}' is not a mesh"}
    if not corners:
        return {"error": "'corners' must be a non-empty list (front_left|front_right|back_left|back_right)"}

    activate(obj)
    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)

    corner_map = {
        "front_left":  (xmin, ymin),
        "front_right": (xmax, ymin),
        "back_left":   (xmin, ymax),
        "back_right":  (xmax, ymax),
    }
    bad = [c for c in corners if c not in corner_map]
    if bad:
        return {"error": f"Unknown corner(s) {bad}. Valid: {list(corner_map.keys())}"}

    if bpy.context.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')

    bm = bmesh.from_edit_mesh(obj.data)
    mat = obj.matrix_world
    tol = max(radius * 0.5, 1e-3)

    selected = 0
    for edge in bm.edges:
        v0 = mat @ edge.verts[0].co
        v1 = mat @ edge.verts[1].co
        if abs(v0.x - v1.x) > 1e-4 or abs(v0.y - v1.y) > 1e-4:
            continue
        if abs(v0.z - v1.z) < 1e-4:
            continue
        ex, ey = v0.x, v0.y
        for cname in corners:
            tx, ty = corner_map[cname]
            if abs(ex - tx) < tol and abs(ey - ty) < tol:
                edge.select = True
                selected += 1
                break

    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)

    if selected == 0:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": f"No vertical corner edges found near {corners}. "
                          f"Object may need loop_cut along Z first if it's a single-segment box."}

    bpy.ops.mesh.bevel(offset=radius, segments=segments, affect='EDGES')
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.shade_smooth()
    if hasattr(obj.data, "use_auto_smooth"):
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(60)

    push_undo(f"round_corners {target} {corners} r={radius}")
    return {"success": True, "target": target, "corners": corners,
            "radius": radius, "segments": segments, "edges_beveled": selected}


def add_modifier(params):
    mod_type = params.get("type", "SUBSURF").upper()
    name     = params.get("name", mod_type.capitalize())
    obj      = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    mod = obj.modifiers.new(name=name, type=mod_type)
    if hasattr(mod, 'levels'):
        mod.levels = params.get("levels", 2)
    if hasattr(mod, 'render_levels'):
        mod.render_levels = params.get("render_levels", params.get("levels", 2))
    if hasattr(mod, 'width'):
        mod.width = params.get("width", 0.1)
    if hasattr(mod, 'segments'):
        mod.segments = params.get("segments", 1)
    if mod_type == "BEVEL":
        limit = params.get("limit_method", "ANGLE").upper()
        if hasattr(mod, 'limit_method'):
            mod.limit_method = limit
        if hasattr(mod, 'angle_limit'):
            mod.angle_limit = math.radians(params.get("angle_limit", 30.0))
    if mod_type == "SHRINKWRAP":
        target_name = params.get("target")
        if not target_name:
            obj.modifiers.remove(mod)
            return {"error": "SHRINKWRAP requires 'target' (the object to wrap onto)"}
        tgt = bpy.data.objects.get(target_name)
        if tgt is None:
            obj.modifiers.remove(mod)
            return {"error": f"target '{target_name}' not found"}
        mod.target = tgt
        offset = params.get("offset")
        if offset is not None and hasattr(mod, 'offset'):
            mod.offset = float(offset)
        wrap_method = params.get("wrap_method", "NEAREST_SURFACEPOINT").upper()
        if hasattr(mod, 'wrap_method'):
            mod.wrap_method = wrap_method
    return {"success": True, "modifier": mod.name}


def apply_modifiers(params):
    name = params.get("name")
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    else:
        obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if obj.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    mod_names = [m.name for m in obj.modifiers]
    if not mod_names:
        return {"success": True, "applied": [], "object": obj.name}
    applied = []
    for mod_name in mod_names:
        if any(m.name == mod_name for m in obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=mod_name)
            applied.append(mod_name)
    return {"success": True, "applied": applied, "object": obj.name}


TOOLS = {
    "smooth_edges":    smooth_edges,
    "round_corners":   round_corners,
    "add_modifier":    add_modifier,
    "apply_modifiers": apply_modifiers,
}

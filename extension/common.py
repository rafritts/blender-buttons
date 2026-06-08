"""Shared geometry/selection helpers used by most tool modules."""

import math

import bpy
import mathutils


def world_bbox(obj):
    """World-space bounding box: (xmin, ymin, zmin, xmax, ymax, zmax)."""
    bb = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    xs = [v.x for v in bb]; ys = [v.y for v in bb]; zs = [v.z for v in bb]
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def world_center(obj):
    """World-space bbox center of an object."""
    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    return ((xmin + xmax) * 0.5, (ymin + ymax) * 0.5, (zmin + zmax) * 0.5)


def nearby_objects(world_pos, exclude_names=(), max_count=3):
    """Return up to max_count nearest mesh objects to world_pos, sorted by distance."""
    px, py, pz = world_pos
    cands = []
    for o in bpy.context.scene.objects:
        if o.name in exclude_names or o.type != 'MESH':
            continue
        cx, cy, cz = world_center(o)
        d = math.sqrt((cx - px) ** 2 + (cy - py) ** 2 + (cz - pz) ** 2)
        cands.append((d, o.name, (cx, cy, cz)))
    cands.sort()
    return [
        {"name": n, "center": [round(c[0], 3), round(c[1], 3), round(c[2], 3)], "dist": round(d, 4)}
        for d, n, c in cands[:max_count]
    ]


def resolve_targets(targets):
    """Resolve a target spec into a list of bpy mesh objects.

    targets: str (single object or collection name), list[str], or None (-> active object).
    Collection names expand to all mesh objects inside (recursively).
    Returns (objects, error). On error, objects is None.
    """
    if targets is None:
        obj = bpy.context.active_object
        if obj is None:
            return None, "No active object and no targets specified"
        return [obj], None

    if isinstance(targets, str):
        targets = [targets]

    if not isinstance(targets, list) or not targets:
        return None, "'targets' must be a non-empty string or list of strings"

    objs = []
    seen = set()
    for name in targets:
        obj = bpy.data.objects.get(name)
        coll = bpy.data.collections.get(name)
        if obj is None and coll is None:
            return None, f"Target '{name}' not found (no object or collection by that name)"
        if obj is not None and obj.name not in seen:
            objs.append(obj)
            seen.add(obj.name)
        if coll is not None:
            for o in coll.all_objects:
                if o.type == 'MESH' and o.name not in seen:
                    objs.append(o)
                    seen.add(o.name)
    return objs, None


def activate(obj):
    """Make obj the sole selected + active object."""
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_scale(obj):
    """Bake object scale into mesh data so obj.scale becomes [1,1,1].
    Required for bevel and other width-based modifiers to behave uniformly."""
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

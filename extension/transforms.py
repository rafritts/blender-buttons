"""Object-level transforms: nudge, resize, rotate, apply_transform, snap_to, snap_to_grid."""

import math

import bpy

from .common import activate, resolve_targets, world_bbox


def nudge(params):
    """Move objects by a relative offset in semantic directions.
    right/left -> ±X, back/forward -> ±Y, up/down -> ±Z. Negative values flip direction."""
    targets = params.get("targets")
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}

    dx = params.get("right", 0.0) - params.get("left", 0.0)
    dy = params.get("back", 0.0) - params.get("forward", 0.0)
    dz = params.get("up", 0.0) - params.get("down", 0.0)

    for o in objs:
        o.location.x += dx
        o.location.y += dy
        o.location.z += dz
    bpy.context.view_layer.update()
    return {"success": True, "moved": [o.name for o in objs],
            "delta": [round(dx, 5), round(dy, 5), round(dz, 5)]}


def resize(params):
    """Resize objects to absolute world-space dimensions (width × depth × height).
    Each dim is optional; omitted dims preserve current size."""
    targets = params.get("targets")
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}

    w = params.get("width")
    d = params.get("depth")
    h = params.get("height")
    if w is None and d is None and h is None:
        return {"error": "resize requires at least one of width, depth, height"}

    results = []
    for o in objs:
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
        cur_w, cur_d, cur_h = xmax - xmin, ymax - ymin, zmax - zmin
        sx = (w / cur_w) if (w is not None and cur_w > 1e-9) else 1.0
        sy = (d / cur_d) if (d is not None and cur_d > 1e-9) else 1.0
        sz = (h / cur_h) if (h is not None and cur_h > 1e-9) else 1.0
        o.scale.x *= sx
        o.scale.y *= sy
        o.scale.z *= sz
        bpy.context.view_layer.update()
        activate(o)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
        results.append({"name": o.name, "dims": [round(xmax - xmin, 4),
                                                  round(ymax - ymin, 4),
                                                  round(zmax - zmin, 4)]})
    return {"success": True, "resized": results}


def apply_transform(params):
    """Bake object transforms into mesh data. After applying scale, obj.scale
    becomes [1,1,1] and modifiers (especially bevel) behave uniformly. Apply
    rotation to clear rotation_euler. Apply location to move the object's
    origin to the world origin (rare; usually undesirable)."""
    targets = params.get("targets")
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}
    do_scale = params.get("scale", True)
    do_rotation = params.get("rotation", False)
    do_location = params.get("location", False)

    for o in objs:
        activate(o)
        bpy.ops.object.transform_apply(
            location=do_location, rotation=do_rotation, scale=do_scale
        )
    return {"success": True,
            "applied_to": [o.name for o in objs],
            "scale": do_scale, "rotation": do_rotation, "location": do_location}


def rotate_object(params):
    """Rotate one or more objects by an angle around an axis."""
    targets = params.get("targets")
    angle = params.get("angle", 0.0)
    axis = params.get("axis", "Z").upper()
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}

    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    rad = math.radians(angle)
    for o in objs:
        o.rotation_euler[axis_idx] += rad
    bpy.context.view_layer.update()
    return {"success": True, "rotated": [o.name for o in objs],
            "angle_deg": angle, "axis": axis}


def snap_to(params):
    """Move the active object so one of its bbox faces aligns with a face of a target object."""
    target_name = params.get("target")
    side = params.get("side", "Z_MAX").upper()
    source_side = params.get("source_side", "AUTO").upper()
    offset = params.get("offset", 0.0)

    obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if not target_name:
        return {"error": "'target' is required"}
    target = bpy.data.objects.get(target_name)
    if target is None:
        return {"error": f"Target '{target_name}' not found"}
    if target == obj:
        return {"error": "Cannot snap object to itself"}

    side_map = {
        "X_MIN": (0, "min"), "X_MAX": (0, "max"),
        "Y_MIN": (1, "min"), "Y_MAX": (1, "max"),
        "Z_MIN": (2, "min"), "Z_MAX": (2, "max"),
    }
    if side not in side_map:
        return {"error": f"Invalid side '{side}'. Use X_MIN|X_MAX|Y_MIN|Y_MAX|Z_MIN|Z_MAX"}
    axis_idx, target_which = side_map[side]

    if source_side == "AUTO":
        source_which = "max" if target_which == "min" else "min"
    elif source_side == "CENTER":
        source_which = "center"
    elif source_side in side_map:
        ax2, which2 = side_map[source_side]
        if ax2 != axis_idx:
            return {"error": f"source_side '{source_side}' must be on the same axis as side '{side}'"}
        source_which = which2
    else:
        return {"error": f"Invalid source_side '{source_side}'"}

    def _coord(o, ax, which):
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
        lo = (xmin, ymin, zmin)[ax]
        hi = (xmax, ymax, zmax)[ax]
        if which == "min": return lo
        if which == "max": return hi
        return 0.5 * (lo + hi)

    target_coord = _coord(target, axis_idx, target_which)
    source_coord = _coord(obj, axis_idx, source_which)
    delta = target_coord - source_coord + offset
    obj.location[axis_idx] += delta

    return {
        "success": True,
        "target": target_name,
        "axis": "XYZ"[axis_idx],
        "target_side": side,
        "source_side": source_which,
        "target_coord": round(target_coord, 5),
        "source_coord_before": round(source_coord, 5),
        "source_coord_after": round(source_coord + delta, 5),
        "delta": round(delta, 5),
    }


def snap_to_grid(params):
    """Round the active object's location to multiples of `size` on the chosen axes."""
    obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    size = params.get("size", 0.1)
    axes = params.get("axes", "XYZ").upper()
    if size <= 0:
        return {"error": "size must be > 0"}

    snapped = []
    for i, ax in enumerate(("X", "Y", "Z")):
        if ax in axes:
            old = obj.location[i]
            new = round(old / size) * size
            obj.location[i] = new
            snapped.append({"axis": ax, "from": round(old, 5), "to": round(new, 5), "moved": round(new - old, 5)})

    return {"success": True, "grid_size": size, "axes": axes, "snapped": snapped,
            "location_after": [round(v, 5) for v in obj.location]}


TOOLS = {
    "nudge":           nudge,
    "resize":          resize,
    "rotate_object":   rotate_object,
    "apply_transform": apply_transform,
    "snap_to":         snap_to,
    "snap_to_grid":    snap_to_grid,
}

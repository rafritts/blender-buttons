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


def _axis_permutation(rot_matrix, tol=1e-4):
    """For an axis-aligned rotation (90°-multiples only), return perm where
    perm[j] = local axis index driving WORLD axis j. Returns None for any
    non-axis-aligned (arbitrary) rotation. world = R @ local, so world[j]
    depends on local[i] via R[j][i]."""
    perm = [None, None, None]
    for j in range(3):
        ones = [i for i in range(3) if abs(abs(rot_matrix[j][i]) - 1.0) < tol]
        zeros = [i for i in range(3) if abs(rot_matrix[j][i]) < tol]
        if len(ones) != 1 or len(zeros) != 2:
            return None
        perm[j] = ones[0]
    return perm if sorted(perm) == [0, 1, 2] else None


def resize(params):
    """Resize objects to absolute world-space dimensions (width × depth × height).
    Each dim is optional; omitted dims preserve current size.

    Rotated objects: resize targets WORLD axes. For axis-aligned rotations
    (90° multiples) the world→local axis mapping is exact, so this works. For
    arbitrary rotations it would shear the geometry, so resize REFUSES before
    touching anything and asks you to apply_transform(rotation=True) first."""
    targets = params.get("targets")
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}

    w = params.get("width")
    d = params.get("depth")
    h = params.get("height")
    if w is None and d is None and h is None:
        return {"error": "resize requires at least one of width, depth, height"}
    req = [w, d, h]  # requested WORLD X / Y / Z extents

    # Refuse arbitrary rotations BEFORE mutating anything (gaps.md E3: a warning
    # attached to an already-sheared result is the worst of both).
    for o in objs:
        if any(abs(r) > 0.0087 for r in o.rotation_euler):  # > ~0.5°
            if _axis_permutation(o.rotation_euler.to_matrix()) is None:
                deg = [round(math.degrees(r), 1) for r in o.rotation_euler]
                return {"error": (
                    f"'{o.name}' has a non-axis-aligned rotation {deg}° — resize works "
                    "in WORLD axes and would shear it. Run apply_transform(rotation=True) "
                    "on it first, or recreate the primitive at the target size. "
                    "Nothing was changed.")}

    results = []
    for o in objs:
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
        cur_world = [xmax - xmin, ymax - ymin, zmax - zmin]
        rotated = any(abs(r) > 0.0087 for r in o.rotation_euler)
        if rotated:
            # Axis-aligned: scale the LOCAL axis that drives each requested WORLD axis.
            perm = _axis_permutation(o.rotation_euler.to_matrix())
            mult = [1.0, 1.0, 1.0]
            for j in range(3):
                if req[j] is None or cur_world[j] <= 1e-9:
                    continue
                mult[perm[j]] *= req[j] / cur_world[j]
            o.scale.x *= mult[0]
            o.scale.y *= mult[1]
            o.scale.z *= mult[2]
        else:
            o.scale.x *= (w / cur_world[0]) if (w is not None and cur_world[0] > 1e-9) else 1.0
            o.scale.y *= (d / cur_world[1]) if (d is not None and cur_world[1] > 1e-9) else 1.0
            o.scale.z *= (h / cur_world[2]) if (h is not None and cur_world[2] > 1e-9) else 1.0
        bpy.context.view_layer.update()
        activate(o)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
        results.append({"name": o.name, "dims": [round(xmax - xmin, 4),
                                                  round(ymax - ymin, 4),
                                                  round(zmax - zmin, 4)]})
    return {"success": True, "resized": results}


def scale_group(params):
    """Uniformly scale a set of objects about a SHARED pivot, preserving their
    relative layout. This is what resize can't do: resize sets each member to the
    same absolute dims; scale_group makes a whole assembly N% bigger in place.

    targets: object/group name or list (required).
    factor:  uniform scale multiplier (required; e.g. 1.08 = 8% bigger).
    pivot:   "center" (default — combined bbox center) | "bottom_center"
             (combined bbox center XY at zmin — keeps feet on the floor) |
             "origin" (world 0,0,0) | an object name (its bbox center) |
             [x, y, z] literal world point.
    """
    targets = params.get("targets")
    factor = params.get("factor")
    pivot_spec = params.get("pivot", "center")
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}
    if factor is None:
        return {"error": "'factor' is required (e.g. 1.08 to grow 8%)"}
    factor = float(factor)
    if factor <= 0:
        return {"error": "'factor' must be > 0"}

    boxes = [world_bbox(o) for o in objs]
    xmin = min(b[0] for b in boxes); ymin = min(b[1] for b in boxes)
    zmin = min(b[2] for b in boxes)
    xmax = max(b[3] for b in boxes); ymax = max(b[4] for b in boxes)
    zmax = max(b[5] for b in boxes)

    if isinstance(pivot_spec, (list, tuple)) and len(pivot_spec) == 3:
        pivot = tuple(float(v) for v in pivot_spec)
    elif pivot_spec == "center":
        pivot = ((xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2)
    elif pivot_spec == "bottom_center":
        pivot = ((xmin + xmax) / 2, (ymin + ymax) / 2, zmin)
    elif pivot_spec == "origin":
        pivot = (0.0, 0.0, 0.0)
    else:
        anchor = bpy.data.objects.get(str(pivot_spec))
        if anchor is None:
            return {"error": (f"pivot '{pivot_spec}' not understood — use 'center', "
                              "'bottom_center', 'origin', an object name, or [x, y, z]")}
        a_xmin, a_ymin, a_zmin, a_xmax, a_ymax, a_zmax = world_bbox(anchor)
        pivot = ((a_xmin + a_xmax) / 2, (a_ymin + a_ymax) / 2, (a_zmin + a_zmax) / 2)

    # Uniform scale about a pivot: p' = pivot + factor * (p - pivot). For objects
    # that's location moved toward/away from the pivot plus local scale (uniform
    # scale commutes with rotation, so rotated parts stay correct).
    for o in objs:
        o.location = tuple(pivot[i] + factor * (o.location[i] - pivot[i]) for i in range(3))
        o.scale = tuple(s * factor for s in o.scale)
    bpy.context.view_layer.update()
    for o in objs:
        if o.type == 'MESH':
            activate(o)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    boxes = [world_bbox(o) for o in objs]
    return {
        "success": True,
        "scaled": [o.name for o in objs],
        "factor": factor,
        "pivot": [round(v, 5) for v in pivot],
        "bounds_after": {
            "x": [round(min(b[0] for b in boxes), 4), round(max(b[3] for b in boxes), 4)],
            "y": [round(min(b[1] for b in boxes), 4), round(max(b[4] for b in boxes), 4)],
            "z": [round(min(b[2] for b in boxes), 4), round(max(b[5] for b in boxes), 4)],
        },
    }


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
    """Rotate one or more objects by an angle around an axis.

    pivot (optional): rotate about a SHARED external point instead of each object's
    own origin. [x,y,z] world point, or an object name (its bbox centre). This is a
    rigid rotation — both position and orientation swing — so clock hands turn about
    the dial centre and a door turns about its hinge without pre-computing the arc.
    Without pivot, behaviour is unchanged: each object spins about its own origin."""
    from mathutils import Matrix, Vector

    targets = params.get("targets")
    angle = params.get("angle", 0.0)
    axis = params.get("axis", "Z").upper()
    pivot_spec = params.get("pivot")
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}

    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    rad = math.radians(angle)

    if pivot_spec is None:
        for o in objs:
            o.rotation_euler[axis_idx] += rad
        bpy.context.view_layer.update()
        return {"success": True, "rotated": [o.name for o in objs],
                "angle_deg": angle, "axis": axis, "pivot": None}

    if isinstance(pivot_spec, str):
        mode = pivot_spec.strip().lower()
        if mode in ("bbox", "bbox_center", "center"):
            # combined geometric centre of all targets (world space)
            pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
            pivot = Vector((sum(p.x for p in pts) / len(pts),
                            sum(p.y for p in pts) / len(pts),
                            sum(p.z for p in pts) / len(pts)))
        elif mode == "cursor":
            pivot = Vector(bpy.context.scene.cursor.location)
        elif mode == "origin":
            pivot = Vector((0.0, 0.0, 0.0))
        else:
            p_obj = bpy.data.objects.get(pivot_spec)
            if p_obj is None:
                return {"error": f"pivot '{pivot_spec}' not understood — use "
                                 f"bbox_center | cursor | origin | an object name | [x,y,z]"}
            pivot = Vector(world_center(p_obj))
    elif isinstance(pivot_spec, (list, tuple)) and len(pivot_spec) == 3:
        pivot = Vector([float(v) for v in pivot_spec])
    else:
        return {"error": "pivot must be [x,y,z] or an object name"}

    # Rigid rotation about the pivot: world' = T(pivot) · R · T(-pivot) · world.
    T = (Matrix.Translation(pivot) @ Matrix.Rotation(rad, 4, axis)
         @ Matrix.Translation(-pivot))
    for o in objs:
        o.matrix_world = T @ o.matrix_world
    bpy.context.view_layer.update()
    return {"success": True, "rotated": [o.name for o in objs],
            "angle_deg": angle, "axis": axis,
            "pivot": [round(v, 5) for v in pivot]}


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


def set_origin(params):
    """Move an object's origin/pivot to a chosen point.

    mode:
      geometry    — origin to mesh median (Blender's ORIGIN_GEOMETRY/MEDIAN).
      bbox_center — origin to bbox centre (ORIGIN_GEOMETRY/BOUNDS).
      mass        — origin to centre of mass (assumes uniform density).
      cursor      — origin to the current 3D cursor location.
      bottom|top|front|back|left|right — origin to the centre of that bbox face.

    Geometry is unchanged in world space; only the local-space pivot moves.
    Mostly used before rotate_object so the rotation pivots around the right point.
    """
    targets = params.get("targets")
    mode = params.get("mode", "geometry").lower()
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}

    direct = {
        "geometry":    ("ORIGIN_GEOMETRY", "MEDIAN"),
        "bbox_center": ("ORIGIN_GEOMETRY", "BOUNDS"),
        "mass":        ("ORIGIN_CENTER_OF_MASS", "MEDIAN"),
        "cursor":      ("ORIGIN_CURSOR", "MEDIAN"),
    }
    face_modes = {"bottom", "top", "front", "back", "left", "right"}
    if mode not in direct and mode not in face_modes:
        return {"error": (f"Invalid mode '{mode}'. Use "
                          "geometry|bbox_center|mass|cursor|bottom|top|front|back|left|right")}

    saved_cursor = bpy.context.scene.cursor.location.copy()
    results = []
    try:
        for o in objs:
            activate(o)
            if mode in direct:
                op_type, center = direct[mode]
                bpy.ops.object.origin_set(type=op_type, center=center)
            else:
                xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
                cx = (xmin + xmax) * 0.5
                cy = (ymin + ymax) * 0.5
                cz = (zmin + zmax) * 0.5
                if   mode == "bottom": cz = zmin
                elif mode == "top":    cz = zmax
                elif mode == "front":  cy = ymin
                elif mode == "back":   cy = ymax
                elif mode == "left":   cx = xmin
                elif mode == "right":  cx = xmax
                bpy.context.scene.cursor.location = (cx, cy, cz)
                bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
            results.append({
                "name": o.name,
                "origin": [round(o.location.x, 5), round(o.location.y, 5), round(o.location.z, 5)],
            })
    finally:
        bpy.context.scene.cursor.location = saved_cursor

    return {"success": True, "mode": mode, "updated": results}


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
    "scale_group":     scale_group,
    "rotate_object":   rotate_object,
    "apply_transform": apply_transform,
    "snap_to":         snap_to,
    "snap_to_grid":    snap_to_grid,
    "set_origin":      set_origin,
}

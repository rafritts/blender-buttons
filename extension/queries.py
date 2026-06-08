"""Relational queries — describe/distance/gap/is_aligned. No coordinate leakage in describe."""

import math

import bpy

from .common import world_bbox, world_center


def describe(params):
    """Describe an object in relational terms — what it rests on, what it's beside,
    and its dimensions. No raw world coordinates in the output."""
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}

    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    w, d, h = xmax - xmin, ymax - ymin, zmax - zmin

    relations = []
    if abs(zmin) < 1e-3:
        relations.append("standing on floor")

    for o in bpy.context.scene.objects:
        if o == obj or o.type != 'MESH':
            continue
        o_xmin, o_ymin, o_zmin, o_xmax, o_ymax, o_zmax = world_bbox(o)
        xy_overlap = (xmin < o_xmax and xmax > o_xmin and ymin < o_ymax and ymax > o_ymin)
        if xy_overlap and abs(zmin - o_zmax) < 1e-3:
            relations.append(f"resting on '{o.name}'")
        elif xy_overlap and abs(zmax - o_zmin) < 1e-3:
            relations.append(f"directly under '{o.name}'")
        z_overlap = (zmin < o_zmax and zmax > o_zmin)
        y_overlap = (ymin < o_ymax and ymax > o_ymin)
        x_overlap = (xmin < o_xmax and xmax > o_xmin)
        if z_overlap and y_overlap:
            if abs(xmax - o_xmin) < 1e-3:
                relations.append(f"flush left of '{o.name}'")
            elif abs(xmin - o_xmax) < 1e-3:
                relations.append(f"flush right of '{o.name}'")
        if z_overlap and x_overlap:
            if abs(ymax - o_ymin) < 1e-3:
                relations.append(f"flush in front of '{o.name}'")
            elif abs(ymin - o_ymax) < 1e-3:
                relations.append(f"flush behind '{o.name}'")

    if not relations:
        relations.append(f"freestanding (origin {round(zmin, 3)}m above floor)")

    dim_str = f"size {round(w, 3)} × {round(d, 3)} × {round(h, 3)} m (W×D×H)"
    sentence = f"{name}: {'; '.join(relations)}; {dim_str}"

    return {
        "success": True,
        "name": name,
        "description": sentence,
        "relations": relations,
        "dimensions": {"width": round(w, 4), "depth": round(d, 4), "height": round(h, 4)},
    }


def distance_between(params):
    """Centre-to-centre distance between two objects. Optionally restricted to one axis."""
    a_name = params.get("a")
    b_name = params.get("b")
    axis = params.get("axis", "ANY").upper()
    a = bpy.data.objects.get(a_name) if a_name else None
    b = bpy.data.objects.get(b_name) if b_name else None
    if a is None or b is None:
        return {"error": f"Both 'a' and 'b' must be existing object names (a={a_name}, b={b_name})"}

    ca = world_center(a)
    cb = world_center(b)
    dx, dy, dz = cb[0] - ca[0], cb[1] - ca[1], cb[2] - ca[2]

    if axis == "X":
        dist = abs(dx)
    elif axis == "Y":
        dist = abs(dy)
    elif axis == "Z":
        dist = abs(dz)
    else:
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

    return {"success": True, "a": a_name, "b": b_name, "axis": axis, "distance": round(dist, 5)}


def gap_between(params):
    """Smallest empty distance between two objects' bounding boxes on each axis.
    Negative gap = overlap. Useful for checking 'are these touching?' or 'how far apart?'"""
    a_name = params.get("a")
    b_name = params.get("b")
    a = bpy.data.objects.get(a_name) if a_name else None
    b = bpy.data.objects.get(b_name) if b_name else None
    if a is None or b is None:
        return {"error": "Both 'a' and 'b' must be existing object names"}

    ax = world_bbox(a)
    bx = world_bbox(b)
    gx = max(bx[0] - ax[3], ax[0] - bx[3])
    gy = max(bx[1] - ax[4], ax[1] - bx[4])
    gz = max(bx[2] - ax[5], ax[2] - bx[5])

    touching_axes = [n for n, g in zip("XYZ", (gx, gy, gz)) if abs(g) < 1e-4]
    return {"success": True, "a": a_name, "b": b_name,
            "gap_x": round(gx, 5), "gap_y": round(gy, 5), "gap_z": round(gz, 5),
            "touching_on_axes": touching_axes}


def is_aligned(params):
    """Check if two objects share an aligned face or center on the given side.
    side: TOP|BOTTOM|LEFT|RIGHT|FRONT|BACK|CENTER_X|CENTER_Y|CENTER_Z"""
    a_name = params.get("a")
    b_name = params.get("b")
    side = params.get("side", "TOP").upper()
    tolerance = params.get("tolerance", 1e-3)
    a = bpy.data.objects.get(a_name) if a_name else None
    b = bpy.data.objects.get(b_name) if b_name else None
    if a is None or b is None:
        return {"error": "Both 'a' and 'b' must be existing object names"}

    a_xmin, a_ymin, a_zmin, a_xmax, a_ymax, a_zmax = world_bbox(a)
    b_xmin, b_ymin, b_zmin, b_xmax, b_ymax, b_zmax = world_bbox(b)

    sides = {
        "TOP":      (a_zmax, b_zmax),
        "BOTTOM":   (a_zmin, b_zmin),
        "LEFT":     (a_xmin, b_xmin),
        "RIGHT":    (a_xmax, b_xmax),
        "FRONT":    (a_ymin, b_ymin),
        "BACK":     (a_ymax, b_ymax),
        "CENTER_X": ((a_xmin + a_xmax) / 2, (b_xmin + b_xmax) / 2),
        "CENTER_Y": ((a_ymin + a_ymax) / 2, (b_ymin + b_ymax) / 2),
        "CENTER_Z": ((a_zmin + a_zmax) / 2, (b_zmin + b_zmax) / 2),
    }
    if side not in sides:
        return {"error": f"Invalid side '{side}'. Use {list(sides.keys())}"}
    va, vb = sides[side]
    return {"success": True, "a": a_name, "b": b_name, "side": side,
            "aligned": abs(va - vb) < tolerance, "difference": round(va - vb, 5)}


TOOLS = {
    "describe":         describe,
    "distance_between": distance_between,
    "gap_between":      gap_between,
    "is_aligned":       is_aligned,
}

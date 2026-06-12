"""Dimensional primitives — add_box, add_plane, add_cylinder, add_sphere, add_cone.

These are the primary way to create geometry: callers give target dimensions
and an optional placement spec, never raw coordinates.
"""

import math

import bpy
import mathutils

from .common import activate, world_bbox
from .placement import resolve_placement


def _rotated_dims(dims, rotation_rad):
    """World-space bbox extents of a `dims`-sized box after `rotation_rad`.

    Primitives are created centered on their origin, so rotation is about the
    center — the rotated bbox stays centered and only its extents change. Placement
    must resolve against THESE extents, not the unrotated ones, or a rotated
    primitive lands wrong (gaps.md E2: a rot_y=90 cylinder floated above its rim)."""
    if not any(rotation_rad):
        return dims
    mat = mathutils.Euler(rotation_rad, 'XYZ').to_matrix()
    hx, hy, hz = dims[0] / 2, dims[1] / 2, dims[2] / 2
    xs, ys, zs = [], [], []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                v = mat @ mathutils.Vector((sx * hx, sy * hy, sz * hz))
                xs.append(v.x); ys.append(v.y); zs.append(v.z)
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def _build_primitive(name, ptype, target_dims, on, rotation_deg, extra=None):
    """Shared body for dimensional primitives. Creates the mesh at origin with
    canonical size, resizes to target_dims, applies scale (so obj.scale = [1,1,1]
    and modifiers see uniform scale), resolves placement, moves, and rotates.

    target_dims: (w, d, h) world-space bounding-box dims after resize.
    on: placement spec (None for origin).
    extra: dict of primitive-specific params (vertices, segments, cap_fill, etc.).
    """
    if not name:
        return {"error": "'name' is required — give the object a meaningful name"}
    if bpy.data.objects.get(name) is not None:
        return {"error": f"Object '{name}' already exists — choose a different name or delete the old one first"}

    extra = extra or {}
    rotation_rad = tuple(math.radians(a) for a in (rotation_deg or [0, 0, 0]))

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')

    if ptype == "BOX":
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    elif ptype == "PLANE":
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, 0, 0))
    elif ptype == "CYLINDER":
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=extra.get("vertices", 32),
            radius=0.5, depth=1.0,
            end_fill_type=extra.get("cap_fill", "NGON").upper(),
            location=(0, 0, 0),
        )
    elif ptype == "SPHERE":
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=extra.get("segments", 32),
            ring_count=extra.get("rings", 16),
            radius=0.5,
            location=(0, 0, 0),
        )
    elif ptype == "CONE":
        # Cone has two radii. We pass both as half-fractions of the wider dim
        # and rely on the resize step to bring it to spec.
        r1 = extra.get("radius1_norm", 0.5)
        r2 = extra.get("radius2_norm", 0.0)
        bpy.ops.mesh.primitive_cone_add(
            vertices=extra.get("vertices", 32),
            radius1=r1, radius2=r2, depth=1.0,
            end_fill_type=extra.get("cap_fill", "NGON").upper(),
            location=(0, 0, 0),
        )
    elif ptype == "ICOSPHERE":
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=extra.get("subdivisions", 2),
            radius=0.5,
            location=(0, 0, 0),
        )
    elif ptype == "CIRCLE":
        bpy.ops.mesh.primitive_circle_add(
            vertices=extra.get("vertices", 32),
            radius=0.5,
            fill_type=extra.get("fill_type", "NOTHING").upper(),
            location=(0, 0, 0),
        )
    elif ptype == "TORUS":
        # Torus has two radii whose ratio determines aspect; we can't reach an
        # arbitrary (W, D, H) by scaling a unit canonical without distorting
        # the cross-section. Create it at the actual radii and skip resize.
        bpy.ops.mesh.primitive_torus_add(
            major_radius=extra["major_radius"],
            minor_radius=extra["minor_radius"],
            major_segments=extra.get("major_segments", 48),
            minor_segments=extra.get("minor_segments", 12),
            location=(0, 0, 0),
        )
    else:
        return {"error": f"Unknown primitive: {ptype}"}

    obj = bpy.context.active_object
    obj.name = name
    if obj.data:
        obj.data.name = name

    w, d, h = target_dims
    if ptype == "TORUS":
        # Already at target dims via the actual major/minor radii; resize would distort.
        pass
    elif ptype in ("PLANE", "CIRCLE"):
        obj.scale = (max(w, 1e-6), max(d, 1e-6), 1.0)
    else:
        obj.scale = (max(w, 1e-6), max(d, 1e-6), max(h, 1e-6))
    bpy.context.view_layer.update()

    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    try:
        # Resolve placement against the POST-rotation extents so rotated
        # primitives rest/sit flush where the spec says (gaps.md E2).
        cx, cy, cz = resolve_placement(on, _rotated_dims(target_dims, rotation_rad))
    except ValueError as e:
        bpy.data.objects.remove(obj, do_unlink=True)
        return {"error": str(e)}
    obj.location = (cx, cy, cz)
    obj.rotation_euler = rotation_rad
    bpy.context.view_layer.update()

    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    return {
        "success": True,
        "object_name": obj.name,
        "dimensions": [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)],
        "world_bounds": {
            "x": [round(xmin, 4), round(xmax, 4)],
            "y": [round(ymin, 4), round(ymax, 4)],
            "z": [round(zmin, 4), round(zmax, 4)],
        },
    }


def add_box(params):
    return _build_primitive(
        name=params.get("name"),
        ptype="BOX",
        target_dims=(params.get("width", 1.0), params.get("depth", 1.0), params.get("height", 1.0)),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
    )


def add_plane(params):
    return _build_primitive(
        name=params.get("name"),
        ptype="PLANE",
        target_dims=(params.get("width", 1.0), params.get("depth", 1.0), 0.0),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
    )


def add_cylinder(params):
    radius = params.get("radius", 0.5)
    return _build_primitive(
        name=params.get("name"),
        ptype="CYLINDER",
        target_dims=(radius * 2, radius * 2, params.get("height", 1.0)),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
        extra={"vertices": params.get("segments") or params.get("vertices", 32),
               "cap_fill": params.get("cap_fill", "NGON")},
    )


def add_sphere(params):
    radius = params.get("radius", 0.5)
    return _build_primitive(
        name=params.get("name"),
        ptype="SPHERE",
        target_dims=(radius * 2, radius * 2, radius * 2),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
        extra={"segments": params.get("segments", 32), "rings": params.get("rings", 16)},
    )


def add_cone(params):
    r_bottom = params.get("radius_bottom", 0.5)
    r_top = params.get("radius_top", 0.0)
    height = params.get("height", 1.0)
    r_max = max(r_bottom, r_top, 1e-6)
    return _build_primitive(
        name=params.get("name"),
        ptype="CONE",
        target_dims=(r_max * 2, r_max * 2, height),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
        extra={
            "vertices": params.get("segments") or params.get("vertices", 32),
            "cap_fill": params.get("cap_fill", "NGON"),
            "radius1_norm": (r_bottom / r_max) * 0.5,
            "radius2_norm": (r_top / r_max) * 0.5,
        },
    )


def add_torus(params):
    major = params.get("major_radius", 0.5)
    minor = params.get("minor_radius", 0.1)
    return _build_primitive(
        name=params.get("name"),
        ptype="TORUS",
        target_dims=((major + minor) * 2, (major + minor) * 2, minor * 2),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
        extra={
            "major_radius":   major,
            "minor_radius":   minor,
            "major_segments": params.get("major_segments", 48),
            "minor_segments": params.get("minor_segments", 12),
        },
    )


def add_icosphere(params):
    radius = params.get("radius", 0.5)
    return _build_primitive(
        name=params.get("name"),
        ptype="ICOSPHERE",
        target_dims=(radius * 2, radius * 2, radius * 2),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
        extra={"subdivisions": params.get("subdivisions", 2)},
    )


def add_circle(params):
    radius = params.get("radius", 0.5)
    return _build_primitive(
        name=params.get("name"),
        ptype="CIRCLE",
        target_dims=(radius * 2, radius * 2, 0.0),
        on=params.get("on"),
        rotation_deg=params.get("rotation_deg", [0, 0, 0]),
        extra={
            "vertices":  params.get("segments") or params.get("vertices", 32),
            "fill_type": params.get("fill_type", "NOTHING"),
        },
    )


_BULK_DISPATCH = {
    "box":       lambda p: add_box(p),
    "plane":     lambda p: add_plane(p),
    "cylinder":  lambda p: add_cylinder(p),
    "sphere":    lambda p: add_sphere(p),
    "cone":      lambda p: add_cone(p),
    "torus":     lambda p: add_torus(p),
    "icosphere": lambda p: add_icosphere(p),
    "circle":    lambda p: add_circle(p),
}


def add_primitives(params):
    """Bulk-add primitives in one call. Each item is a dict with at minimum
    {"type": "box|plane|cylinder|sphere|cone|torus|icosphere|circle", "name": "..."}
    plus whatever the matching single-primitive tool accepts (width/depth/height,
    radius, on=..., rot_x/y/z, etc.).

    Stops on the first failure and returns what succeeded.
    """
    specs = params.get("specs") or []
    if not isinstance(specs, list) or not specs:
        return {"error": "'specs' must be a non-empty list of primitive dicts"}
    created = []
    for i, s in enumerate(specs):
        if not isinstance(s, dict):
            return {"error": f"specs[{i}] is not a dict", "created": created}
        ptype = (s.get("type") or "").lower()
        if ptype not in _BULK_DISPATCH:
            return {"error": f"specs[{i}].type '{ptype}' invalid. "
                              f"Use one of {sorted(_BULK_DISPATCH)}", "created": created}
        sub = {k: v for k, v in s.items() if k not in ("type", "rot_x", "rot_y", "rot_z")}
        # Single-primitive MCP tools expose rot_x/y/z and map them to rotation_deg;
        # bulk specs use the same names, so do the same mapping here.
        if any(k in s for k in ("rot_x", "rot_y", "rot_z")) and "rotation_deg" not in sub:
            sub["rotation_deg"] = [s.get("rot_x", 0), s.get("rot_y", 0), s.get("rot_z", 0)]
        result = _BULK_DISPATCH[ptype](sub)
        if not result.get("success"):
            return {"error": f"specs[{i}] ({ptype}): {result.get('error')}",
                    "created": created}
        created.append({"type": ptype, "name": result["object_name"],
                        "dimensions": result.get("dimensions")})
    return {"success": True, "created": created, "count": len(created)}


def add_floor(params):
    """Add a large ground plane at z=0 for character-modeling reference and shadow catching.

    name: object name (default 'floor').
    size: side length in meters (default 10).
    """
    name = params.get("name") or "floor"
    size = float(params.get("size", 10.0))
    return _build_primitive(
        name=name,
        ptype="PLANE",
        target_dims=(size, size, 0.0),
        on={"z": 0.0},
        rotation_deg=[0, 0, 0],
    )


TOOLS = {
    "add_box":        add_box,
    "add_primitives": add_primitives,
    "add_floor":      add_floor,
    "add_plane":     add_plane,
    "add_cylinder":  add_cylinder,
    "add_sphere":    add_sphere,
    "add_cone":      add_cone,
    "add_torus":     add_torus,
    "add_icosphere": add_icosphere,
    "add_circle":    add_circle,
}

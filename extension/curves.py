"""Curve-based geometry: spline_tube.

Design notes (why interpolating, why not Bezier handles): an LLM works in
checkable claims — "the curve passes through these named places". Catmull-Rom
interpolates THROUGH every control point, so each point is verifiable.
Bezier tangent handles are invisible state that only surfaces at render time.
The curve is sampled into a dense poly spline, swept with a round bevel and
per-point radius, and converted to a plain mesh in one call — no curve-object
lifecycle to manage afterward.
"""

import json

import bpy

from .common import world_bbox, world_center


def _catmull_rom(points, resolution):
    """Sample a uniform Catmull-Rom spline through `points` (list of [x,y,z]),
    `resolution` samples per segment, ends clamped by endpoint duplication.
    Returns (samples, ts) where ts[i] is the global parameter 0..(n_segments)
    used for radius interpolation. Pure math — no bpy."""
    n = len(points)
    if n == 2:
        # Straight segment — still sample so per-point radius tapers smoothly.
        samples, ts = [], []
        for s in range(resolution + 1):
            t = s / resolution
            samples.append([points[0][i] + (points[1][i] - points[0][i]) * t for i in range(3)])
            ts.append(t)
        return samples, ts

    samples, ts = [], []
    for seg in range(n - 1):
        p0 = points[max(seg - 1, 0)]
        p1 = points[seg]
        p2 = points[seg + 1]
        p3 = points[min(seg + 2, n - 1)]
        last = (seg == n - 2)
        steps = resolution + 1 if last else resolution
        for s in range(steps):
            t = s / resolution
            t2, t3 = t * t, t * t * t
            pt = [
                0.5 * ((2 * p1[i])
                       + (-p0[i] + p2[i]) * t
                       + (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * t2
                       + (-p0[i] + 3 * p1[i] - 3 * p2[i] + p3[i]) * t3)
                for i in range(3)
            ]
            samples.append(pt)
            ts.append(seg + t)
    return samples, ts


def _radius_at(radii, t):
    """Linear interpolation of per-control-point radii at global parameter t
    (t = segment index + local 0..1). Pure math — no bpy."""
    seg = min(int(t), len(radii) - 2)
    local = t - seg
    return radii[seg] + (radii[seg + 1] - radii[seg]) * local


def _polyline_length(samples):
    total = 0.0
    for a, b in zip(samples, samples[1:]):
        total += sum((b[i] - a[i]) ** 2 for i in range(3)) ** 0.5
    return total


def _resolve_point(entry, idx):
    """Resolve one control point: [x, y, z] literal, or
    {"near": "object", "offset": [dx, dy, dz]} anchored to an object's center.
    Anchors resolve ONCE at creation — no live constraint."""
    if isinstance(entry, (list, tuple)) and len(entry) == 3:
        return [float(v) for v in entry], None
    if isinstance(entry, dict):
        unknown = set(entry) - {"near", "offset"}
        if unknown:
            return None, (f"points[{idx}]: unknown key(s) {sorted(unknown)} — "
                          "use [x,y,z] or {\"near\": name, \"offset\": [dx,dy,dz]}")
        anchor_name = entry.get("near")
        if not anchor_name:
            return None, f"points[{idx}]: anchored point requires 'near' (object name)"
        anchor = bpy.data.objects.get(anchor_name)
        if anchor is None:
            return None, f"points[{idx}]: anchor object '{anchor_name}' not found"
        cx, cy, cz = world_center(anchor)
        off = entry.get("offset", [0, 0, 0])
        if not (isinstance(off, (list, tuple)) and len(off) == 3):
            return None, f"points[{idx}]: 'offset' must be [dx, dy, dz]"
        return [cx + float(off[0]), cy + float(off[1]), cz + float(off[2])], None
    return None, (f"points[{idx}] must be [x,y,z] or "
                  "{\"near\": name, \"offset\": [dx,dy,dz]}")


def spline_tube(params):
    """Create a tube mesh swept along an interpolating spline through 2–32 points.

    name:       required, unique.
    points:     list of control points the curve passes THROUGH. Each is
                [x, y, z] world coords, or {"near": "obj", "offset": [dx,dy,dz]}
                relative to an existing object's bbox center.
    radius:     tube radius in meters — a single float, or a list (one per
                control point) for taper. Default 0.02.
    resolution: curve samples per segment (default 8; higher = smoother bends).
    sides:      cross-section resolution (default 4 → 16-sided tube).

    Result is a plain MESH object (smooth-shaded, capped ends). The control
    points are stored on the object and reported by describe().
    """
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    if bpy.data.objects.get(name) is not None:
        return {"error": f"Object '{name}' already exists — choose a different name"}

    raw_points = params.get("points")
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        return {"error": "'points' must be a list of at least 2 control points"}
    if len(raw_points) > 32:
        return {"error": f"'points' supports at most 32 control points (got {len(raw_points)})"}

    points = []
    for i, entry in enumerate(raw_points):
        pt, err = _resolve_point(entry, i)
        if err:
            return {"error": err}
        points.append(pt)

    radius = params.get("radius", 0.02)
    if isinstance(radius, (int, float)):
        radii = [float(radius)] * len(points)
    elif isinstance(radius, (list, tuple)):
        if len(radius) != len(points):
            return {"error": (f"'radius' list must match points count "
                              f"({len(radius)} radii vs {len(points)} points)")}
        radii = [float(r) for r in radius]
    else:
        return {"error": "'radius' must be a number or a list of numbers"}
    if any(r <= 0 for r in radii):
        return {"error": "all radii must be > 0"}

    resolution = max(2, min(int(params.get("resolution", 8)), 64))
    sides = max(2, min(int(params.get("sides", 4)), 16))

    samples, ts = _catmull_rom(points, resolution)

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    cu = bpy.data.curves.new(name, type='CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = 1.0          # actual radius comes from per-point radius
    cu.bevel_resolution = sides
    cu.use_fill_caps = True
    spline = cu.splines.new('POLY')
    spline.points.add(len(samples) - 1)
    for pt, t, cpt in zip(samples, ts, spline.points):
        cpt.co = (pt[0], pt[1], pt[2], 1.0)
        cpt.radius = _radius_at(radii, t)

    obj = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target='MESH')
    obj = bpy.context.active_object
    bpy.ops.object.shade_smooth()

    rounded_pts = [[round(v, 4) for v in p] for p in points]
    obj["bb_spline_points"] = json.dumps(rounded_pts)
    obj["bb_spline_radii"] = json.dumps([round(r, 4) for r in radii])

    bpy.context.view_layer.update()
    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    return {
        "success": True,
        "object_name": obj.name,
        "points": rounded_pts,
        "radii": [round(r, 4) for r in radii],
        "length": round(_polyline_length(samples), 4),
        "dimensions": [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)],
        "world_bounds": {
            "x": [round(xmin, 4), round(xmax, 4)],
            "y": [round(ymin, 4), round(ymax, 4)],
            "z": [round(zmin, 4), round(zmax, 4)],
        },
    }


TOOLS = {
    "spline_tube": spline_tube,
}

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


def _resolve_anchor(anchor, idx):
    """Validate a point's `anchor` spec and resolve its current world position.

    Forms: {"object": "name"} | {"bone": "armature_name/bone_name"} |
           {"bone": "bone_name", "armature": "armature_name"}.
    Returns ({"object": bpy_obj, "bone": name|None, "world": Vector}, None) or
    (None, error). For a bone, world position is its head in the CURRENT pose —
    callers must anchor in the rig's rest pose (see add_curve)."""
    if not isinstance(anchor, dict):
        return None, f"points[{idx}]: 'anchor' must be a dict"
    if "object" in anchor:
        name = anchor["object"]
        obj = bpy.data.objects.get(name)
        if obj is None:
            return None, f"points[{idx}]: anchor object '{name}' not found"
        return {"object": obj, "bone": None,
                "world": obj.matrix_world.translation.copy()}, None
    if "bone" in anchor:
        spec = anchor["bone"]
        if "/" in spec:
            arm_name, bone_name = spec.split("/", 1)
        else:
            arm_name, bone_name = anchor.get("armature"), spec
        if not arm_name:
            return None, (f"points[{idx}]: bone anchor needs \"armature/bone\" "
                          "or a separate 'armature' key")
        arm = bpy.data.objects.get(arm_name)
        if arm is None or arm.type != 'ARMATURE':
            return None, f"points[{idx}]: anchor armature '{arm_name}' not found"
        pbone = arm.pose.bones.get(bone_name)
        if pbone is None:
            return None, (f"points[{idx}]: bone '{bone_name}' not on '{arm_name}' "
                          f"(have {[b.name for b in arm.pose.bones]})")
        world = (arm.matrix_world @ pbone.matrix).translation.copy()
        return {"object": arm, "bone": bone_name, "world": world}, None
    return None, f"points[{idx}]: 'anchor' needs 'object' or 'bone'"


def _resolve_curve_point(entry, idx):
    """Resolve one add_curve control point to (pos[x,y,z], anchor|None, error).

    Position: [x,y,z] | {"at":[x,y,z]} | {"near":obj,"offset":[..]} | (default
    to the anchor target's location if only an anchor is given). Anchor: optional
    {"anchor": {...}} key making the point a live Hook target."""
    if isinstance(entry, (list, tuple)) and len(entry) == 3:
        return [float(v) for v in entry], None, None
    if not isinstance(entry, dict):
        return None, None, f"points[{idx}] must be [x,y,z] or a dict"

    anchor = None
    if entry.get("anchor") is not None:
        anchor, err = _resolve_anchor(entry["anchor"], idx)
        if err:
            return None, None, err

    if "at" in entry:
        at = entry["at"]
        if not (isinstance(at, (list, tuple)) and len(at) == 3):
            return None, None, f"points[{idx}]: 'at' must be [x,y,z]"
        return [float(v) for v in at], anchor, None
    if "near" in entry:
        pos, err = _resolve_point({"near": entry["near"],
                                   "offset": entry.get("offset", [0, 0, 0])}, idx)
        return (None, None, err) if err else (pos, anchor, None)
    if anchor is not None:
        return list(anchor["world"]), anchor, None
    return None, None, (f"points[{idx}] needs a position ([x,y,z], 'at', or "
                        "'near') or an 'anchor' to derive it from")


def spline_tube(params):
    """Create a tube mesh swept along an interpolating spline through 2–32 points.

    name:       required, unique.
    points:     list of control points the curve passes THROUGH. Each is
                [x, y, z] world coords, or {"near": "obj", "offset": [dx,dy,dz]}
                relative to an existing object's bbox center.
    between:    [A, B] — alternative to `points`: connect two named objects with a
                straight tube, endpoints picked at the NEAREST SURFACE points
                between them (BVH). The generic strut/cable/wire — no offset math.
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

    # `between`: connect two named anchors with a straight tube whose endpoints are
    # the NEAREST SURFACE points between them (the generic "strut/cable between A and
    # B" — struts, wiring, linkages, a cradle's suspension string). No offset math:
    # the BVH finds where the two surfaces face each other.
    between = params.get("between")
    raw_points = params.get("points")
    if between is not None:
        if raw_points:
            return {"error": "pass either 'points' or 'between' — not both"}
        if not (isinstance(between, (list, tuple)) and len(between) == 2):
            return {"error": "'between' must be [A, B] — two object names to connect"}
        from .introspect import _prepare
        from .queries import _nearest_surface_pair
        preps = []
        for nm in between:
            o = bpy.data.objects.get(nm)
            if o is None:
                return {"error": f"'between' anchor '{nm}' not found"}
            p = _prepare(o)
            if p is None:
                return {"error": f"'between' anchor '{nm}' has no geometry to connect"}
            preps.append(p)
        d, pt_a, pt_b = _nearest_surface_pair(preps[0], preps[1])
        if pt_a is None:
            return {"error": f"no surface path found between '{between[0]}' and '{between[1]}'"}
        raw_points = [[pt_a[0], pt_a[1], pt_a[2]], [pt_b[0], pt_b[1], pt_b[2]]]

    if not isinstance(raw_points, list) or len(raw_points) < 2:
        return {"error": "'points' must be a list of at least 2 control points (or use 'between')"}
    # G20: the old cap of 32 blocked legitimate hand-authored swept paths (a 9-turn
    # coil needs ~73). The per-point resolve is cheap; 256 is a generous ceiling that
    # still guards against a runaway payload. For a CONTINUOUS helix/coil use
    # `add type=helix`, which generates its own dense samples and ignores this cap.
    if len(raw_points) > 256:
        return {"error": f"'points' supports at most 256 control points (got "
                         f"{len(raw_points)}); for a continuous coil use add type=helix"}

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


def add_curve(params):
    """Create a LIVE curve datablock object (not a baked mesh).

    Unlike spline_tube (which samples a spline into a fixed mesh), this leaves a
    real editable curve object in the scene — the thing you want as a camera dolly
    path (Follow Path constraint target), a bevel/taper profile, or a scatter
    distribution control. Editable after the fact in Blender's curve tools.

    name:      object name (required, unique).
    points:    2+ control points. Each is [x, y, z], {"near": obj, "offset":[..]},
               or a dict that also carries a live ANCHOR:
                 {"at": [x,y,z], "anchor": {"object": "winch_drum"}}
                 {"anchor": {"bone": "catapult_rig/arm_swing"}}   # pos = bone head
               An anchored point gets a Hook modifier, so the curve follows that
               object/bone when it moves or poses — a rope/cable/hose that stretches
               between a drum and a swinging arm. Anchor ANY point (both ends, or a
               sag midpoint); unanchored points stay put in world space and the
               curve interpolates through them. IMPORTANT: anchor in the rig's REST
               pose — the hook captures the point in the bone's rest space, so
               assigning while posed bakes in an offset.
    type:      BEZIER (default, smooth auto-handles through each point) |
               NURBS (smooth, approximating) | POLY (straight segments).
    cyclic:    close the curve into a loop (default False).
    resolution: curve render/eval subdivisions per segment (default 12).
    bevel_depth: optional round-bevel radius (meters). >0 gives the curve
               thickness so it renders as a tube; 0 (default) is a pure path.

    Delivery note: an anchored curve is a LIVE rig accessory. For a game-ready
    mesh, pose the rig, then bake it with convert_to_mesh(this curve) — one call
    evaluates the hooks AND the bevel into actual texturable geometry. (Plain
    apply_modifiers leaves it a CURVE, which still can't take a textured material.)
    """
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    if bpy.data.objects.get(name) is not None:
        return {"error": f"Object '{name}' already exists"}

    raw = params.get("points") or []
    if len(raw) < 2:
        return {"error": "'points' needs at least 2 control points"}
    pts = []
    anchors = []  # parallel to pts: anchor dict or None per control point
    for i, entry in enumerate(raw):
        p, anchor, err = _resolve_curve_point(entry, i)
        if err:
            return {"error": err}
        pts.append(p)
        anchors.append(anchor)

    ctype = (params.get("type") or "BEZIER").upper()
    if ctype not in ("BEZIER", "NURBS", "POLY"):
        return {"error": "type must be BEZIER, NURBS, or POLY"}
    cyclic = bool(params.get("cyclic", False))
    resolution = int(params.get("resolution", 12))
    bevel_depth = float(params.get("bevel_depth", 0.0))

    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = resolution
    if bevel_depth > 0.0:
        curve.bevel_depth = bevel_depth

    spline = curve.splines.new(ctype)
    if ctype == 'BEZIER':
        spline.bezier_points.add(len(pts) - 1)
        for bp, p in zip(spline.bezier_points, pts):
            bp.co = p
            bp.handle_left_type = 'AUTO'
            bp.handle_right_type = 'AUTO'
    else:
        spline.points.add(len(pts) - 1)
        for sp, p in zip(spline.points, pts):
            sp.co = (p[0], p[1], p[2], 1.0)
        if ctype == 'NURBS':
            spline.order_u = min(4, len(pts))
            spline.use_endpoint_u = True
    spline.use_cyclic_u = cyclic

    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()

    # Live anchors → one Hook modifier per anchored control point. The hook
    # formula deforms hooked points by  obj_world⁻¹ · target_world · matrix_inverse;
    # add_curve always creates obj at the identity transform, so setting
    # matrix_inverse = target_world⁻¹ makes the rest pose a no-op and the point
    # follows the target's delta thereafter. For a BEZIER point the flat hook
    # index space is (handle_left, co, handle_right) per point — hook all three
    # so the whole point (and its handles) travel together.
    anchored = []
    for i, anchor in enumerate(anchors):
        if anchor is None:
            continue
        target = anchor["object"]
        bone = anchor["bone"]
        mod = obj.modifiers.new(name=f"Hook_{i}_{target.name}", type='HOOK')
        mod.object = target
        if bone:
            mod.subtarget = bone
        mod.falloff_type = 'NONE'
        idxs = [3 * i, 3 * i + 1, 3 * i + 2] if ctype == 'BEZIER' else [i]
        mod.vertex_indices_set(idxs)
        if bone:
            target_mat = target.matrix_world @ target.pose.bones[bone].matrix
        else:
            target_mat = target.matrix_world
        mod.matrix_inverse = target_mat.inverted()
        anchored.append({"point": i, "target": target.name, "bone": bone})

    bpy.context.view_layer.update()
    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    return {
        "success": True,
        "object_name": obj.name,
        "type": ctype,
        "control_points": len(pts),
        "cyclic": cyclic,
        "bevel_depth": bevel_depth,
        "anchored": anchored,
        "dimensions": [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)],
    }


_AXES = {"X": 0, "Y": 1, "Z": 2}


def helix_coil(params):
    """G20 — a continuous parametric helix / coil swept into a tube mesh. Subsumes
    wire wraps, springs, screw threads, coiled cable/rope, twist-fluting — the thing
    11 stacked torus rings only faked. Generates its OWN dense sample polyline, so it
    sidesteps the control-point cap entirely instead of fighting it.

    name:        required, unique.
    turns:       number of full revolutions (float ok, e.g. 9 or 4.5).
    height:      total rise along the axis in meters (0 = a flat spiral).
    radius:      helix radius — distance of the coil centreline from the axis.
    tube_radius: cross-section radius of the swept wire (default 0.02).
    taper:       end/start tube_radius ratio (1.0 = uniform; 0.5 = wire halves along
                 its length; >1 = thickens). Tapers the wire thickness, not the coil.
    handedness:  'right' (default, CCW rising) | 'left'.
    axis:        coil axis X|Y|Z (default Z).
    center:      [x,y,z] base centre of the coil (default origin = world cursor 0).
    segments_per_turn: samples per revolution (default 24; higher = rounder).
    sides:       tube cross-section resolution (default 4 → 16-sided)."""
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    if bpy.data.objects.get(name) is not None:
        return {"error": f"Object '{name}' already exists — choose a different name"}

    import math
    turns = float(params.get("turns", 3))
    if turns <= 0:
        return {"error": "'turns' must be > 0"}
    height = float(params.get("height", 0.2))
    radius = float(params.get("radius", 0.05))
    if radius <= 0:
        return {"error": "'radius' must be > 0"}
    tube_radius = float(params.get("tube_radius", 0.02))
    if tube_radius <= 0:
        return {"error": "'tube_radius' must be > 0"}
    taper = float(params.get("taper", 1.0))
    if taper <= 0:
        return {"error": "'taper' must be > 0 (end/start thickness ratio)"}
    handed = (params.get("handedness") or "right").lower()
    sign = -1.0 if handed.startswith("l") else 1.0
    axis = (params.get("axis") or "Z").upper()
    if axis not in _AXES:
        return {"error": "'axis' must be X, Y, or Z"}
    ai = _AXES[axis]
    ui, vi = [i for i in range(3) if i != ai]   # the two in-plane axes
    center = params.get("center") or [0.0, 0.0, 0.0]
    if not (isinstance(center, (list, tuple)) and len(center) == 3):
        return {"error": "'center' must be [x, y, z]"}
    spt = max(3, min(int(params.get("segments_per_turn", 24)), 128))
    sides = max(2, min(int(params.get("sides", 4)), 16))

    n = max(2, int(round(turns * spt)))
    samples, radii = [], []
    for i in range(n + 1):
        t = i / n
        ang = sign * 2.0 * math.pi * turns * t
        p = [0.0, 0.0, 0.0]
        p[ui] = center[ui] + radius * math.cos(ang)
        p[vi] = center[vi] + radius * math.sin(ang)
        p[ai] = center[ai] + height * t
        samples.append(p)
        radii.append(tube_radius * (1.0 + (taper - 1.0) * t))

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    cu = bpy.data.curves.new(name, type='CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = 1.0
    cu.bevel_resolution = sides
    cu.use_fill_caps = True
    spline = cu.splines.new('POLY')
    spline.points.add(len(samples) - 1)
    for pt, r, cpt in zip(samples, radii, spline.points):
        cpt.co = (pt[0], pt[1], pt[2], 1.0)
        cpt.radius = r

    obj = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target='MESH')
    obj = bpy.context.active_object
    bpy.ops.object.shade_smooth()

    bpy.context.view_layer.update()
    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    return {
        "success": True,
        "object_name": obj.name,
        "turns": turns, "handedness": "left" if sign < 0 else "right",
        "axis": axis,
        "wire_length": round(_polyline_length(samples), 4),
        "dimensions": [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)],
        "world_bounds": {
            "x": [round(xmin, 4), round(xmax, 4)],
            "y": [round(ymin, 4), round(ymax, 4)],
            "z": [round(zmin, 4), round(zmax, 4)],
        },
    }


def _spline_centreline(spline, resolution):
    """World-LOCAL centreline samples of one spline as a list of mathutils.Vector
    (object space — caller applies matrix_world). Bezier segments are sampled with
    interpolate_bezier; poly/nurbs fall back to their points. Pure read."""
    from mathutils import Vector
    from mathutils.geometry import interpolate_bezier
    pts = []
    if spline.type == 'BEZIER' and len(spline.bezier_points) >= 2:
        bp = spline.bezier_points
        for k in range(len(bp) - 1):
            a, b = bp[k], bp[k + 1]
            seg = interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co,
                                     max(2, resolution + 1))
            pts.extend(seg[1:] if k > 0 else seg)
    elif len(spline.points) >= 2:
        pts = [p.co.to_3d() for p in spline.points]
    else:
        pts = [Vector(bp.co) for bp in spline.bezier_points]
    return pts


def feel_curve(params):
    """G65 — read a curve's CENTRELINE quality, the read 'is this a clean arc or a
    lump' needs and that nothing emitted before. Reports total length, curvature κ
    along the run, the TIGHTEST bend (min radius + where, as a fraction along),
    total turning angle, the count of inflections (S-bend sign-flips of the bend
    direction), and the endpoint tangent DIRECTIONS (so the agent can check 'does it
    leave the way the opening points'). Read-only, works on a LIVE curve (no bake).
    Generalises extrude_along_curve's bend-radius-vs-profile preflight; pass
    profile_radius= to get a feasibility flag against it."""
    import math
    from mathutils import Vector
    name = (params.get("target") or "").strip()
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"curve '{name}' not found"}
    if obj.type != 'CURVE':
        return {"error": f"'{name}' is a {obj.type.lower()}, not a curve — "
                         f"feel op=curve reads curve centrelines"}
    resolution = max(2, int(params.get("resolution", 24)))
    profile_radius = params.get("profile_radius")
    profile_radius = float(profile_radius) if profile_radius is not None else None
    mw = obj.matrix_world

    splines = []
    for si, spline in enumerate(obj.data.splines):
        local = _spline_centreline(spline, resolution)
        if len(local) < 2:
            continue
        P = [mw @ Vector(p) for p in local]
        # cumulative arclength
        seglens = [(P[i + 1] - P[i]).length for i in range(len(P) - 1)]
        length = sum(seglens)
        if length < 1e-9:
            continue
        cum = [0.0]
        for L in seglens:
            cum.append(cum[-1] + L)

        max_k = 0.0
        at_frac = 0.0
        turning = 0.0
        inflections = 0
        prev_bn = None
        mean_k_num = 0.0
        for i in range(1, len(P) - 1):
            a, b, c = P[i - 1], P[i], P[i + 1]
            ab, bc, ca = (b - a).length, (c - b).length, (a - c).length
            cross = (b - a).cross(c - b)
            # turning angle at b
            d0, d1 = (b - a), (c - b)
            if d0.length > 1e-9 and d1.length > 1e-9:
                cosang = max(-1.0, min(1.0, d0.normalized().dot(d1.normalized())))
                turning += math.degrees(math.acos(cosang))
            denom = ab * bc * ca
            if denom > 1e-12:
                area = cross.length / 2.0
                k = 4.0 * area / denom    # Menger curvature 1/R
                mean_k_num += k * (ab + bc) / 2.0
                if k > max_k:
                    max_k = k
                    at_frac = cum[i] / length
            # inflection: the bend's binormal flips to the other side
            if cross.length > 1e-9:
                bn = cross.normalized()
                if prev_bn is not None and bn.dot(prev_bn) < -0.2:
                    inflections += 1
                prev_bn = bn

        min_radius = (1.0 / max_k) if max_k > 1e-9 else None
        t0 = (P[1] - P[0]).normalized()
        t1 = (P[-1] - P[-2]).normalized()
        sp = {
            "index": si,
            "length_cm": round(length * 100, 2),
            "min_bend_radius_cm": round(min_radius * 100, 2) if min_radius else None,
            "tightest_at": round(at_frac, 2),
            "turning_deg": round(turning, 1),
            "inflections": inflections,
            "shape": ("straight" if turning < 5 else
                      "single arc" if inflections == 0 else
                      f"S-bend ({inflections} inflection(s))"),
            "start": [round(c, 4) for c in P[0]],
            "end": [round(c, 4) for c in P[-1]],
            "start_tangent": [round(c, 4) for c in t0],
            "end_tangent": [round(c, 4) for c in t1],
        }
        if profile_radius is not None and min_radius is not None:
            sp["profile_radius_cm"] = round(profile_radius * 100, 2)
            sp["sweep_feasible"] = min_radius > profile_radius
        splines.append(sp)

    if not splines:
        return {"error": f"'{name}' has no samplable spline (need ≥2 points)"}
    return {"success": True, "curve": name, "splines": splines}


TOOLS = {
    "spline_tube": spline_tube,
    "add_curve":   add_curve,
    "helix_coil":  helix_coil,
    "feel_curve":  feel_curve,
}

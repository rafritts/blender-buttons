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


def _min_bend_radius(pts):
    """Tightest centreline bend radius (m) over a polyline, via Menger curvature — the same
    measure feel op=curve reports. None if effectively straight. Used to preflight a sweep
    for self-intersection (G121): a bend radius below the tube/profile radius folds the wall
    through itself."""
    import math  # noqa: F401
    from mathutils import Vector
    # A near-coincident sample — e.g. a baked tube's center-fan cap-tip ring centroid
    # sitting almost on its neighbour — makes the Menger denominator tiny and spikes the
    # curvature into a bogus sub-mm radius (G171: reported 0.8cm on a clean 5cm-radius
    # bend, firing a false self-intersection warning). Skip any triple whose shortest arm
    # is a small fraction of the median segment, so a degenerate end-sample can't collapse
    # the reported bend radius. Uniform curve samples (feel op=curve) skip nothing.
    seglens = [(Vector(pts[i + 1]) - Vector(pts[i])).length for i in range(len(pts) - 1)]
    med = sorted(seglens)[len(seglens) // 2] if seglens else 0.0
    floor = 0.2 * med
    max_k = 0.0
    for i in range(1, len(pts) - 1):
        a, b, c = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[i + 1])
        ab, bc, ca = (b - a).length, (c - b).length, (a - c).length
        if med > 0 and (ab < floor or bc < floor):
            continue
        cross = (b - a).cross(c - b)
        denom = ab * bc * ca
        if denom > 1e-12 and cross.length > 1e-12:
            k = 4.0 * (cross.length / 2.0) / denom
            if k > max_k:
                max_k = k
    return (1.0 / max_k) if max_k > 1e-9 else None


def _bend_warning(min_radius, profile_radius, what="tube"):
    """G121 — a one-line warning when the tightest bend is smaller than the swept profile, so
    the wall self-intersects there (interior, invisible in render, but a permanent
    self_intersection finding). None when the sweep is feasible."""
    if min_radius is None or profile_radius <= 0 or min_radius >= profile_radius:
        return None
    return (f"{what} self-intersects at the tightest bend: min bend radius "
            f"{min_radius * 100:.2f}cm < profile radius {profile_radius * 100:.2f}cm — the "
            f"wall folds through itself there. Widen the bend (move the point / raise "
            f"resolution) or keep the radius below {min_radius * 100:.2f}cm.")


def _tube_geometry(samples, radii_per_sample, sides):
    """Build clean swept-tube mesh data (verts, faces) directly, instead of beveling a POLY
    curve and converting. G161/G177: the curve-bevel→convert route produced self-intersecting
    end caps (a fill-cap n-gon over a beveled POLY endpoint folds on itself) and zero-area
    rings where Catmull-Rom endpoint clamping left near-coincident samples. Building rings on a
    rotation-minimizing frame + a clean center-vertex cap fan at each end removes BOTH: a
    straight tube is a manifold prism, and the only self-intersections left are real ones (a
    bend tighter than the radius). Pure math — no bpy."""
    import math
    from mathutils import Vector

    # Dedupe consecutive near-coincident samples (the source of the zero-area end rings),
    # carrying the larger radius forward so a taper end isn't dropped.
    pts, rs = [], []
    for p, r in zip(samples, radii_per_sample):
        v = Vector(p)
        if pts and (v - pts[-1]).length < 1e-6:
            rs[-1] = max(rs[-1], r)
            continue
        pts.append(v)
        rs.append(float(r))
    n = len(pts)
    if n < 2:
        return None, None

    # Per-sample unit tangents (central difference interior, one-sided at the ends).
    tang = []
    for i in range(n):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        tang.append(t.normalized() if t.length > 1e-9 else Vector((0.0, 0.0, 1.0)))

    # Rotation-minimizing frame (double-reflection, Wang et al. 2008) — a stable normal that
    # doesn't flip on straight runs (Frenet's failure) and barely twists around bends.
    seed = Vector((1.0, 0.0, 0.0)) if abs(tang[0].x) < 0.9 else Vector((0.0, 1.0, 0.0))
    nrm = (seed - tang[0] * seed.dot(tang[0])).normalized()
    normals = [nrm]
    for i in range(n - 1):
        v1 = pts[i + 1] - pts[i]
        c1 = v1.dot(v1)
        if c1 > 1e-12:
            rL = normals[i] - (2.0 / c1) * v1.dot(normals[i]) * v1
            tL = tang[i] - (2.0 / c1) * v1.dot(tang[i]) * v1
        else:
            rL, tL = normals[i], tang[i]
        v2 = tang[i + 1] - tL
        c2 = v2.dot(v2)
        nN = rL - (2.0 / c2) * v2.dot(rL) * v2 if c2 > 1e-12 else rL
        nN = nN - tang[i + 1] * nN.dot(tang[i + 1])
        normals.append(nN.normalized() if nN.length > 1e-9 else normals[i])

    cross = max(3, 4 * sides)                      # default sides=4 → 16-sided tube
    verts = []
    ring0 = []
    for i in range(n):
        T, N = tang[i], normals[i]
        B = T.cross(N).normalized()
        ring0.append(len(verts))
        for k in range(cross):
            a = 2.0 * math.pi * k / cross
            off = (math.cos(a) * N + math.sin(a) * B) * rs[i]
            verts.append((pts[i].x + off.x, pts[i].y + off.y, pts[i].z + off.z))

    faces = []
    for i in range(n - 1):
        a0, b0 = ring0[i], ring0[i + 1]
        for k in range(cross):
            k2 = (k + 1) % cross
            faces.append((a0 + k, a0 + k2, b0 + k2, b0 + k))

    # Center-vertex cap fans (clean convex disks — no self-intersecting fill n-gon).
    c_start = len(verts)
    verts.append((pts[0].x, pts[0].y, pts[0].z))
    for k in range(cross):
        k2 = (k + 1) % cross
        faces.append((c_start, ring0[0] + k, ring0[0] + k2))
    c_end = len(verts)
    verts.append((pts[-1].x, pts[-1].y, pts[-1].z))
    for k in range(cross):
        k2 = (k + 1) % cross
        faces.append((c_end, ring0[-1] + k2, ring0[-1] + k))
    return verts, faces


def _frame_anchor(name):
    """Resolve a path's start/seed anchor to (origin, (N, U, V)) — a measured orthonormal
    basis with provenance, never divined. A minted handle Empty (feel op=aim/facing/frame)
    carries its measured frame in matrix_world (local Z = the outward normal/aim it was minted
    along); any other object contributes its own world axes about its bbox centre. Returns
    ((origin, (N,U,V)), None) or (None, error)."""
    from mathutils import Vector
    obj = bpy.data.objects.get(name)
    if obj is None:
        return None, f"path anchor '{name}' not found"
    b = obj.matrix_world.to_3x3()
    X = b.col[0].normalized() if b.col[0].length > 1e-9 else Vector((1.0, 0.0, 0.0))
    Y = b.col[1].normalized() if b.col[1].length > 1e-9 else Vector((0.0, 1.0, 0.0))
    Z = b.col[2].normalized() if b.col[2].length > 1e-9 else Vector((0.0, 0.0, 1.0))
    if obj.get("bb_handle"):
        origin = obj.matrix_world.translation.copy()
    else:
        origin = Vector(world_center(obj))
    return (origin, (Z, X, Y)), None             # N = normal/aim, (U, V) = the two tangents


def _build_relational_path(raw):
    """G174 — grow a sweep centerline from a MEASURED anchor frame as vectors in its (n,u,v)
    basis, so no world coordinate is ever typed (origin measured, basis measured, the
    multipliers are authored dimensions). The uniform application of edit op=field's
    measured-frame vector language to the sweep family. Detected when raw is a list whose
    first entry is a dict carrying 'from'. Returns (abs_points, note, error); (None, None,
    None) when raw is NOT a relational path (caller falls through to literal points).

    Header  raw[0]:  {"from": anchor, "frame": tangent_normal|world,
                      "f": {steps, t:[t0,t1], n:expr, u:expr, v:expr},  # parametric f(t)
                      "cumulative": bool}                               # vector-list mode
    Body    raw[1:]: [n,u,v] basis-vector steps (incremental by default), and/or a terminus
                     {"to": anchor} that lands the path exactly on a second handle (the
                     connecting-extrude case — free path = no 'to', connecting = with 'to')."""
    if not (isinstance(raw, list) and raw and isinstance(raw[0], dict) and "from" in raw[0]):
        return None, None, None
    from mathutils import Vector
    head = raw[0]
    unknown = set(head) - {"from", "frame", "f", "cumulative"}
    if unknown:
        return None, None, f"path header: unknown key(s) {sorted(unknown)}"
    anc, err = _frame_anchor(head["from"])
    if err:
        return None, None, err
    O, (N, U, V) = anc
    frame = (head.get("frame") or "tangent_normal").lower()
    if frame == "world":
        N, U, V = Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((0, 1, 0))

    def place(nuv):
        return O + nuv[0] * N + nuv[1] * U + nuv[2] * V

    note = None
    pts = []
    fspec = head.get("f")
    if fspec is not None:
        # Parametric f(t): the path is COMPUTED (helix/spiral/taper in one expression).
        import numpy as np
        from . import fields
        if not isinstance(fspec, dict):
            return None, None, "path 'f' must be a dict {steps, n, u, v, t:[t0,t1]}"
        steps = max(2, min(int(fspec.get("steps", 32)), 1024))
        trange = fspec.get("t", [0.0, 1.0])
        if not (isinstance(trange, (list, tuple)) and len(trange) == 2):
            return None, None, "path f.t must be [t0, t1]"
        ts = np.linspace(float(trange[0]), float(trange[1]), steps)
        comps = []
        for key in ("n", "u", "v"):
            src = (fspec.get(key) or "0").strip() if isinstance(fspec.get(key), str) else \
                str(fspec.get(key, 0))
            arr, e = fields._eval_expr(np, src, {"t": ts}, 0)
            if e:
                return None, None, f"path f.{key}: {e}"
            comps.append(arr)
        for i in range(steps):
            pts.append(list(place((float(comps[0][i]), float(comps[1][i]), float(comps[2][i])))))
        note = f"parametric path from '{head['from']}' · {steps} samples"
        return pts, note, None

    # Vector-list mode: start AT the anchor, then walk the basis-vector steps.
    cumulative = bool(head.get("cumulative", False))
    cur = O.copy()
    pts.append(list(cur))
    welded = None
    for i, entry in enumerate(raw[1:], 1):
        if isinstance(entry, dict):
            tk = entry.get("to") or entry.get("weld")
            if not tk:
                return None, None, (f"path body[{i}]: dict must be a terminus "
                                    "{\"to\": anchor} (or [n,u,v] vector)")
            tanc, err = _frame_anchor(tk)
            if err:
                return None, None, err
            pts.append(list(tanc[0]))
            welded = tk
            continue
        if not (isinstance(entry, (list, tuple)) and len(entry) == 3):
            return None, None, f"path body[{i}] must be [n,u,v] or {{\"to\": anchor}}"
        vec = (float(entry[0]), float(entry[1]), float(entry[2]))
        if cumulative:
            pts.append(list(place(vec)))
        else:
            cur = cur + vec[0] * N + vec[1] * U + vec[2] * V
            pts.append(list(cur))
    if len(pts) < 2:
        return None, None, "relational path needs at least one [n,u,v] step or a {\"to\":…}"
    note = (f"relational path from '{head['from']}'"
            + (f" welded to '{welded}'" if welded else " (free end)")
            + f" · {'cumulative' if cumulative else 'incremental'} steps")
    return pts, note, None


def spline_tube(params):
    """Create a tube mesh swept along an interpolating spline through 2–32 points.

    name:       required, unique.
    points:     list of control points the curve passes THROUGH. Each is
                [x, y, z] world coords, or {"near": "obj", "offset": [dx,dy,dz]}
                relative to an existing object's bbox center.
                RELATIONAL PATH (G174) — instead of typed coordinates, grow the path
                from a MEASURED handle frame as vectors in its (n,u,v) basis, so no
                world coordinate is divined. Pass points as a list whose FIRST entry
                is a header {"from": <handle/obj>, "frame": "tangent_normal"} and the
                rest are [n,u,v] basis-vector steps (incremental from the anchor), an
                optional terminus {"to": <handle>} to weld the end onto a second
                anchor, OR a parametric form
                {"from":A, "f":{"steps":64, "n":"0.02*cos(tau*5*t)",
                                "u":"0.02*sin(tau*5*t)", "v":"0.06*t"}} (a helix/coil
                in one expression; n/u/v are sandboxed exprs in t∈[0,1]).
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

    # G174: a relational vector-path (grown from a measured handle frame) in place of typed
    # coordinates — see _build_relational_path. No-op for ordinary [x,y,z]/{"near"} lists.
    rel_pts, rel_note, rel_err = _build_relational_path(raw_points)
    if rel_err:
        return {"error": rel_err}
    if rel_pts is not None:
        raw_points = rel_pts

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
    radii_per_sample = [_radius_at(radii, t) for t in ts]

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # G161/G177: build the swept mesh DIRECTLY (clean rings + center-vertex cap fans on a
    # rotation-minimizing frame) instead of beveling a POLY curve and converting — that route
    # self-intersected at the end caps on clean paths and straight runs.
    verts, faces = _tube_geometry(samples, radii_per_sample, sides)
    if verts is None:
        return {"error": "tube path collapsed to one point — give distinct control points"}
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)   # consistent outward winding
    bm.to_mesh(me)
    bm.free()
    me.update()
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()
    obj = bpy.context.active_object

    rounded_pts = [[round(v, 4) for v in p] for p in points]
    obj["bb_spline_points"] = json.dumps(rounded_pts)
    obj["bb_spline_radii"] = json.dumps([round(r, 4) for r in radii])

    bpy.context.view_layer.update()
    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    result = {
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
    # G121: preflight the bend-vs-radius feasibility at creation (instead of only via a
    # separate feel op=curve) — warn when the tube self-intersects at a tight turn.
    mbr = _min_bend_radius(samples)
    result["min_bend_radius"] = round(mbr, 4) if mbr else None
    warn = _bend_warning(mbr, max(radii), "tube")
    if warn:
        result.setdefault("notes", []).append(warn)
    if rel_note:
        result.setdefault("notes", []).append(rel_note)
        result["relational_path"] = True
    return result


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
    # G174: relational vector-path grown from a measured handle frame (same grammar as
    # spline_tube) → resolve to absolute control points before the normal per-point loop.
    rel_pts, rel_note, rel_err = _build_relational_path(raw)
    if rel_err:
        return {"error": rel_err}
    if rel_pts is not None:
        raw = rel_pts
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
    out = {
        "success": True,
        "object_name": obj.name,
        "type": ctype,
        "control_points": len(pts),
        "cyclic": cyclic,
        "bevel_depth": bevel_depth,
        "anchored": anchored,
        "dimensions": [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)],
    }
    if rel_note:
        out["notes"] = [rel_note]
        out["relational_path"] = True
    return out


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

        # Pass 1 — per-sample curvature κ, bend-plane normal, and local turn angle.
        max_k = 0.0
        at_frac = 0.0
        turning = 0.0
        samples = []   # (arc_frac, k, unit bend-normal, turn_deg)
        for i in range(1, len(P) - 1):
            a, b, c = P[i - 1], P[i], P[i + 1]
            ab, bc, ca = (b - a).length, (c - b).length, (a - c).length
            cross = (b - a).cross(c - b)
            d0, d1 = (b - a), (c - b)
            turn_local = 0.0
            if d0.length > 1e-9 and d1.length > 1e-9:
                cosang = max(-1.0, min(1.0, d0.normalized().dot(d1.normalized())))
                turn_local = math.degrees(math.acos(cosang))
                turning += turn_local
            denom = ab * bc * ca
            if denom > 1e-12 and cross.length > 1e-12:
                k = 4.0 * (cross.length / 2.0) / denom    # Menger curvature 1/R
                if k > max_k:
                    max_k = k
                    at_frac = cum[i] / length
                samples.append((cum[i] / length, k, cross.normalized(), turn_local))

        # Pass 2 — segment the curve into constant-bend-sense RUNS and count the real
        # LOBES. A clean arch is one lobe (0 inflections); a real S is two big lobes
        # (1). A 3-pt Bézier overshoots a sliver opposite the arc at each endpoint,
        # and discretisation can jitter a stray sample at the reversal — both make
        # tiny runs. Keeping only runs that carry a meaningful share of the total
        # turning (≥12%) drops the slivers, so a plain arch no longer reads 'S-bend',
        # and inflections = (real lobes − 1) regardless of where they fall.
        inflections = 0
        infl_at = []
        if samples:
            ref = max(samples, key=lambda s: s[1])[2]   # normal at the tightest bend
            runs = []   # [sign, turning_sum, start_frac]
            for frac, k, bn, turn in samples:
                if k < 0.10 * max_k:
                    continue                          # near-straight → ignore (noise)
                sign = 1 if bn.dot(ref) >= 0 else -1
                if runs and runs[-1][0] == sign:
                    runs[-1][1] += turn
                else:
                    runs.append([sign, turn, frac])
            total_turn = sum(r[1] for r in runs)
            if total_turn > 1e-6:
                lobes = [r for r in runs if r[1] >= 0.12 * total_turn]
                inflections = max(0, len(lobes) - 1)
                infl_at = [round(lobes[i][2], 2) for i in range(1, len(lobes))]

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
            "inflection_at": infl_at,
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

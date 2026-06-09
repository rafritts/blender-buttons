"""Sculpt brushes — programmatic equivalents to Blender sculpt mode.

Each brush operates on a region of an object's mesh defined by a world-space
center and radius. No mouse, no sculpt mode, no view dependence — just bmesh
deformations on the verts inside the region, weighted by a falloff curve.

Brushes (each is a dedicated tool with a custom signature):
  sculpt_grab     pull region toward a target point (translation by offset)
  sculpt_inflate  push verts along their own normals (organic bulge/deflate)
  sculpt_draw     push verts along a single averaged normal (uniform ridge)
  sculpt_smooth   laplacian relax (no amount — strength is iterations)
  sculpt_crease   pull verts toward center with sharp falloff (folds, valleys)
  sculpt_pinch    pull verts radially inward in the tangent plane
  sculpt_flatten  project verts toward an average plane through center

Brushes are one-shot: caller does NOT need to be in edit mode. The brush
enters edit mode internally, applies, and exits — feels like an object-mode op.

The kernel is shared:
  1. Validate target/at/radius/falloff.
  2. (Optional) locally subdivide edges in radius for finer control.
  3. Find verts within radius of `at` in world space, weighted by t = dist/radius.
  4. Apply per-brush displacement, scaled by falloff(t).

Topology gotcha: a 32x16 sphere has ~7cm faces — too coarse for a 2cm brush.
Pass subdivide=True to get density before sculpting, or use a denser mesh.
"""

import bpy
import bmesh
import mathutils

from .state import push_undo


_FALLOFFS = {"SMOOTH", "LINEAR", "SPHERE", "SHARP", "ROOT", "CONSTANT"}


def _falloff_weight(t, kind):
    """t in [0, 1] (0 at center, 1 at radius edge). Returns weight in [0, 1]."""
    if t >= 1.0:
        return 0.0
    if t <= 0.0:
        return 1.0
    if kind == "SMOOTH":
        return 1.0 - t * t * (3.0 - 2.0 * t)
    if kind == "LINEAR":
        return 1.0 - t
    if kind == "SPHERE":
        inner = 1.0 - t * t
        return inner ** 0.5 if inner > 0 else 0.0
    if kind == "SHARP":
        return (1.0 - t) ** 2
    if kind == "ROOT":
        return 1.0 - t ** 0.5
    return 1.0  # CONSTANT


def _validate(params, default_falloff="SMOOTH"):
    """Common parameter validation. Returns (obj, center_world, radius, falloff, err_dict).
    On success err_dict is None; on failure the other fields are None."""
    target = params.get("target")
    if not target:
        return None, None, None, None, {"error": "'target' (object name) is required"}
    obj = bpy.data.objects.get(target)
    if obj is None:
        return None, None, None, None, {"error": f"Object '{target}' not found"}
    if obj.type != 'MESH':
        return None, None, None, None, {"error": f"'{target}' is not a mesh (type={obj.type})"}

    at = params.get("at")
    if not (isinstance(at, list) and len(at) == 3):
        return None, None, None, None, {"error": "'at' must be a [x, y, z] world-space list"}
    center = mathutils.Vector((float(at[0]), float(at[1]), float(at[2])))

    radius = float(params.get("radius", 0.05))
    if radius <= 0:
        return None, None, None, None, {"error": "'radius' must be > 0"}

    falloff = (params.get("falloff") or default_falloff).upper()
    if falloff not in _FALLOFFS:
        return None, None, None, None, {
            "error": f"Invalid falloff '{falloff}'. Use one of {sorted(_FALLOFFS)}"}

    return obj, center, radius, falloff, None


def _enter_edit(obj):
    """Make obj active + enter edit mode. Returns the bmesh handle."""
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    return bmesh.from_edit_mesh(obj.data)


def _exit_edit(obj):
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    # Force the bound_box cache to refresh so post-sculpt status reflects new bounds.
    # Without this, status reports stale dims/bounds until something else triggers a depsgraph eval.
    obj.data.update()
    bpy.context.view_layer.update()


_LOW_AFFECTED_WARN = 8


def _affected_warning(verts_affected, subdivided, brush_name):
    """Build a 'too few verts' warning if the brush had nothing to grip."""
    if verts_affected >= _LOW_AFFECTED_WARN or subdivided:
        return None
    return (f"{brush_name} only moved {verts_affected} verts — mesh likely too coarse "
            f"in this region. Pass subdivide=True to add density, or increase radius.")


def _verts_in_radius(bm, obj, center_world, radius):
    """Return [(vert, t)] for verts within world-space `radius` of `center_world`.
    t = distance/radius in [0, 1] — pass straight to _falloff_weight."""
    mat = obj.matrix_world
    r2 = radius * radius
    hits = []
    for v in bm.verts:
        wv = mat @ v.co
        d2 = (wv - center_world).length_squared
        if d2 < r2:
            t = (d2 ** 0.5) / radius
            hits.append((v, t))
    return hits


def _maybe_subdivide(bm, obj, center_world, radius, want):
    """Locally subdivide edges whose midpoint is within radius. Returns count."""
    if not want:
        return 0
    mat = obj.matrix_world
    r2 = radius * radius
    edges = []
    for e in bm.edges:
        midw = (mat @ e.verts[0].co + mat @ e.verts[1].co) * 0.5
        if (midw - center_world).length_squared < r2:
            edges.append(e)
    if not edges:
        return 0
    bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
    return len(edges)


def _world_to_local_dir(obj, world_dir):
    """Transform a world-space direction (no translation) into the object's local space."""
    return obj.matrix_world.inverted().to_3x3() @ world_dir


def sculpt_grab(params):
    """Pull a region toward a world-space target point.

    target: object name.
    at:     [x, y, z] world-space brush center.
    to:     [x, y, z] world-space destination. Verts at the brush center move by
            (to - at) and verts at the radius edge don't move; everything between
            interpolates by falloff.
    radius: meters.
    falloff: SMOOTH (default) | LINEAR | SPHERE | SHARP | ROOT | CONSTANT.
    subdivide: if True, locally subdivide edges in radius first. Default False.
    """
    obj, center, radius, falloff, err = _validate(params)
    if err:
        return err
    to = params.get("to")
    if not (isinstance(to, list) and len(to) == 3):
        return {"error": "'to' must be a [x, y, z] world-space list"}
    target_world = mathutils.Vector((float(to[0]), float(to[1]), float(to[2])))
    offset_world = target_world - center
    offset_local = _world_to_local_dir(obj, offset_world)

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False))
    hits = _verts_in_radius(bm, obj, center, radius)
    for v, t in hits:
        v.co += offset_local * _falloff_weight(t, falloff)
    _exit_edit(obj)
    push_undo(f"sculpt_grab {obj.name}")
    result = {"success": True, "verts_affected": len(hits),
              "offset_world": [round(c, 4) for c in offset_world],
              "subdivided_edges": subdivided}
    warn = _affected_warning(len(hits), subdivided, "sculpt_grab")
    if warn:
        result["warning"] = warn
    return result


def sculpt_inflate(params):
    """Push verts along their own normals — organic bulge/deflate.

    amount: meters along normal. Positive = outward (bulge), negative = inward.
    """
    obj, center, radius, falloff, err = _validate(params)
    if err:
        return err
    amount = float(params.get("amount", 0.01))

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False))
    bm.normal_update()
    hits = _verts_in_radius(bm, obj, center, radius)
    moved = 0
    for v, t in hits:
        n = v.normal
        if n.length == 0:
            continue
        v.co += n * (amount * _falloff_weight(t, falloff))
        moved += 1
    _exit_edit(obj)
    push_undo(f"sculpt_inflate {amount}")
    result = {"success": True, "verts_affected": moved, "amount": amount,
              "subdivided_edges": subdivided}
    warn = _affected_warning(moved, subdivided, "sculpt_inflate")
    if warn:
        result["warning"] = warn
    return result


def sculpt_draw(params):
    """Push verts along a SINGLE averaged normal — uniform-direction ridge/dent.

    amount: meters along the averaged normal. Signed.
    normal: optional [x, y, z] world-space normal override. If omitted, the average
            of vert normals in the brush region is used. Pass an override when the
            surface is curved enough that the average is unstable.
    """
    obj, center, radius, falloff, err = _validate(params)
    if err:
        return err
    amount = float(params.get("amount", 0.01))

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False))
    bm.normal_update()
    hits = _verts_in_radius(bm, obj, center, radius)

    override = params.get("normal")
    if isinstance(override, list) and len(override) == 3:
        avg_n_world = mathutils.Vector((float(override[0]), float(override[1]), float(override[2])))
    else:
        mat3 = obj.matrix_world.to_3x3()
        avg_n_world = mathutils.Vector((0.0, 0.0, 0.0))
        for v, _ in hits:
            avg_n_world += mat3 @ v.normal
    if avg_n_world.length == 0:
        _exit_edit(obj)
        return {"error": "averaged normal is zero — pass `normal` explicitly"}
    avg_n_world = avg_n_world.normalized()
    offset_local = _world_to_local_dir(obj, avg_n_world * amount)

    for v, t in hits:
        v.co += offset_local * _falloff_weight(t, falloff)
    _exit_edit(obj)
    push_undo(f"sculpt_draw {amount}")
    result = {"success": True, "verts_affected": len(hits), "amount": amount,
              "avg_normal_world": [round(c, 4) for c in avg_n_world],
              "subdivided_edges": subdivided}
    warn = _affected_warning(len(hits), subdivided, "sculpt_draw")
    if warn:
        result["warning"] = warn
    return result


def sculpt_smooth(params):
    """Laplacian relax — pull each vert toward the centroid of its neighbors.

    iterations: int (default 1). Strength is iterations × falloff; no `amount`.
    """
    obj, center, radius, falloff, err = _validate(params)
    if err:
        return err
    iterations = max(1, int(params.get("iterations", 1)))

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False))

    last_hits = 0
    for _ in range(iterations):
        hits = _verts_in_radius(bm, obj, center, radius)
        last_hits = len(hits)
        new_positions = []
        for v, t in hits:
            if not v.link_edges:
                continue
            nb_sum = mathutils.Vector((0.0, 0.0, 0.0))
            nb_count = 0
            for e in v.link_edges:
                nb_sum += e.other_vert(v).co
                nb_count += 1
            if nb_count == 0:
                continue
            avg = nb_sum / nb_count
            new_positions.append((v, v.co.lerp(avg, _falloff_weight(t, falloff))))
        for v, p in new_positions:
            v.co = p

    _exit_edit(obj)
    push_undo(f"sculpt_smooth iter={iterations}")
    result = {"success": True, "iterations": iterations,
              "verts_per_pass": last_hits, "subdivided_edges": subdivided}
    warn = _affected_warning(last_hits, subdivided, "sculpt_smooth")
    if warn:
        result["warning"] = warn
    return result


def sculpt_crease(params):
    """Pull verts directly toward the brush center — sharp folds, valleys.

    Default falloff is SHARP (the whole point is a tight fold); override if you
    want a softer crease.

    amount: meters of pull toward center. Positive = pull in, negative = push out.
    """
    obj, center, radius, falloff, err = _validate(params, default_falloff="SHARP")
    if err:
        return err
    amount = float(params.get("amount", 0.005))

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False))
    hits = _verts_in_radius(bm, obj, center, radius)
    mat = obj.matrix_world

    for v, t in hits:
        toward = center - (mat @ v.co)
        if toward.length == 0:
            continue
        offset_world = toward.normalized() * (amount * _falloff_weight(t, falloff))
        v.co += _world_to_local_dir(obj, offset_world)

    _exit_edit(obj)
    push_undo(f"sculpt_crease {amount}")
    result = {"success": True, "verts_affected": len(hits), "amount": amount,
              "subdivided_edges": subdivided}
    warn = _affected_warning(len(hits), subdivided, "sculpt_crease")
    if warn:
        result["warning"] = warn
    return result


def sculpt_pinch(params):
    """Pull verts radially inward in their TANGENT PLANE — tightens without raising.

    Unlike crease (which moves toward center directly), pinch projects the
    toward-center direction onto each vert's tangent plane, so the surface
    puckers without changing average height.

    amount: meters of in-plane pull. Positive = inward, negative = outward.
    """
    obj, center, radius, falloff, err = _validate(params)
    if err:
        return err
    amount = float(params.get("amount", 0.005))

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False))
    bm.normal_update()
    hits = _verts_in_radius(bm, obj, center, radius)
    mat = obj.matrix_world
    mat3 = mat.to_3x3()

    for v, t in hits:
        wv = mat @ v.co
        toward = center - wv
        if toward.length == 0:
            continue
        n_world = mat3 @ v.normal
        if n_world.length == 0:
            continue
        n_world = n_world.normalized()
        in_plane = toward - n_world * toward.dot(n_world)
        if in_plane.length == 0:
            continue
        offset_world = in_plane.normalized() * (amount * _falloff_weight(t, falloff))
        v.co += _world_to_local_dir(obj, offset_world)

    _exit_edit(obj)
    push_undo(f"sculpt_pinch {amount}")
    result = {"success": True, "verts_affected": len(hits), "amount": amount,
              "subdivided_edges": subdivided}
    warn = _affected_warning(len(hits), subdivided, "sculpt_pinch")
    if warn:
        result["warning"] = warn
    return result


def sculpt_flatten(params):
    """Project verts toward an average plane through the brush center — smooths bumps.

    amount: 0..1 blend toward the plane. 1 = fully flattened, 0.5 = halfway.
            Negative values push AWAY from the plane (anti-flatten / amplify bumps).
    plane_normal: optional [x, y, z] world-space normal override. If omitted, the
                  average of vert normals in the region is used. Pass an override
                  for "flatten against THIS plane" (e.g. floor normal [0, 0, 1]).
    """
    obj, center, radius, falloff, err = _validate(params)
    if err:
        return err
    amount = float(params.get("amount", 1.0))
    amount = max(-1.0, min(1.0, amount))

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False))
    bm.normal_update()
    hits = _verts_in_radius(bm, obj, center, radius)

    override = params.get("plane_normal")
    if isinstance(override, list) and len(override) == 3:
        plane_n = mathutils.Vector((float(override[0]), float(override[1]), float(override[2])))
    else:
        mat3 = obj.matrix_world.to_3x3()
        plane_n = mathutils.Vector((0.0, 0.0, 0.0))
        for v, _ in hits:
            plane_n += mat3 @ v.normal
    if plane_n.length == 0:
        _exit_edit(obj)
        return {"error": "averaged plane normal is zero — pass `plane_normal` explicitly"}
    plane_n = plane_n.normalized()

    mat = obj.matrix_world
    for v, t in hits:
        wv = mat @ v.co
        d = (wv - center).dot(plane_n)
        # offset_world moves the vert by -d * amount along plane_n (toward the plane)
        offset_world = plane_n * (-d * amount * _falloff_weight(t, falloff))
        v.co += _world_to_local_dir(obj, offset_world)

    _exit_edit(obj)
    push_undo(f"sculpt_flatten {amount}")
    result = {"success": True, "verts_affected": len(hits), "amount": amount,
              "plane_normal_world": [round(c, 4) for c in plane_n],
              "subdivided_edges": subdivided}
    warn = _affected_warning(len(hits), subdivided, "sculpt_flatten")
    if warn:
        result["warning"] = warn
    return result


TOOLS = {
    "sculpt_grab":    sculpt_grab,
    "sculpt_inflate": sculpt_inflate,
    "sculpt_draw":    sculpt_draw,
    "sculpt_smooth":  sculpt_smooth,
    "sculpt_crease":  sculpt_crease,
    "sculpt_pinch":   sculpt_pinch,
    "sculpt_flatten": sculpt_flatten,
}

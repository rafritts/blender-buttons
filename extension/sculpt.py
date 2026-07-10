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
from .editmode import _has_dir_words, _describe_dir, _NORMAL_DEGENERATE


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


# A stroke that shoves a vert much farther than the brush's own radius is almost
# always a wrong-magnitude `amount`, not intent (G148 — one inflate ballooned icing
# 56 cm through the floor). We never block — sculpt is destructive-by-design and undo
# is one call away — but every displacement brush now ECHOES its achieved max move and
# flags a catastrophic one so the agent sees it in the status block instead of finding
# out three ops later.
_RUNAWAY_RADIUS_MULT = 3.0
# G208: a stroke that would move any vert more than this many brush-radii is refused
# BEFORE it mutates — a wrong-magnitude `amount` (over-large by an order of magnitude) is
# almost never intent, and a refuse-before is legible where a warn-after has already
# ballooned the mesh. Distinct from the 3× post-hoc echo, which stays for the grey zone.
_RUNAWAY_REFUSE_MULT = 2.0


def _runaway_refusal(predicted, radius, brush_name, hint="amount"):
    """G208 — refuse a displacement brush BEFORE mutating when its predicted maximum move
    exceeds 2× the brush radius. Returns an error dict, or None to proceed."""
    if radius and predicted > _RUNAWAY_REFUSE_MULT * radius:
        cap = round(_RUNAWAY_REFUSE_MULT * radius, 4)
        return {"error": (
            f"{brush_name} would move a vert up to {round(predicted, 4)} m — over "
            f"{int(_RUNAWAY_REFUSE_MULT)}× the brush radius ({round(radius, 4)} m). Refused "
            f"before mutating: that's almost certainly a wrong-magnitude {hint} (every dial "
            f"here is METERS). Keep it under {cap} m, or widen radius= to match the reach "
            f"you intend.")}
    return None


def _displacement_report(max_disp, radius, brush_name):
    """Return (max_displacement_value, warning_or_None) for a displacement brush."""
    md = round(float(max_disp), 4)
    if radius and max_disp > _RUNAWAY_RADIUS_MULT * radius:
        warn = (f"{brush_name} moved a vert {md} m — over {int(_RUNAWAY_RADIUS_MULT)}x "
                f"the brush radius ({round(radius, 4)} m). That's almost certainly an "
                f"over-large amount; check the resulting bounds and `history undo` if "
                f"it ballooned.")
        return md, warn
    return md, None


def _verts_in_radius(bm, obj, center_world, radius, connected=False):
    """Return [(vert, t)] for verts within `radius` of `center_world`; t = dist/radius in
    [0, 1] for _falloff_weight. Euclidean by default; connected=True (G215) scopes by
    GEODESIC distance along the surface from the nearest vert, so a brush on a thin shell
    walks ONE wall instead of ballooning through space to grab the opposing wall."""
    if connected:
        return _verts_in_radius_geodesic(bm, obj, center_world, radius)
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


def _verts_in_radius_geodesic(bm, obj, center_world, radius):
    """G215 — scope by geodesic (along-surface) distance from the surface vert nearest the
    brush centre, in WORLD-space edge lengths (scale-correct). A thin clad shell's two
    walls share no short edge path, so the flood never crosses to the back face."""
    import heapq
    mat = obj.matrix_world
    bm.verts.ensure_lookup_table()
    seed = None
    best = None
    for v in bm.verts:
        d2 = ((mat @ v.co) - center_world).length_squared
        if best is None or d2 < best:
            best = d2
            seed = v
    if seed is None or best ** 0.5 > radius:
        return []
    dist = {seed.index: 0.0}
    heap = [(0.0, seed.index)]
    while heap:
        d, vi = heapq.heappop(heap)
        if d > dist.get(vi, radius):
            continue
        if d >= radius:
            continue
        v = bm.verts[vi]
        wv = mat @ v.co
        for e in v.link_edges:
            w = e.other_vert(v)
            nd = d + (wv - (mat @ w.co)).length
            if nd < dist.get(w.index, radius):
                dist[w.index] = nd
                heapq.heappush(heap, (nd, w.index))
    return [(bm.verts[vi], d / radius) for vi, d in dist.items()]


def _two_wall_warning(obj, hits, connected):
    """G215 — cheap detector for a euclidean footprint that spans a thin shell's two
    opposing walls. Reference = the normal of the hit NEAREST the brush centre (the wall
    the brush sits on); any hit whose normal strongly OPPOSES it (dot < -0.3, i.e. >107°
    apart) is the far/back wall — a split a single smoothly-curved wall can't produce
    within a small radius. Robust to a 50/50 balance the mean would cancel to noise.
    Returns a warning steering to connected=true, or None (silent when geodesic/sparse)."""
    if connected or len(hits) < 6:
        return None
    mat3 = obj.matrix_world.to_3x3()
    ns = []
    for v, t in hits:
        wn = mat3 @ v.normal
        if wn.length:
            ns.append((t, wn.normalized()))
    if len(ns) < 6:
        return None
    ref = min(ns, key=lambda p: p[0])[1]     # normal of the closest-to-centre hit
    opposed = sum(1 for _, n in ns if n.dot(ref) < -0.3)
    if opposed >= 2:
        return ("brush footprint spans two opposing surfaces (a thin shell's front and "
                "back wall) — the euclidean radius grabbed both, so this stroke can shred "
                "the shell (validate will flag the self-intersections). Re-run with "
                "connected=true to scope geodesically along one wall.")
    return None


def _maybe_subdivide(bm, obj, center_world, radius, want, detail=None):
    """Densify edges under the brush so the stroke has mesh to grip and can EXPRESS its
    falloff curve. Auto-densifies (G213) until no edge whose midpoint is inside the
    footprint is longer than `detail` (a target edge length in world meters, default
    radius/4) — iterate to the target, not one blind pass, so a coarse footprint can't
    sample a smooth falloff at 2-3 verts. subdivide=True forces at least one pass even
    when already fine. Bounded passes. Returns the number of edges subdivided."""
    mat = obj.matrix_world
    r2 = radius * radius
    if detail is None or detail <= 0:
        detail = radius / 4.0

    def _footprint_edges(long_only):
        out = []
        for e in bm.edges:
            a = mat @ e.verts[0].co
            b = mat @ e.verts[1].co
            # In the footprint if EITHER endpoint or the midpoint is within the radius —
            # endpoint-inclusion is what lets a huge edge radiating from the brush centre
            # (whose midpoint sits outside a small radius) still get densified, so detail
            # converges INWARD toward the centre pass by pass.
            near = ((a - center_world).length_squared < r2
                    or (b - center_world).length_squared < r2
                    or ((a + b) * 0.5 - center_world).length_squared < r2)
            if not near:
                continue
            if long_only and (a - b).length <= detail:
                continue
            out.append(e)
        return out

    total = 0
    for i in range(8):                       # backstop against runaway subdivision
        edges = _footprint_edges(long_only=True)
        if i == 0 and want and not edges:
            # explicit request, footprint already fine-grained: one uniform pass on top.
            edges = _footprint_edges(long_only=False)
        if not edges:
            break
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
        total += len(edges)
    return total


def _world_to_local_dir(obj, world_dir):
    """Transform a world-space direction (no translation) into the object's local space."""
    return obj.matrix_world.inverted().to_3x3() @ world_dir


def _grab_offset_from_words(obj, hits, params):
    """F3: resolve sculpt_grab's offset from the F1 direction words (meters, world).
    'out' follows the average normal of the brushed verts. Returns
    (offset_vec, frame_str | None, err_dict | None)."""
    nmat = obj.matrix_world.to_3x3()
    vec = mathutils.Vector((0.0, 0.0, 0.0))
    vec.x += float(params.get("right", 0.0) or 0.0) - float(params.get("left", 0.0) or 0.0)
    vec.y += float(params.get("back", 0.0) or 0.0) - float(params.get("forward", 0.0) or 0.0)
    vec.z += float(params.get("up", 0.0) or 0.0) - float(params.get("down", 0.0) or 0.0)
    frame = None
    nrm_amt = float(params.get("out", 0.0) or 0.0) - float(params.get("inward", 0.0) or 0.0)
    if nrm_amt != 0.0:
        acc = mathutils.Vector((0.0, 0.0, 0.0))
        total = 0
        for v, _t in hits:
            wn = nmat @ v.normal
            if wn.length == 0:
                continue
            acc += wn.normalized()
            total += 1
        if total == 0 or acc.length == 0 or acc.length / total < _NORMAL_DEGENERATE:
            return None, None, {"error":
                "brushed region's normals cancel — 'out'/'inward' has no direction here. "
                "Pass a world direction (up/down/left/right/forward/back) or a 'to' point."}
        n = acc.normalized()
        vec += n * nrm_amt
        frame = "out ≈ " + _describe_dir(n)
    if vec.length == 0:
        return None, None, {"error": "no offset resolved from direction words"}
    return vec, frame, None


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
    has_to = isinstance(to, list) and len(to) == 3
    has_dir = _has_dir_words(params)
    if not has_to and not has_dir:
        return {"error": "give a destination: 'to' [x,y,z] world point, OR direction "
                         "words (out=, up=, left=… in meters)"}

    connected = bool(params.get("connected", False))
    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False),
                                  params.get("detail"))
    bm.normal_update()
    hits = _verts_in_radius(bm, obj, center, radius, connected)

    frame = None
    if has_to:
        target_world = mathutils.Vector((float(to[0]), float(to[1]), float(to[2])))
        offset_world = target_world - center
    else:
        # F3: the offset is the part that wants to be local. 'out' follows the
        # region's average normal (the brushed verts); the world words are the
        # nudge axes — all in meters.
        offset_world, frame, derr = _grab_offset_from_words(obj, hits, params)
        if derr:
            _exit_edit(obj)
            return derr
    refusal = _runaway_refusal(offset_world.length, radius, "sculpt_grab", "offset")
    if refusal:
        _exit_edit(obj)
        return refusal
    offset_local = _world_to_local_dir(obj, offset_world)

    for v, t in hits:
        v.co += offset_local * _falloff_weight(t, falloff)
    two_wall = _two_wall_warning(obj, hits, connected)   # before _exit_edit frees the bmesh
    _exit_edit(obj)
    push_undo(f"sculpt_grab {obj.name}")
    md, runaway = _displacement_report(offset_world.length, radius, "sculpt_grab")
    result = {"success": True, "verts_affected": len(hits),
              "offset_world": [round(c, 4) for c in offset_world],
              "max_displacement": md, "subdivided_edges": subdivided, "connected": connected}
    if frame:
        result["frame"] = frame
    warn = (runaway or two_wall
            or _affected_warning(len(hits), subdivided, "sculpt_grab"))
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
    connected = bool(params.get("connected", False))
    # G208: refuse before mutating — `amount` is METERS along the normal; a value over
    # 2× the radius is a wrong-magnitude dial, not intent.
    refusal = _runaway_refusal(abs(amount), radius, "sculpt_inflate")
    if refusal:
        return refusal

    # G208: denominate in true world meters — divide the local normal delta by the
    # object's per-axis scale, exactly like edit op=inflate, so a scaled host doesn't
    # silently amplify the move.
    scale = obj.scale
    sx = abs(scale.x) or 1.0
    sy = abs(scale.y) or 1.0
    sz = abs(scale.z) or 1.0

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False),
                                  params.get("detail"))
    bm.normal_update()
    hits = _verts_in_radius(bm, obj, center, radius, connected)
    moved = 0
    max_disp = 0.0
    for v, t in hits:
        n = v.normal
        if n.length == 0:
            continue
        w = _falloff_weight(t, falloff)
        v.co.x += n.x * amount * w / sx
        v.co.y += n.y * amount * w / sy
        v.co.z += n.z * amount * w / sz
        moved += 1
        disp = abs(amount * w)
        if disp > max_disp:
            max_disp = disp
    two_wall = _two_wall_warning(obj, hits, connected)   # before _exit_edit frees the bmesh
    _exit_edit(obj)
    push_undo(f"sculpt_inflate {amount}")
    md, runaway = _displacement_report(max_disp, radius, "sculpt_inflate")
    result = {"success": True, "verts_affected": moved, "amount": amount,
              "max_displacement": md, "subdivided_edges": subdivided, "connected": connected}
    warn = (runaway or two_wall
            or _affected_warning(moved, subdivided, "sculpt_inflate"))
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
    connected = bool(params.get("connected", False))
    refusal = _runaway_refusal(abs(amount), radius, "sculpt_draw")
    if refusal:
        return refusal

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False),
                                  params.get("detail"))
    bm.normal_update()
    hits = _verts_in_radius(bm, obj, center, radius, connected)

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
    two_wall = _two_wall_warning(obj, hits, connected)   # before _exit_edit frees the bmesh
    _exit_edit(obj)
    push_undo(f"sculpt_draw {amount}")
    md, runaway = _displacement_report(abs(amount), radius, "sculpt_draw")
    result = {"success": True, "verts_affected": len(hits), "amount": amount,
              "avg_normal_world": [round(c, 4) for c in avg_n_world],
              "max_displacement": md, "subdivided_edges": subdivided, "connected": connected}
    warn = (runaway or two_wall
            or _affected_warning(len(hits), subdivided, "sculpt_draw"))
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
    connected = bool(params.get("connected", False))

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False),
                                  params.get("detail"))

    last_hits = 0
    last_hit_list = []
    for _ in range(iterations):
        hits = _verts_in_radius(bm, obj, center, radius, connected)
        last_hits = len(hits)
        last_hit_list = hits
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

    two_wall = _two_wall_warning(obj, last_hit_list, connected)  # before _exit_edit
    _exit_edit(obj)
    push_undo(f"sculpt_smooth iter={iterations}")
    result = {"success": True, "iterations": iterations,
              "verts_per_pass": last_hits, "subdivided_edges": subdivided,
              "connected": connected}
    warn = (two_wall
            or _affected_warning(last_hits, subdivided, "sculpt_smooth"))
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
    connected = bool(params.get("connected", False))
    refusal = _runaway_refusal(abs(amount), radius, "sculpt_crease")
    if refusal:
        return refusal

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False),
                                  params.get("detail"))
    hits = _verts_in_radius(bm, obj, center, radius, connected)
    mat = obj.matrix_world

    for v, t in hits:
        toward = center - (mat @ v.co)
        if toward.length == 0:
            continue
        offset_world = toward.normalized() * (amount * _falloff_weight(t, falloff))
        v.co += _world_to_local_dir(obj, offset_world)

    two_wall = _two_wall_warning(obj, hits, connected)   # before _exit_edit frees the bmesh
    _exit_edit(obj)
    push_undo(f"sculpt_crease {amount}")
    md, runaway = _displacement_report(abs(amount), radius, "sculpt_crease")
    result = {"success": True, "verts_affected": len(hits), "amount": amount,
              "max_displacement": md, "subdivided_edges": subdivided, "connected": connected}
    warn = (runaway or two_wall
            or _affected_warning(len(hits), subdivided, "sculpt_crease"))
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
    connected = bool(params.get("connected", False))
    refusal = _runaway_refusal(abs(amount), radius, "sculpt_pinch")
    if refusal:
        return refusal

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False),
                                  params.get("detail"))
    bm.normal_update()
    hits = _verts_in_radius(bm, obj, center, radius, connected)
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

    two_wall = _two_wall_warning(obj, hits, connected)   # before _exit_edit frees the bmesh
    _exit_edit(obj)
    push_undo(f"sculpt_pinch {amount}")
    md, runaway = _displacement_report(abs(amount), radius, "sculpt_pinch")
    result = {"success": True, "verts_affected": len(hits), "amount": amount,
              "max_displacement": md, "subdivided_edges": subdivided, "connected": connected}
    warn = (runaway or two_wall
            or _affected_warning(len(hits), subdivided, "sculpt_pinch"))
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
    connected = bool(params.get("connected", False))

    bm = _enter_edit(obj)
    subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False),
                                  params.get("detail"))
    bm.normal_update()
    hits = _verts_in_radius(bm, obj, center, radius, connected)

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

    two_wall = _two_wall_warning(obj, hits, connected)   # before _exit_edit frees the bmesh
    _exit_edit(obj)
    push_undo(f"sculpt_flatten {amount}")
    result = {"success": True, "verts_affected": len(hits), "amount": amount,
              "plane_normal_world": [round(c, 4) for c in plane_n],
              "subdivided_edges": subdivided, "connected": connected}
    warn = (two_wall
            or _affected_warning(len(hits), subdivided, "sculpt_flatten"))
    if warn:
        result["warning"] = warn
    return result


def sculpt_gravity(params):
    """Region-parametric GRAVITY drape — SPEC-08 Tier A, the lead deformer.

    Pins the TOP of the region (the attachment) and lets the lower mass fall along
    world -Z, weighted by height: the top is frozen, the bottom falls fully, the
    middle ramps. The fullest point sinks and the lower pole elongates downward → a
    hanging / teardrop form BY CONSTRUCTION, not by a seeing hand. The correctness
    lives in the algorithm; the agent only tunes magnitude (strength + pin), which
    the numeric reads can verify (feel op=silhouette/protrusion).

    target:   object name (required).
    at:       optional [x, y, z] world center to SCOPE the drape to a sphere. Omit
              to drape the WHOLE mesh (SPEC-08 build-order Phase 1).
    radius:   sphere radius (m) — required when `at` is given; ignored otherwise.
    strength: metres the FREE (bottom) end falls. Default 0.02.
    pin:      0..1 fraction of the region's Z-height, measured from the TOP, that is
              FROZEN (the attachment line). Default 0.25 — the top quarter holds, the
              rest hangs. pin=0 lets everything fall (rigid slide, no sag); pin→1
              freezes nearly all of it.
    falloff:  radial falloff at the sphere edge (scoped mode only). Default SMOOTH.
    """
    target = params.get("target")
    if not target:
        return {"error": "'target' (object name) is required"}
    obj = bpy.data.objects.get(target)
    if obj is None:
        return {"error": f"Object '{target}' not found"}
    if obj.type != 'MESH':
        return {"error": f"'{target}' is not a mesh (type={obj.type})"}

    at = params.get("at")
    scoped = isinstance(at, list) and len(at) == 3
    falloff = (params.get("falloff") or "SMOOTH").upper()
    if falloff not in _FALLOFFS:
        return {"error": f"Invalid falloff '{falloff}'. Use one of {sorted(_FALLOFFS)}"}
    strength = float(params.get("strength", params.get("amount", 0.02)))
    pin = max(0.0, min(0.95, float(params.get("pin", 0.25))))
    connected = bool(params.get("connected", False))

    bm = _enter_edit(obj)
    subdivided = 0
    if scoped:
        center = mathutils.Vector((float(at[0]), float(at[1]), float(at[2])))
        radius = float(params.get("radius", 0.0))
        if radius <= 0:
            _exit_edit(obj)
            return {"error": "'radius' must be > 0 when 'at' is given"}
        refusal = _runaway_refusal(abs(strength), radius, "sculpt_gravity", "strength")
        if refusal:
            _exit_edit(obj)
            return refusal
        subdivided = _maybe_subdivide(bm, obj, center, radius, params.get("subdivide", False),
                                      params.get("detail"))
        hits = _verts_in_radius(bm, obj, center, radius, connected)
    else:
        hits = [(v, 0.0) for v in bm.verts]

    if not hits:
        _exit_edit(obj)
        return {"error": "no verts in region"}

    mat = obj.matrix_world
    world = [(v, mat @ v.co) for v, _ in hits]
    zs = [w.z for _, w in world]
    zmin, zmax = min(zs), max(zs)
    pin_z = zmax - pin * (zmax - zmin)
    free_span = pin_z - zmin
    if free_span <= 1e-9:
        _exit_edit(obj)
        return {"error": "region has no vertical extent below the pin line to drape"}
    # Transition band just below the pin line: the free mass ramps in over the top
    # 30% of the free span, then falls at FULL strength below that. This translates
    # the mass DOWN as a body (the fullest point descends) rather than only stretching
    # the bottom — the fix for "gravity didn't de-cone" (the old linear-to-bottom ramp
    # under-moved the apex).
    band = 0.3 * free_span

    moved = 0
    max_drop = 0.0
    for v, w in world:
        if w.z >= pin_z:
            continue  # frozen attachment
        vw = min(1.0, (pin_z - w.z) / band)
        vw = vw * vw * (3.0 - 2.0 * vw)
        if scoped:
            # LATERAL falloff only — horizontal distance from the gravity axis through
            # `center`, ignoring Z. The old 3D falloff pinned the lower pole (far from
            # center because it's LOW), killing exactly the verts that should fall most.
            # Horizontal-only softens just the lateral seam; the vertical drape is the
            # pin gradient's job.
            dx = w.x - center.x
            dy = w.y - center.y
            th = min(1.0, ((dx * dx + dy * dy) ** 0.5) / radius)
            rw = _falloff_weight(th, falloff)
        else:
            rw = 1.0
        drop = strength * vw * rw
        if drop == 0.0:
            continue
        v.co += _world_to_local_dir(obj, mathutils.Vector((0.0, 0.0, -drop)))
        moved += 1
        if drop > max_drop:
            max_drop = drop

    _exit_edit(obj)
    push_undo(f"sculpt_gravity strength={strength}")
    result = {"success": True, "verts_affected": moved, "strength": strength,
              "pin": pin, "region": "sphere" if scoped else "whole_mesh",
              "max_drop": round(max_drop, 4), "subdivided_edges": subdivided}
    warn = _affected_warning(moved, subdivided, "sculpt_gravity")
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
    "sculpt_gravity": sculpt_gravity,
}

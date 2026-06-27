"""Bundled finishes: smooth_edges, round_corners, add_modifier, apply_modifiers."""

import math

import bpy

from .common import activate, linked_guard, resolve_targets, world_bbox
from .state import push_undo, ui_override


def smooth_edges(params):
    """Round off the sharp edges of one or more objects.
    Adds a BEVEL modifier with angle-limit (only sharp edges get beveled, not coplanar ones),
    then shade_smooth + auto_smooth so the rounded edges read as smooth, not faceted.
    width: bevel offset in world units (default 2mm). segments: more = smoother curve.
    angle_limit: edges sharper than this (degrees) get beveled. Default 30°."""
    targets = params.get("targets")
    width = params.get("width", 0.002)
    segments = params.get("segments", 2)
    angle_limit_deg = params.get("angle_limit", 30.0)
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    processed = []
    for o in objs:
        if o.type != 'MESH':
            continue
        activate(o)
        if any(abs(s - 1.0) > 1e-4 for s in o.scale):
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        for m in list(o.modifiers):
            if m.name == "Smooth_Bevel":
                o.modifiers.remove(m)

        mod = o.modifiers.new(name="Smooth_Bevel", type='BEVEL')
        mod.width = width
        mod.segments = segments
        mod.limit_method = 'ANGLE'
        mod.angle_limit = math.radians(angle_limit_deg)
        mod.miter_outer = 'MITER_ARC'
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.ops.object.shade_smooth()
        if hasattr(o.data, "use_auto_smooth"):
            o.data.use_auto_smooth = True
            o.data.auto_smooth_angle = math.radians(angle_limit_deg)
        processed.append(o.name)

    return {"success": True, "smoothed": processed, "width": width,
            "segments": segments, "angle_limit": angle_limit_deg}


def round_corners(params):
    """Round specific vertical corner edges of an object by a real-world radius.

    target:   object name.
    corners:  list of "front_left" | "front_right" | "back_left" | "back_right".
    radius:   bevel offset in meters (the rounding radius). Default 0.02 (2cm).
    segments: number of segments in the round; more = smoother curve. Default 6.
    """
    import bmesh
    target = params.get("target")
    corners = params.get("corners", [])
    radius = params.get("radius", 0.02)
    segments = params.get("segments", 6)

    obj = bpy.data.objects.get(target) if target else None
    if obj is None:
        return {"error": f"Object '{target}' not found"}
    if obj.type != 'MESH':
        return {"error": f"'{target}' is not a mesh"}
    if not corners:
        return {"error": "'corners' must be a non-empty list (front_left|front_right|back_left|back_right)"}

    activate(obj)
    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)

    corner_map = {
        "front_left":  (xmin, ymin),
        "front_right": (xmax, ymin),
        "back_left":   (xmin, ymax),
        "back_right":  (xmax, ymax),
    }
    bad = [c for c in corners if c not in corner_map]
    if bad:
        return {"error": f"Unknown corner(s) {bad}. Valid: {list(corner_map.keys())}"}

    if bpy.context.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')

    bm = bmesh.from_edit_mesh(obj.data)
    mat = obj.matrix_world
    tol = max(radius * 0.5, 1e-3)

    selected = 0
    for edge in bm.edges:
        v0 = mat @ edge.verts[0].co
        v1 = mat @ edge.verts[1].co
        if abs(v0.x - v1.x) > 1e-4 or abs(v0.y - v1.y) > 1e-4:
            continue
        if abs(v0.z - v1.z) < 1e-4:
            continue
        ex, ey = v0.x, v0.y
        for cname in corners:
            tx, ty = corner_map[cname]
            if abs(ex - tx) < tol and abs(ey - ty) < tol:
                edge.select = True
                selected += 1
                break

    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)

    if selected == 0:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": f"No vertical corner edges found near {corners}. "
                          f"Object may need loop_cut along Z first if it's a single-segment box."}

    bpy.ops.mesh.bevel(offset=radius, segments=segments, affect='EDGES')
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.shade_smooth()
    if hasattr(obj.data, "use_auto_smooth"):
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(60)

    push_undo(f"round_corners {target} {corners} r={radius}")
    return {"success": True, "target": target, "corners": corners,
            "radius": radius, "segments": segments, "edges_beveled": selected}


def bend(params):
    """Bend objects into an arc — the one-call curving verb (SimpleDeform BEND).

    targets: object name, group name, or list (required).
    angle:   bend angle in degrees (required). 30–60 = gentle arc, 90 = quarter
             turn, 180 = U shape. Negative flips direction.
    axis:    X | Y | Z — the axis to bend AROUND (local space). A vertical (Z-tall)
             object bends into a C in the plane perpendicular to this axis: axis=X
             curls it forward/back, axis=Y curls it left/right. Default X.
    apply:   bake the deformation into the mesh (default True). Pass False to
             keep the modifier live for tweaking via modify_modifier.

    PIVOT & SHAPE (G21 — the legibility this verb owes you). SimpleDeform BEND
    pivots about the object's ORIGIN and is SYMMETRIC about it: geometry on BOTH
    sides of the origin (along the span perpendicular to `axis`) curls by the same
    amount, the curl growing with distance from the origin. So a bar CENTRED on its
    origin does NOT make a simple one-way arc — both halves sweep up into a
    hump/"mustache" (apexes out at the arms, tips recurving). To get a clean
    one-directional crescent, move the origin to ONE END first (set the 3D-cursor
    there → object origin to cursor), so the whole span bends the same way; or accept
    the symmetric arc and design around it. Worked example: an X-aligned bar, origin
    at its centre, axis=Y, +30° → both arms sweep +Z in the XZ plane, a symmetric
    smile about the origin (NOT a tilted single arc).

    SIDE EFFECT: apply=True forces OBJECT mode (modifier_apply can't run in Edit) —
    which doubles as a reliable "leave Edit mode" escape hatch.

    Geometry needs segments along its length to bend smoothly — primitives like
    cylinders/cones have them around the circumference but only 2 rings along Z;
    run loop_cut first if the bend comes out faceted.
    """
    targets = params.get("targets")
    angle = params.get("angle")
    axis = (params.get("axis") or "X").upper()
    do_apply = params.get("apply", True)
    if angle is None:
        return {"error": "'angle' (degrees) is required"}
    if axis not in ("X", "Y", "Z"):
        return {"error": "axis must be X, Y, or Z"}
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bent = []
    notes = []
    for o in objs:
        if o.type != 'MESH':
            continue
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
        dims = (xmax - xmin, ymax - ymin, zmax - zmin)
        long_axis = "XYZ"[dims.index(max(dims))]
        if long_axis == axis:
            notes.append(f"'{o.name}': bending around its own long axis ({axis}) "
                         "barely changes shape — a perpendicular axis usually wants this")
        activate(o)
        mod = o.modifiers.new(name="Bend", type='SIMPLE_DEFORM')
        mod.deform_method = 'BEND'
        mod.deform_axis = axis
        mod.angle = math.radians(float(angle))
        if do_apply:
            bpy.ops.object.modifier_apply(modifier=mod.name)
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
        bent.append({"name": o.name,
                     "dims_after": [round(xmax - xmin, 4), round(ymax - ymin, 4),
                                    round(zmax - zmin, 4)]})

    if not bent:
        return {"error": "No mesh objects in targets"}
    push_undo(f"bend {angle}° around {axis}")
    out = {"success": True, "bent": bent, "angle": angle, "axis": axis,
           "applied": bool(do_apply)}
    if notes:
        out["warnings"] = notes
    return out


def noise_displace(params):
    """G55 — coherent organic surface noise via a DISPLACE modifier driven by a
    procedural noise texture.

    Unlike edit op=jitter (per-vertex WHITE noise — every vert moves independently, so
    the result is spiky and uncorrelated), a texture-driven displace samples a noise
    field that varies SMOOTHLY across space, so neighbouring verts move together → real
    LUMPS. The move for foliage canopies, terrain, bark, rock — any soft irregular
    surface. The noise is sampled in WORLD space, so copies at different positions get
    different break-up for free (no two scattered bushes look identical).

    target:    mesh to break up (empty = active).
    strength:  ≈ peak displacement in meters (default 0.05). The amount.
    scale:     feature size — noise texture scale (default 0.5). Larger = bigger, broader
               lumps; smaller = finer, busier detail.
    detail:    extra octaves of finer noise layered on the big lumps (default 2).
    direction: NORMAL (default — push along each vert's normal, the organic puff) |
               X | Y | Z (push along a world axis).
    apply:     bake the displacement into the mesh (default True). False keeps the
               DISPLACE modifier + texture live for tweaking via modify_modifier.

    NEEDS RESOLUTION: displacement only shows where there are verts to move — a coarse
    primitive barely ripples. remesh / subdivide first so the surface has verts to break
    up. This is BREAK-UP (positional/textured), distinct from inflate (normal push on a
    dense mesh). Refused on rigged/keyed meshes when apply=True (modifier_apply can't
    bake over shape keys / deform binds — duplicate and strip first, or pass apply=False).
    """
    from .common import linked_guard, deform_binds
    name = params.get("target") or params.get("name")
    obj = bpy.data.objects.get(name) if name else bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": f"'{name}' is not a mesh" if name else "No active mesh object"}
    err = linked_guard(obj)
    if err:
        return {"error": err}
    strength = float(params.get("strength", 0.05))
    scale = float(params.get("scale", 0.5))
    detail = max(0, int(params.get("detail", 2)))
    direction = (params.get("direction") or "NORMAL").upper()
    do_apply = bool(params.get("apply", True))
    if direction not in ("NORMAL", "X", "Y", "Z"):
        return {"error": "direction must be NORMAL | X | Y | Z"}
    if scale <= 0:
        return {"error": "scale must be > 0 (noise feature size, meters)"}
    if do_apply and (obj.data.shape_keys or deform_binds(obj)):
        return {"error": "refusing to bake a displace over a rigged/keyed mesh "
                         "(modifier_apply can't run with shape keys / deform binds). "
                         "Duplicate it and strip the rig, or pass apply=False to keep "
                         "the modifier live."}

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    activate(obj)
    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    dims_before = [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)]

    # CLOUDS = multi-octave Perlin — coherent, organic, fast. noise_scale sets the
    # feature size; noise_depth adds finer octaves on top.
    tex = bpy.data.textures.new(name=f"{obj.name}_noise", type='CLOUDS')
    if hasattr(tex, "noise_scale"):
        tex.noise_scale = scale
    if hasattr(tex, "noise_depth"):
        tex.noise_depth = detail

    mod = obj.modifiers.new(name="Noise_Displace", type='DISPLACE')
    mod.texture = tex
    mod.strength = strength
    mod.mid_level = 0.5            # CLOUDS ~0..1; mid 0.5 displaces both in and out
    mod.texture_coords = 'GLOBAL'  # world-space → placed copies break up differently
    mod.direction = direction

    applied = False
    if do_apply:
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
            applied = True
            bpy.data.textures.remove(tex)  # baked in — the texture is now an orphan
        except RuntimeError as e:
            return {"error": f"displace apply failed: {e}"}

    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    dims_after = [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)]
    push_undo(f"noise_displace {obj.name} strength={strength} scale={scale}")
    return {"success": True, "object": obj.name, "strength": strength, "scale": scale,
            "detail": detail, "direction": direction, "applied": applied,
            "modifier": None if applied else mod.name,
            "dims_before": dims_before, "dims_after": dims_after}


def _configure_array(mod, params):
    """G73: set ARRAY count + offset. `offset` (meters) → constant offset along `axis`
    (the intent-space spacing: "links 0.11 m apart"); `factor` → relative offset as a
    multiple of the object's bbox along `axis`; `axis` picks the run direction (default
    X). Constant wins if both are given. Returns applied-prop descriptions."""
    applied = []
    axis = (params.get("axis") or "X").upper()
    axis_idx = {"X": 0, "Y": 1, "Z": 2}.get(axis, 0)
    if params.get("count") is not None:
        mod.count = int(params["count"])
        applied.append(f"count={mod.count}")
    const = params.get("offset")
    rel = params.get("factor")
    if const is not None:
        mod.use_constant_offset = True
        mod.use_relative_offset = False
        disp = [0.0, 0.0, 0.0]
        disp[axis_idx] = float(const)
        mod.constant_offset_displace = disp
        applied.append(f"constant_offset[{axis}]={const}m")
    elif rel is not None:
        mod.use_relative_offset = True
        mod.use_constant_offset = False
        disp = [0.0, 0.0, 0.0]
        disp[axis_idx] = float(rel)
        mod.relative_offset_displace = disp
        applied.append(f"relative_offset[{axis}]={rel}×bbox")
    return applied


# G89: modifier types that consume `target` as a PARTNER object (the surface/cage/
# armature/lattice that drives the modifier), NOT as the host whose stack gets it.
# For these the host is the active object and `target` is resolved below as the partner.
_PARTNER_TYPES = {"SHRINKWRAP", "MESH_DEFORM", "ARMATURE", "LATTICE"}


def _subsurf_dome_warning(obj):
    """G120 — SUBSURF on a capped primitive with no holding edge loop near the cap pulls the
    flat (n-gon/disk) cap into a downward dome — the classic 'mug base sits on a point' trap.
    Warn when an axis-aligned flat n-gon cap has NO supporting loop within ~15% of the
    object's extent on that axis. Gated on n-gon caps (≥5-vert) so a plain box — which just
    rounds, as intended — doesn't false-warn. Returns a note or None."""
    import bmesh
    if obj is None or obj.type != 'MESH' or obj.data is None:
        return None
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    try:
        if not bm.faces:
            return None
        ends = []
        for axis_i, axis_name in ((0, 'X'), (1, 'Y'), (2, 'Z')):
            coords = [v.co[axis_i] for v in bm.verts]
            lo, hi = min(coords), max(coords)
            ext = hi - lo
            if ext < 1e-6:
                continue
            band = 0.15 * ext
            for end_pos, sgn, end_name in ((hi, 1.0, '+' + axis_name), (lo, -1.0, '-' + axis_name)):
                cap = None
                for f in bm.faces:
                    if len(f.verts) >= 5 and f.normal[axis_i] * sgn > 0.85:
                        c = f.calc_center_median()
                        if abs(c[axis_i] - end_pos) < 0.02 * ext:
                            cap = f
                            break
                if cap is None:
                    continue
                supported = any(0.0 < (end_pos - v.co[axis_i]) * sgn < band for v in bm.verts)
                if not supported:
                    ends.append(end_name)
        if not ends:
            return None
        return (f"SUBSURF will DOME the flat cap(s) at {', '.join(ends)} — a capped primitive "
                f"with no holding edge loop near the cap rounds the flat end into a dome (the "
                f"'sits on a point' trap). Add a holding loop just inside the cap "
                f"(edit op=loop_cut near the rim) before subsurf, or expect the rounding.")
    finally:
        bm.free()


def add_modifier(params):
    mod_type = params.get("type", "SUBSURF").upper()
    name     = params.get("name", mod_type.capitalize())
    target   = params.get("target")
    # G89: for every type that DOESN'T use `target` as a partner, `target` names the
    # HOST object whose stack receives the modifier — matching modify/remove/list/apply,
    # so an ARRAY/SUBSURF/BEVEL/… lands on the named part even when it isn't active.
    # The partner family keeps host=active (their tested, documented semantics).
    if mod_type in _PARTNER_TYPES:
        # P2.8: let the agent NAME the host (the object that receives the modifier) so a
        # partner mod never lands on whatever happens to be active — the trap that made
        # target==active and produced a "target ID assignment to itself" error.
        host = params.get("host")
        if host:
            obj = bpy.data.objects.get(host)
            if obj is None:
                return {"error": f"host '{host}' not found"}
        else:
            obj = bpy.context.active_object
    elif target:
        obj = bpy.data.objects.get(target)
        if obj is None:
            return {"error": f"target '{target}' not found"}
    else:
        obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    mod = obj.modifiers.new(name=name, type=mod_type)
    if mod_type == "ARRAY":
        # G73: configure ARRAY offset explicitly. Default (no offset/factor given) is a
        # relative offset of 1.0 along X — copies touch end-to-end, one bbox length apart
        # — instead of Blender's raw default which packed copies unusably tight here.
        if params.get("offset") is None and params.get("factor") is None:
            mod.use_relative_offset = True
            mod.use_constant_offset = False
            mod.relative_offset_displace = (1.0, 0.0, 0.0)
        _configure_array(mod, params)
    if hasattr(mod, 'levels'):
        mod.levels = params.get("levels", 2)
    if hasattr(mod, 'render_levels'):
        mod.render_levels = params.get("render_levels", params.get("levels", 2))
    if hasattr(mod, 'width'):
        mod.width = params.get("width", 0.1)
    if hasattr(mod, 'segments'):
        mod.segments = params.get("segments", 1)
    if mod_type == "BEVEL":
        limit = params.get("limit_method", "ANGLE").upper()
        if hasattr(mod, 'limit_method'):
            mod.limit_method = limit
        if hasattr(mod, 'angle_limit'):
            mod.angle_limit = math.radians(params.get("angle_limit", 30.0))
    if mod_type == "MIRROR":
        axis = (params.get("axis") or "X").upper()
        use_x = "X" in axis
        use_y = "Y" in axis
        use_z = "Z" in axis
        if hasattr(mod, "use_axis"):
            mod.use_axis[0] = use_x
            mod.use_axis[1] = use_y
            mod.use_axis[2] = use_z
        merge_threshold = params.get("merge_threshold")
        if merge_threshold is not None:
            if hasattr(mod, "use_mirror_merge"):
                mod.use_mirror_merge = True
            if hasattr(mod, "merge_threshold"):
                mod.merge_threshold = float(merge_threshold)
        mirror_object = params.get("mirror_object")
        if mirror_object and hasattr(mod, "mirror_object"):
            mo = bpy.data.objects.get(mirror_object)
            if mo is None:
                obj.modifiers.remove(mod)
                return {"error": f"mirror_object '{mirror_object}' not found"}
            mod.mirror_object = mo
    if mod_type == "SHRINKWRAP":
        target_name = params.get("target")
        if not target_name:
            obj.modifiers.remove(mod)
            return {"error": "SHRINKWRAP requires 'target' (the object to wrap onto)"}
        tgt = bpy.data.objects.get(target_name)
        if tgt is None:
            obj.modifiers.remove(mod)
            return {"error": f"target '{target_name}' not found"}
        # P2.8: a SHRINKWRAP can't wrap an object onto ITSELF. Catch it with a clear
        # message (and remove the just-created modifier) instead of letting Blender raise
        # "target ID assignment to itself" deep inside and leave a half-built modifier.
        if tgt is obj:
            obj.modifiers.remove(mod)
            return {"error": (f"SHRINKWRAP target must be a DIFFERENT object than the host "
                              f"'{obj.name}' — name the surface to wrap ONTO via target=, and "
                              f"the object that receives the modifier via host= (or make it "
                              f"active). For draping a new shell over a form, prefer object op=clad.")}
        try:
            mod.target = tgt
        except Exception as e:
            obj.modifiers.remove(mod)
            return {"error": f"SHRINKWRAP target assignment failed ({e}); no modifier left behind."}
        offset = params.get("offset")
        if offset is not None and hasattr(mod, 'offset'):
            mod.offset = float(offset)
        wrap_method = params.get("wrap_method", "NEAREST_SURFACEPOINT").upper()
        if hasattr(mod, 'wrap_method'):
            mod.wrap_method = wrap_method
        # PROJECT casts each vert along ONE axis onto the target, so a bump keeps its
        # height — unlike NEAREST_SURFACEPOINT, which snaps a tip to the nearest flank
        # and flattens it. axis= picks the cast axis (default Y = depth); both
        # directions are enabled so the ray finds the surface whether it sits in front
        # of or behind the vert.
        if wrap_method == "PROJECT":
            paxis = (params.get("axis") or "Y").upper()
            for ax in ("x", "y", "z"):
                attr = f"use_project_{ax}"
                if hasattr(mod, attr):
                    setattr(mod, attr, ax == paxis.lower())
            if hasattr(mod, "use_negative_direction"):
                mod.use_negative_direction = True
            if hasattr(mod, "use_positive_direction"):
                mod.use_positive_direction = True
        # vertex_group confines the wrap to a weighted region and PINS everything at
        # weight 0 — so a partial transfer (e.g. just the breast) leaves the rest of
        # the mesh, and its boundary ring, exactly in place: no separate / weld, no
        # seam. Mint the group from a selection with edit op... assign_weight first.
        vgroup = params.get("vertex_group")
        if vgroup:
            if vgroup not in obj.vertex_groups:
                obj.modifiers.remove(mod)
                return {"error": f"vertex_group '{vgroup}' not found on '{obj.name}' "
                                 f"(have: {[g.name for g in obj.vertex_groups]})"}
            mod.vertex_group = vgroup
    # Deform modifiers that bind/track another object. All three drive obj's
    # geometry from a partner via mod.object (a cage mesh, an armature, a lattice)
    # — the recovery door for production deform stacks (gaps.md V1). MESH_DEFORM is
    # added unbound; bind it with bind_mesh_deform.
    if mod_type in ("MESH_DEFORM", "ARMATURE", "LATTICE"):
        target_name = params.get("target")
        if not target_name:
            obj.modifiers.remove(mod)
            return {"error": f"{mod_type} requires 'target' "
                             f"(the {'cage mesh' if mod_type == 'MESH_DEFORM' else mod_type.lower()} that drives the deform)"}
        tgt = bpy.data.objects.get(target_name)
        if tgt is None:
            obj.modifiers.remove(mod)
            return {"error": f"target '{target_name}' not found"}
        expected = {"MESH_DEFORM": "MESH", "ARMATURE": "ARMATURE", "LATTICE": "LATTICE"}[mod_type]
        if tgt.type != expected:
            obj.modifiers.remove(mod)
            return {"error": f"{mod_type} target '{target_name}' must be a {expected}, "
                             f"got {tgt.type}"}
        mod.object = tgt
        if mod_type == "MESH_DEFORM":
            precision = params.get("precision")
            if precision is not None and hasattr(mod, "precision"):
                mod.precision = int(precision)
            return {"success": True, "modifier": mod.name, "bound": False,
                    "note": f"MESH_DEFORM added against cage '{target_name}' (unbound) — "
                            f"call bind_mesh_deform('{obj.name}') to bind it."}
    # CORRECTIVE_SMOOTH: corrects deform-skinning collapse on bends. Two rest
    # sources — ORCO (smooth toward the base mesh, no bind) and BIND (smooth toward
    # a captured pose, vertex-keyed like mesh-deform). Created unbound here; default
    # rest_source=BIND so rebind_deform can capture it (gaps.md W1 — the stack piece
    # the production original carried that add_modifier couldn't recreate).
    if mod_type == "CORRECTIVE_SMOOTH":
        rest_source = (params.get("rest_source") or "BIND").upper()
        if hasattr(mod, "rest_source"):
            mod.rest_source = rest_source
        factor = params.get("factor")
        if factor is not None and hasattr(mod, "factor"):
            mod.factor = float(factor)
        iterations = params.get("iterations")
        if iterations is not None and hasattr(mod, "iterations"):
            mod.iterations = int(iterations)
        note = (f"CORRECTIVE_SMOOTH added (rest_source={rest_source}, unbound) — "
                f"call rebind_deform('{obj.name}') to capture the bind."
                if rest_source == "BIND" else
                f"CORRECTIVE_SMOOTH added (rest_source=ORCO — smooths toward the base mesh).")
        return {"success": True, "modifier": mod.name, "note": note}
    out = {"success": True, "modifier": mod.name, "status_focus": obj.name}
    if mod_type == "SUBSURF":
        dome = _subsurf_dome_warning(obj)
        if dome:
            out.setdefault("notes", []).append(dome)
    if mod_type == "SOLIDIFY":
        # Let thickness/offset be set at add time (so `add type=SOLIDIFY thickness=` works
        # in one call), and report the effective WORLD wall thickness + warn on unapplied
        # scale — the silent-2× wall that bit G132.
        thickness = params.get("thickness")
        if thickness is not None and hasattr(mod, "thickness"):
            mod.thickness = float(thickness)
        offset = params.get("offset")
        if offset is not None and hasattr(mod, "offset"):
            mod.offset = float(offset)
        from .common import scale_unit_note
        eff, note = scale_unit_note(obj, mod.thickness, what="wall thickness")
        if note:
            out["world_thickness"] = eff
            out.setdefault("notes", []).append(note)
    # status_focus so the status block reports the HOST object's bounds (G89) even when
    # the modifier was added to a named, non-active object.
    return out


def bind_mesh_deform(params):
    """Bind / unbind / rebind a Mesh Deform modifier (gaps.md V1).

    MESH_DEFORM drives a mesh from a low-res cage — higher-quality cloth/skin
    deformation than direct skinning. The bind is computed once and is keyed to
    the mesh's vertex count, so any topology edit invalidates it (gaps.md V2) and
    a rebind is the recovery. Nothing in the toolset reached the bind operator
    before this; the deform stack was unrecoverable after an edit.

    mesh:      mesh carrying (or to carry) the MESH_DEFORM modifier (required).
    cage:      cage object that drives the deform. If the mesh has no MESH_DEFORM
               modifier yet, one is created against this cage; if it already has
               one, cage is optional (re-points it when given).
    modifier:  name of a specific MESH_DEFORM modifier (when the mesh has several);
               defaults to the first one on the mesh.
    action:    'bind' (default — bind if currently unbound) |
               'unbind' (drop the bind data) |
               'rebind' (unbind then bind — after a cage edit or topology change).
    precision: optional bind precision 2–10 (higher = sharper, slower bind).
    """
    mesh_name = params.get("mesh")
    if not mesh_name:
        return {"error": "'mesh' is required"}
    mesh = bpy.data.objects.get(mesh_name)
    if mesh is None or mesh.type != 'MESH':
        return {"error": f"mesh '{mesh_name}' not found or not a mesh"}
    err = linked_guard(mesh)
    if err:
        return {"error": err}

    action = (params.get("action") or "bind").lower()
    if action not in ("bind", "unbind", "rebind"):
        return {"error": "action must be 'bind', 'unbind', or 'rebind'"}

    mod_name = params.get("modifier")
    if mod_name:
        mod = mesh.modifiers.get(mod_name)
        if mod is None or mod.type != 'MESH_DEFORM':
            return {"error": f"no MESH_DEFORM modifier '{mod_name}' on '{mesh_name}'"}
    else:
        mod = next((m for m in mesh.modifiers if m.type == 'MESH_DEFORM'), None)

    cage_name = params.get("cage")
    cage = None
    if cage_name:
        cage = bpy.data.objects.get(cage_name)
        if cage is None or cage.type != 'MESH':
            return {"error": f"cage '{cage_name}' not found or not a mesh"}

    if mod is None:
        if cage is None:
            return {"error": f"'{mesh_name}' has no MESH_DEFORM modifier — pass "
                             f"'cage' to create one (or add_modifier type=MESH_DEFORM first)"}
        mod = mesh.modifiers.new(name="MeshDeform", type='MESH_DEFORM')
        mod.object = cage
    elif cage is not None:
        mod.object = cage
    if mod.object is None:
        return {"error": f"MESH_DEFORM '{mod.name}' has no cage object — pass 'cage'"}

    precision = params.get("precision")
    if precision is not None and hasattr(mod, "precision"):
        mod.precision = max(2, min(10, int(precision)))

    activate(mesh)
    override = ui_override()

    def _toggle():
        # meshdeform_bind is a toggle: binds when unbound, unbinds when bound.
        if override:
            with bpy.context.temp_override(**override):
                bpy.ops.object.meshdeform_bind(modifier=mod.name)
        else:
            bpy.ops.object.meshdeform_bind(modifier=mod.name)

    was_bound = bool(mod.is_bound)
    if action == "unbind":
        if was_bound:
            _toggle()
    elif action == "rebind":
        if was_bound:
            _toggle()  # unbind first
        _toggle()       # then bind fresh
    else:  # bind
        if not was_bound:
            _toggle()

    bound = bool(mod.is_bound)
    # A 'bind' that comes back unbound means the operator silently refused (cage
    # doesn't enclose the mesh is the usual cause) — surface it, don't claim success.
    if action in ("bind", "rebind") and not bound:
        return {"error": f"bind failed — '{mod.name}' is still unbound after the bind. "
                         f"The cage '{mod.object.name}' must be a closed volume that "
                         f"wraps '{mesh_name}' (a flat/open or zero-volume cage won't "
                         f"bind). Fix the cage, then bind again."}

    if bound:
        # X4: a fresh valid bind — record the vert count it's keyed to, so a later
        # position-only edit can be flagged as shadowed (and a topology edit as dead).
        mesh["bb_bind_vcount"] = len(mesh.data.vertices)
    push_undo(f"{action} mesh-deform '{mod.name}' on {mesh_name}")
    return {"success": True, "mesh": mesh_name, "modifier": mod.name,
            "cage": mod.object.name, "action": action, "bound": bound,
            "was_bound": was_bound}


# The three deform modifiers that store vertex-keyed bind data, each with the
# is-bound flag to read, the operator to (re)bind it, and the attribute holding
# its driving object (None for corrective-smooth, which binds the mesh to its own
# captured pose). rebind_deform dispatches on type so one verb cures whichever the
# bind-invalidation warning diagnosed.
_BIND_TYPES = {
    'MESH_DEFORM':       ("is_bound", "meshdeform_bind",       "object"),
    'SURFACE_DEFORM':    ("is_bound", "surfacedeform_bind",    "target"),
    'CORRECTIVE_SMOOTH': ("is_bind",  "correctivesmooth_bind", None),
}


def rebind_deform(params):
    """Rebind stale deform binds after a topology edit or a stack-order move (gaps.md W3).

    The recovery verb the DEFORM BIND INVALIDATED warning points at. MESH_DEFORM,
    SURFACE_DEFORM, and CORRECTIVE_SMOOTH(rest_source=BIND) each store bind data
    keyed to the mesh's vertex count + order; a topology edit (V2) or a
    move_modifier that changes the modifier's evaluated input (W1) leaves the flag
    reading bound while the bind is silently dead. Rebinding (unbind → bind)
    recomputes it against the current geometry.

    This RE-BINDS existing modifiers only — it never creates one (use add_modifier
    / bind_mesh_deform for that). bind_mesh_deform stays the MESH_DEFORM setup verb
    (it manages the cage); rebind_deform is the type-agnostic recovery verb.

    mesh:     mesh carrying the bound deform modifier(s) (required).
    modifier: name of one specific modifier; default rebinds EVERY bindable deform
              modifier on the mesh.

    A CORRECTIVE_SMOOTH set to rest_source=ORCO has no stored bind (it smooths
    toward Original Coordinates), so it is reported as such, not toggled blind.
    """
    mesh_name = params.get("mesh")
    if not mesh_name:
        return {"error": "'mesh' is required"}
    mesh = bpy.data.objects.get(mesh_name)
    if mesh is None or mesh.type != 'MESH':
        return {"error": f"mesh '{mesh_name}' not found or not a mesh"}
    err = linked_guard(mesh)
    if err:
        return {"error": err}

    mod_name = params.get("modifier")
    if mod_name:
        mod = mesh.modifiers.get(mod_name)
        if mod is None:
            return {"error": f"no modifier '{mod_name}' on '{mesh_name}'"}
        if mod.type not in _BIND_TYPES:
            return {"error": f"modifier '{mod_name}' is {mod.type}, not a bindable deform "
                             f"modifier (MESH_DEFORM / SURFACE_DEFORM / CORRECTIVE_SMOOTH)"}
        targets = [mod]
    else:
        targets = [m for m in mesh.modifiers if m.type in _BIND_TYPES]
        if not targets:
            return {"error": f"'{mesh_name}' has no MESH_DEFORM / SURFACE_DEFORM / "
                             f"CORRECTIVE_SMOOTH modifier to rebind"}

    activate(mesh)
    override = ui_override()

    def _bind_op(mod):
        op = getattr(bpy.ops.object, _BIND_TYPES[mod.type][1])
        if override:
            with bpy.context.temp_override(**override):
                op(modifier=mod.name)
        else:
            op(modifier=mod.name)

    rebound, skipped = [], []
    for mod in targets:
        flag = _BIND_TYPES[mod.type][0]
        # A corrective-smooth bind only exists when rest_source=BIND; with ORCO
        # there is no bind data to recompute — toggling the operator would just
        # create one, which is a different (unrequested) intent. Report, skip.
        if mod.type == 'CORRECTIVE_SMOOTH' and getattr(mod, "rest_source", "ORCO") != 'BIND':
            skipped.append({"modifier": mod.name, "type": mod.type,
                            "reason": "no bind data (rest source is Original Coords, not Bind)"})
            continue
        # MESH_DEFORM / SURFACE_DEFORM need their driving object to bind against
        # (the cage / surface, on different attributes — .object vs .target).
        driver_attr = _BIND_TYPES[mod.type][2]
        if driver_attr and getattr(mod, driver_attr, None) is None:
            skipped.append({"modifier": mod.name, "type": mod.type,
                            "reason": f"no {'cage' if mod.type == 'MESH_DEFORM' else 'target'} object set"})
            continue
        was_bound = bool(getattr(mod, flag, False))
        if was_bound:
            _bind_op(mod)   # unbind (toggle off the stale bind)
        _bind_op(mod)       # bind fresh against current geometry
        if not bool(getattr(mod, flag, False)):
            return {"error": f"rebind failed — '{mod.name}' ({mod.type}) is still unbound "
                             f"after rebinding. For MESH_DEFORM/SURFACE_DEFORM the driving "
                             f"object must enclose/cover the mesh; check it, then retry.",
                    "rebound": rebound, "skipped": skipped}
        rebound.append({"modifier": mod.name, "type": mod.type})

    if not rebound:
        # Nothing was actually rebound — every candidate was a no-bind skip. Surface
        # it as a clear (non-success) result rather than a hollow success.
        return {"error": f"nothing to rebind on '{mesh_name}' — "
                         + "; ".join(f"{s['modifier']}: {s['reason']}" for s in skipped),
                "skipped": skipped}

    mesh["bb_bind_vcount"] = len(mesh.data.vertices)  # X4: bind valid at this count
    push_undo(f"rebind {len(rebound)} deform modifier(s) on {mesh_name}")
    return {"success": True, "mesh": mesh_name, "rebound": rebound, "skipped": skipped}


_MODIFIER_PROPS = {
    "levels":        ("levels",       float),  # SUBSURF
    "render_levels": ("render_levels", int),
    "width":         ("width",        float),  # BEVEL / SOLIDIFY
    "segments":      ("segments",     int),
    "thickness":     ("thickness",    float),  # SOLIDIFY
    "offset":        ("offset",       float),  # SHRINKWRAP / SOLIDIFY
    "angle_limit":   ("angle_limit",  "radians"),  # BEVEL (degrees in → radians)
    "count":         ("count",        int),    # ARRAY
    "wrap_method":   ("wrap_method",  str),    # SHRINKWRAP
    "vertex_group":  ("vertex_group", str),    # SHRINKWRAP (limit + pin) / others
    "use_clamp":     ("use_clamp_overlap", bool),
    "factor":        ("factor",       float),  # CORRECTIVE_SMOOTH / SMOOTH strength
    "strength":      ("strength",     float),  # DISPLACE strength
    "iterations":    ("iterations",   int),    # CORRECTIVE_SMOOTH / SMOOTH passes
}


def modify_modifier(params):
    """Tweak properties on an existing modifier without rebuilding it.

    target:        object name (required).
    modifier_name: modifier name on that object (required — get it from add_modifier's return).
    target_object: SHRINKWRAP / ARRAY object-offset target (re-point at a different object).

    Plus any of these keyword props (only ones that apply to the modifier type take effect):
      levels, render_levels, width, segments, thickness, offset,
      angle_limit (degrees), count, wrap_method, use_clamp,
      factor (CORRECTIVE_SMOOTH/SMOOTH strength), strength (DISPLACE), iterations,
      show_viewport / show_render (enable-disable the modifier without removing it).

    Returns which props were actually applied vs. skipped (didn't exist on this modifier type).
    """
    target = params.get("target")
    if not target:
        return {"error": "'target' (object name) is required"}
    obj = bpy.data.objects.get(target)
    if obj is None:
        return {"error": f"Object '{target}' not found"}
    mod_name = params.get("modifier_name")
    if not mod_name:
        return {"error": "'modifier_name' is required"}
    mod = obj.modifiers.get(mod_name)
    if mod is None:
        return {"error": f"Modifier '{mod_name}' not found on '{target}'. "
                          f"Available: {[m.name for m in obj.modifiers]}"}

    applied = []
    skipped = []

    # X5: enable/disable toggles live on EVERY modifier (not in the prop table). The
    # escape hatch for a modifier that's actively harmful mid-edit (e.g. a deform
    # bind shadowing a rest-shape edit) — disable it without remove_modifier throwing
    # away production-tuned settings.
    for flag in ("show_viewport", "show_render"):
        if flag in params:
            setattr(mod, flag, bool(params[flag]))
            applied.append(f"{flag}={bool(params[flag])}")

    target_object = params.get("target_object")
    if target_object is not None:
        if hasattr(mod, "target"):
            tgt = bpy.data.objects.get(target_object)
            if tgt is None:
                return {"error": f"target_object '{target_object}' not found"}
            mod.target = tgt
            applied.append(f"target={target_object}")
        else:
            skipped.append("target_object")

    # G73: ARRAY offset is a vector + boolean toggles, not a scalar the generic table
    # below can set — intercept it here and consume the keys so they don't get
    # mis-skipped (this is why `factor` on an ARRAY used to report "skipped").
    if mod.type == 'ARRAY':
        applied.extend(_configure_array(mod, params))
        for k in ("offset", "factor", "count"):
            params.pop(k, None)

    for key, (attr, coerce) in _MODIFIER_PROPS.items():
        if key not in params:
            continue
        val = params[key]
        if not hasattr(mod, attr):
            skipped.append(key)
            continue
        if coerce == "radians":
            setattr(mod, attr, math.radians(float(val)))
        elif coerce is bool:
            setattr(mod, attr, bool(val))
        elif coerce is int:
            setattr(mod, attr, int(val))
        elif coerce is float:
            setattr(mod, attr, float(val))
        else:
            setattr(mod, attr, val)
        applied.append(f"{key}={val}")

    out = {
        "success": True,
        "target": target,
        "modifier": mod.name,
        "type": mod.type,
        "applied": applied,
        "skipped": skipped,
    }
    # G132: SOLIDIFY thickness is in LOCAL units, so an unapplied object scale yields a
    # world wall thicker than the named thickness, silently. Report the effective world
    # thickness + warn whenever the thickness was just set on a scaled object.
    if mod.type == 'SOLIDIFY' and "thickness" in params:
        from .common import scale_unit_note
        eff, note = scale_unit_note(obj, mod.thickness, what="wall thickness")
        if note:
            out["world_thickness"] = eff
            out.setdefault("notes", []).append(note)
    return out


def remove_modifier(params):
    """Remove a modifier from an object by name. Use list_modifiers to see what's on it.

    target:        object name (required).
    modifier_name: modifier name (required). Use 'ALL' to clear every modifier.
    """
    target = params.get("target")
    if not target:
        return {"error": "'target' is required"}
    obj = bpy.data.objects.get(target)
    if obj is None:
        return {"error": f"Object '{target}' not found"}
    mod_name = params.get("modifier_name")
    if not mod_name:
        return {"error": "'modifier_name' is required (or 'ALL')"}
    if mod_name.upper() == "ALL":
        removed = [m.name for m in obj.modifiers]
        for m in list(obj.modifiers):
            obj.modifiers.remove(m)
        return {"success": True, "target": target, "removed": removed}
    mod = obj.modifiers.get(mod_name)
    if mod is None:
        return {"error": f"Modifier '{mod_name}' not found on '{target}'. "
                          f"Available: {[m.name for m in obj.modifiers]}"}
    obj.modifiers.remove(mod)
    return {"success": True, "target": target, "removed": [mod_name]}


def list_modifiers(params):
    """List the modifier stack on an object, in evaluation order (top → bottom).

    target: object name (required).
    """
    target = params.get("target")
    if not target:
        return {"error": "'target' is required"}
    obj = bpy.data.objects.get(target)
    if obj is None:
        return {"error": f"Object '{target}' not found"}
    stack = []
    for m in obj.modifiers:
        entry = {"name": m.name, "type": m.type}
        for attr in ("levels", "render_levels", "width", "segments", "thickness",
                     "offset", "count"):
            if hasattr(m, attr):
                entry[attr] = getattr(m, attr)
        if hasattr(m, "target") and m.target is not None:
            entry["target"] = m.target.name
        if hasattr(m, "wrap_method"):
            entry["wrap_method"] = m.wrap_method
            if m.wrap_method == "PROJECT":
                entry["project_axis"] = "".join(
                    ax.upper() for ax in ("x", "y", "z")
                    if getattr(m, f"use_project_{ax}", False)) or "none"
        if getattr(m, "vertex_group", ""):
            entry["vertex_group"] = m.vertex_group
        stack.append(entry)
    return {"success": True, "target": target, "modifiers": stack}


def move_modifier(params):
    """Reorder a modifier in the object's stack (gaps.md W1).

    Stack ORDER is semantics, not cosmetics: a deform modifier ABOVE a Subsurf
    binds against the base mesh; below it, against the 4×-denser subdivided
    result. add_modifier / bind_mesh_deform append to the BOTTOM, and nothing
    could move them before this — so a production stack whose MeshDeform belongs
    at index 0 (before Subsurf/Displace) was unrebuildable.

    target:   object name (required).
    modifier: name of the modifier to move (required).
    Exactly one destination:
      index:  absolute target index (0 = top of the stack).
      before: move it directly ABOVE this modifier (by name).
      after:  move it directly BELOW this modifier (by name).

    TRAP (handled): moving a BOUND deform modifier changes its evaluated input, so
    the bind computed at the old position dies — silently, and WITHOUT a vert-count
    change, so the V2 guard can't see it. This returns a DEFORM BIND INVALIDATED
    warning whenever it moves a bound deform modifier; the recipe is move → then
    rebind_deform.
    """
    target = params.get("target")
    if not target:
        return {"error": "'target' (object name) is required"}
    obj = bpy.data.objects.get(target)
    if obj is None:
        return {"error": f"Object '{target}' not found"}
    err = linked_guard(obj)
    if err:
        return {"error": err}
    mod_name = params.get("modifier")
    if not mod_name:
        return {"error": "'modifier' (name of the modifier to move) is required"}
    mods = obj.modifiers
    mod = mods.get(mod_name)
    if mod is None:
        return {"error": f"Modifier '{mod_name}' not found on '{target}'. "
                          f"Available: {[m.name for m in mods]}"}

    n = len(mods)
    index, before, after = params.get("index"), params.get("before"), params.get("after")
    given = [k for k, v in (("index", index), ("before", before), ("after", after)) if v is not None]
    if len(given) != 1:
        return {"error": "pass exactly one destination: index=, before=, or after="}

    cur = list(mods).index(mod)
    if index is not None:
        dest = int(index)
        if dest < 0 or dest >= n:
            return {"error": f"index {dest} out of range 0..{n - 1}"}
    else:
        ref_name = before if before is not None else after
        ref = mods.get(ref_name)
        if ref is None:
            return {"error": f"reference modifier '{ref_name}' not found on '{target}'. "
                             f"Available: {[m.name for m in mods]}"}
        if ref.name == mod.name:
            return {"error": f"'{mod_name}' can't be placed relative to itself"}
        ref_idx = list(mods).index(ref)
        # Land directly above (before) or below (after) the reference. Account for
        # the modifier vacating its current slot when it sits above the reference.
        dest = ref_idx if before is not None else ref_idx + 1
        if cur < ref_idx:
            dest -= 1
        dest = max(0, min(n - 1, dest))

    # Read bind state BEFORE the move — the move itself doesn't flip is_bound, but
    # the bind is dead against the new evaluated input (W1 trap).
    from .common import deform_bind_warning
    was_bound = (mod.type in _BIND_TYPES
                 and bool(getattr(mod, _BIND_TYPES[mod.type][0], False)))

    activate(obj)
    override = ui_override()
    if override:
        with bpy.context.temp_override(**override):
            bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=dest)
    else:
        bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=dest)

    result = {"success": True, "target": target, "modifier": mod.name,
              "from_index": cur, "to_index": list(mods).index(mod)}
    if was_bound:
        result["bind_invalidated"] = True
        result["bind_warning"] = deform_bind_warning([(mod.name, mod.type)], cause="stackmove")
    push_undo(f"move modifier '{mod.name}' on {target} to index {dest}")
    return result


def apply_modifiers(params):
    name = params.get("name")
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    else:
        obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if obj.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    mod_names = [m.name for m in obj.modifiers]
    if not mod_names:
        return {"success": True, "applied": [], "object": obj.name}
    had_bevel = any(m.type == 'BEVEL' for m in obj.modifiers)
    applied = []
    for mod_name in mod_names:
        if any(m.name == mod_name for m in obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=mod_name)
            applied.append(mod_name)
    out = {"success": True, "applied": applied, "object": obj.name}
    # G167: a BEVEL applied next to an NGON cap drops ~one zero-area sliver face per
    # segment — a hard validate defect with no suppression path. Clean the slivers the
    # apply just produced (merge-by-distance + dissolve-degenerate) and report the count,
    # so a rounded ceramic edge can't silently ship non-renderable geometry.
    if had_bevel:
        removed = _dissolve_degenerate_faces(obj)
        if removed:
            out["degenerate_dissolved"] = removed
    return out


def _dissolve_degenerate_faces(obj, dist=3e-4):
    """Merge coincident verts + dissolve degenerate edges/faces on obj's base mesh, used
    after a BEVEL apply to clear zero-area sliver faces (G167). Returns the count of
    zero-area faces removed (0 if the apply was clean, leaving the mesh untouched)."""
    import bmesh
    me = obj.data
    if me is None:
        return 0
    before = sum(1 for p in me.polygons if p.area < 1e-9)
    if before == 0:
        return 0
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=dist)
    try:
        bmesh.ops.dissolve_degenerate(bm, dist=dist, edges=bm.edges[:])
    except Exception:
        pass
    bm.to_mesh(me)
    bm.free()
    me.update()
    after = sum(1 for p in me.polygons if p.area < 1e-9)
    return max(0, before - after)


def convert_to_mesh(params):
    """Bake a non-mesh object (curve / text / metaball) into a real mesh.

    Object > Convert > Mesh: evaluates the full result — modifiers, the curve's
    bevel/extrude, and any hooks — and replaces the object's data with that mesh.
    The R4 following rope is a LIVE curve; once the rig is posed, one
    convert_to_mesh bakes the beveled, hook-deformed tube into game-ready,
    texturable geometry (a curve still can't take set_textured_material's UVs as
    cleanly as a mesh, and isn't export geometry). Already-mesh objects are a
    no-op, reported not errored.

    name: object name. If omitted, the active object.
    """
    name = params.get("name")
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
    else:
        obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    if obj.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    was_type = obj.type
    if was_type == 'MESH':
        return {"success": True, "object": obj.name, "converted": False,
                "from_type": "MESH", "note": "already a mesh"}
    activate(obj)
    bpy.ops.object.convert(target='MESH')
    me = obj.data
    return {"success": True, "object": obj.name, "converted": True,
            "from_type": was_type,
            "vertices": len(me.vertices), "faces": len(me.polygons)}


def _has_open_boundary_obj(obj):
    """True if obj's base mesh has any open boundary edge (1 linked face) — i.e. it isn't
    watertight, which makes it a fragile boolean operand (G127)."""
    import bmesh
    if obj is None or obj.type != 'MESH' or obj.data is None:
        return False
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    val = any(len(e.link_faces) == 1 for e in bm.edges)
    bm.free()
    return val


def _weld_clean(obj):
    """Merge coincident verts + dissolve degenerate edges/faces on obj's base mesh — the
    sliver junk a boolean UNION leaves at a tangential join (G109). Returns verts removed."""
    import bmesh
    if obj is None or obj.type != 'MESH' or obj.data is None:
        return 0
    me = obj.data
    before = len(me.vertices)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    try:
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
    except Exception:
        pass
    bm.to_mesh(me)
    bm.free()
    me.update()
    return max(0, before - len(me.vertices))


def _recalc_normals_outside(obj):
    """Recalculate consistent OUTWARD-facing normals on obj's base mesh — Blender's
    Mesh ▸ Normals ▸ Recalculate Outside (Shift-N). Idempotent: on an already-correct
    winding it is a no-op (it never regret-flips a correct result), and it repairs a
    fully-inverted shell (G175)."""
    import bmesh
    if obj is None or obj.type != 'MESH' or obj.data is None:
        return
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    me.update()


def boolean(params):
    """Cut, fuse, or intersect two meshes via a Boolean modifier.

    target:      the mesh that will be modified (kept after the op).
    cutter:      the mesh used as the operand. Typically hidden after the op.
    op:          DIFFERENCE (default — subtract cutter from target),
                 UNION       (fuse them),
                 INTERSECT   (keep only the overlap).
    solver:      EXACT (default — robust, slower) | FAST (legacy, brittle).
    apply:       if True, apply the modifier immediately and bake into target's mesh.
                 If False, leave the modifier live so you can tweak the cutter
                 and see updates. Default False.
    hide_cutter: hide the cutter object in viewport + render after the op (default True).

    KNOWN FRAGILITY: boolean ops are sensitive to mesh quality. They fail or
    produce garbage on non-manifold meshes, overlapping coplanar faces, and
    objects with un-applied non-uniform scale. If apply fails, run
    `apply_transform(targets='target,cutter', scale=True)` first and retry.
    The modifier is left in place on apply failure so you can inspect it.
    """
    target_name = params.get("target")
    cutter_name = params.get("cutter")
    op          = (params.get("op", "DIFFERENCE") or "DIFFERENCE").upper()
    solver      = (params.get("solver", "EXACT") or "EXACT").upper()
    apply       = bool(params.get("apply", False))
    hide_cutter = bool(params.get("hide_cutter", True))

    if not target_name or not cutter_name:
        return {"error": "'target' and 'cutter' are required"}
    target = bpy.data.objects.get(target_name)
    cutter = bpy.data.objects.get(cutter_name)
    if target is None: return {"error": f"target '{target_name}' not found"}
    if cutter is None: return {"error": f"cutter '{cutter_name}' not found"}
    if target == cutter: return {"error": "target and cutter must be different objects"}
    if target.type != 'MESH' or cutter.type != 'MESH':
        return {"error": "both target and cutter must be mesh objects"}
    if op not in ("UNION", "DIFFERENCE", "INTERSECT"):
        return {"error": "op must be UNION, DIFFERENCE, or INTERSECT"}
    if solver not in ("EXACT", "FAST"):
        return {"error": "solver must be EXACT or FAST"}

    # G127: a non-watertight operand (open boundary edges) makes the EXACT solver leave
    # internal membranes / dangling faces — the 14-edge non-manifold mess a tube-into-wall
    # union produced. Flag it up front so the result isn't silently fused into a defect.
    open_notes = []
    for label_, ob in (("target", target), ("cutter", cutter)):
        if _has_open_boundary_obj(ob):
            open_notes.append(label_)

    mod_name = f"bool_{op.lower()}_{cutter_name}"
    mod = target.modifiers.new(name=mod_name, type='BOOLEAN')
    mod.operation = op
    mod.object = cutter
    if hasattr(mod, "solver"):
        mod.solver = solver

    applied = False
    apply_error = None
    empty_result = False
    if apply:
        # Preview the modifier result before baking. A DIFFERENCE against a
        # multi-island mesh whose islands interpenetrate can collapse the target to
        # zero verts, and modifier_apply reports success on that empty result
        # (gaps.md T8) — one render later it's "where did the part go". Check the
        # evaluated mesh first; refuse to bake a 0-vert result and leave the
        # modifier live (the base mesh is untouched until apply), exactly the way
        # an apply failure already leaves the modifier for inspection.
        bpy.context.view_layer.update()
        eval_obj = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
        eval_mesh = eval_obj.to_mesh()
        result_verts = len(eval_mesh.vertices)
        eval_obj.to_mesh_clear()
        if result_verts == 0:
            empty_result = True
        else:
            activate(target)
            try:
                bpy.ops.object.modifier_apply(modifier=mod.name)
                applied = True
            except RuntimeError as e:
                apply_error = str(e)

    # G109/G127: a UNION across a thin-wall/tangential join shatters into sliver/degenerate
    # boundary loops + coincident verts. Weld them once the result is baked — merge doubles
    # and dissolve degenerate edges/faces — so the output isn't left a non-manifold mess.
    welded = 0
    if applied and bool(params.get("clean", True)):
        welded = _weld_clean(target)

    # G175: a second sequential EXACT boolean on a mesh that is ALREADY a boolean result
    # can flip the whole shell's winding (normals face inward) — Blender's boolean apply
    # doesn't guarantee consistent outward normals, and _weld_clean above only touches
    # doubles/degenerates, never winding. Recalculate consistent-outside after every applied
    # boolean so chained cuts can't ship an inverted mesh. recalc-outside is the safe choice:
    # a no-op on a correctly-wound result, a repair on an inverted one.
    normals_recalced = False
    if applied:
        _recalc_normals_outside(target)
        normals_recalced = True

    if hide_cutter:
        try:
            cutter.hide_set(True)
        except Exception:
            pass
        cutter.hide_render = True

    result = {
        "success": True,
        "target": target_name,
        "cutter": cutter_name,
        "op": op,
        "solver": solver,
        "applied": applied,
        "modifier": None if applied else mod.name,
        "cutter_hidden": hide_cutter,
    }
    if welded:
        result["welded_verts"] = welded
    if normals_recalced:
        result["normals_recalc_outside"] = True
    if open_notes:
        result.setdefault("notes", []).append(
            f"boolean operand(s) {', '.join(open_notes)} are NOT watertight (open boundary "
            f"edges) — EXACT can leave internal membranes / non-manifold edges here. Cap the "
            f"operand(s) (object op=hollow open=none, or fill the rim) before the boolean, or "
            f"check the result with feel op=topology. (The topology-delta floor will flag new "
            f"non-manifold edges this op leaves.)")
    if apply_error is not None:
        result["apply_error"] = apply_error
        result["hint"] = (
            "boolean apply failed — likely non-manifold geometry, overlapping "
            "faces, or un-applied scale. Try apply_transform(scale=True) on both "
            "objects, or set solver='FAST'. Modifier is still on the target so "
            "you can inspect or remove_modifier."
        )
    if empty_result:
        result["empty_result"] = True
        result["warning"] = (
            f"REFUSED TO APPLY: the {op} result is an empty mesh (0 verts) — "
            f"baking it would silently delete '{target_name}'. The modifier is left "
            f"live and unapplied (base mesh intact); inspect it or remove_modifier. "
            f"For a multi-island target, split_by_part and boolean the relevant "
            f"island alone (gaps.md T8)."
        )
    return result


TOOLS = {
    "smooth_edges":    smooth_edges,
    "round_corners":   round_corners,
    "bend":            bend,
    "noise_displace":  noise_displace,
    "add_modifier":    add_modifier,
    "bind_mesh_deform": bind_mesh_deform,
    "rebind_deform":   rebind_deform,
    "modify_modifier": modify_modifier,
    "remove_modifier": remove_modifier,
    "list_modifiers":  list_modifiers,
    "move_modifier":   move_modifier,
    "apply_modifiers": apply_modifiers,
    "convert_to_mesh": convert_to_mesh,
    "boolean":         boolean,
}

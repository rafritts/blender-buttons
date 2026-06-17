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


def add_modifier(params):
    mod_type = params.get("type", "SUBSURF").upper()
    name     = params.get("name", mod_type.capitalize())
    obj      = bpy.context.active_object
    if obj is None:
        return {"error": "No active object"}
    mod = obj.modifiers.new(name=name, type=mod_type)
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
        mod.target = tgt
        offset = params.get("offset")
        if offset is not None and hasattr(mod, 'offset'):
            mod.offset = float(offset)
        wrap_method = params.get("wrap_method", "NEAREST_SURFACEPOINT").upper()
        if hasattr(mod, 'wrap_method'):
            mod.wrap_method = wrap_method
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
    return {"success": True, "modifier": mod.name}


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

    return {
        "success": True,
        "target": target,
        "modifier": mod.name,
        "type": mod.type,
        "applied": applied,
        "skipped": skipped,
    }


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
    applied = []
    for mod_name in mod_names:
        if any(m.name == mod_name for m in obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=mod_name)
            applied.append(mod_name)
    return {"success": True, "applied": applied, "object": obj.name}


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

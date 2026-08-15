"""Bundled finishes: bend, add_modifier, apply_modifiers, materials."""

import math
import os

import bpy

from .common import activate, linked_guard, resolve_targets, world_bbox
from .state import push_undo, ui_override


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

    # G211: refuse BEFORE mutating when the bend axis IS an object's own dominant long
    # axis — bending around the length pivots in a plane that barely changes the shape
    # (the degenerate case that used to mutate then warn after, costing an undo). Checked
    # for every target up front so a batch refuses cleanly before touching any of them.
    # The 1.1× guard skips near-cube objects, where no axis is meaningfully "the length".
    for o in objs:
        if o.type != 'MESH':
            continue
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
        dims = (xmax - xmin, ymax - ymin, zmax - zmin)
        long_axis = "XYZ"[dims.index(max(dims))]
        dominant = max(dims) > 1.1 * sorted(dims)[-2]
        if long_axis == axis and dominant:
            perp = [a for a in "XYZ" if a != axis]
            return {"error": (
                f"bend refused before mutating: axis={axis} is '{o.name}'s own long axis "
                f"({long_axis}), so the bend pivots around the length and barely changes "
                f"the shape. Bend around a PERPENDICULAR axis to curl the length into an "
                f"arc — try axis={perp[0]} or axis={perp[1]}.")}

    bent = []
    notes = []
    for o in objs:
        if o.type != 'MESH':
            continue
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
# Modifiers whose behaviour is defined by a PARTNER object bound via mod.object /
# mod.target — host= names the RECEIVER so the modifier never lands on the partner by
# mistake, and a partner that can't be bound refuses loudly (G89/G197). Keep this a set,
# not a hardcoded branch list, so the next partner-taking type is one entry, not a repeat.
_PARTNER_TYPES = {"SHRINKWRAP", "MESH_DEFORM", "ARMATURE", "LATTICE", "CURVE"}
# Partner types bound through mod.object (SHRINKWRAP uses mod.target, handled separately),
# mapped to the object TYPE their partner must be.
_OBJECT_PARTNER_EXPECT = {"MESH_DEFORM": "MESH", "ARMATURE": "ARMATURE",
                          "LATTICE": "LATTICE", "CURVE": "CURVE"}


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
                              f"active). For a new shell that follows a form, build it natively: duplicate the surface region and add a Solidify (guidance://techniques/shell).")}
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
    # added unbound; bind it with rebind_deform.
    if mod_type in _OBJECT_PARTNER_EXPECT:
        partner_role = {"MESH_DEFORM": "cage mesh", "ARMATURE": "armature",
                        "LATTICE": "lattice", "CURVE": "curve"}[mod_type]
        target_name = params.get("target")
        if not target_name:
            obj.modifiers.remove(mod)
            return {"error": f"{mod_type} requires 'target' "
                             f"(the {partner_role} that {'shapes' if mod_type == 'CURVE' else 'drives'} the deform)"}
        tgt = bpy.data.objects.get(target_name)
        if tgt is None:
            obj.modifiers.remove(mod)
            return {"error": f"target '{target_name}' not found"}
        expected = _OBJECT_PARTNER_EXPECT[mod_type]
        if tgt.type != expected:
            obj.modifiers.remove(mod)
            return {"error": f"{mod_type} target '{target_name}' must be a {expected}, "
                             f"got {tgt.type}"}
        mod.object = tgt
        if mod_type == "CURVE":
            # deform_axis = which of the mesh's local axes runs ALONG the curve
            # (the ARRAY→CURVE chain-along-a-path pattern). axis= picks it; default X.
            ax = (params.get("axis") or "X").upper()
            deform_axis = {"X": "POS_X", "Y": "POS_Y", "Z": "POS_Z"}.get(ax, "POS_X")
            if hasattr(mod, "deform_axis"):
                mod.deform_axis = deform_axis
            return {"success": True, "modifier": mod.name, "status_focus": obj.name,
                    "note": f"CURVE bound to '{target_name}' (deform_axis={deform_axis}) — "
                            f"the mesh now bends along that curve."}
        if mod_type == "MESH_DEFORM":
            precision = params.get("precision")
            if precision is not None and hasattr(mod, "precision"):
                mod.precision = int(precision)
            return {"success": True, "modifier": mod.name, "bound": False,
                    "note": f"MESH_DEFORM added against cage '{target_name}' (unbound) — "
                            f"call rebind_deform('{obj.name}') to bind it."}
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
    if mod_type == "CLOTH":
        # G196: a cloth modifier only behaves like a garment once it's PINNED — the
        # vertex group it hangs from (else gravity slides the whole thing through the
        # floor). pin_group names that group; the sim runs via scene op=bake_physics.
        pin_group = params.get("pin_group")
        if pin_group:
            if pin_group not in obj.vertex_groups:
                obj.modifiers.remove(mod)
                return {"error": f"pin_group '{pin_group}' not found on '{obj.name}' "
                                 f"(have: {[g.name for g in obj.vertex_groups]}) — mint it "
                                 f"with pose op=assign_weight group={pin_group} first"}
            mod.settings.vertex_group_mass = pin_group
        return {"success": True, "modifier": mod.name, "status_focus": obj.name,
                "note": (f"CLOTH added (pin_group={pin_group or 'NONE — unpinned, will fall'})"
                         f". Add COLLISION to the bodies it should rest on, then run "
                         f"scene op=bake_physics frames=N to simulate.")}
    if mod_type == "COLLISION":
        # G196: the body a garment drapes over needs a COLLISION modifier or the cloth
        # passes straight through it. Defaults are fine; nothing to dial.
        return {"success": True, "modifier": mod.name, "status_focus": obj.name,
                "note": "COLLISION added — cloth/soft-body sims will now collide with this object."}
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
    # G200 — a type-specific dial passed to a type that can't use it must be REPORTED,
    # not dropped in silence (the trap that landed a 10mm default when thickness= was
    # meant for a SOLIDIFY but sent to another type). Echo it as skipped so the caller
    # isn't told plain 'success' while its value evaporated.
    _dial_owner = {"thickness": "SOLIDIFY", "angle_limit": "BEVEL"}
    skipped_dials = [f"{d} (only {owner})" for d, owner in _dial_owner.items()
                     if params.get(d) is not None and mod_type != owner]
    if skipped_dials:
        out["skipped"] = skipped_dials
        out.setdefault("notes", []).append(
            f"ignored dial(s) not used by {mod_type}: {', '.join(skipped_dials)}")
    # status_focus so the status block reports the HOST object's bounds (G89) even when
    # the modifier was added to a named, non-active object.
    return out


# Bind-flag / bind-op / driver-attr per deform type. Used by rebind_deform and
# move_modifier (W1/W3). Restored after SPEC-22 Phase 2 deleted the dict and
# left every use behind (bugs.md B8).
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
    for that). add_modifier adds the MESH_DEFORM cage unbound; rebind_deform is the
    type-agnostic verb that binds and re-binds it.

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

    # G191: a Geometry-Nodes modifier's dials are its socket VALUES, not python props —
    # set them live here with the same {socket: value} map add_asset takes, so raising a
    # scatter's Density or toggling Realize Instances no longer forces a remove+re-add.
    if mod.type == 'NODES':
        inputs = params.get("inputs")
        if inputs:
            if mod.node_group is None:
                return {"error": f"NODES modifier '{mod_name}' has no node group to set inputs on"}
            sockets = _gn_input_sockets(mod.node_group)
            menu_maps = _menu_maps(mod, sockets)
            set_inputs, unknown = _set_gn_inputs(mod, sockets, inputs, menu_maps)
            mod.id_data.update_tag()
            bpy.context.view_layer.update()
            for name, v in set_inputs.items():
                applied.append(f"{name}={v}")
            if unknown:
                skipped.extend(unknown)
            out = {"success": True, "target": target, "modifier": mod.name,
                   "type": mod.type, "applied": applied, "skipped": skipped,
                   "inputs_available": _describe_inputs(mod, sockets, menu_maps)}
            if unknown:
                out.setdefault("notes", []).append(
                    f"unrecognised input(s) {unknown} — settable inputs: {list(sockets)}")
            return out

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
    result. add_modifier appends to the BOTTOM, and nothing
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
    realized = []
    warnings = []
    for mod_name in mod_names:
        m = next((x for x in obj.modifiers if x.name == mod_name), None)
        if m is None:
            continue
        # G207: a NODES modifier whose output is instances-on-points (Realize Instances
        # off, the default) silently DROPS them on apply — the mesh comes back without the
        # scatter. Flip its 'Realize Instances' input True first so they bake into editable
        # geometry; if the group has no such input, leave it LIVE rather than lose it.
        if m.type == 'NODES' and m.node_group is not None:
            n_inst = _evaluated_instance_count(obj)
            if n_inst:
                socks = _gn_input_sockets(m.node_group)
                ri = next((ident for nm, (ident, _st) in socks.items()
                           if nm.strip().lower() == "realize instances"), None)
                if ri is not None:
                    try:
                        _gn_set(m, ri, True)
                        m.id_data.update_tag()
                        bpy.context.view_layer.update()
                        realized.append({"modifier": mod_name, "instances": n_inst})
                    except Exception as e:
                        warnings.append(f"could not set Realize Instances on '{mod_name}': {e}")
                else:
                    warnings.append(
                        f"'{mod_name}' emits {n_inst} instance(s) but its node group has no "
                        "'Realize Instances' input — LEFT LIVE (applying would drop them). "
                        "Add a Realize Instances node in the group, then apply.")
                    continue
        bpy.ops.object.modifier_apply(modifier=mod_name)
        applied.append(mod_name)
    out = {"success": True, "applied": applied, "object": obj.name}
    if realized:
        out["realized_instances"] = realized
    if warnings:
        out["warnings"] = warnings
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
    texturable geometry (a curve still can't take UV-projected textures as
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
    solver:      EXACT (default — robust, slower) | FLOAT (fast, brittle; Blender 5.0
                 renamed the old "Fast" solver to "Float"). Legacy "FAST" is accepted and
                 mapped to FLOAT.
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
    # Blender 5.0 renamed the Boolean solver value "FAST" -> "FLOAT" (PR#141686), across the
    # modifier, the edit-mode operator, and the Python enum. Accept the legacy name so older
    # recipes/callers keep working, but write the 5.x value to the modifier.
    if solver == "FAST":
        solver = "FLOAT"
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
    if solver not in ("EXACT", "FLOAT"):
        return {"error": "solver must be EXACT or FLOAT (legacy 'FAST' is mapped to FLOAT)"}

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
            f"operand(s) (give it walls with a Solidify, or fill the rim with edit op=grid_fill) before the boolean, or "
            f"check the result with feel op=topology. (The topology-delta floor will flag new "
            f"non-manifold edges this op leaves.)")
    if apply_error is not None:
        result["apply_error"] = apply_error
        result["hint"] = (
            "boolean apply failed — likely non-manifold geometry, overlapping "
            "faces, or un-applied scale. Try apply_transform(scale=True) on both "
            "objects, or set solver='FLOAT'. Modifier is still on the target so "
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


def _essentials_geonode_blends():
    """Every bundled Essentials geometry-nodes .blend in THIS build (SPEC-20 II.5).

    Blender 5.0 ships the new GN modifiers (Scatter on Surface, GN Array, Instance on
    Elements, Randomize Instances, Curve to Tube, Geometry Input) as node-group ASSETS
    under the app's datafiles — not as typed modifiers. We DISCOVER them from the live
    build rather than hardcode an asset-identifier string (R3: derive from the build).

    The on-disk LAYOUT differs by version — confirmed live, not from memory:
      • Blender 5.1: consolidated into  assets/nodes/geometry_nodes_essentials.blend
      • 4.x-era:     one file per asset  assets/geometry_nodes/<name>.blend
    So we scan assets/ recursively and keep every .blend whose path or filename names
    'geometry_nodes' — covers both layouts and is robust to the next reshuffle."""
    import glob, os
    assets = os.path.join(bpy.utils.system_resource('DATAFILES'), "assets")
    found = [p for p in glob.glob(os.path.join(assets, "**", "*.blend"), recursive=True)
             if "geometry_nodes" in p.lower()]
    return sorted(set(found))


def _find_asset_node_group(asset):
    """Return a GeometryNodeTree named `asset`, appending it from the Essentials library
    if it isn't already in bpy.data. Match is exact first, then case-insensitive.
    Returns (node_group, error_str) — exactly one is non-None."""
    # Already appended in a prior call? Reuse it (don't append a .001 duplicate).
    existing = bpy.data.node_groups.get(asset)
    if existing is not None and existing.bl_idname == 'GeometryNodeTree':
        return existing, None

    want = asset.strip().lower()
    available = []
    for path in _essentials_geonode_blends():
        try:
            with bpy.data.libraries.load(path, link=False, assets_only=True) as (src, dst):
                names = list(src.node_groups)
                available.extend(names)
                match = next((n for n in names if n == asset), None) \
                    or next((n for n in names if n.lower() == want), None)
                if match:
                    dst.node_groups = [match]
                else:
                    continue
        except Exception as e:  # unreadable .blend — skip, keep scanning
            continue
        ng = bpy.data.node_groups.get(match)
        if ng is not None:
            return ng, None
    if not _essentials_geonode_blends():
        return None, ("no bundled geometry-nodes Essentials assets found in this build "
                      f"({os.path.join(bpy.utils.system_resource('DATAFILES'),'assets','geometry_nodes')})")
    return None, (f"asset node-group '{asset}' not found in the Essentials library. "
                  f"Available: {sorted(set(available))}")


def _gn_input_sockets(ng):
    """Map of {socket-name: (identifier, socket_type)} for a node group's INPUT sockets
    (the modifier's exposed dials). Identifiers are stable; names/indices are not."""
    out = {}
    for item in ng.interface.items_tree:
        if getattr(item, "item_type", None) == 'SOCKET' and getattr(item, "in_out", None) == 'INPUT':
            out[item.name] = (item.identifier, getattr(item, "socket_type", ""))
    return out


def _gn_input_prop(mod, ident):
    """Blender 5.2+: Geometry Nodes modifier inputs are RNA under
    `mod.properties.inputs.<identifier>` (release notes 1561c1ea4a). Pre-5.2 used
    IDProperties (`mod[ident]`). Returns the RNA input wrapper or None on older builds /
    missing sockets."""
    props = getattr(mod, "properties", None)
    inputs = getattr(props, "inputs", None) if props is not None else None
    if inputs is None:
        return None
    return getattr(inputs, ident, None)


def _gn_get(mod, ident):
    """Read a NODES-modifier input value (5.2 RNA `.value`, else IDProperty)."""
    prop = _gn_input_prop(mod, ident)
    if prop is not None and hasattr(prop, "value"):
        return prop.value
    return mod[ident]


def _gn_set(mod, ident, val):
    """Write a NODES-modifier input value (5.2 RNA `.value`, else IDProperty)."""
    prop = _gn_input_prop(mod, ident)
    if prop is not None and hasattr(prop, "value"):
        prop.value = val
        return
    mod[ident] = val


def _menu_options(ng):
    """G204 — {menu_socket_identifier: [item_name, ...]} for every NodeSocketMenu input,
    read by walking each menu socket from the Group Input node to the Menu Switch node it
    drives (whose enum_definition holds the item NAMES). On pre-5.2 builds the int stored
    in the modifier's IDProperty is an INDEX into this list (see B7 / `_menu_value_map`);
    on 5.2+ menus are RNA string enums and this walk is only a fallback."""
    opts = {}
    for node in ng.nodes:
        if node.type != 'GROUP_INPUT':
            continue
        for out_sock in node.outputs:
            for link in out_sock.links:
                tgt = link.to_node
                if tgt.bl_idname == 'GeometryNodeMenuSwitch':
                    try:
                        items = [it.name for it in tgt.enum_definition.enum_items]
                    except Exception:
                        continue
                    if items and out_sock.identifier not in opts:
                        opts[out_sock.identifier] = items
    return opts


def _menu_value_map(mod, ident):
    """B7 — AUTHORITATIVE {option_display_name: stored_value} for a NODES-modifier menu
    socket.

    Blender 5.2+: RNA enum on `mod.properties.inputs.<id>.value` — stored value is the
    enum *identifier* (a string). Read enum_items from the property RNA.

    Pre-5.2: IDProperty int whose VALUE is NOT the node-graph declaration order (Scatter
    on Surface stores Instance Type Object=1/Collection=0, Density Method Density=1/
    Amount=0 — both REVERSED). Writing the walk index selected the wrong option (live
    donut bug). Prefer `id_properties_ui` items so writes match the N-panel.

    Empty {} if neither path is readable (caller falls back to walk order)."""
    prop = _gn_input_prop(mod, ident)
    if prop is not None:
        try:
            rna = prop.bl_rna.properties.get("value")
            if rna is not None and getattr(rna, "enum_items", None):
                # display name → enum identifier (usually identical; identifier is what
                # prop.value stores / accepts).
                return {it.name: it.identifier for it in rna.enum_items}
        except Exception:
            pass
    try:
        items = mod.id_properties_ui(ident).as_dict().get("items") or []
        # each item tuple is (identifier, name, description, icon, value)
        return {it[1]: it[4] for it in items}
    except Exception:
        return {}


def _menu_maps(mod, sockets):
    """{menu_socket_identifier: {option_name: stored_value}} for every menu socket on
    `mod`. Prefer `_menu_value_map` (5.2 RNA enums / pre-5.2 id_properties_ui); fall back
    to node-graph declaration order (name→index) only when those are unreadable."""
    walk = _menu_options(mod.node_group)
    out = {}
    for _name, (ident, stype) in sockets.items():
        if stype != 'NodeSocketMenu':
            continue
        vm = _menu_value_map(mod, ident)
        if not vm:
            vm = {nm: i for i, nm in enumerate(walk.get(ident, []))}
        if vm:
            out[ident] = vm
    return out


def _describe_inputs(mod, sockets, menu_maps):
    """G204 — legible list of a NODES modifier's inputs: name, type, current value, and —
    for menu sockets — the options BY NAME. Replaces the old bare name list so magic ints
    are never a blind sweep. Returns a list of one-line strings."""
    out = []
    for name, (ident, stype) in sockets.items():
        short = stype.replace("NodeSocket", "") or "?"
        try:
            cur = _gn_get(mod, ident)
        except Exception:
            cur = None
        if stype == 'NodeSocketMenu':
            vm = menu_maps.get(ident, {})
            # B7 / 5.2: resolve stored value back to a display name via the value map
            # (int on pre-5.2; string enum identifier on 5.2 — often equals the name).
            curname = next((nm for nm, v in vm.items() if v == cur), cur)
            if curname is None or (isinstance(curname, str) is False and cur is not None):
                # 5.2 already stores the identifier string; prefer that over a raw int.
                curname = cur if isinstance(cur, str) else curname
            opts = "|".join(vm.keys()) if vm else "?"
            out.append(f"{name} (menu: {opts} = {curname})")
        elif stype in ('NodeSocketObject', 'NodeSocketCollection'):
            out.append(f"{name} ({short} = {getattr(cur, 'name', cur)})")
        else:
            if isinstance(cur, float):
                cur = round(cur, 4)
            elif hasattr(cur, "__len__") and not isinstance(cur, str):
                cur = [round(c, 4) if isinstance(c, float) else c for c in cur]
            out.append(f"{name} ({short} = {cur})")
    return out


def _pick_instance_advisory(mod, sockets):
    """G226 — if a GN instancer's source is a multi-prototype collection and
    Pick Instance is off, all K prototypes stack on every point. Returns a
    teaching note or None. Never auto-flips the socket (the density-floor
    warning doesn't either)."""
    assigned = []
    for name, (ident, stype) in sockets.items():
        if stype != 'NodeSocketCollection':
            continue
        try:
            val = _gn_get(mod, ident)
        except Exception:
            continue
        if val is None:
            continue
        coll = val if hasattr(val, "all_objects") else bpy.data.collections.get(
            getattr(val, "name", None) or str(val))
        if coll is None:
            continue
        n = len(list(coll.all_objects))
        if n > 1:
            assigned.append((coll.name, n))
    if not assigned:
        return None
    pick_on = None
    for name, (ident, stype) in sockets.items():
        if stype != 'NodeSocketBool':
            continue
        if name.strip().lower().replace("_", " ") != "pick instance":
            continue
        try:
            pick_on = bool(_gn_get(mod, ident))
        except Exception:
            pick_on = None
        break
    if pick_on is True:
        return None
    if pick_on is None:
        return None
    coll_name, k = assigned[0]
    return (f"⚠ collection '{coll_name}' has {k} prototypes and Pick Instance is off "
            f"— all {k} will stack on every point. Set Pick Instance=True to draw "
            f"one at random.")


def _evaluated_instance_count(obj):
    """G206 — number of instances `obj`'s modifier stack currently emits, read from the
    evaluated depsgraph (the ground truth a Scatter/Instance modifier otherwise hides).
    None if the read fails."""
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        n = 0
        for inst in dg.object_instances:
            if inst.is_instance and inst.parent is not None and inst.parent.original == obj:
                n += 1
        return n
    except Exception:
        return None


def _set_gn_inputs(mod, sockets, inputs, menu_maps=None):
    """Set {socket-name: value} on a NODES modifier by socket IDENTIFIER, matching names
    case-insensitively. Collection/Object-typed sockets take a datablock NAME; MENU sockets
    (G204) take the option NAME, resolved to the stored value via menu_maps (B7): an int
    on pre-5.2 IDProperties, a string enum identifier on 5.2+ RNA. Shared by add_asset
    (create-time) and modify (live-edit, G191).

    B7: `set_inputs` reports the EFFECTIVE value read back from the modifier, not the value we
    asked for — a write that silently fails to latch (e.g. a bad menu mapping) surfaces as a
    mismatch note instead of a phantom success the readback would otherwise launder.
    Returns (set_inputs, unknown)."""
    menu_maps = menu_maps or {}
    set_inputs, unknown = {}, []
    for key, val in (inputs or {}).items():
        match = next((n for n in sockets if n == key), None) \
            or next((n for n in sockets if n.lower() == str(key).strip().lower()), None)
        if match is None:
            unknown.append(key)
            continue
        ident, stype = sockets[match]
        want = inputs[key]
        if stype == 'NodeSocketCollection':
            val = bpy.data.collections.get(val)
        elif stype == 'NodeSocketObject':
            val = bpy.data.objects.get(val)
        elif stype == 'NodeSocketMenu' and isinstance(val, str):
            # Resolve display NAME → stored value (int pre-5.2 / string enum id on 5.2).
            # Also accept a direct match on the stored identifier itself.
            vm = menu_maps.get(ident, {})
            want_l = val.strip().lower()
            hit = next((v for nm, v in vm.items() if nm.lower() == want_l), None)
            if hit is None:
                hit = next((v for _nm, v in vm.items() if str(v).lower() == want_l), None)
            if hit is None:
                unknown.append(f"{key} (menu value '{val}' not one of {list(vm) or '?'})")
                continue
            val = hit
        try:
            _gn_set(mod, ident, val)
        except Exception as e:
            unknown.append(f"{key} (set failed: {e})")
            continue
        # B7: verify the write landed by reading the modifier's effective state back, and
        # report THAT (not the requested value). A silent no-op becomes visible.
        try:
            eff = _gn_get(mod, ident)
        except Exception:
            eff = None
        if stype == 'NodeSocketMenu':
            vm = menu_maps.get(ident, {})
            set_inputs[match] = next((nm for nm, v in vm.items() if v == eff), eff)
            if eff != val:
                unknown.append(f"{key} (write did not latch: asked '{want}', "
                               f"effective '{set_inputs[match]}')")
        elif stype in ('NodeSocketCollection', 'NodeSocketObject'):
            set_inputs[match] = getattr(eff, "name", None)
            if eff is None and want:
                unknown.append(f"{key} (datablock '{want}' not found / not set)")
        else:
            # Vector/Color sockets read back as bpy arrays (not JSON-serializable);
            # coerce to a plain rounded list. Scalars pass through. Force float() so bpy
            # subtypes never leak into the tool result.
            if hasattr(eff, "__len__") and not isinstance(eff, (str, bytes)):
                try:
                    eff = [round(float(c), 4) for c in eff]
                except (TypeError, ValueError):
                    eff = list(eff)
            elif isinstance(eff, (float, int)) and not isinstance(eff, bool):
                eff = round(float(eff), 4)
            set_inputs[match] = eff
    return set_inputs, unknown


def add_asset_modifier(params):
    """Add a Geometry-Nodes modifier that points at a bundled Essentials node-group asset
    (SPEC-20 II.5) — the path `modifiers.new(type=...)` can't reach. This is what retires
    the bespoke `scatter_on_surface` sampler: `asset="Scatter on Surface"`.

    asset:      the Essentials node-group name (e.g. "Scatter on Surface", "Curve to Tube").
    host/target: object that receives the modifier (defaults to active).
    name:       modifier name (defaults to the asset name).
    collection: convenience — assign this collection to the modifier's first Collection-typed
                input (the instance source for Scatter on Surface → multi-prototype sprinkles).
    inputs:     dict {socket-name: value} set by socket IDENTIFIER (Density, Seed, …).
    """
    asset = (params.get("asset") or "").strip()
    if not asset:
        return {"error": "'asset' (Essentials node-group name) is required"}
    host = params.get("host") or params.get("target")
    obj = bpy.data.objects.get(host) if host else bpy.context.active_object
    if obj is None:
        return {"error": f"host '{host}' not found" if host else "no active object"}

    ng, err = _find_asset_node_group(asset)
    if err:
        return {"error": err}

    name = params.get("name") or asset
    mod = obj.modifiers.new(name=name, type='NODES')
    mod.node_group = ng

    sockets = _gn_input_sockets(ng)
    menu_maps = _menu_maps(mod, sockets)
    set_inputs = {}
    unknown_inputs = []

    # collection= → the first Collection-typed input socket.
    coll_name = params.get("collection")
    if coll_name:
        coll = bpy.data.collections.get(coll_name)
        if coll is None:
            obj.modifiers.remove(mod)
            return {"error": f"collection '{coll_name}' not found"}
        coll_socket = next((n for n, (_id, t) in sockets.items() if t == 'NodeSocketCollection'), None)
        if coll_socket is None:
            obj.modifiers.remove(mod)
            return {"error": f"'{asset}' has no Collection input to assign collection='{coll_name}'",
                    "inputs_available": _describe_inputs(mod, sockets, menu_maps)}
        _gn_set(mod, sockets[coll_socket][0], coll)
        set_inputs[coll_socket] = coll_name
        # G205: the Collection socket is GATED by an instance-source menu (Scatter on
        # Surface's "Instance Type" defaults to 'Object' → the Collection input is
        # ignored, a silent no-op). Flip the menu whose options include 'Collection' to
        # 'Collection', so collection= actually instances from it — unless the caller set
        # that menu explicitly in inputs=.
        # B7: write the option's stored VALUE from menu_maps (int pre-5.2 / string enum on
        # 5.2+), not a walk index — pre-5.2 Instance Type stores Collection=0, so the old
        # index-1 write selected Object (the live no-op).
        explicit = {str(k).strip().lower() for k in (params.get("inputs") or {})}
        for mname, (mident, mtype) in sockets.items():
            if mtype != 'NodeSocketMenu' or mname.lower() in explicit:
                continue
            vm = menu_maps.get(mident, {})
            gate = next((v for nm, v in vm.items() if nm.lower() == "collection"), None)
            if gate is not None:
                _gn_set(mod, mident, gate)
                # report the EFFECTIVE option name read back, not a hardcoded label
                eff = _gn_get(mod, mident)
                set_inputs[mname] = next((nm for nm, v in vm.items() if v == eff), eff)
                break

    # inputs={name: value} → set by identifier; match socket name case-insensitively.
    got, unknown_inputs2 = _set_gn_inputs(mod, sockets, params.get("inputs"), menu_maps)
    set_inputs.update(got)
    unknown_inputs.extend(unknown_inputs2)

    mod.id_data.update_tag()
    bpy.context.view_layer.update()

    result = {
        "success": True,
        "object": obj.name,
        "modifier": mod.name,
        "asset": ng.name,
        "type": "NODES",
        "inputs_available": _describe_inputs(mod, sockets, menu_maps),
    }
    if set_inputs:
        result["inputs_set"] = set_inputs
    if unknown_inputs:
        result.setdefault("notes", []).append(
            f"unrecognised input(s) {unknown_inputs} — settable inputs: {list(sockets)}")
    # G206: report the evaluated instance count so a zero-emission config is legible
    # instantly instead of being extracted by duplicate→realize→apply→count.
    n_inst = _evaluated_instance_count(obj)
    if n_inst is not None:
        result["evaluated_instances"] = n_inst
        if n_inst == 0:
            result.setdefault("notes", []).append(
                "⚠ this modifier currently emits 0 instances — nothing will show. Common "
                "causes: Density (1/m² default) floors to 0 at tutorial scale (raise it); "
                "the instance-source gate/collection is unset; or Viewport Visibility is 0.")
    # G226: a Collection source with Pick Instance off stacks every prototype on
    # every point — visually wrong, numerically plausible. Same class as the
    # density-floor note: the input dump already knows; say so.
    pick_note = _pick_instance_advisory(mod, sockets)
    if pick_note:
        result.setdefault("notes", []).append(pick_note)
    # G207: instances are realized by op=apply ONLY when the group has a Realize
    # Instances control (Scatter on Surface does) — apply now sets it. State it honestly.
    result.setdefault("notes", []).append(
        "native GN scatter/instances emit INSTANCES-on-points, not separate objects; "
        "modifier op=apply realizes them into editable mesh (it flips Realize Instances "
        "for you before baking).")
    return result


TOOLS = {
    "bend":            bend,
    "add_modifier":    add_modifier,
    "add_asset_modifier": add_asset_modifier,
    "rebind_deform":   rebind_deform,
    "modify_modifier": modify_modifier,
    "remove_modifier": remove_modifier,
    "list_modifiers":  list_modifiers,
    "move_modifier":   move_modifier,
    "apply_modifiers": apply_modifiers,
    "convert_to_mesh": convert_to_mesh,
    "boolean":         boolean,
}

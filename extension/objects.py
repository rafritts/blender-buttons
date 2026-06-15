"""Object-level basics: select, delete, rename, duplicate, join, mode, info, profile, selection readback."""

import math

import bpy
import mathutils

from . import state
from .common import world_bbox, world_center, activate


def rename_object(params):
    old_name = params.get("old_name")
    new_name = params.get("new_name")
    if not old_name or not new_name:
        return {"error": "'old_name' and 'new_name' are required"}
    obj = bpy.data.objects.get(old_name)
    if obj is None:
        return {"error": f"Object '{old_name}' not found"}
    obj.name = new_name
    if obj.data:
        obj.data.name = new_name
    return {"success": True, "old_name": old_name, "new_name": obj.name}


def select_object(params):
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}

    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}

    # Object-level selection requires Object Mode — from POSE/EDIT/SCULPT the
    # select_all operator's poll() fails ("context is incorrect"). SPEC-05 makes
    # the verb the mode context: auto-switch instead of erroring, and tell the
    # agent it happened (it may have meant to stay in the other mode).
    notes = []
    if bpy.context.mode != 'OBJECT':
        prev = bpy.context.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        notes.append(f"auto-switched {prev} → OBJECT to select an object")

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    out = {"success": True, "selected": name}
    if notes:
        out["notes"] = notes
    return out


def delete_object(params):
    """Delete an object OR a group. If 'name' resolves to a collection, every
    mesh inside it (recursively, including nested sub-collections) is deleted
    and the empty collections are removed."""
    name = params.get("name")
    if name:
        coll = bpy.data.collections.get(name)
        if coll is not None:
            return _delete_collection(coll)
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object or group '{name}' not found"}
    else:
        obj = bpy.context.active_object
        if obj is None:
            return {"error": "No active object to delete"}
    deleted = obj.name
    # Delete via the data API, NOT bpy.ops.object.delete(): the operator only acts
    # on SELECTED objects, and a hidden object (e.g. a boolean cutter hidden by
    # hide_cutter=True) can't be selected — so the operator silently deletes nothing
    # while the tool reports success, leaving the name claimed (gaps.md T7).
    # objects.remove() ignores visibility/selection entirely.
    bpy.data.objects.remove(obj, do_unlink=True)
    if deleted in bpy.data.objects:
        return {"error": f"delete failed: '{deleted}' still present after remove()"}
    return {"success": True, "deleted": deleted}


def _delete_collection(coll):
    coll_name = coll.name
    members = [o.name for o in coll.all_objects]
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    # Remove via the data API so hidden members are deleted too (bpy.ops.delete
    # skips anything that can't be selected — same T7 no-op).
    for o in list(coll.all_objects):
        bpy.data.objects.remove(o, do_unlink=True)
    sub_colls = []
    def _collect(c):
        for child in c.children:
            _collect(child)
            sub_colls.append(child)
    _collect(coll)
    for c in sub_colls:
        bpy.data.collections.remove(c)
    bpy.data.collections.remove(coll)
    for c in [c for c in bpy.data.collections if not c.all_objects and not c.children]:
        bpy.data.collections.remove(c)
    return {"success": True, "deleted_group": coll_name, "deleted_members": members}


def duplicate_object(params):
    name     = params.get("name")
    new_name = params.get("new_name")
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    active = bpy.context.active_object
    if active is None:
        return {"error": "No active object to duplicate"}
    original = active.name
    bpy.ops.object.duplicate(linked=False)
    dup = bpy.context.active_object
    if new_name and dup:
        dup.name = new_name
        if dup.data:
            dup.data.name = new_name
    return {"success": True, "original": original, "duplicate": dup.name if dup else None}


def join_objects(params):
    names = params.get("names", [])
    if len(names) < 2:
        return {"error": "'names' must list at least 2 objects"}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    first = None
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
        obj.select_set(True)
        if first is None:
            first = obj
    bpy.context.view_layer.objects.active = first
    bpy.ops.object.join()
    result = bpy.context.active_object

    merged = None
    merge_threshold = params.get("merge_threshold")
    if merge_threshold is not None and result is not None:
        import bmesh
        threshold = float(merge_threshold)
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(result.data)
        before = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=threshold)
        after = len(bm.verts)
        bmesh.update_edit_mesh(result.data)
        bpy.ops.object.mode_set(mode='OBJECT')
        merged = {"threshold": threshold, "verts_before": before,
                  "verts_after": after, "merged": before - after}

    out = {"success": True, "result_object": result.name if result else None, "joined": names}
    if merged is not None:
        out["merged"] = merged
    return out


def set_mode(params):
    mode = params.get("mode", "OBJECT").upper()
    active = bpy.context.active_object
    prev_mode = active.mode if active is not None else None
    # W2: snapshot deform binds when EDIT is entered, so a topology edit spread
    # across separate socket commands (set_mode EDIT → select → delete_geometry →
    # set_mode OBJECT) is still caught when edit mode is exited. The request-scoped
    # V2 guard only spans a single target= edit verb and misses this manual path.
    if mode == 'EDIT' and prev_mode != 'EDIT':
        state.snapshot_edit_binds(active)
    bpy.ops.object.mode_set(mode=mode)
    result = {"success": True, "mode": mode}
    if mode == 'OBJECT' and prev_mode == 'EDIT':
        warn = state.check_edit_binds(bpy.context.active_object)
        if warn:
            result.update(warn)
    return result


def get_object_info(params):
    bpy.context.view_layer.update()
    name = params.get("name") if params else None
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
    else:
        obj = bpy.context.active_object
    if obj is None:
        return {"error": "No active object and no 'name' specified"}
    loc = obj.location
    scale = obj.scale
    rot = obj.rotation_euler
    bb = obj.bound_box
    world_bb = [obj.matrix_world @ mathutils.Vector(c) for c in bb]
    xs = [v.x for v in world_bb]
    ys = [v.y for v in world_bb]
    zs = [v.z for v in world_bb]

    mat3 = obj.matrix_world.to_3x3()
    local_z_world = (mat3 @ mathutils.Vector((0, 0, 1)))
    local_x_world = (mat3 @ mathutils.Vector((1, 0, 0)))
    if local_z_world.length > 1e-9: local_z_world.normalize()
    if local_x_world.length > 1e-9: local_x_world.normalize()
    world_up = mathutils.Vector((0, 0, 1))
    tilt_deg = round(math.degrees(local_z_world.angle(world_up)), 2)
    lx_xy = mathutils.Vector((local_x_world.x, local_x_world.y, 0.0))
    if lx_xy.length > 1e-6:
        lx_xy.normalize()
        yaw_deg = round(math.degrees(math.atan2(lx_xy.y, lx_xy.x)), 2)
    else:
        yaw_deg = None  # local +X is vertical — yaw undefined

    if tilt_deg < 1.0:
        orient = "upright"
    elif tilt_deg < 5.0:
        orient = f"nearly upright (tilted {tilt_deg}° from vertical)"
    elif tilt_deg > 175.0:
        orient = f"upside-down (tilted {tilt_deg}° from vertical)"
    elif 85.0 < tilt_deg < 95.0:
        orient = f"on its side (tilted {tilt_deg}° from vertical)"
    else:
        orient = f"tilted {tilt_deg}° from vertical"
    if yaw_deg is not None and abs(yaw_deg) > 1.0:
        orient += f", yaw {yaw_deg}°"

    info = {
        "name": obj.name,
        "type": obj.type,
        "location": [round(loc.x, 4), round(loc.y, 4), round(loc.z, 4)],
        "scale": [round(scale.x, 4), round(scale.y, 4), round(scale.z, 4)],
        "rotation_deg": [round(math.degrees(rot.x), 2), round(math.degrees(rot.y), 2), round(math.degrees(rot.z), 2)],
        "tilt_off_vertical_deg": tilt_deg,
        "yaw_deg": yaw_deg,
        "orientation": orient,
        "dimensions": [round(max(xs) - min(xs), 4), round(max(ys) - min(ys), 4), round(max(zs) - min(zs), 4)],
        "world_bounds": {
            "x": [round(min(xs), 4), round(max(xs), 4)],
            "y": [round(min(ys), 4), round(max(ys), 4)],
            "z": [round(min(zs), 4), round(max(zs), 4)],
        },
    }
    if obj.type == 'MESH':
        info["vertex_count"] = len(obj.data.vertices)
        info["edge_count"] = len(obj.data.edges)
        info["face_count"] = len(obj.data.polygons)
        from .common import material_summary
        info["materials"] = material_summary(obj)
        if obj.modifiers:
            info["modifiers"] = [{"name": m.name, "type": m.type} for m in obj.modifiers]
    return {"success": True, "info": info}


# Z3: profiling a production mesh whole (the arms returned 4140 rings / 261KB) blows
# the tool-result budget. Cap the ring count by default — evenly resampled and
# REPORTED, never silently truncated — so the tool is safe even when the caller
# doesn't ask for a window.
_PROFILE_MAX_RINGS = 200


def get_mesh_profile(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "No active mesh object"}
    axis = params.get("axis", "Z").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    other = [(i, n) for i, n in enumerate(['X', 'Y', 'Z']) if i != axis_idx]
    # Z3: optional world-space window on the PROFILE axis (same units as the output),
    # and a max-ring cap with even resampling. min/max are world coords, not 0..1.
    win_min = params.get("min")
    win_max = params.get("max")
    win_min = float(win_min) if win_min is not None else None
    win_max = float(win_max) if win_max is not None else None
    full = bool(params.get("full", False))
    try:
        bands = int(params.get("bands") or 0)
    except (TypeError, ValueError):
        bands = 0
    mr = params.get("max_rings", _PROFILE_MAX_RINGS)
    max_rings = int(mr) if mr else 0  # 0 / None → uncapped

    was_edit = obj.mode == 'EDIT'
    if was_edit:
        bm = bmesh.from_edit_mesh(obj.data)
    else:
        bm = bmesh.new()
        bm.from_mesh(obj.data)

    # One pass: collect (pos-on-axis, [coords on the two other axes]) for every
    # vert inside the optional window.
    samples = []
    for v in bm.verts:
        wco = obj.matrix_world @ v.co
        pos = wco[axis_idx]
        if (win_min is not None and pos < win_min) or (win_max is not None and pos > win_max):
            continue
        samples.append((pos, [wco[i] for i, _ in other]))

    if not was_edit:
        bm.free()

    if not samples:
        win = f" in {axis} window [{win_min}, {win_max}]" if (win_min is not None or win_max is not None) else ""
        return {"error": f"No geometry found{win}."}

    pos_min = min(s[0] for s in samples)
    pos_max = max(s[0] for s in samples)

    if full:
        # SHOW_ME_EVERYTHING: one ring per distinct axis position (exact grouping),
        # capped + evenly resampled. The raw dump — opt-in only.
        rings = {}
        for pos, coords in samples:
            key = round(pos, 4)
            rings.setdefault(key, [[] for _ in other])
            for j, c in enumerate(coords):
                rings[key][j].append(c)
        keys = sorted(rings)
        total = len(keys)
        resampled = False
        if max_rings and total > max_rings:
            idxs = [round(i * (total - 1) / (max_rings - 1)) for i in range(max_rings)]
            keys = [keys[i] for i in sorted(set(idxs))]
            resampled = True
        profile = []
        for pos in keys:
            entry = {axis: round(pos, 4)}
            for j, (_, n) in enumerate(other):
                vals = rings[pos][j]
                lo, hi = min(vals), max(vals)
                entry[f"{n}_range"] = [round(lo, 4), round(hi, 4)]
                entry[f"{n}_width"] = round(hi - lo, 4)
            profile.append(entry)
        return {"success": True, "mode": "full", "axis": axis, "rings": len(profile),
                "rings_total": total, "resampled": resampled,
                "windowed": win_min is not None or win_max is not None,
                "window": [win_min, win_max], "profile": profile}

    # DEFAULT: aggregate into evenly spaced bands and report each band's real
    # cross-section width (span across all its verts), with the narrowest band
    # (the pinch — armpit, waist, neck) and widest band flagged. This is what the
    # profile is actually reached for; the per-ring dump was noise.
    if bands <= 0:
        bands = 24
    extent = pos_max - pos_min
    if extent <= 1e-9:
        bands = 1
    band_w = (extent / bands) if bands and extent > 0 else max(extent, 1e-9)

    binned = [[[] for _ in other] for _ in range(bands)]
    bcount = [0] * bands
    for pos, coords in samples:
        bi = int((pos - pos_min) / band_w) if band_w > 0 else 0
        if bi >= bands:
            bi = bands - 1
        for j, c in enumerate(coords):
            binned[bi][j].append(c)
        bcount[bi] += 1

    out_bands = []
    for bi in range(bands):
        if bcount[bi] == 0:
            continue
        center = pos_min + (bi + 0.5) * band_w
        entry = {axis: round(center, 4), "n": bcount[bi]}
        widths = []
        for j, (_, n) in enumerate(other):
            vals = binned[bi][j]
            w = max(vals) - min(vals)
            entry[f"{n}_width"] = round(w, 4)
            widths.append(w)
        # girth = summed bbox span of the two cross-section axes — a single scalar
        # for "how big is the section here", used to find the pinch/bulge.
        entry["girth"] = round(sum(widths), 4)
        out_bands.append(entry)

    narrow = min(out_bands, key=lambda b: b["girth"])
    wide = max(out_bands, key=lambda b: b["girth"])
    return {"success": True, "mode": "bands", "axis": axis,
            "bands": len(out_bands), "band_width": round(band_w, 4),
            "extent": [round(pos_min, 4), round(pos_max, 4)],
            "windowed": win_min is not None or win_max is not None,
            "window": [win_min, win_max],
            "narrowest": narrow, "widest": wide, "profile": out_bands}


def get_current_selection(params):
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}
    bm = bmesh.from_edit_mesh(obj.data)
    sel = [v for v in bm.verts if v.select]
    if not sel:
        return {"success": True, "selected_count": 0, "centroid_world": None, "bbox_world": None}
    world_pos = [obj.matrix_world @ v.co for v in sel]
    xs = [p.x for p in world_pos]
    ys = [p.y for p in world_pos]
    zs = [p.z for p in world_pos]
    n = len(sel)
    return {
        "success": True,
        "selected_count": n,
        "centroid_world": [round(sum(xs)/n, 4), round(sum(ys)/n, 4), round(sum(zs)/n, 4)],
        "bbox_world": {
            "x": [round(min(xs), 4), round(max(xs), 4)],
            "y": [round(min(ys), 4), round(max(ys), 4)],
            "z": [round(min(zs), 4), round(max(zs), 4)],
        },
    }


def duplicate_mirrored(params):
    """Bake a mirrored copy of an object across a world axis plane.

    The static "make the other half" escape hatch — for symmetry that's already
    finalized (the MIRROR modifier / placement mirror_of handle live cases).

    target:   object to mirror (required).
    axis:     X | Y | Z — the plane is perpendicular to this axis (default X,
              i.e. mirror left↔right across the Y-Z plane).
    pivot:    "WORLD" (default — reflect across the axis=0 plane through the
              world origin) | "SELF" (reflect about the object's own origin) |
              an object name (reflect across the plane through that object's
              center) | [x, y, z] explicit plane point.
    new_name: name for the copy. Defaults to "<target>_mirror".

    Reflection inverts the mesh, so winding/normals are recalculated outward
    afterward and the transform is applied (scale stays positive, [1,1,1])."""
    target = params.get("target")
    if not target:
        return {"error": "'target' is required"}
    obj = bpy.data.objects.get(target)
    if obj is None:
        return {"error": f"Object '{target}' not found"}
    axis = (params.get("axis") or "X").upper()
    if axis not in ("X", "Y", "Z"):
        return {"error": "axis must be X, Y, or Z"}
    ai = "XYZ".index(axis)

    pivot = params.get("pivot", "WORLD")
    if isinstance(pivot, (list, tuple)) and len(pivot) == 3:
        c = mathutils.Vector(pivot)
    elif isinstance(pivot, str) and pivot.upper() == "WORLD":
        c = mathutils.Vector((0.0, 0.0, 0.0))
    elif isinstance(pivot, str) and pivot.upper() == "SELF":
        c = obj.matrix_world.translation.copy()
    else:  # object name
        piv = bpy.data.objects.get(pivot)
        if piv is None:
            return {"error": f"pivot object '{pivot}' not found"}
        c = mathutils.Vector(world_center(piv))

    # Reflection across the plane through c, perpendicular to `axis`:
    #   R = T(c) · S(-1 on axis) · T(-c)
    S = mathutils.Matrix.Identity(4)
    S[ai][ai] = -1.0
    R = mathutils.Matrix.Translation(c) @ S @ mathutils.Matrix.Translation(-c)

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    activate(obj)
    bpy.ops.object.duplicate(linked=False)
    dup = bpy.context.active_object
    dup.matrix_world = R @ dup.matrix_world

    new_name = params.get("new_name") or f"{target}_mirror"
    dup.name = new_name
    if dup.data and dup.data.users == 1:
        dup.data.name = new_name

    # Bake the negative-determinant transform, then fix the inverted normals.
    activate(dup)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if dup.type == 'MESH':
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')

    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(dup)
    return {
        "success": True,
        "original": target,
        "mirror": dup.name,
        "axis": axis,
        "pivot": pivot,
        "dimensions": [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)],
    }


# ─────────────────────── custom properties (U2) ───────────────────────
# Production rigs/addons/game-export pipelines store metadata in custom
# properties — IK/FK switches, panel toggles, LOD flags. General Blender data,
# not rig-specific, so it lives here with the other object basics.

def _prop_holder(name, bone):
    """Resolve the ID that carries custom props: a pose bone if `bone` is given
    (where rig controls live), else the object. Returns (holder, error)."""
    obj = bpy.data.objects.get(name)
    if obj is None:
        return None, f"Object '{name}' not found"
    if bone:
        if obj.type != 'ARMATURE':
            return None, f"'{name}' is not an armature; 'bone' only applies to armatures"
        pb = obj.pose.bones.get(bone)
        if pb is None:
            return None, f"bone '{bone}' not found on '{name}'"
        return pb, None
    return obj, None


def _user_props(holder):
    """User-defined custom properties on holder, minus Blender/addon internals
    and this addon's own bb_* bookkeeping."""
    out = {}
    for k in holder.keys():
        if k in ("_RNA_UI", "cycles") or k.startswith("bb_"):
            continue
        v = holder[k]
        try:
            if hasattr(v, "to_list"):
                v = v.to_list()
            elif hasattr(v, "to_dict"):
                v = v.to_dict()
            elif hasattr(v, "__len__") and not isinstance(v, str):
                v = list(v)
        except Exception:
            v = str(v)
        out[k] = v
    return out


def get_custom_properties(params):
    """List user-defined custom properties on an object, or on one of its pose
    bones (bone=...). Read-only."""
    name = params.get("name")
    bone = params.get("bone")
    holder, err = _prop_holder(name, bone)
    if err:
        return {"error": err}
    props = _user_props(holder)
    return {"success": True, "name": name, "bone": bone,
            "properties": props, "count": len(props)}


def set_custom_property(params):
    """Set (or create) a custom property on an object or pose bone — the way to
    drive a rig's IK/FK switch or any addon/export metadata."""
    name = params.get("name")
    bone = params.get("bone")
    key = params.get("key")
    if not key:
        return {"error": "'key' is required"}
    if "value" not in params:
        return {"error": "'value' is required"}
    value = params.get("value")
    holder, err = _prop_holder(name, bone)
    if err:
        return {"error": err}
    existed = key in holder.keys()
    try:
        holder[key] = value
    except (TypeError, ValueError) as e:
        return {"error": f"could not set '{key}' = {value!r}: {e}"}
    # Re-evaluate so any drivers/constraints reading this property update.
    bpy.context.view_layer.update()
    return {"success": True, "name": name, "bone": bone, "key": key,
            "value": value, "created": not existed}


# ─────────────────────── particle systems (U7) ───────────────────────

def _particle_systems(obj):
    """(name, type, count) per particle system, or [] if none."""
    out = []
    for ps in getattr(obj, "particle_systems", []) or []:
        st = ps.settings
        out.append((ps.name, st.type, st.count))
    return out


def set_particle_visibility(params):
    """Show or hide an object's particle systems in the viewport. Hair/fur often
    buries the mesh under strands; this toggles show_viewport on every
    PARTICLE_SYSTEM modifier so the underlying object is workable."""
    name = params.get("name")
    show = bool(params.get("show", False))
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}
    mods = [m for m in obj.modifiers if m.type == 'PARTICLE_SYSTEM']
    if not mods:
        return {"error": f"'{name}' has no particle systems"}
    for m in mods:
        m.show_viewport = show
    return {"success": True, "name": name, "show": show,
            "particle_systems": [m.name for m in mods]}


# ─────────────────────── shape keys (U8) ───────────────────────

def list_shape_keys(params):
    """List an object's shape keys (morph targets) and their current values."""
    name = params.get("name")
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}
    data = getattr(obj, "data", None)
    sk = getattr(data, "shape_keys", None) if data is not None else None
    if sk is None:
        return {"success": True, "name": name, "shape_keys": [], "count": 0}
    keys = [{"name": k.name, "value": round(k.value, 4),
             "min": round(k.slider_min, 4), "max": round(k.slider_max, 4)}
            for k in sk.key_blocks]
    return {"success": True, "name": name, "shape_keys": keys, "count": len(keys)}


def set_shape_key(params):
    """Set a shape key's value (0..1 typical) — drive a morph/corrective."""
    name = params.get("name")
    key = params.get("key")
    if not key:
        return {"error": "'key' is required"}
    if "value" not in params:
        return {"error": "'value' is required"}
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}
    data = getattr(obj, "data", None)
    sk = getattr(data, "shape_keys", None) if data is not None else None
    if sk is None:
        return {"error": f"'{name}' has no shape keys"}
    kb = sk.key_blocks.get(key)
    if kb is None:
        return {"error": f"shape key '{key}' not found on '{name}'. "
                         f"Available: {[k.name for k in sk.key_blocks]}"}
    kb.value = float(params.get("value"))
    bpy.context.view_layer.update()
    return {"success": True, "name": name, "key": key, "value": round(kb.value, 4)}


def set_active_shape_key(params):
    """Aim subsequent edit-mode / sculpt edits at a chosen shape key (Y1d).

    On a mesh with shape keys, vertex edits land on the ACTIVE key, not the
    displayed mesh — so a position edit silently vanishes (and becomes a landmine)
    if the wrong key is active. This sets which key edits will write to.

    key: shape-key name, or 'Basis' to target the rest shape (the usual intent —
         'position-only edits are safe' is FALSE on keyed meshes, so aim at Basis
         deliberately before reshaping the rest geometry).
    """
    name = params.get("name")
    key = params.get("key")
    if not key:
        return {"error": "'key' is required (shape-key name, or 'Basis' for the rest shape)"}
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}
    data = getattr(obj, "data", None)
    sk = getattr(data, "shape_keys", None) if data is not None else None
    if sk is None:
        return {"error": f"'{name}' has no shape keys"}
    blocks = sk.key_blocks
    idx = blocks.find(key)
    if idx < 0:
        return {"error": f"shape key '{key}' not found on '{name}'. "
                         f"Available: {[k.name for k in blocks]}"}
    obj.active_shape_key_index = idx
    kb = blocks[idx]
    is_basis = idx == 0 or kb == sk.reference_key
    return {"success": True, "name": name, "key": kb.name, "index": idx,
            "value": round(kb.value, 4), "is_basis": is_basis}


def set_object_visibility(params):
    """Show or hide an object in the viewport and/or render, without deleting or
    unbinding it. Hiding an armature hides its bones from the user's live view while
    the Armature modifier keeps deforming the bound mesh (gaps.md T5)."""
    name = params.get("name")
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}
    viewport = params.get("viewport")
    render = params.get("render")
    if viewport is None and render is None:
        return {"error": "set 'viewport' and/or 'render' (bool) to show/hide"}
    if viewport is not None:
        obj.hide_set(not bool(viewport))
        obj.hide_viewport = not bool(viewport)
    if render is not None:
        obj.hide_render = not bool(render)
    return {"success": True, "name": name,
            "viewport_visible": not obj.hide_viewport,
            "render_visible": not obj.hide_render}


TOOLS = {
    "rename_object":          rename_object,
    "select_object":          select_object,
    "delete_object":          delete_object,
    "duplicate_object":       duplicate_object,
    "duplicate_mirrored":     duplicate_mirrored,
    "join_objects":           join_objects,
    "set_mode":               set_mode,
    "get_object_info":        get_object_info,
    "get_mesh_profile":       get_mesh_profile,
    "get_current_selection":  get_current_selection,
    "get_custom_properties":  get_custom_properties,
    "set_custom_property":    set_custom_property,
    "set_particle_visibility": set_particle_visibility,
    "list_shape_keys":        list_shape_keys,
    "set_shape_key":          set_shape_key,
    "set_active_shape_key":   set_active_shape_key,
    "set_object_visibility":  set_object_visibility,
}

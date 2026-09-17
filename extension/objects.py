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
    and the empty collections are removed.

    G156: 'pattern' bulk-deletes every object whose name matches a glob (fnmatch,
    e.g. 'SprinkleRed_inst*') or — when the pattern has no glob metacharacters — a
    plain prefix ('SprinkleRed_inst'). One call clears a whole scatter/array instead
    of N sequential deletes."""
    pattern = params.get("pattern")
    if pattern:
        return _delete_by_pattern(pattern)
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
    # on SELECTED objects, and a hidden object (e.g. a live-boolean cutter hidden by
    # hide_cutter=True) can't be selected — so the operator silently deletes nothing
    # while the tool reports success, leaving the name claimed (gaps.md T7).
    # objects.remove() ignores visibility/selection entirely.
    bpy.data.objects.remove(obj, do_unlink=True)
    if deleted in bpy.data.objects:
        return {"error": f"delete failed: '{deleted}' still present after remove()"}
    return {"success": True, "deleted": deleted}


def _delete_by_pattern(pattern):
    """Delete every object whose name matches `pattern` — a glob (if it contains
    *?[ ) or otherwise a plain prefix. Reports the count and a sample so a too-broad
    pattern is legible, not a silent scene-wipe."""
    import fnmatch
    is_glob = any(c in pattern for c in "*?[")
    if is_glob:
        matches = [o for o in bpy.data.objects if fnmatch.fnmatchcase(o.name, pattern)]
    else:
        matches = [o for o in bpy.data.objects if o.name.startswith(pattern)]
    if not matches:
        kind = "glob" if is_glob else "prefix"
        return {"error": f"no objects match {kind} '{pattern}' — nothing deleted"}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    names = [o.name for o in matches]
    # objects.remove() (not bpy.ops.delete) so hidden/unselectable members go too (T7).
    for o in matches:
        bpy.data.objects.remove(o, do_unlink=True)
    still = [n for n in names if n in bpy.data.objects]
    if still:
        return {"error": f"delete failed: {len(still)} still present after remove()"}
    return {"success": True, "deleted_count": len(names), "pattern": pattern,
            "deleted_sample": names[:5]}


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
    # G54: linked=True is the Alt+D INSTANCE — the copy shares the source mesh
    # datablock instead of getting its own. N instances cost one mesh, not N, and
    # edits to one propagate to all. linked=False (default) keeps the old
    # independent-copy behaviour.
    linked   = bool(params.get("linked", False))
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
    bpy.ops.object.duplicate(linked=linked)
    dup = bpy.context.active_object
    if new_name and dup:
        dup.name = new_name
        # A linked duplicate SHARES the source mesh, so renaming dup.data would
        # rename that shared datablock — only rename data on a full (independent) copy.
        if dup.data and not linked:
            dup.data.name = new_name
    return {"success": True, "original": original, "duplicate": dup.name if dup else None,
            "linked": linked,
            "shared_mesh": (dup.data.name if (linked and dup and dup.data) else None)}


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
    # G114: join() folds every selected object's geometry INTO the active object's mesh
    # datablock. If that datablock is shared (linked instances from a scatter), the merged
    # geometry overwrites the mesh every OTHER instance also points at — so joining a
    # SUBSET silently corrupts the survivors (they suddenly render as the merged blob).
    # Make the active single-user first, but only when its mesh is actually shared with an
    # object OUTSIDE the join set (otherwise the copy is needless).
    made_single_user = False
    names_set = set(names)
    if getattr(first, "data", None) is not None and first.data.users > 1:
        shared_outside = any(
            o.name not in names_set and getattr(o, "data", None) is first.data
            for o in bpy.data.objects)
        if shared_outside:
            first.data = first.data.copy()
            made_single_user = True
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

    # G63 — re-home handles. join() deletes the consumed objects and folds their verts
    # (and vertex groups — names are globally unique, so no collision) into `result`.
    # A handle whose owner was a consumed object is now orphaned; re-point its bb_owner
    # to the surviving result, keeping its name + vgroup so bridge/relate find it again.
    rehomed = []
    if result is not None:
        consumed = {n for n in names if n != result.name}
        coll = bpy.data.collections.get("Handles")
        if coll and consumed:
            for h in coll.objects:
                if h.get("bb_handle") and h.get("bb_owner") in consumed:
                    h["bb_owner"] = result.name
                    rehomed.append(h.name)

    out = {"success": True, "result_object": result.name if result else None, "joined": names}
    if merged is not None:
        out["merged"] = merged
    if rehomed:
        out["rehomed_handles"] = rehomed
    if made_single_user:
        out["made_single_user"] = True
        out.setdefault("notes", []).append(
            "G114: the join target shared its mesh with objects outside the join set "
            "(linked instances) — made it single-user first so the merge didn't corrupt "
            "the survivors. Those instances are unchanged.")
    return out


def set_mode(params):
    mode = params.get("mode", "OBJECT").upper()
    target = params.get("target") or ""
    # G7: with an explicit target, select+activate it FIRST so a stray human click
    # can't make a mode switch land on the wrong object. Drop any other object's
    # edit/sculpt mode before re-pointing the active object.
    prev_mode = None
    if target:
        obj = bpy.data.objects.get(target)
        if obj is None:
            return {"error": f"target '{target}' not found"}
        active = bpy.context.active_object
        # Capture the TARGET's pre-switch mode before we touch anything — the bind
        # check below keys off it, and the G18 exit-to-OBJECT can erase it.
        prev_mode = obj.mode
        # G18: object.select_all / select_set / activate are OBJECT-mode operators —
        # their poll() fails if the active object is still in EDIT/SCULPT/POSE. Exit
        # to OBJECT first whenever the active object is in any non-OBJECT mode. This
        # includes the case where the *target* is itself the active edit-mode object
        # (the old `active is not obj` guard skipped it, so EDIT→OBJECT name=<self>
        # hit select_all's failing poll and never left Edit mode).
        if active is not None and active.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    active = bpy.context.active_object
    if prev_mode is None:
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


def _dual_read(obj, core, params):
    """Run a world-space mesh read (profile/section/silhouette) over the CAGE and —
    when a modifier makes the evaluated mesh differ — over the EVALUATED mesh too,
    returning {cage, evaluated, modifiers}. feel always reports what renders; the cage
    alone silently understated size and mis-read SOLIDIFY/MIRROR/BOOLEAN topology.
    `core(bm, params)` reads one world-space bmesh; this owns and frees both bmeshes."""
    from . import topology
    from .common import modifier_stack, evaluated_differs
    cage_bm = topology._topology_bmesh(obj, "cage")
    try:
        cage = core(cage_bm, params)
    finally:
        cage_bm.free()
    if not cage.get("success"):
        return cage          # a window/empty error applies to both bases — surface it
    ev = None
    if evaluated_differs(obj):
        ev_bm = topology._topology_bmesh(obj, "evaluated")
        try:
            ev = core(ev_bm, params)
        finally:
            ev_bm.free()
        if not ev.get("success"):
            ev = None
    return {"success": True, "object": obj.name,
            "modifiers": modifier_stack(obj), "cage": cage, "evaluated": ev}


def _combined_world_bmesh(objs):
    """One world-space bmesh unioning several objects' EVALUATED geometry (modifiers
    applied, transforms baked) — the substrate for a composite shape read over an
    assembly (G207). Copies faces (so section-slicing works) plus any loose edges (so a
    wire/edge-only part stays gap-free). Caller owns it and must .free(). None if the set
    yields no geometry."""
    import bmesh
    from .common import eval_world_bmesh
    combined = bmesh.new()
    any_geo = False
    for o in objs:
        sub = eval_world_bmesh(o)
        if sub is None:
            continue
        vmap = {v: combined.verts.new(v.co) for v in sub.verts}
        for f in sub.faces:
            try:
                combined.faces.new([vmap[v] for v in f.verts])
            except (ValueError, KeyError):
                pass                       # duplicate/degenerate face — skip
        for e in sub.edges:
            if not e.link_faces:           # loose edge (no face) — preserve the wire
                try:
                    combined.edges.new((vmap[e.verts[0]], vmap[e.verts[1]]))
                except (ValueError, KeyError):
                    pass
        sub.free()
        any_geo = True
    if not any_geo:
        combined.free()
        return None
    combined.verts.ensure_lookup_table()
    combined.edges.ensure_lookup_table()
    combined.faces.ensure_lookup_table()
    return combined


def _shape_read(core, params):
    """Front-door for the shape reads (profile / silhouette / section). Resolves target=
    to one or MANY meshes. ONE mesh → the cage/evaluated dual read (unchanged). A
    comma-list or collection name → the COMPOSITE read: every part unioned into one
    world-space bmesh and projected as a SINGLE shape, so an assembly's overall
    silhouette/profile/section is legible without a destructive join (G207 — 'the pieces
    are each correct' is not 'the whole reads well')."""
    from .common import resolve_targets
    tgt = params.get("target")
    objs, err = resolve_targets(tgt)
    if err:
        return {"error": err}
    objs = [o for o in objs if o.type == 'MESH']
    if not objs:
        return {"error": "no mesh object" + (f" in '{tgt}'" if tgt else " (nothing active)")}
    if len(objs) == 1:
        return _dual_read(objs[0], core, params)
    bm = _combined_world_bmesh(objs)
    if bm is None:
        return {"error": "no projectable geometry in the target set"}
    try:
        result = core(bm, params)
    finally:
        bm.free()
    if not result.get("success"):
        return result
    return {"success": True, "composite": True, "n_objects": len(objs),
            "object": ", ".join(o.name for o in objs),
            "modifiers": [], "cage": result, "evaluated": None}


def get_mesh_profile(params):
    return _shape_read(_profile_core, params)


def _profile_core(bm, params):
    """Profile sweep over one world-space bmesh (the wrapper owns/frees bm)."""
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

    # One pass: collect (pos-on-axis, [coords on the two other axes]) for every
    # vert inside the optional window. bm is already in world space.
    samples = []
    for v in bm.verts:
        wco = v.co
        pos = wco[axis_idx]
        if (win_min is not None and pos < win_min) or (win_max is not None and pos > win_max):
            continue
        samples.append((pos, [wco[i] for i, _ in other]))

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


def get_silhouette(params):
    """Orthographic projected coverage along a view axis (gaps.md G37) — the 2D shape,
    read directly instead of cross-multiplying two 1D profile sweeps.

    Pure geometry, NOT a render: project faces onto the plane perpendicular to
    `axis` into a coarse occupancy grid, returned as a text map of '#' (covered) /
    '.' (empty). A closed slab/cylinder reads as a filled disc, not a hollow edge
    ring; a real through-hole stays empty. Edges are still walked so wires and
    grazing faces remain visible — occupancy is coverage, not an edge hit.

    axis:      view axis to look ALONG (X|Y|Z). Default X = the side view (Y-depth ×
               Z-height plane). The silhouette is the other two axes.
    res:       grid resolution on the wider plane axis (default 32, 4..120).
    selection: True = only the live selection's verts (default whole mesh).
    target:    one mesh, OR a comma-list / collection name → the COMPOSITE silhouette of
               the whole assembly, unioned and projected as one shape (G207)."""
    return _shape_read(_silhouette_core, params)


def _silhouette_core(bm, params):
    """Silhouette raster over one world-space bmesh (the wrapper owns/frees bm)."""
    axis = params.get("axis", "X").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 0)
    others = [(i, n) for i, n in enumerate(['X', 'Y', 'Z']) if i != axis_idx]
    ui, vi = others[0][0], others[1][0]
    res = max(4, min(120, int(params.get("res") or 32)))
    sel_only = bool(params.get("selection", False))

    pts = [(v.co[ui], v.co[vi]) for v in bm.verts if (v.select if sel_only else True)]
    if not pts:
        return {"error": "no verts" + (" selected" if sel_only else "")}

    umin = min(p[0] for p in pts)
    umax = max(p[0] for p in pts)
    vmin = min(p[1] for p in pts)
    vmax = max(p[1] for p in pts)
    uext = (umax - umin) or 1e-9
    vext = (vmax - vmin) or 1e-9
    # square-ish cells: res cells on the wider axis, the other axis proportional.
    if uext >= vext:
        cols = res
        cell = uext / cols
        rows = max(1, round(vext / cell))
    else:
        rows = res
        cell = vext / rows
        cols = max(1, round(uext / cell))
    grid = [[False] * cols for _ in range(rows)]

    def mark(u, w):
        ci = min(cols - 1, max(0, int((u - umin) / uext * cols)))
        ri = min(rows - 1, max(0, int((w - vmin) / vext * rows)))
        grid[ri][ci] = True

    def _in_tri(p, a, b, c):
        """Barycentric inclusion in a 2D triangle. Degenerate (edge-on) → False."""
        ax, ay = a; bx, by = b; cx, cy = c; px, py = p
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-18:
            return False
        w1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
        w2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
        w3 = 1.0 - w1 - w2
        eps = 1e-9
        return w1 >= -eps and w2 >= -eps and w3 >= -eps

    def _fill_tri(a, b, c):
        us = (a[0], b[0], c[0])
        vs = (a[1], b[1], c[1])
        ci0 = min(cols - 1, max(0, int((min(us) - umin) / uext * cols)))
        ci1 = min(cols - 1, max(0, int((max(us) - umin) / uext * cols)))
        ri0 = min(rows - 1, max(0, int((min(vs) - vmin) / vext * rows)))
        ri1 = min(rows - 1, max(0, int((max(vs) - vmin) / vext * rows)))
        for ri in range(ri0, ri1 + 1):
            for ci in range(ci0, ci1 + 1):
                if grid[ri][ci]:
                    continue
                uc = umin + (ci + 0.5) * uext / cols
                vc = vmin + (ri + 0.5) * vext / rows
                if _in_tri((uc, vc), a, b, c):
                    grid[ri][ci] = True

    # Faces first: projected coverage. Do NOT flood-fill the outline — that would
    # paint real through-holes. Fan-triangulating an n-gon with a hole would also
    # paint the hole, so triangulate first (bmesh splits around inner loops).
    # An edge-on face is degenerate in 2D; the edge walk below still marks its line.
    import bmesh as _bmesh
    try:
        _bmesh.ops.triangulate(bm, faces=bm.faces[:])
    except Exception:
        pass
    for f in bm.faces:
        fverts = list(f.verts)
        if sel_only and not all(v.select for v in fverts):
            continue
        if len(fverts) < 3:
            continue
        pts2 = [(v.co[ui], v.co[vi]) for v in fverts]
        origin = pts2[0]
        for i in range(1, len(pts2) - 1):
            _fill_tri(origin, pts2[i], pts2[i + 1])

    # Walk every (qualifying) edge in cell-sized steps so wires and grazing faces
    # stay visible — no empty bands between vert-rings.
    for e in bm.edges:
        a, b = e.verts
        if sel_only and not (a.select and b.select):
            continue
        ua, wa = a.co[ui], a.co[vi]
        ub, wb = b.co[ui], b.co[vi]
        steps = max(1, int(((ua - ub) ** 2 + (wa - wb) ** 2) ** 0.5 / cell) + 1)
        for s in range(steps + 1):
            f = s / steps
            mark(ua + (ub - ua) * f, wa + (wb - wa) * f)
    for u, w in pts:  # stray edgeless verts
        mark(u, w)
    filled = sum(c for row in grid for c in row)
    # rows emitted high-v first so the text map reads top-down like the viewport.
    return {"success": True, "axis": axis, "u_label": others[0][1], "v_label": others[1][1],
            "cols": cols, "rows": rows, "cell_m": round(cell, 4),
            "u_range": [round(umin, 4), round(umax, 4)],
            "v_range": [round(vmin, 4), round(vmax, 4)],
            "filled_cells": filled,
            "occupancy": "coverage",
            "grid": ["".join("#" if c else "." for c in grid[r]) for r in range(rows - 1, -1, -1)]}


def _section_loops_area(edges, axis_idx):
    """Walk a set of cut edges into closed contours; return (summed shoelace area,
    n_loops). Each contour is shoelaced in the 2D section plane (the two non-axis
    coords). Approximate on branching cuts; exact on clean closed loops."""
    from collections import defaultdict
    adj = defaultdict(list)
    coords = {}
    for e in edges:
        a, b = e.verts
        adj[a.index].append(b.index)
        adj[b.index].append(a.index)
        coords[a.index] = a.co
        coords[b.index] = b.co
    o = [i for i in range(3) if i != axis_idx]
    visited = set()
    total = 0.0
    nloops = 0
    for start in list(adj):
        if start in visited:
            continue
        loop = []
        prev = None
        cur = start
        while cur is not None and cur not in visited:
            visited.add(cur)
            loop.append(cur)
            nbrs = [x for x in adj[cur] if x != prev]
            prev = cur
            cur = nbrs[0] if nbrs else None
        if len(loop) >= 3:
            nloops += 1
            pts = [(coords[i][o[0]], coords[i][o[1]]) for i in loop]
            s = 0.0
            for k in range(len(pts)):
                x1, y1 = pts[k]
                x2, y2 = pts[(k + 1) % len(pts)]
                s += x1 * y2 - x2 * y1
            total += abs(s) * 0.5
    return total, nloops


def get_section(params):
    """True cross-section PERIMETER + enclosed AREA along an axis (gaps.md G47).

    Unlike profile (bbox width per band), this slices the actual mesh with a plane at
    each section position and sums the cut-contour edge lengths (perimeter ≈ girth /
    circumference) plus the shoelace area — so circumference and cross-sectional area
    are first-class (cup size, pipe girth, limb circumference, volume reasoning).

    axis:     slice axis (X|Y|Z, default Z).
    sections: number of evenly spaced slices (default 12).
    min, max: optional world-space window on the axis.
    target:   one mesh, OR a comma-list / collection name → the COMPOSITE section sweep
              over the whole assembly, unioned (G207)."""
    return _shape_read(_section_core, params)


def _section_core(src, params):
    """Cross-section sweep over one world-space bmesh (the wrapper owns/frees src)."""
    import bmesh
    axis = params.get("axis", "Z").upper()
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
    n = max(1, int(params.get("sections") or 12))
    win_min = params.get("min")
    win_max = params.get("max")
    win_min = float(win_min) if win_min is not None else None
    win_max = float(win_max) if win_max is not None else None

    axis_vals = [v.co[axis_idx] for v in src.verts]
    if not axis_vals:
        return {"error": "mesh has no geometry"}
    lo = win_min if win_min is not None else min(axis_vals)
    hi = win_max if win_max is not None else max(axis_vals)
    if hi - lo <= 1e-9:
        return {"error": "no extent on this axis to section"}

    # Sample inside the span (avoid the exact end caps, which bisect to nothing).
    no = [0.0, 0.0, 0.0]
    no[axis_idx] = 1.0
    sections = []
    for i in range(n):
        frac = (i + 0.5) / n
        pos = lo + frac * (hi - lo)
        bm = src.copy()
        co = [0.0, 0.0, 0.0]
        co[axis_idx] = pos
        try:
            res = bmesh.ops.bisect_plane(
                bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                plane_co=co, plane_no=no, clear_inner=False, clear_outer=False)
            cut_edges = [g for g in res["geom_cut"] if isinstance(g, bmesh.types.BMEdge)]
            perim = sum((e.verts[0].co - e.verts[1].co).length for e in cut_edges)
            area, nloops = _section_loops_area(cut_edges, axis_idx)
        finally:
            bm.free()
        if not cut_edges:
            continue
        sections.append({axis: round(pos, 4), "perimeter_cm": round(perim * 100, 2),
                         "area_cm2": round(area * 10000, 2), "loops": nloops,
                         "cut_edges": len(cut_edges)})
    if not sections:
        return {"error": "no closed cross-sections found in the window"}
    widest = max(sections, key=lambda s: s["perimeter_cm"])
    narrow = min(sections, key=lambda s: s["perimeter_cm"])
    return {"success": True, "axis": axis, "sections": len(sections),
            "extent": [round(lo, 4), round(hi, 4)],
            "windowed": win_min is not None or win_max is not None,
            "widest": widest, "narrowest": narrow, "profile": sections}


def _selection_extent_report(n, world_pos, scope):
    """Build the centroid/bbox report from a list of world-space points. Shared by
    every selection-extent path so edit-mode and object-mode reads look identical."""
    xs = [p.x for p in world_pos]
    ys = [p.y for p in world_pos]
    zs = [p.z for p in world_pos]
    npts = len(world_pos)
    return {
        "success": True,
        "selected_count": n,
        "scope": scope,
        "centroid_world": [round(sum(xs)/npts, 4), round(sum(ys)/npts, 4), round(sum(zs)/npts, 4)],
        "bbox_world": {
            "x": [round(min(xs), 4), round(max(xs), 4)],
            "y": [round(min(ys), 4), round(max(ys), 4)],
            "z": [round(min(zs), 4), round(max(zs), 4)],
        },
    }


def get_current_selection(params):
    """Report the live selection's world-space extent (centroid + bbox), in ANY
    mode (G181). In EDIT mode it reads the bmesh vertex selection; in OBJECT mode
    it reads the component selection STILL stored on the active mesh — the verts a
    `select op=material` / `op=group` flagged before the auto mode-exit — so a
    material/vgroup region's reach is one read, no edit-mode hop. With no component
    selection it falls back to the bbox over the selected OBJECTS."""
    import bmesh
    from .common import world_bbox_corners
    obj = bpy.context.active_object

    if obj is not None and obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(obj.data)
        sel = [v for v in bm.verts if v.select]
        if not sel:
            return {"success": True, "selected_count": 0, "scope": "edit verts",
                    "centroid_world": None, "bbox_world": None}
        world_pos = [obj.matrix_world @ v.co for v in sel]
        return _selection_extent_report(len(sel), world_pos, "edit verts")

    # OBJECT (or any non-edit) mode: the per-vertex .select flags persist on the
    # mesh after the mode exit, so a material/vgroup component selection is still
    # readable without re-entering edit mode (same source fit/coverage read, G178).
    if obj is not None and obj.type == 'MESH':
        me = obj.data
        sel_verts = [v for v in me.vertices if v.select]
        if sel_verts:
            world_pos = [obj.matrix_world @ v.co for v in sel_verts]
            return _selection_extent_report(len(sel_verts), world_pos,
                                            "mesh component (object mode)")

    # No component selection — report the extent of the selected OBJECTS so the
    # read never hard-errors on a mode mismatch.
    sel_objs = list(bpy.context.selected_objects)
    if sel_objs:
        world_pos = [c for o in sel_objs for c in world_bbox_corners(o)]
        return _selection_extent_report(len(sel_objs), world_pos, "objects")

    return {"success": True, "selected_count": 0, "scope": None,
            "centroid_world": None, "bbox_world": None}


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


def delete_shape_key(params):
    """Delete one shape key, or ALL of them, from a mesh (Object Data > Shape Keys >
    the ⌄ menu > Delete / Delete All Shapes). Removing EVERY key turns a keyed mesh
    back into a plain mesh — which is what UNBLOCKS apply-Subsurf and dyntopo (both
    refuse to run while any shape key exists). A mesh duplicated from a rigged source
    inherits its keys; clear them before densifying for sculpt. Deleting all leaves
    the mesh at the Basis shape — to keep a dialed-in non-Basis mix, apply it to
    the mesh first."""
    name = params.get("name")
    key = params.get("key") or ""
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}
    data = getattr(obj, "data", None)
    sk = getattr(data, "shape_keys", None) if data is not None else None
    if sk is None:
        return {"error": f"'{name}' has no shape keys"}
    before = [k.name for k in sk.key_blocks]
    if not key or key.upper() == "ALL":
        obj.shape_key_clear()
        return {"success": True, "name": name, "deleted": before, "remaining": []}
    kb = sk.key_blocks.get(key)
    if kb is None:
        return {"error": f"shape key '{key}' not found on '{name}'. Available: {before}"}
    obj.shape_key_remove(kb)
    after = obj.data.shape_keys
    remaining = [k.name for k in after.key_blocks] if after else []
    return {"success": True, "name": name, "deleted": [key], "remaining": remaining}


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


def remesh(params):
    """G50 — REMESH: rebuild the whole mesh's topology automatically (the auto-retopology
    primitive). Two modes:
      voxel — flood the volume with a uniform voxel grid → an even, watertight all-quad-ish
              surface at `voxel_size` (m). The sculpt-density remesh: kills stretched/poor
              flow, gives uniform resolution to sculpt on. Smaller voxel = more detail kept.
      quad  — QuadriFlow: solve a clean, mostly-quad field at ~`target_faces` faces. The
              deformation-grade retopo: even quad flow over the form. Slower.
    Destructive (replaces the geometry); object must be a mesh. Refused on rigged/keyed
    meshes (a full retopo invalidates every deform bind / shape key)."""
    from .common import linked_guard, deform_binds
    name = params.get("name") or params.get("target")
    obj = bpy.data.objects.get(name) if name else bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": f"'{name}' is not a mesh"}
    err = linked_guard(obj)
    if err:
        return {"error": err}
    if obj.data.shape_keys or deform_binds(obj):
        return {"error": "refusing to remesh a rigged/keyed mesh — a full retopo "
                         "invalidates every shape key and deform bind. Duplicate it "
                         "(object op=duplicate), strip the rig, then remesh the copy."}
    mode = (params.get("mode") or "voxel").lower()
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    activate(obj)
    v_before = len(obj.data.vertices)
    f_before = len(obj.data.polygons)
    if mode == "voxel":
        vsize = float(params.get("voxel_size", 0.05))
        if vsize <= 0:
            return {"error": "voxel_size must be > 0 (meters)"}
        obj.data.remesh_voxel_size = vsize
        try:
            bpy.ops.object.voxel_remesh()
        except RuntimeError as e:
            return {"error": f"voxel_remesh failed: {e}"}
        detail = {"voxel_size": vsize}
    elif mode == "quad":
        target = int(params.get("target_faces", 5000))
        try:
            bpy.ops.object.quadriflow_remesh(target_faces=target, use_mesh_symmetry=False)
        except RuntimeError as e:
            return {"error": f"quadriflow_remesh failed: {e}"}
        detail = {"target_faces": target}
    else:
        return {"error": f"unknown mode '{mode}' — use 'voxel' or 'quad'"}
    result = {"success": True, "object": obj.name, "mode": mode,
              "verts_before": v_before, "faces_before": f_before,
              "verts_after": len(obj.data.vertices), "faces_after": len(obj.data.polygons)}
    result.update(detail)
    return result


def clad_surface(params):
    """G97: create a watertight offset SHELL that follows a surface region — the
    create-half of shrinkwrap. Clothing, armor, plating, a phone case, bark over a trunk,
    an apple's skin, candle wax over a wick, shrink-wrap film: all are 'a new shell that
    follows a surface, held a clearance off it, with a wall thickness'. Today that's an
    8-call hand retopo (duplicate → restrict to region → delete the rest → inflate off the
    skin → solidify → material); this is the one call.

    The SHRINKWRAP modifier only fits a shell you've ALREADY modelled and placed onto a
    target, and has no standoff dial. This CREATES the region-following shell with the
    clearance baked in — clothing's whole point is to float just above the skin.

    target:    the surface to clad (empty = active object).
    region:    'whole' = the entire surface | 'selection' = the live vertex selection on
               the target (select the band/patch first, then clad) | 'trunk' = the whole
               mesh minus its limbs/protrusions (so a garment dodges T-posed arms — the
               'mesh minus limbs' selection the agent otherwise can't express).
    clearance: outward standoff in m — how far the shell's inner wall floats off the
               surface (default 0.005 = 5mm). The skin is lifted along its normals by this.
    thickness: wall thickness in m (default 0.004 = 4mm), carried as a live SOLIDIFY
               modifier grown OUTWARD so the inner wall stays exactly `clearance` proud.
    new_name:  name for the shell object (default '<target>_shell').
    """
    import bmesh
    target_name = params.get("target") or params.get("name")
    clearance = float(params.get("clearance", 0.005))
    thickness = float(params.get("thickness", 0.004))
    region = (params.get("region") or "whole").lower()
    target = bpy.data.objects.get(target_name) if target_name else bpy.context.active_object
    if target is None or target.type != 'MESH':
        return {"error": f"clad needs a mesh target (got {target_name!r})"}
    if region not in ("whole", "selection", "trunk"):
        return {"error": "region must be 'whole', 'selection', or 'trunk'"}
    new_name = params.get("new_name") or f"{target.name}_shell"

    # 'trunk' resolves to a vertex set NOW (off the cage topology) so it survives the
    # duplicate as plain selection flags, same path as region='selection'.
    trunk_ids = None
    if region == "trunk":
        from . import topology
        abm = topology._topology_bmesh(target, "cage")
        try:
            bbox = topology._bbox(abm)
            prots, _ap = topology.find_protrusions(abm, bbox)
        finally:
            abm.free()
        limb_ids = set()
        for p in prots:
            limb_ids.update(p["member_ids"])
        n = len(target.data.vertices)
        trunk_ids = [i for i in range(n) if i not in limb_ids]
        if not trunk_ids or len(trunk_ids) == n:
            return {"error": "region='trunk' found no limbs to exclude — the mesh has no "
                             "protrusions (run feel op=topology method=structure to see "
                             "the regime). Use region='whole' or 'selection'."}

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # For region='trunk' write the computed selection onto the source mesh so the
    # duplicate inherits it; region='selection' relies on the selection already set.
    if region == "trunk":
        for v in target.data.vertices:
            v.select = False
        for i in trunk_ids:
            target.data.vertices[i].select = True

    bpy.ops.object.select_all(action='DESELECT')
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.duplicate(linked=False)
    dup = bpy.context.active_object
    dup.name = new_name
    if dup.data:
        dup.data.name = new_name

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    if region in ("selection", "trunk"):
        bm = bmesh.from_edit_mesh(dup.data)
        if not any(v.select for v in bm.verts):
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.data.objects.remove(dup, do_unlink=True)
            return {"error": f"region='{region}' but no vertices are selected on "
                             f"'{target.name}' — make the selection first."}
        # Keep the region: drop everything else.
        bpy.ops.mesh.select_all(action='INVERT')
        bpy.ops.mesh.delete(type='VERT')
        bpy.ops.mesh.select_all(action='SELECT')
    else:
        bpy.ops.mesh.select_all(action='SELECT')

    # Lift the skin off the body along its own normals by `clearance` (local-space,
    # scale-corrected — same convention as edit op=shrink_fatten).
    sx = abs(dup.scale.x) or 1.0
    sy = abs(dup.scale.y) or 1.0
    sz = abs(dup.scale.z) or 1.0
    bm = bmesh.from_edit_mesh(dup.data)
    bm.normal_update()
    lifted = 0
    for v in bm.verts:
        nrm = v.normal
        if nrm.length == 0:
            continue
        v.co.x += nrm.x * clearance / sx
        v.co.y += nrm.y * clearance / sy
        v.co.z += nrm.z * clearance / sz
        lifted += 1
    bmesh.update_edit_mesh(dup.data)
    bpy.ops.object.mode_set(mode='OBJECT')

    # Wall thickness as a live SOLIDIFY, grown OUTWARD (offset=1) so the inner wall —
    # the lifted skin — keeps its `clearance` standoff and the wall thickens away from
    # the body.
    mod = dup.modifiers.new(name="Shell", type='SOLIDIFY')
    mod.thickness = thickness
    mod.offset = 1.0

    bb = world_bbox(dup)
    dims = [round(bb[3] - bb[0], 4), round(bb[4] - bb[1], 4), round(bb[5] - bb[2], 4)]
    return {"success": True, "shell": dup.name, "target": target.name,
            "region": region, "clearance": round(clearance, 5),
            "thickness": round(thickness, 5), "verts": lifted, "dimensions": dims}


def hollow(params):
    """G106/G127 — hollow a solid into an OPEN VESSEL in one call: the reliable recipe the
    dogfood reverse-engineered every time (delete the end cap → SOLIDIFY inward → a
    manifold cup), instead of inset→extrude (which seals the wrong end, G118) or a manual
    cutter-cylinder. Applies the solidify so the result is concrete + inspectable, and
    REPORTS the measured world wall thickness (so an unapplied scale can't hide a 2× wall).

    target:    the mesh to hollow (empty = active).
    thickness: wall thickness in m (default 0.004 = 4mm). Grown INWARD (offset=-1) so the
               outer silhouette is unchanged.
    open:      which end to open — 'top' (default, +Z cap) | 'bottom' (−Z) | 'none' (a
               closed hollow shell, no opening).
    """
    import bmesh
    from .common import scale_unit_note, linked_guard
    name = params.get("target") or params.get("name")
    obj = bpy.data.objects.get(name) if name else bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": f"hollow needs a mesh target (got {name!r})"}
    err = linked_guard(obj)
    if err:
        return {"error": err}
    thickness = float(params.get("thickness", 0.004))
    if thickness <= 0:
        return {"error": "thickness must be > 0 (the wall thickness in m)"}
    open_end = (params.get("open") or "top").lower()
    if open_end not in ("top", "bottom", "none"):
        return {"error": "open must be 'top', 'bottom', or 'none'"}

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    deleted = 0
    if open_end != "none":
        me = obj.data
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        zs = [v.co.z for v in bm.verts]
        zmin, zmax = min(zs), max(zs)
        span = (zmax - zmin) or 1.0
        ndir = 1.0 if open_end == "top" else -1.0
        edge_z = zmax if open_end == "top" else zmin
        caps = []
        for f in bm.faces:
            c = f.calc_center_median()
            if f.normal.z * ndir > 0.7 and abs(c.z - edge_z) < 0.03 * span:
                caps.append(f)
        if not caps:
            bm.free()
            return {"error": f"no {open_end} cap face found to open — is the mesh capped "
                             f"on that end, and is +Z its up axis?"}
        bmesh.ops.delete(bm, geom=caps, context='FACES')
        deleted = len(caps)
        bm.to_mesh(me)
        bm.free()

    mod = obj.modifiers.new(name="Hollow", type='SOLIDIFY')
    mod.thickness = thickness
    mod.offset = -1.0   # grow inward; outer silhouette unchanged
    activate(obj)
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
        applied = True
    except RuntimeError as e:
        applied = False
        obj.modifiers.remove(mod)
        return {"error": f"hollow: SOLIDIFY apply failed ({e}); no change committed."}

    out = {"success": True, "object": obj.name, "thickness": round(thickness, 5),
           "open": open_end, "cap_faces_removed": deleted, "applied": applied,
           "status_focus": obj.name}
    eff, note = scale_unit_note(obj, thickness, what="wall thickness")
    if note:
        out["world_thickness"] = eff
        out.setdefault("notes", []).append(note)
    return out


TOOLS = {
    "remesh":                 remesh,
    "clad_surface":           clad_surface,
    "hollow":                 hollow,
    "rename_object":          rename_object,
    "select_object":          select_object,
    "delete_object":          delete_object,
    "duplicate_object":       duplicate_object,
    "join_objects":           join_objects,
    "set_mode":               set_mode,
    "get_object_info":        get_object_info,
    "get_mesh_profile":       get_mesh_profile,
    "get_silhouette":         get_silhouette,
    "get_section":            get_section,
    "get_current_selection":  get_current_selection,
    "get_custom_properties":  get_custom_properties,
    "set_custom_property":    set_custom_property,
    "set_particle_visibility": set_particle_visibility,
    "list_shape_keys":        list_shape_keys,
    "set_shape_key":          set_shape_key,
    "set_active_shape_key":   set_active_shape_key,
    "delete_shape_key":       delete_shape_key,
    "set_object_visibility":  set_object_visibility,
}

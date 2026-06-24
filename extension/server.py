"""Dispatch + socket server.

Aggregates the per-module TOOLS dicts into a single registry, runs each
incoming command on Blender's main thread, then auto-appends history +
status (subject to per-tool opt-out sets in `state`).
"""

import json
import socket
import threading

import bpy

from . import (
    addons,
    armature,
    assembly,
    bands,
    collab,
    connectors,
    curves,
    designs,
    editmode,
    fields,
    fit,
    finishes,
    groups,
    handles,
    history,
    introspect,
    lighting,
    lint,
    objects,
    primitives,
    queries,
    relational,
    render,
    rings,
    scatter,
    sculpt,
    shaders,
    shading,
    state,
    status,
    textures,
    topology,
    transforms,
    validation,
    viewport,
)

# Modules order doesn't matter for dispatch, but later entries overwrite earlier
# duplicates — which is intentionally never expected to happen.
_TOOL_MODULES = (
    status,      # get_scene_tree, get_blender_status
    viewport,
    collab,      # SPEC-12 shared-state collaboration panel
    history,
    primitives,
    curves,
    connectors,
    objects,
    transforms,
    queries,
    relational,
    groups,
    finishes,
    editmode,
    fields,
    fit,
    rings,
    bands,
    shading,
    shaders,
    textures,
    lighting,
    render,
    armature,
    scatter,
    sculpt,
    designs,
    lint,
    introspect,
    topology,
    handles,
    assembly,
    validation,  # SPEC-16: validate_* ops (expect / intended / stats / run)
    addons,      # generic addon/operator bridge (addon_list / addon_inspect / addon_run)
)

TOOLS = {}
for _mod in _TOOL_MODULES:
    TOOLS.update(_mod.TOOLS)

# SPEC-15: tools that stay available while the external-mutation lock is SET. The lock
# is an ALLOWLIST (fail-closed) — anything not named here is blocked until acknowledge.
# Reads (state.NON_UNDOABLE_TOOLS) ∪ pure selection ∪ mode/nav ∪ render (a read→image)
# ∪ status ∪ the acknowledge op itself. Selection mutates only the SELECTION, never world
# geometry, so it's safe — it's how the agent re-grounds before clearing the lock.
_SELECTION_TOOLS = {
    "set_component_mode", "select_all", "select_by_axis", "select_between",
    "select_by_vgroup", "select_by_material", "grow_selection", "flood_to_crease",
    "random_select", "select_in_sphere", "select_boundary", "select_limb",
    "select_ring", "select_rings", "verify_selection", "select_object",
}
LOCK_EXEMPT_TOOLS = (
    state.NON_UNDOABLE_TOOLS | _SELECTION_TOOLS |
    {"acknowledge_mutation", "render_to_file", "get_blender_status", "set_mode"}
)

# Tools that require edit mode — support an optional `target` param that auto-selects the
# named object and enters edit mode, then exits back to OBJECT mode after the call.
EDIT_MODE_TOOLS = {
    "bevel", "extrude", "loop_cut", "subdivide_selection", "set_component_mode", "select_all",
    "select_by_axis", "select_between", "grow_selection", "move_vertices",
    "scale_vertices", "delete_geometry", "separate_selection", "jitter_vertices",
    "random_select", "proportional_move", "inflate_selection", "mark_sharp",
    "set_edge_crease", "merge_by_distance", "select_in_sphere", "select_by_radius", "split_by_part",
    "get_rings", "select_ring", "select_rings", "scale_rings", "taper_end", "taper_section",
    "shape_profile", "flute", "field",
    "assign_weight", "select_boundary", "select_limb", "flood_to_crease",
    "select_by_vgroup", "select_by_material",
    "relax_selection", "slide_selection", "poke_faces", "inset_faces", "grid_fill",
}

# Y1: verbs that write VERTEX POSITIONS, so on a keyed mesh they land on the active
# shape key. A position edit on a non-Basis active key is silently swallowed (value
# 0) or scaled (value>0) — every one of these must say which key it wrote to. Pure
# selection / topology-flag verbs are excluded (they don't move verts). Sculpt
# strokes write to the active key too, so they're in here despite not being EDIT.
SHAPE_KEY_SHADOW_TOOLS = {
    "move_vertices", "scale_vertices", "snap_loop", "proportional_move",
    "inflate_selection",
    "jitter_vertices", "bevel", "extrude", "extrude_along_curve", "scale_rings",
    "subdivide_selection", "relax_selection", "slide_selection",
    "poke_faces", "inset_faces", "grid_fill",
    "taper_end", "taper_section", "shape_profile", "flute", "field",
    "sculpt_grab", "sculpt_inflate", "sculpt_draw", "sculpt_smooth", "sculpt_crease",
    "sculpt_pinch", "sculpt_flatten", "sculpt_gravity",
}


# G56: every op that's SUPPOSED to change an object's geometry or its transform. A
# "success" that leaves the signature byte-identical is a no-op — surfaced so it can't
# launder a mistake. EXCLUDED on purpose: pure selection / flag ops (mark_sharp, crease,
# select_*, assign_weight) and non-geometry mutations (material, visibility, rename,
# modifier add/modify/remove without bake) — they don't touch geometry or transform, so
# an unchanged signature is expected, not a no-op (checking them would cry wolf).
# Creation ops (add_*, array_*, mirror, scatter, duplicate) are out too — they always
# yield new geometry, so "unchanged" is meaningless. Sculpt is in; multires (which stores
# displacement off the base verts) isn't built here, so base-vert reads are valid.
NOOP_CHECK_TOOLS = {
    # edit-mode geometry writers
    "move_vertices", "scale_vertices", "snap_loop", "proportional_move",
    "inflate_selection", "jitter_vertices", "bevel", "extrude",
    "extrude_along_curve", "scale_rings", "subdivide_selection",
    "relax_selection", "slide_selection", "poke_faces", "inset_faces",
    "grid_fill", "taper_end", "taper_section", "shape_profile", "flute", "field",
    "loop_cut", "merge_by_distance",
    "delete_geometry", "separate_selection", "bridge_handles",
    # object transforms (caught via the TRS component of the signature)
    "nudge", "place", "aim_axis", "rest_on", "move_to", "rotate_to",
    "resize", "scale_group", "rotate_object", "apply_transform",
    "snap_to", "snap_to_grid", "set_origin", "match_dimension",
    # geometry bakers. G101: smooth_edges is EXCLUDED — it adds a BEVEL modifier + sets
    # shade-smooth flags and never touches base vertex positions, so the geometry
    # signature is byte-identical by design; checking it cried "no-op" on every successful
    # shade-smooth. Shading-only ops have no geometry no-op to detect.
    "boolean", "apply_modifiers", "noise_displace", "bend",
    "round_corners", "remesh", "join_objects", "bake_shape_keys_to_basis", "hollow",
    # sculpt strokes
    "sculpt_grab", "sculpt_inflate", "sculpt_draw", "sculpt_smooth",
    "sculpt_crease", "sculpt_pinch", "sculpt_flatten", "sculpt_gravity",
}


# Bakers whose CHANGED object is the `target` param (their other object — cutter /
# reference — is a separate param). Everywhere else the moved object is `targets` (the
# moved selection) or `name`/`names`; for snap_to / rest_on the `target` param is the
# reference/surface, NOT what moves, so it must never be picked.
_NOOP_TARGET_KEY = {"boolean", "match_dimension", "noise_displace", "round_corners"}


# G77: ops that PLACE a single part — after these, the status block auto-surfaces a NEW
# penetration of the placed object against its neighbours, so the agent verifies clearance
# by reading rather than hand-computing. Bulk placers (array_*/scatter) and curve builders
# are excluded (one focus object, and they're usually deliberately interleaved).
PLACEMENT_TOOLS = {
    "nudge", "place", "move_to", "rest_on", "seat_into", "snap_to",
    "rotate_object", "scale_group",
    "add_box", "add_plane", "add_cylinder", "add_sphere", "add_cone",
    "add_torus", "add_icosphere", "add_circle", "add_text",
}


# SPEC-16: the ops after which the always-on `validate` floor runs (scoped to the
# touched delta) and the ambient `feel` delta is attached. Geometry/transform mutators
# plus the single-part placers — every op that can introduce a z-fight, a penetration,
# a flipped normal, or non-manifold junk. The relational `validate` clipping check
# SUBSUMES the old G77 placement self-report (auto_proximity_note), so that separate
# emission is retired here — validate is now the single relational authority, with
# intent-suppression the raw note never had.
VALIDATE_AFTER = NOOP_CHECK_TOOLS | PLACEMENT_TOOLS

# G105/G118/G134: ops that can change CONNECTIVITY (add/remove geometry, weld, cut, fill)
# — the only ones where a topology degrade (new boundary loop, non-manifold edge, broken
# Euler) is possible. Pure transforms and vert-moving deformers can't change topology, so
# they're excluded to keep the before/after snapshot off the hot path.
TOPO_CHECK_TOOLS = {
    "extrude", "extrude_along_curve", "inset_faces", "poke_faces", "loop_cut",
    "subdivide_selection", "grid_fill", "merge_by_distance", "delete_geometry",
    "separate_selection", "bridge_handles", "boolean", "apply_modifiers", "remesh",
    "join_objects", "round_corners", "bevel",
}

# SPEC-16 (feedback P1.4): the ambient `feel` delta only earns its keep on ops that
# change TOPOLOGY (or create geometry) — for a pure transform (nudge/place/rotate/
# resize/snap) the status block already carries the new dims, so a `feel: …42v… dims…`
# line every nudge is pure chatter across a 130-call build. validate still runs on
# transforms (a nudge can author a clip); only the perceptual echo is gated.
_PURE_TRANSFORMS = {
    "nudge", "place", "aim_axis", "rest_on", "seat_into", "move_to", "rotate_to",
    "resize", "scale_group", "rotate_object", "apply_transform", "snap_to",
    "snap_to_grid", "set_origin", "match_dimension",
}
FEEL_DELTA_AFTER = VALIDATE_AFTER - _PURE_TRANSFORMS


def _noop_obj(tool, params, edit_target):
    """The object a no-op-checked op should change. EDIT_MODE_TOOLS already resolved it
    into `edit_target` (popped from params). Object-level ops name the moved object in
    `targets` (preferred — `target` is a reference for snap/rest/boolean), or `name`/
    `mesh`/`names`, or (bakers) `target`. A list / comma string → its first entry
    (best-effort on multi-target: if the whole op no-op'd, the first one is unchanged
    too). Falls back to the active object — which most ops leave as their changed
    object (activate()) — for sculpt and in-session edits."""
    if edit_target:
        name = edit_target
    else:
        cand = params.get("targets")
        if not cand and tool in _NOOP_TARGET_KEY:
            cand = params.get("target")
        if not cand:
            cand = params.get("name") or params.get("mesh") or params.get("names")
        if isinstance(cand, (list, tuple)):
            cand = cand[0] if cand else ""
        if isinstance(cand, str) and "," in cand:
            cand = cand.split(",")[0].strip()
        name = cand
    obj = bpy.data.objects.get(name) if isinstance(name, str) and name else None
    return obj or bpy.context.active_object


def _geo_signature(obj):
    """G56 — a cheap fingerprint for no-op detection over BOTH halves of "modifies an
    object": its transform AND its mesh.

    Transform: the raw TRS fields (location / scale / euler + quaternion, quantized),
    read directly so a pure object move registers even though local vert coords don't —
    and read immediately (no depsgraph), since the op just set them.

    Mesh: vert/face counts plus a SUM OF PER-VERTEX coordinate HASHES. The per-vertex
    hash must be non-linear: a plain Σcoord is invariant under a symmetric edit (a ring
    scaled about its centre moves every vert by a mirror-cancelling delta), which once
    made a real flare read as a no-op. Hashing each quantized position breaks that while
    the outer sum stays order-independent. Works for non-mesh objects too (TRS only).
    None for a missing object."""
    if obj is None:
        return None
    loc, scl = obj.location, obj.scale
    re_, rq = obj.rotation_euler, obj.rotation_quaternion
    trs = (int(loc.x * 1e5), int(loc.y * 1e5), int(loc.z * 1e5),
           int(scl.x * 1e5), int(scl.y * 1e5), int(scl.z * 1e5),
           int(re_.x * 1e5), int(re_.y * 1e5), int(re_.z * 1e5),
           int(rq.w * 1e5), int(rq.x * 1e5), int(rq.y * 1e5), int(rq.z * 1e5))
    vcount = fcount = 0
    acc = 0
    if getattr(obj, "type", None) == 'MESH':
        import bmesh
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            vcount, fcount = len(bm.verts), len(bm.faces)
            coords = [v.co for v in bm.verts]
        else:
            me = obj.data
            vcount, fcount = len(me.vertices), len(me.polygons)
            coords = [v.co for v in me.vertices]
        for co in coords:
            acc = (acc + hash((int(co.x * 1e5), int(co.y * 1e5), int(co.z * 1e5)))) \
                & 0xFFFFFFFFFFFFFFFF
    return (vcount, fcount, acc, trs)


def _topo_signature(obj):
    """G105/G118/G134 — a cheap topology fingerprint captured before/after a geometry op
    so the dispatch can warn the MOMENT an op DEGRADES the mesh (the mirror of the no-op
    detector, which only catches an op that did NOTHING). Carries the boundary-loop count,
    the true non-manifold edge count (0 or 3+ linked faces — NOT 1-face rims, G129), and
    χ/Euler validity. O(V+E); skips the expensive self-intersection BVH (the floor still
    catches that in the same response). None for a non-mesh / missing object."""
    if obj is None or getattr(obj, "type", None) != 'MESH' or obj.data is None:
        return None
    import bmesh
    owned = False
    if obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(obj.data)
    else:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        owned = True
    try:
        from .common import boundary_loop_count, euler_consistent, mesh_components
        V, E, F = len(bm.verts), len(bm.edges), len(bm.faces)
        non_manifold = sum(1 for e in bm.edges if len(e.link_faces) not in (1, 2))
        b = boundary_loop_count(bm)
        euler_ok, chi = euler_consistent(V, E, F, b, mesh_components(bm))
        return {"boundary_loops": b, "non_manifold": non_manifold,
                "chi": chi, "euler_ok": euler_ok}
    finally:
        if owned:
            bm.free()


def _topology_delta_warning(before, after):
    """Build the one-line 'this op degraded the geometry' warning from two _topo_signature
    snapshots, or None when nothing got worse. Only DEGRADATIONS speak (a heal is silent —
    exception-reporting, like the rest of the floor)."""
    if not before or not after:
        return None
    bits = []
    db = after["boundary_loops"] - before["boundary_loops"]
    if db > 0:
        bits.append(f"opened {db} new boundary loop(s) (was {before['boundary_loops']}, "
                    f"now {after['boundary_loops']}) — a part that should stay closed may "
                    f"have sprung a hole; if intended, validate op=expect to declare it")
    dn = after["non_manifold"] - before["non_manifold"]
    if dn > 0:
        bits.append(f"created {dn} non-manifold edge(s) (now {after['non_manifold']}) — "
                    f"3+-face junctions a boolean/weld left behind")
    if before["euler_ok"] and not after["euler_ok"]:
        bits.append(f"made the topology INCONSISTENT (χ={after['chi']}, "
                    f"{after['boundary_loops']} boundary loop(s) — impossible for a clean "
                    f"surface): the op likely did the opposite of its intent")
    if not bits:
        return None
    return "topology degraded: " + "; ".join(bits)


def _enter_edit_for_target(target_name):
    """Select target and enter EDIT mode. Returns (switched, error)."""
    active = bpy.context.active_object
    if active is not None and active.name == target_name and active.mode == 'EDIT':
        return False, None
    if active is not None and active.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    obj = bpy.data.objects.get(target_name)
    if obj is None:
        return False, f"target '{target_name}' not found"
    # Editing the geometry of library-linked data fails or silently no-ops in
    # Blender — block it loudly (gaps.md U10). Every edit-mode tool routes through
    # here, so this one hook guards the whole geometry-edit family.
    from .common import linked_guard
    err = linked_guard(obj)
    if err:
        return False, err
    # W2: the request-scoped path below does its own bind snapshot/compare around
    # this single verb. Drop any pending manual-path snapshot so a stale one (from
    # an edit session abandoned via the Blender UI) can't bleed onto this edit.
    state.clear_edit_binds()
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    return True, None


def _status_focus(result):
    """G76: the name of the object an op ACTED ON, read from the handler's own result
    keys (the handler knows what it touched — unambiguous, unlike the overloaded request
    `target`, which for snap/rest_on names the REFERENCE, not the moved object). The
    status block focuses its bounds on this so a name-addressed op (multi-target material
    or transform) reports the right object instead of the stale viewport-active one.
    Returns the first acted-on name, or None to fall back to the active object."""
    explicit = result.get("status_focus")
    if isinstance(explicit, str) and explicit:
        return explicit
    for key in ("moved", "rotated", "resized", "scaled", "aimed", "applied_to",
                "assigned_to", "placed", "rested", "object_name", "objects", "renamed"):
        v = result.get(key)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, list) and v:
            first = v[0]
            if isinstance(first, str) and first:
                return first
            if isinstance(first, dict) and isinstance(first.get("name"), str):
                return first["name"]
    return None


def execute_command(command):
    tool   = command.get("tool")
    params = command.get("params", {})
    label  = command.get("label", "")
    fn = TOOLS.get(tool)
    if fn is None:
        return {"error": f"Unknown tool: {tool}. Available: {list(TOOLS.keys())}"}

    # X6: if a prior op timed out and orphaned, force-retag the object it touched
    # before this command reads anything, so introspection sees real geometry.
    state.flush_eval_dirty()

    target = params.pop("target", "") if tool in EDIT_MODE_TOOLS else ""
    # G40/G34: a target= GUARANTEES the op lands in the right mode. But the natural
    # chain "select a region (leaves Object mode), then act on it" passes no target on
    # the second call — so fall back to the ACTIVE mesh as the implicit target. The
    # selection survives on the mesh, so this enters Edit on the right object and the
    # op finds its selection. If the active object is already in EDIT (an explicit
    # multi-op edit session), _enter_edit_for_target is a no-op and won't exit after —
    # the session is preserved.
    if tool in EDIT_MODE_TOOLS and not target:
        _active = bpy.context.active_object
        if _active is not None and _active.type == 'MESH':
            target = _active.name
    auto_switched = False
    bind_snapshot = None  # (target_name, [(mod, type)…], pre-edit vert count) — V2
    if target:
        auto_switched, err = _enter_edit_for_target(target)
        if err:
            return {"error": err}
        # V2: snapshot any vert-count-dependent deform binds before the edit, so we
        # can warn loudly if this topology edit silently invalidated them.
        from .common import deform_binds
        _tobj = bpy.data.objects.get(target)
        if _tobj is not None and getattr(_tobj, "data", None) is not None:
            binds = deform_binds(_tobj)
            if binds and hasattr(_tobj.data, "vertices"):
                _vc = len(_tobj.data.vertices)
                if "bb_bind_vcount" not in _tobj:  # X4: seed valid count on first sight
                    _tobj["bb_bind_vcount"] = _vc
                bind_snapshot = (target, binds, _vc)

    is_mutating = tool not in state.NON_UNDOABLE_TOOLS
    # Snapshot the scene once, before the very first mutating op, so an undo that
    # walks all the way back to empty can still be verified against a known state.
    if is_mutating and not state._history and state._undo_baseline is None:
        state._undo_baseline = state.scene_object_names()

    # G56: snapshot a cheap geometry signature for the no-op detector. A mutating
    # geometry op that reports success while changing nothing LAUNDERS the mistake —
    # the corrosive failure for a trust-the-status-block system. Captured here (after
    # the target= edit-mode entry, so we read the right object) and compared post-op.
    noop_name = None
    geo_before = None
    topo_before = None
    if tool in NOOP_CHECK_TOOLS:
        _gobj = _noop_obj(tool, params, target)
        if _gobj is not None:
            noop_name = _gobj.name
            geo_before = _geo_signature(_gobj)
            # G105/G118/G134: snapshot topology too, so a degrade (new hole, non-manifold
            # junk, broken Euler) is caught at the op, not one read later.
            if tool in TOPO_CHECK_TOOLS:
                topo_before = _topo_signature(_gobj)

    try:
        result = fn(params)
    except Exception as e:
        result = {"error": str(e)}
    finally:
        if auto_switched:
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

    # Y1a: a position-writing edit on a keyed mesh lands on the ACTIVE shape key, not
    # the displayed mesh. Surface which key — generically, so it fires on the target=
    # path AND an in-session no-target edit (both route through here). Computed before
    # the bind check so it takes precedence over the misleading bind_shadowed (Y1c).
    shape_shadow = None
    if tool in SHAPE_KEY_SHADOW_TOOLS and isinstance(result, dict) and result.get("success"):
        from .common import active_shape_key_shadow, shape_key_shadow_warning
        edited = bpy.data.objects.get(target) if target else bpy.context.active_object
        shape_shadow = active_shape_key_shadow(edited) if edited is not None else None
        if shape_shadow:
            result["shape_key_shadowed"] = shape_shadow["shadowed"]
            result["shape_key_active"] = shape_shadow
            result["shape_key_warning"] = shape_key_shadow_warning(shape_shadow, edited.name)

    # V2: after the edit verb returned to OBJECT mode (mesh data resynced), check
    # whether the topology actually changed under a bound modifier. A vert-count
    # delta is the documented bind-killer; a position-only edit (move_vertices …)
    # leaves the count — and the bind — intact, so it never warns.
    if bind_snapshot and isinstance(result, dict) and result.get("success"):
        from .common import deform_bind_warning, rest_shadow_warning
        tname, binds, before = bind_snapshot
        tobj = bpy.data.objects.get(tname)
        if (tobj is not None and getattr(tobj, "data", None) is not None
                and hasattr(tobj.data, "vertices")):
            after = len(tobj.data.vertices)
            if after != before:
                result["bind_invalidated"] = True
                result["bind_warning"] = deform_bind_warning(binds)
            elif tobj.get("bb_bind_vcount") == after and shape_shadow is None:
                # X4: position-only edit under a still-valid reconstruct bind — the
                # rest-shape change is shadowed until rebind. Skipped when a shape-key
                # shadow already explained the vanished edit (Y1c precedence).
                result["bind_shadowed"] = True
                result["bind_warning"] = rest_shadow_warning(binds)

    # G56: compare the post-op signature. Identical geometry under a reported success
    # means the op was a no-op — surface it rather than let the success launder it. The
    # warning rides the same channel as the bind/shape-key warnings (see _core._status).
    if (geo_before is not None and noop_name and isinstance(result, dict)
            and result.get("success")):
        _gobj2 = bpy.data.objects.get(noop_name)
        geo_after = _geo_signature(_gobj2) if _gobj2 is not None else None
        if geo_after is not None and geo_after == geo_before:
            result["no_op"] = True
            result["no_op_warning"] = (
                "no-op: this op reported success but the geometry is byte-identical "
                "before and after — nothing moved. Check the selection captured what "
                "you intended and the parameters are non-trivial (e.g. scale≠1, "
                "amount≠0, a ring that actually has spread to scale).")

    # G105/G118/G134: the mirror of the no-op detector — an op that SUCCEEDED but
    # DEGRADED the geometry (sprang a hole, left non-manifold junk, broke the Euler
    # invariant). Warns at the moment of the op, not on the next read's floor line.
    if (topo_before is not None and noop_name and isinstance(result, dict)
            and result.get("success")):
        _tobj2 = bpy.data.objects.get(noop_name)
        topo_after = _topo_signature(_tobj2) if _tobj2 is not None else None
        tw = _topology_delta_warning(topo_before, topo_after)
        if tw:
            result["topology_delta_warning"] = tw

    # Log + push the undo step AFTER edit-mode tools have returned to OBJECT mode,
    # so each step is an object-mode checkpoint (undoable from object mode) and
    # the history log stays exactly 1:1 with Blender's undo stack.
    if is_mutating and isinstance(result, dict) and result.get("success"):
        result["op_id"] = state.log_operation(tool, params, label)
        state.push_undo_step(result["op_id"])
        # SPEC-12: every mutating op auto-enqueues for sign-off — the queue stays 1:1
        # with the undo stack (the whole diff), never an agent-curated subset.
        collab.enqueue(result["op_id"], label or tool)

    # SPEC-16: the two forced senses. After a geometry/placement op, run the always-on
    # correctness floor (`validate`, scoped to the touched delta + its relations) and
    # attach the ambient perceptual delta (`feel`, the touched object). Both ride the
    # result so _core._status renders them. validate's clipping check generalises the
    # old G77 placement self-report — there is no separate auto_proximity_note emission.
    if tool in VALIDATE_AFTER and isinstance(result, dict) and result.get("success"):
        try:
            focus = _status_focus(result)
            touched = [focus] if focus else None
            vres = validation.run_validate(touched)
            # G133: echo the CALL that produced this auto-fired read as a one-line suffix —
            # the floor fires these dozens of times a build, so each doubles as a worked
            # example of the verb to reach for (and cues WHICH read, e.g. clearance vs
            # contacts, when a deeper look is wanted). Suffix, not a new line: ~zero cost.
            if isinstance(vres, dict) and vres.get("line"):
                tgt = focus or "(scene)"
                vres["line"] += f"   ⟵ validate op=run targets={tgt}"
            result["validate"] = vres
            if focus and tool in FEEL_DELTA_AFTER:
                fd = validation.feel_delta(focus)
                if fd:
                    result["feel_delta"] = fd + f"   ⟵ feel op=all target={focus}"
            # SPEC-16 P1.6: accrue epistemic drift; periodically surface a whole-scene
            # re-ground recap so a stale mental model re-anchors on a long build.
            recap = validation.accrue_drift(tool)
            if recap:
                result["reground"] = recap
        except Exception:
            pass

    if tool not in state.NO_STATUS_TOOLS and isinstance(result, dict):
        try:
            focus = _status_focus(result) if result.get("success") else None
            sp = {"focus": focus} if focus else {}
            result["blender_status"] = status.get_blender_status(sp).get("status")
            # The floor must announce its own absence on EVERY block, so a disabled
            # validator can never be mistaken for a clean one (SPEC-16). For geometry
            # ops the validate dict already carries the OFF line; for the rest, flag it.
            if "validate" not in result and validation.is_global_off():
                result["validate_off"] = True
        except Exception:
            pass
    return result


def handle_client(conn):
    try:
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break

        command = json.loads(data.decode().strip())
        result_event = threading.Event()
        result_box = [None]

        def on_main_thread():
            # SPEC-15: external-mutation interlock, enforced at the CLIENT boundary (not
            # in execute_command, so headless test harnesses that orchestrate the scene
            # via direct bpy + execute_command calls are unaffected). Re-hash the live
            # scene; if something the server didn't do changed it, latch the lock and
            # HARD-BLOCK every world-mutating tool until the agent acknowledges. Reads /
            # selection / feel / render stay open so it can re-ground first.
            state.detect_external_mutation()
            tool = command.get("tool")
            if state._world_locked and tool not in LOCK_EXEMPT_TOOLS:
                result_box[0] = state.lock_error(tool)
            else:
                result_box[0] = execute_command(command)
            result_event.set()
            return None

        # Per-call timeout: long-running ops (render_to_file) carry their own
        # ceiling so they aren't cut off at the default 30s.
        timeout = command.get("timeout") or 30
        state._request_queue.put(on_main_thread)
        result_event.wait(timeout=timeout)

        if result_box[0] is None:
            # The op didn't finish within `timeout`. CRITICAL: never serialize None
            # here — `json.dumps(None)` is "null", which the MCP-side wrapper then
            # crashes on with `'NoneType' object has no attribute 'get'` (gaps.md X1).
            # Return an honest, actionable timeout error instead. The op was NOT
            # cancelled: it keeps running on the main thread, may complete, and logs
            # itself as a success — so retrying blindly stacks a second op behind it.
            tool = command.get("tool")
            p = command.get("params") or {}
            tname = p.get("target") or p.get("mesh") or p.get("name") or p.get("targets")
            if isinstance(tname, str) and tname:
                # The orphan completion can wedge this object's eval cache (X6) —
                # mark it so the next command force-retags before reading.
                state.mark_eval_dirty(tname.split(",")[0].strip())
            conn.sendall((json.dumps({"error":
                f"'{tool}' did not finish within {timeout}s. IMPORTANT: it was NOT "
                f"cancelled — a heavy bind/build keeps running on the main thread and "
                f"may COMPLETE and log itself as a success shortly. Do NOT blindly "
                f"retry (that queues a SECOND op behind the first). Check get_history "
                f"/ get_blender_status first; if it landed, you're done. For a "
                f"genuinely slow bind, retry with a larger timeout."}) + "\n").encode())
        else:
            conn.sendall((json.dumps(result_box[0]) + "\n").encode())
    except Exception as e:
        try:
            conn.sendall((json.dumps({"error": str(e)}) + "\n").encode())
        except Exception:
            pass
    finally:
        conn.close()


def bind_free_port():
    """Bind the first free port in [PORT_MIN, PORT_MAX) and set state.PORT to it.

    Returns a listening, accept-ready socket, or None if the whole range is taken
    (≥20 instances). Binding here on the main thread — then handing the socket to
    server_loop — avoids a TOCTOU race where a probe-bind-close leaves a window for
    a sibling instance to grab the same port before the loop re-binds it."""
    for p in range(state.PORT_MIN, state.PORT_MAX):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("localhost", p))
        except OSError:
            s.close()
            continue
        s.listen(5)
        s.settimeout(1.0)
        state.PORT = p
        return s
    return None


def server_loop(sock=None):
    if sock is None:
        # Legacy / direct-call path: bind the fixed port ourselves.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("localhost", state.PORT))
        sock.listen(5)
        sock.settimeout(1.0)
    while state._running:
        try:
            conn, _ = sock.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
        except socket.timeout:
            continue
    sock.close()


def process_queue():
    import queue as _queue
    while not state._request_queue.empty():
        try:
            fn = state._request_queue.get_nowait()
            fn()
        except _queue.Empty:
            break
    return 0.05

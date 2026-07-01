"""Module-wide mutable state: port, server flags, request queue, history log.

Kept in one place so any module can read/append without circular imports.
"""

import hashlib
import json
import math
import queue
import time

import bpy

# Each Blender instance grabs the first FREE port in [PORT_MIN, PORT_MAX) at start
# (server.bind_free_port), so N instances coexist instead of colliding on one port.
# PORT is overwritten with the actually-bound port; the MCP side scans the same range
# and `ping`s each to discover live instances (server/instances.py).
PORT = 8765
PORT_MIN = 8765
PORT_MAX = 8785          # exclusive — 20 instance slots

_request_queue = queue.Queue()
_server_thread = None
_running = False

_history = []
_redo_stack = []        # entries undone and available to redo (cleared on any new op)
_undo_baseline = None   # scene object-name set captured before the first mutating op
_snapshots = {}         # op_id -> {obj_name: geometry signature} for diff_since (P11)
_marks = {}             # G12: checkpoint name -> op_id of the history head when marked
                        # (None = marked at the empty baseline). `restore` undoes to it.

# ── SPEC-15: external-mutation interlock ──────────────────────────────────────
# THE ONE RULE made operational. The scene is a SHARED canvas: the user can edit in
# the Blender UI, an autosave or script can fire — it is only "static between our calls"
# by the user's courtesy, never by guarantee. So every server-known state carries a
# geometry hash; before each tool runs we re-hash the live scene and, on a mismatch,
# LATCH a lock that hard-blocks every world-mutating tool until the agent explicitly
# acknowledges. Reads / selection / feel stay open so it can re-ground first.
_clean_snapshot = None  # geometry snapshot as of the last server-known (clean) state
_scene_hash = None      # md5 of _clean_snapshot — the "edit hash" we compare against
_baseline_ref = None    # {op, label} the clean baseline corresponds to (for honest "since")
_world_locked = False   # True once an external mutation is detected; cleared by ack
_lock_info = None       # {since_op, since_label, added, removed, changed} for the error

_TOUCH = 0.0005         # 0.5 mm — matches introspect.diff_since's change floor

_VSAMPLE_CAP = 150      # max per-object vertices stored per snapshot (downsampled)


# Modifier props that are pure UI/panel state — toggling them isn't a meaningful change.
_MOD_PROP_SKIP = {"show_expanded", "is_active", "use_pin_to_last"}


def _modifier_props(m):
    """A JSON-stable dict of a modifier's writable parameters, read generically from its
    RNA so no per-type knowledge is needed. Pointers (target objects, vertex groups)
    collapse to their name; vectors/arrays to lists; UI-only panel state is skipped. This
    is what lets the interlock notice a modifier *retuned* (Solidify thickness, Subsurf
    levels), not just added/removed."""
    props = {}
    for p in m.bl_rna.properties:
        k = p.identifier
        if k == "rna_type" or k in _MOD_PROP_SKIP or p.is_readonly:
            continue
        try:
            v = getattr(m, k)
        except Exception:
            continue
        if isinstance(v, (bool, int, str)):
            props[k] = v
        elif isinstance(v, float):
            props[k] = round(v, 6)
        elif hasattr(v, "name"):           # pointer to a datablock (object/mesh/…)
            props[k] = v.name
        elif hasattr(v, "__len__"):        # vector / color / array
            try:
                props[k] = [round(x, 6) if isinstance(x, float) else x for x in v]
            except Exception:
                props[k] = str(v)
        # collections / unhandled types are skipped (consistently → no spurious diff)
    return props


def _object_signature(obj):
    """Compact, cheap geometry signature for diff_since. Transform (loc/rot/scale)
    is stored separately from a LOCAL-space vertex sample, so rigid motion and
    actual mesh deformation can be told apart later. Local verts mean a translate
    or rotate doesn't masquerade as a deformation."""
    sig = {
        "type": obj.type,
        "loc": [round(v, 6) for v in obj.location],
        "rot": [round(math.degrees(v), 4) for v in obj.rotation_euler],
        "scale": [round(v, 6) for v in obj.scale],
    }
    # SPEC-15: modifiers are NON-DESTRUCTIVE — they never touch the base mesh, so a
    # Solidify/Subdivision added OR retuned in the UI would be invisible to a vertex-only
    # fingerprint. Capture each modifier's identity AND its parameters, so adding,
    # removing, OR tweaking a modifier (e.g. Solidify thickness) trips the lock.
    mods = getattr(obj, "modifiers", None)
    if mods is not None and len(mods):
        sig["mods"] = [{"name": m.name, "type": m.type, "props": _modifier_props(m)}
                       for m in mods]
    me = getattr(obj, "data", None)
    if obj.type == 'MESH' and me is not None and hasattr(me, "vertices"):
        verts, edges, faces = me.vertices, me.edges, me.polygons
        # Edit-mode edits live in a separate bmesh and DON'T flush to me.vertices until
        # the session ends — so an in-progress viewport edit (e.g. an extrude made while
        # still in Edit Mode) would be invisible to the base-mesh read. Read the live
        # bmesh instead. (Mirrors server._geo_signature's edit-aware no-op read.)
        if obj.mode == 'EDIT':
            try:
                import bmesh
                bm = bmesh.from_edit_mesh(me)
                bm.verts.ensure_lookup_table()
                verts, edges, faces = bm.verts, bm.edges, bm.faces
            except Exception:
                verts, edges, faces = me.vertices, me.edges, me.polygons
        n = len(verts)
        sig["vcount"] = n
        sig["ecount"] = len(edges)
        sig["fcount"] = len(faces)
        step = max(1, n // _VSAMPLE_CAP)
        sig["vstep"] = step
        sig["vsample"] = [[round(c, 6) for c in verts[i].co] for i in range(0, n, step)]
    return sig


def capture_geometry_snapshot():
    """Signature of every current mesh/object — the per-op checkpoint diff_since
    rewinds to. Wrapped defensively: a snapshot must never break a tool."""
    snap = {}
    try:
        for o in bpy.context.scene.objects:
            snap[o.name] = _object_signature(o)
    except Exception:
        pass
    return snap


# ── SPEC-15 interlock helpers ─────────────────────────────────────────────────

def _hash_snapshot(snap):
    """Stable digest of a whole-scene geometry snapshot — the scene's 'edit hash'."""
    return hashlib.md5(json.dumps(snap, sort_keys=True).encode()).hexdigest()


def set_clean_baseline(snap=None, ref=None):
    """Mark the scene as server-known-clean: stash its snapshot + hash + what it
    corresponds to (`ref` = {op, label}). Called after every logged op and on
    acknowledge, so the next call diffs against current reality and reports an honest
    'since' point."""
    global _clean_snapshot, _scene_hash, _baseline_ref
    if snap is None:
        snap = capture_geometry_snapshot()
    _clean_snapshot = snap
    _scene_hash = _hash_snapshot(snap)
    _baseline_ref = ref or {}


def _mods_index(mods):
    return {m["name"]: m for m in (mods or [])}


def _modifier_changes(old_mods, new_mods):
    """(added, removed, changed) between two modifier stacks. `changed` entries name the
    modifier and which params differ — so a retuned Solidify reads as changed, not just
    add/remove."""
    o, n = _mods_index(old_mods), _mods_index(new_mods)
    added = sorted(set(n) - set(o))
    removed = sorted(set(o) - set(n))
    changed = []
    for name in sorted(set(o) & set(n)):
        if o[name].get("type") != n[name].get("type"):
            changed.append({"name": name, "params": ["type"]})
            continue
        op, np_ = o[name].get("props", {}), n[name].get("props", {})
        keys = sorted(k for k in set(op) | set(np_) if op.get(k) != np_.get(k))
        if keys:
            changed.append({"name": name, "params": keys})
    return added, removed, changed


def _diff_snapshots(old, new):
    """Lightweight per-object diff between two snapshots — added / removed / changed
    (moved / rotated / scaled / deformed / topology). Pure (no bpy) so it's safe to call
    from anywhere; the rich region-aware version lives in introspect.diff_since."""
    old_names, new_names = set(old), set(new)
    changed = []
    for name in sorted(old_names & new_names):
        o, n = old[name], new[name]
        kinds = []
        dloc = math.dist(o["loc"], n["loc"])
        if dloc > _TOUCH:
            kinds.append(f"moved {round(dloc * 1000, 1)}mm")
        drot = max((abs(a - b) for a, b in zip(o["rot"], n["rot"])), default=0.0)
        if drot > 0.1:
            kinds.append(f"rotated {round(drot, 1)}deg")
        dscl = max((abs(a - b) for a, b in zip(o["scale"], n["scale"])), default=0.0)
        if dscl > 0.001:
            kinds.append("scaled")
        # topology — verts/edges/faces deltas together (so deleting a face, which leaves
        # the verts, still reads; a vcount-only check would miss it).
        topo = []
        for key, word in (("vcount", "verts"), ("ecount", "edges"), ("fcount", "faces")):
            if key in o and key in n and o[key] != n[key]:
                topo.append(f"{n[key] - o[key]:+d} {word}")
        if topo:
            kinds.append("topology " + "/".join(topo))
        elif (o.get("vcount") == n.get("vcount") and o.get("vsample") and n.get("vsample")
                and len(o["vsample"]) == len(n["vsample"])):
            maxd = max((math.dist(a, b) for a, b in zip(o["vsample"], n["vsample"])),
                       default=0.0)
            if maxd > _TOUCH:
                kinds.append(f"deformed {round(maxd * 1000, 1)}mm")
        # modifier stack added/removed/retuned (non-destructive changes the vertex read misses)
        added_m, removed_m, changed_m = _modifier_changes(o.get("mods"), n.get("mods"))
        if added_m:
            kinds.append("+modifier " + ", ".join(added_m))
        if removed_m:
            kinds.append("-modifier " + ", ".join(removed_m))
        for cm in changed_m:
            shown = ", ".join(cm["params"][:4]) + ("…" if len(cm["params"]) > 4 else "")
            kinds.append(f"modifier {cm['name']} retuned ({shown})")
        if kinds:
            changed.append({"object": name, "kinds": kinds})
    return {"added": sorted(new_names - old_names),
            "removed": sorted(old_names - new_names),
            "changed": changed}


def rich_diff(old, new, only=None):
    """Detailed per-object before→after breakdown for `history op=changes` (the lock's
    'call for more detail' affordance). Snapshot-derived, so it reports WHAT is different
    (transform deltas, vert/edge/face counts, modifier stack, deformation) — not the
    sequence of operations, which Blender doesn't expose for UI edits. `only` filters to
    objects whose name contains that substring."""
    names = set(old) | set(new)
    if only:
        names = {x for x in names if only.lower() in x.lower()}
    out = []
    for name in sorted(names):
        o, n = old.get(name), new.get(name)
        if o is None:
            out.append({"object": name, "status": "added", "type": (n or {}).get("type")})
            continue
        if n is None:
            out.append({"object": name, "status": "removed", "type": o.get("type")})
            continue
        c = {}
        dloc = math.dist(o["loc"], n["loc"])
        if dloc > _TOUCH:
            c["moved_mm"] = round(dloc * 1000, 1)
        drot = max((abs(a - b) for a, b in zip(o["rot"], n["rot"])), default=0.0)
        if drot > 0.1:
            c["rotated_deg"] = round(drot, 1)
        if any(abs(a - b) > 0.001 for a, b in zip(o["scale"], n["scale"])):
            c["scale"] = {"from": o["scale"], "to": n["scale"]}
        topo = {}
        for key, word in (("vcount", "verts"), ("ecount", "edges"), ("fcount", "faces")):
            if key in o and key in n and o[key] != n[key]:
                topo[word] = {"from": o[key], "to": n[key], "delta": n[key] - o[key]}
        if topo:
            c["topology"] = topo
        elif (o.get("vcount") == n.get("vcount") and o.get("vsample") and n.get("vsample")
                and len(o["vsample"]) == len(n["vsample"])):
            maxd = max((math.dist(a, b) for a, b in zip(o["vsample"], n["vsample"])),
                       default=0.0)
            if maxd > _TOUCH:
                c["deformed_mm"] = round(maxd * 1000, 1)
        added_m, removed_m, changed_m = _modifier_changes(o.get("mods"), n.get("mods"))
        if added_m or removed_m or changed_m:
            md = {}
            if added_m:
                md["added"] = added_m
            if removed_m:
                md["removed"] = removed_m
            if changed_m:
                oi, ni = _mods_index(o.get("mods")), _mods_index(n.get("mods"))
                md["changed"] = [
                    {"name": cm["name"],
                     "params": {k: {"from": oi[cm["name"]].get("props", {}).get(k),
                                    "to": ni[cm["name"]].get("props", {}).get(k)}
                                for k in cm["params"]}}
                    for cm in changed_m]
            c["modifiers"] = md
        if c:
            out.append({"object": name, "status": "changed", "changes": c})
    return out


def detect_external_mutation():
    """Compare the live scene to the clean-baseline hash. A mismatch means something
    other than this server changed the world → latch the lock. The lock stays latched
    until acknowledge, but the reported diff is RECOMPUTED in full on every call, so it
    always describes EVERYTHING that currently differs from the baseline — not just the
    first change that tripped it (an object deleted after the trip would otherwise be
    reported as still-present). No-op before the first op (no baseline yet)."""
    global _world_locked, _lock_info
    if _scene_hash is None:
        return
    current = capture_geometry_snapshot()
    diverged = _hash_snapshot(current) != _scene_hash
    if not diverged and not _world_locked:
        return  # clean and unlocked — nothing to do
    if diverged:
        _world_locked = True
    # Refresh the FULL current diff vs the (frozen-while-locked) clean baseline.
    ref = _baseline_ref or {}
    _lock_info = {"since_op": ref.get("op"), "since_label": ref.get("label"),
                  **_diff_snapshots(_clean_snapshot or {}, current)}


def lock_error(tool):
    """The hard-stop error returned for a world-mutating tool while the lock is set —
    names what was mutated and how to clear it."""
    info = _lock_info or {}
    lines = [f"  - {c['object']}: {', '.join(c['kinds'])}" for c in info.get("changed", [])]
    lines += [f"  - added: {a}" for a in info.get("added", [])]
    lines += [f"  - removed: {r}" for r in info.get("removed", [])]
    body = "\n".join(lines) or ("  - (the scene now matches the baseline again — the lock "
                                "stays latched until you acknowledge)")
    return {"error": (
        "########## WORLD STATE IS DIRTY - ACTION BLOCKED ##########\n"
        f"'{tool}' was ABORTED. The scene changed since your last op "
        f"[{info.get('since_op')}] ({info.get('since_label')}) by something other than "
        "this server - you editing in the Blender UI, an autosave, or a script:\n"
        f"{body}\n"
        "→ For the full per-object breakdown (transform, verts/edges/faces, modifiers), "
        "call history op=changes [name=<object>].\n"
        "Any read or derivation from before now may be STALE. You can still READ to "
        "re-ground - select, feel, history op=diff, render. When you've re-grounded and "
        "intend to mutate again, call history op=acknowledge to clear the lock.\n"
        "##########################################################"),
        "world_locked": True, "mutated": info}


def acknowledge_mutation():
    """Clear the dirty lock and re-baseline to the live scene, so mutating resumes.
    Honest no-op when nothing was locked (still refreshes the baseline)."""
    global _world_locked, _lock_info
    cleared = _lock_info
    was_locked = _world_locked
    _world_locked = False
    _lock_info = None
    set_clean_baseline(ref={"op": None, "label": "your acknowledgement"})
    if not was_locked:
        return {"success": True, "acknowledged": False,
                "note": "world was already clean - nothing to acknowledge; baseline refreshed."}
    return {"success": True, "acknowledged": True, "cleared": cleared}


# Tools whose invocation should NOT be recorded in the history log.
NO_LOG_TOOLS = {
    "get_scene_tree",
    "get_history", "undo_steps", "undo_to", "redo_steps",
    # G12 checkpoints: mark is pure metadata; restore delegates to undo_to (which is
    # itself unlogged), so neither should consume a log slot / undo step.
    "mark_checkpoint", "restore_checkpoint",
    # SPEC-12 collab panel: shared-state read — reads phase / the sign-off queue /
    # the human's decisions; touches no mesh, so it must not consume a history slot
    # or an undo step. (The queue fills automatically from the dispatch; Reject undoes
    # via the history path.)
    "collab_status",
    # SPEC-15: acknowledging the external-mutation lock is pure state bookkeeping —
    # it clears a flag and re-baselines the scene hash, moves no geometry.
    "acknowledge_mutation",
    # SPEC-15: the change-detail read — compares baseline vs live, mutates nothing.
    "inspect_changes",
    # SPEC-16: the validate verb's ops are reads / registry bookkeeping — an on-demand
    # sweep, declaring an intent, listing the registry, telemetry. None move geometry.
    "validate_run", "validate_expect", "validate_forget", "validate_intended", "validate_stats",
    "feel_telemetry",
    # generic addon bridge: listing addons + introspecting an operator are pure reads.
    # addon_run is a mutator (logged + undoable) and is deliberately NOT here.
    "addon_list", "addon_inspect",
}

# Tools that neither log to history NOR consume an undo step: pure queries,
# viewport navigation, and the history ops themselves. Logging and undo-push
# share THIS set so the history log and Blender's real undo stack stay exactly
# 1:1 — the invariant that makes undo safe (see gaps.md E1, where they desynced
# and undo(2) wiped a 27-op build back to the startup file).
NON_UNDOABLE_TOOLS = NO_LOG_TOOLS | {
    # instance discovery: pure identity probe, mutates nothing (server/instances.py).
    "ping",
    "describe", "distance_between", "gap_between", "is_aligned",
    "check_symmetry", "is_symmetric", "get_object_info", "get_current_selection",
    "get_mesh_profile", "get_silhouette", "get_section",
    "get_rings", "parts_in", "list_modifiers", "list_designs",
    "set_viewport_angle", "set_viewport_shading", "set_viewport_overlays", "frame_scene",
    "zoom_to_selected", "orbit_viewport",
    # read-only introspection / lint tools (P3-P12) — pure queries, no scene mutation
    "find_coplanar_overlaps", "validate_scene", "check_mesh", "audit_asset",
    "check_contacts", "check_clearance", "trace_profile", "check_framing",
    "check_focus", "check_resting", "diff_since",
    # render config read (G11) — pure query
    "render_settings",
    # rig + metadata introspection (U1, U2, U9) — read-only
    "get_bone_tree", "describe_bone", "list_constraints", "get_custom_properties",
    # mesh-data introspection (U8) — read-only
    "list_shape_keys",
    # handle registry read-model (SPEC-07) — read-only scan / recompute. accept_handle
    # rewrites a handle's provenance snapshot (metadata only, no geometry), so it stays
    # out of the undo stack too — keeping history 1:1 with geometry ops.
    "list_handles", "resolve_handle", "accept_handle",
    # topology sense (SPEC-04) — read-only structural query
    "get_topology",
    # multi-feel (SPEC-07 Phase 4) — feel_map is a pure raycast read (mints nothing);
    # feel_assembly DOES mint boundary handles, so it stays mutating (logged + undoable)
    # and is NOT listed here. feel_relate (G16) is a pure handle-pair measurement.
    "feel_map", "feel_relate",
    # geometry fit (SPEC-14) — a read: fits a parametric model to the selection and
    # returns params/residual. The optional as_handle/as_curve minting is a deliberate
    # opt-in side effect (like feel_map's read shape); the fit itself moves no geometry.
    "fit",
    # new_scene reloads the startup file, wiping Blender's undo stack and the
    # scene; it resets the history log itself (designs.new_scene) rather than
    # pushing an undo step that would immediately be desynced.
    "new_scene",
    # G196 timeline/bake: set_frame just moves the playhead (a nav read, like
    # frame_scene); bake_physics runs the point-cache sim and can't be meaningfully
    # captured by the geometry-diff undo snapshot — keep both off the undo stack.
    "set_frame", "bake_physics",
}

# Tools that should NOT have blender_status appended to their result
# (read-only visual / query tools — the status block would be noise).
NO_STATUS_TOOLS = {
    "get_blender_status",
    "ping",   # identity probe — its own payload IS the answer; status would be noise
    "get_scene_tree", "get_history", "get_bone_tree", "render_settings",
    "mark_checkpoint",
    "list_handles", "resolve_handle", "accept_handle",
    # multi-feel (SPEC-07 Phase 4) — perception ops; assembly mints as a side effect
    # but is read-shaped, so neither carries the status block.
    "feel_assembly", "feel_map", "feel_relate", "fit",
    # handle GC (G15) — registry tidying; deleting an Empty doesn't move geometry, so
    # the status block would be noise (matches list/accept). Still mutating/undoable.
    "prune_handles", "forget_handle",
    # SPEC-12 collab panel: shared-state read — the status block would be pure noise
    # on a status round-trip (the agent reads geometry from the geometry verbs).
    "collab_status",
    # SPEC-15: change-detail read — its own per-object breakdown IS the payload; the
    # status block would be noise.
    "inspect_changes",
    # SPEC-16: validate verb ops — their own structured payload IS the answer; the
    # status block would be noise on a registry/stats round-trip.
    "validate_run", "validate_expect", "validate_forget", "validate_intended", "validate_stats",
    "feel_telemetry",
    # generic addon bridge reads — their own payload IS the answer; status would be noise.
    "addon_list", "addon_inspect",
}


def reset_history_state():
    """Clear all undo/history/diff bookkeeping. The scene it described is gone.

    new_scene does this inline when it reloads the startup file; a manual
    File > Open bypasses every tool, so the load_post handler (extension/__init__)
    calls this — otherwise history, diff_since snapshots, and undo verification all
    describe a scene that no longer exists, and undo() would check against a
    snapshot from another file (gaps.md U11)."""
    global _undo_baseline, _pending_edit_bind, _eval_dirty
    global _clean_snapshot, _scene_hash, _baseline_ref, _world_locked, _lock_info
    _history.clear()
    _redo_stack.clear()
    _snapshots.clear()
    _marks.clear()
    _undo_baseline = None
    _pending_edit_bind = None
    _eval_dirty = set()
    # SPEC-15: the scene it described is gone — drop the baseline + any latched lock.
    _clean_snapshot = None
    _scene_hash = None
    _baseline_ref = None
    _world_locked = False
    _lock_info = None
    # SPEC-16: the declared-intent registry describes THIS scene's design ("Hair clips
    # Body") — a new scene starts with no declarations, so drop them too.
    try:
        from . import validation
        validation.clear_intents()
    except Exception:
        pass


def scene_object_names():
    """Sorted list of the current scene's object names — the per-op snapshot used
    to verify the scene actually matches the history log after an undo/redo."""
    return sorted(o.name for o in bpy.context.scene.objects)


def ui_override():
    """Build a context-override dict (window + screen + VIEW_3D area + region)
    for running UI-context operators — undo / redo / undo_push — from the
    socket→timer thread.

    A bare `temp_override(window=...)` REPLACES the context with only the window,
    dropping the screen/area the global-undo operator resolves against. In a live
    GUI session that makes `bpy.ops.ed.undo()` a silent no-op (gaps.md:
    live-session undo). Supplying the full VIEW_3D context is the canonical recipe
    for driving these operators from a script.

    Returns None in headless / windowless contexts, where the bare operator call
    already works — so the headless path is left exactly as it was."""
    wm = bpy.context.window_manager
    wins = list(wm.windows) if wm else []
    if not wins:
        return None
    win = wins[0]
    override = {"window": win}
    screen = getattr(win, "screen", None)
    if screen:
        override["screen"] = screen
        area = next((a for a in screen.areas if a.type == 'VIEW_3D'), None)
        if area:
            override["area"] = area
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if region:
                override["region"] = region
    return override


def log_operation(tool, params, label=""):
    op_id = hashlib.md5(
        f"{tool}{json.dumps(params, sort_keys=True)}{time.time()}".encode()
    ).hexdigest()[:8]
    # `active` is the G12 attribution signal SPEC-07 Phase 3 reads: which object was
    # active when this op ran. For target= edit verbs the dispatch pops `target` out of
    # params before logging, so the touched mesh would be lost — but it's the active
    # object by then (_enter_edit_for_target made it active), so this recovers it.
    _history.append({"id": op_id, "label": label or tool, "tool": tool,
                     "params": params, "objects": scene_object_names(),
                     "active": getattr(bpy.context.active_object, "name", None)})
    snap = capture_geometry_snapshot()
    _snapshots[op_id] = snap          # diff_since (P11) checkpoint
    # SPEC-15: this op is the new server-known clean state — UNLESS the world is locked.
    # While locked only exempt tools run, but some of those (selection) still log; letting
    # them re-baseline to the dirty scene would erase the divergence the lock describes.
    # The baseline stays frozen at the last real edit until acknowledge re-grounds it.
    if not _world_locked:
        set_clean_baseline(snap, ref={"op": op_id, "label": label or tool})
    _redo_stack.clear()  # a new operation forks history; old redo branch is dead
    return op_id


def push_undo_step(message):
    """Push exactly ONE named undo checkpoint for the just-completed tool.

    Socket/timer-driven operator calls don't generate the UI events that make
    Blender auto-push undo steps, so without this a multi-op build collapses to
    a handful of sparse undo points (gaps.md E1). Called once per mutating tool
    by the dispatch — never from inside tools (that would double-push)."""
    try:
        override = ui_override()
        if override:
            with bpy.context.temp_override(**override):
                bpy.ops.ed.undo_push(message=str(message)[:64])
        else:
            bpy.ops.ed.undo_push(message=str(message)[:64])
    except Exception:
        pass


def push_undo(label):
    """Deprecated no-op. Undo checkpoints are now pushed centrally by the dispatch
    (extension/server.py) after every mutating tool — one tool call == one undo
    step. Kept so existing in-tool callers don't double-push or break imports."""
    return


# ── W2: edit-session-scoped deform-bind guard ────────────────────────────────
# The V2 bind-invalidation check in server.execute_command is REQUEST-scoped: it
# snapshots before an edit verb and compares after that same verb. But the manual
# path is several socket commands — set_mode(EDIT) → select_… → delete_geometry
# (no target=) → set_mode(OBJECT) — and no single request spans the topology
# change, so nothing fired (gaps.md W2). This snapshot lives across commands: it's
# stashed when EDIT mode is entered and compared when EDIT mode is exited.
_pending_edit_bind = None  # (object_name, [(mod_name, type)…], vert_count) | None


def snapshot_edit_binds(obj):
    """Stash an object's deform-bind state as it enters EDIT mode, so a topology
    edit made across separate socket commands is still caught on exit (W2).

    Overwrites any prior pending snapshot — if a previous edit session was
    abandoned (e.g. the user exited edit mode via the Blender UI, which bypasses
    every tool), entering edit again via the MCP simply replaces the stale one
    rather than leaking it onto an unrelated object."""
    global _pending_edit_bind
    _pending_edit_bind = None
    from .common import deform_binds
    if obj is None or getattr(obj, "data", None) is None:
        return
    if not hasattr(obj.data, "vertices"):
        return
    binds = deform_binds(obj)
    if binds:
        vcount = len(obj.data.vertices)
        # X4: seed the bind's valid vert-count on first observation. A reconstruct
        # bind (mesh-deform / surface-deform / corrective-smooth-BIND) is "valid"
        # while this count holds; a topology edit later makes it mismatch → dead.
        # Seed only if absent so an already-recorded (post-rebind) count survives.
        if "bb_bind_vcount" not in obj:
            obj["bb_bind_vcount"] = vcount
        _pending_edit_bind = (obj.name, binds, vcount)


def clear_edit_binds():
    """Drop any pending edit-bind snapshot without comparing — used when the
    request-scoped path (target= edit verbs) takes over, since it does its own
    snapshot/compare and must not be cross-contaminated by a manual-path one."""
    global _pending_edit_bind
    _pending_edit_bind = None


def check_edit_binds(obj):
    """On EDIT exit, compare the live vert count against the snapshot. Returns a
    warning dict (or None), consuming the snapshot either way. Two cases:

    - vert count CHANGED → the bind is dead (V2/W2 topology kill): bind_invalidated.
    - vert count UNCHANGED but a VALID reconstruct-bind is present → the rest-shape
      edit is shadowed: it won't show until rebind (X4): bind_shadowed."""
    global _pending_edit_bind
    snap = _pending_edit_bind
    _pending_edit_bind = None
    if snap is None or obj is None:
        return None
    name, binds, before = snap
    if obj.name != name or getattr(obj, "data", None) is None:
        return None
    if not hasattr(obj.data, "vertices"):
        return None
    after = len(obj.data.vertices)
    if after != before:
        from .common import deform_bind_warning
        return {"bind_invalidated": True, "bind_warning": deform_bind_warning(binds)}
    # Position-only edit. Y1c: check shape-key shadowing FIRST — on a keyed mesh the
    # ACTIVE shape key is the real eraser of the edit, not the bind, and blaming the
    # bind here sends the diagnosis down the wrong path (a rebind won't bring the
    # edit back). The shape-key warning takes precedence over bind_shadowed.
    from .common import active_shape_key_shadow, shape_key_shadow_warning
    shadow = active_shape_key_shadow(obj)
    if shadow:
        return {"shape_key_shadowed": shadow["shadowed"], "shape_key_active": shadow,
                "shape_key_warning": shape_key_shadow_warning(shadow, obj.name)}
    # Warn only if the bind is still VALID (count matches the recorded valid count) —
    # a dead bind is inert and shows base-mesh edits 1:1, so warning there would be
    # false (gaps.md X4).
    if obj.get("bb_bind_vcount") == after:
        from .common import rest_shadow_warning
        return {"bind_shadowed": True, "bind_warning": rest_shadow_warning(binds)}
    return None


# ── X6: recover from a wedged evaluated-mesh cache after a timed-out op ───────
# A socket request that exceeds its timeout returns an error, but the op it queued
# is NOT cancelled — it keeps running on the main thread and completes later (X1),
# and on completion can leave the touched object's evaluated mesh WEDGED: object
# mode renders a stale eval and every introspection channel reports the ghost as
# truth (gaps.md X6). When a timeout is detected we record the touched object here;
# the next command force-retags it so reads see the real geometry, not the ghost.
_eval_dirty = set()  # object names whose eval cache may be stale after an orphaned op


def mark_eval_dirty(name):
    """Record an object whose evaluated mesh may have wedged behind a timed-out op."""
    if name:
        _eval_dirty.add(name)


def flush_eval_dirty():
    """Force a depsgraph re-evaluation of objects touched by a timed-out (orphaned)
    op, before the next command reads anything. Cheap no-op when nothing is dirty."""
    global _eval_dirty
    if not _eval_dirty:
        return
    for nm in _eval_dirty:
        o = bpy.data.objects.get(nm)
        if o is not None:
            try:
                o.update_tag()
            except Exception:
                pass
    _eval_dirty = set()
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

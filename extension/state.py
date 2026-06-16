"""Module-wide mutable state: port, server flags, request queue, history log.

Kept in one place so any module can read/append without circular imports.
"""

import hashlib
import json
import math
import queue
import time

import bpy

PORT = 8765

_request_queue = queue.Queue()
_server_thread = None
_running = False

_history = []
_redo_stack = []        # entries undone and available to redo (cleared on any new op)
_undo_baseline = None   # scene object-name set captured before the first mutating op
_snapshots = {}         # op_id -> {obj_name: geometry signature} for diff_since (P11)

_VSAMPLE_CAP = 150      # max per-object vertices stored per snapshot (downsampled)


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
    me = getattr(obj, "data", None)
    if obj.type == 'MESH' and me is not None and hasattr(me, "vertices"):
        verts = me.vertices
        n = len(verts)
        sig["vcount"] = n
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

# Tools whose invocation should NOT be recorded in the history log.
NO_LOG_TOOLS = {
    "get_scene_tree",
    "get_history", "undo_steps", "undo_to", "redo_steps",
}

# Tools that neither log to history NOR consume an undo step: pure queries,
# viewport navigation, and the history ops themselves. Logging and undo-push
# share THIS set so the history log and Blender's real undo stack stay exactly
# 1:1 — the invariant that makes undo safe (see gaps.md E1, where they desynced
# and undo(2) wiped a 27-op build back to the startup file).
NON_UNDOABLE_TOOLS = NO_LOG_TOOLS | {
    "describe", "distance_between", "gap_between", "is_aligned",
    "check_symmetry", "is_symmetric", "get_object_info", "get_current_selection",
    "get_mesh_profile", "get_rings", "parts_in", "list_modifiers", "list_designs",
    "set_viewport_angle", "set_viewport_shading", "set_viewport_overlays", "frame_scene",
    "zoom_to_selected", "orbit_viewport",
    # read-only introspection / lint tools (P3-P12) — pure queries, no scene mutation
    "find_coplanar_overlaps", "validate_scene", "check_mesh", "audit_asset",
    "check_contacts", "trace_profile", "check_framing", "check_resting", "diff_since",
    # rig + metadata introspection (U1, U2, U9) — read-only
    "get_bone_tree", "describe_bone", "list_constraints", "get_custom_properties",
    # mesh-data introspection (U8) — read-only
    "list_shape_keys",
    # handle registry read-model (SPEC-07) — read-only scan / recompute
    "list_handles", "resolve_handle",
    # topology sense (SPEC-04) — read-only structural query
    "get_topology",
    # new_scene reloads the startup file, wiping Blender's undo stack and the
    # scene; it resets the history log itself (designs.new_scene) rather than
    # pushing an undo step that would immediately be desynced.
    "new_scene",
}

# Tools that should NOT have blender_status appended to their result
# (read-only visual / query tools — the status block would be noise).
NO_STATUS_TOOLS = {
    "get_blender_status",
    "get_scene_tree", "get_history", "get_bone_tree",
    "list_handles", "resolve_handle",
}


def reset_history_state():
    """Clear all undo/history/diff bookkeeping. The scene it described is gone.

    new_scene does this inline when it reloads the startup file; a manual
    File > Open bypasses every tool, so the load_post handler (extension/__init__)
    calls this — otherwise history, diff_since snapshots, and undo verification all
    describe a scene that no longer exists, and undo() would check against a
    snapshot from another file (gaps.md U11)."""
    global _undo_baseline, _pending_edit_bind, _eval_dirty
    _history.clear()
    _redo_stack.clear()
    _snapshots.clear()
    _undo_baseline = None
    _pending_edit_bind = None
    _eval_dirty = set()


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
    _history.append({"id": op_id, "label": label or tool, "tool": tool,
                     "params": params, "objects": scene_object_names()})
    _snapshots[op_id] = capture_geometry_snapshot()  # diff_since (P11) checkpoint
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

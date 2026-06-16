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
    armature,
    bands,
    curves,
    designs,
    editmode,
    finishes,
    groups,
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
    viewport,
)

# Modules order doesn't matter for dispatch, but later entries overwrite earlier
# duplicates — which is intentionally never expected to happen.
_TOOL_MODULES = (
    status,      # get_scene_tree, get_blender_status
    viewport,
    history,
    primitives,
    curves,
    objects,
    transforms,
    queries,
    relational,
    groups,
    finishes,
    editmode,
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
)

TOOLS = {}
for _mod in _TOOL_MODULES:
    TOOLS.update(_mod.TOOLS)

# Tools that require edit mode — support an optional `target` param that auto-selects the
# named object and enters edit mode, then exits back to OBJECT mode after the call.
EDIT_MODE_TOOLS = {
    "bevel", "extrude", "loop_cut", "set_component_mode", "select_all",
    "select_by_axis", "select_between", "grow_selection", "move_vertices",
    "scale_vertices", "delete_geometry", "separate_selection", "jitter_vertices",
    "random_select", "proportional_move", "inflate_selection", "mark_sharp",
    "set_edge_crease", "merge_by_distance", "select_in_sphere", "split_by_part",
    "get_rings", "select_ring", "select_rings", "scale_rings", "taper_end", "taper_section",
    "assign_weight", "select_boundary", "select_limb",
}

# Y1: verbs that write VERTEX POSITIONS, so on a keyed mesh they land on the active
# shape key. A position edit on a non-Basis active key is silently swallowed (value
# 0) or scaled (value>0) — every one of these must say which key it wrote to. Pure
# selection / topology-flag verbs are excluded (they don't move verts). Sculpt
# strokes write to the active key too, so they're in here despite not being EDIT.
SHAPE_KEY_SHADOW_TOOLS = {
    "move_vertices", "scale_vertices", "proportional_move", "inflate_selection",
    "jitter_vertices", "bevel", "extrude", "extrude_along_curve", "scale_rings",
    "taper_end", "taper_section",
    "sculpt_grab", "sculpt_inflate", "sculpt_draw", "sculpt_smooth", "sculpt_crease",
    "sculpt_pinch", "sculpt_flatten",
}


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

    # Log + push the undo step AFTER edit-mode tools have returned to OBJECT mode,
    # so each step is an object-mode checkpoint (undoable from object mode) and
    # the history log stays exactly 1:1 with Blender's undo stack.
    if is_mutating and isinstance(result, dict) and result.get("success"):
        result["op_id"] = state.log_operation(tool, params, label)
        state.push_undo_step(result["op_id"])

    if tool not in state.NO_STATUS_TOOLS and isinstance(result, dict):
        try:
            result["blender_status"] = status.get_blender_status({}).get("status")
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


def server_loop():
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

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
    bands,
    curves,
    designs,
    editmode,
    finishes,
    groups,
    history,
    lighting,
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
    scatter,
    sculpt,
    designs,
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

    target = params.pop("target", "") if tool in EDIT_MODE_TOOLS else ""
    auto_switched = False
    if target:
        auto_switched, err = _enter_edit_for_target(target)
        if err:
            return {"error": err}

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

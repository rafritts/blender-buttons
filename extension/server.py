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
    rings,
    scatter,
    shading,
    state,
    status,
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
    objects,
    transforms,
    queries,
    relational,
    groups,
    finishes,
    editmode,
    rings,
    shading,
    lighting,
    scatter,
    designs,
)

TOOLS = {}
for _mod in _TOOL_MODULES:
    TOOLS.update(_mod.TOOLS)


def execute_command(command):
    tool   = command.get("tool")
    params = command.get("params", {})
    label  = command.get("label", "")
    fn = TOOLS.get(tool)
    if fn is None:
        return {"error": f"Unknown tool: {tool}. Available: {list(TOOLS.keys())}"}
    try:
        result = fn(params)
        if tool not in state.NO_LOG_TOOLS and result.get("success"):
            result["op_id"] = state.log_operation(tool, params, label)
        if tool not in state.NO_STATUS_TOOLS:
            try:
                result["blender_status"] = status.get_blender_status({}).get("status")
            except Exception:
                pass
        return result
    except Exception as e:
        return {"error": str(e)}


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

        state._request_queue.put(on_main_thread)
        result_event.wait(timeout=30)

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

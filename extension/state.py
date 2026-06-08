"""Module-wide mutable state: port, server flags, request queue, history log.

Kept in one place so any module can read/append without circular imports.
"""

import hashlib
import json
import queue
import time

import bpy

PORT = 8765

_request_queue = queue.Queue()
_server_thread = None
_running = False

_history = []

# Tools whose invocation should NOT be recorded in the history log.
NO_LOG_TOOLS = {
    "get_scene_tree", "get_viewport_screenshot", "get_viewport_collage",
    "get_history", "undo_steps", "undo_to",
}

# Tools that should NOT have blender_status appended to their result
# (read-only visual / query tools — the status block would be noise).
NO_STATUS_TOOLS = {
    "get_blender_status", "get_viewport_screenshot", "get_viewport_collage",
    "get_scene_tree", "get_history",
}


def log_operation(tool, params, label=""):
    op_id = hashlib.md5(
        f"{tool}{json.dumps(params, sort_keys=True)}{time.time()}".encode()
    ).hexdigest()[:8]
    _history.append({"id": op_id, "label": label or tool, "tool": tool, "params": params})
    return op_id


def push_undo(label):
    """Push an explicit undo checkpoint. Required after bmesh mutations since they
    bypass Blender's operator-driven undo system."""
    try:
        bpy.ops.ed.undo_push(message=str(label)[:64])
    except Exception:
        pass

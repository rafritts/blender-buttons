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
_redo_stack = []        # entries undone and available to redo (cleared on any new op)
_undo_baseline = None   # scene object-name set captured before the first mutating op

# Tools whose invocation should NOT be recorded in the history log.
NO_LOG_TOOLS = {
    "get_scene_tree", "get_viewport_screenshot", "get_viewport_collage",
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
    "set_viewport_angle", "set_viewport_shading", "frame_scene",
    "zoom_to_selected", "orbit_viewport",
}

# Tools that should NOT have blender_status appended to their result
# (read-only visual / query tools — the status block would be noise).
NO_STATUS_TOOLS = {
    "get_blender_status", "get_viewport_screenshot", "get_viewport_collage",
    "get_scene_tree", "get_history",
}


def scene_object_names():
    """Sorted list of the current scene's object names — the per-op snapshot used
    to verify the scene actually matches the history log after an undo/redo."""
    return sorted(o.name for o in bpy.context.scene.objects)


def log_operation(tool, params, label=""):
    op_id = hashlib.md5(
        f"{tool}{json.dumps(params, sort_keys=True)}{time.time()}".encode()
    ).hexdigest()[:8]
    _history.append({"id": op_id, "label": label or tool, "tool": tool,
                     "params": params, "objects": scene_object_names()})
    _redo_stack.clear()  # a new operation forks history; old redo branch is dead
    return op_id


def push_undo_step(message):
    """Push exactly ONE named undo checkpoint for the just-completed tool.

    Socket/timer-driven operator calls don't generate the UI events that make
    Blender auto-push undo steps, so without this a multi-op build collapses to
    a handful of sparse undo points (gaps.md E1). Called once per mutating tool
    by the dispatch — never from inside tools (that would double-push)."""
    try:
        wins = bpy.context.window_manager.windows
        if wins:
            with bpy.context.temp_override(window=wins[0]):
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

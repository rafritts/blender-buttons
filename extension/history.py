"""History readback and undo. Operates on state._history."""

import bpy

from . import state


def get_history(params):
    return {"history": state._history, "count": len(state._history)}


def undo_steps(params):
    steps = max(1, min(params.get("steps", 1), len(state._history)))
    window = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=window):
        for _ in range(steps):
            bpy.ops.ed.undo()
    for _ in range(steps):
        if state._history:
            state._history.pop()
    return {"success": True, "steps": steps, "history_remaining": len(state._history)}


def undo_to(params):
    target_id = params.get("id")
    idx = next((i for i, h in enumerate(state._history) if h["id"] == target_id), None)
    if idx is None:
        return {"error": f"ID '{target_id}' not found in history"}
    steps = len(state._history) - idx - 1
    if steps > 0:
        window = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=window):
            for _ in range(steps):
                bpy.ops.ed.undo()
        del state._history[idx + 1:]
    return {"success": True, "steps": steps}


TOOLS = {
    "get_history": get_history,
    "undo_steps":  undo_steps,
    "undo_to":     undo_to,
}

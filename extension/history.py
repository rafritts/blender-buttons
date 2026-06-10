"""History readback, undo, and redo. Operates on state._history / state._redo_stack.

Each mutating tool pushes exactly one Blender undo step (extension/server.py
dispatch), so the log and Blender's undo stack stay 1:1. undo/redo walk both in
lockstep, then VERIFY the live scene matches the snapshot recorded for the point
they landed on — a mismatch is reported loudly instead of as silent success
(gaps.md E1: a lying undo is worse than no undo).
"""

import bpy

from . import state


def get_history(params):
    return {"history": state._history, "count": len(state._history),
            "redo_available": len(state._redo_stack)}


def _step_op(op_name):
    """Run bpy.ops.ed.<undo|redo> under a full VIEW_3D context override when a
    GUI window exists (a bare window-only override is a no-op for global undo —
    see state.ui_override / gaps.md), or a bare call in headless."""
    op = getattr(bpy.ops.ed, op_name)
    override = state.ui_override()
    if override:
        with bpy.context.temp_override(**override):
            op()
    else:
        op()


def _verify(target_objects):
    """Compare the live scene's object names to the snapshot for the point we
    landed on. Returns (missing, unexpected) name lists; both empty == verified."""
    if target_objects is None:
        return [], []
    live = set(o.name for o in bpy.context.scene.objects)
    expected = set(target_objects)
    return sorted(expected - live), sorted(live - expected)


def _attach_verification(result, target_objects):
    missing, extra = _verify(target_objects)
    if missing or extra:
        result["verified"] = False
        result["warning"] = (
            "POST-UNDO MISMATCH — the scene does not match the expected state for "
            f"this history point (missing={missing} unexpected={extra}). The history "
            "log and Blender's undo stack may have diverged; recover with open_design "
            "from a save_design checkpoint rather than trusting further undo."
        )
    else:
        result["verified"] = True
    return result


def undo_steps(params):
    steps = params.get("steps", 1)
    if not isinstance(steps, int) or steps < 1:
        return {"error": "'steps' must be a positive integer"}
    if steps > len(state._history):
        return {"error": f"Cannot undo {steps} step(s) — only {len(state._history)} "
                         "in the history log. Scene left untouched."}

    reverted = []
    for _ in range(steps):
        entry = state._history.pop()
        state._redo_stack.append(entry)
        reverted.append(entry["label"])
        _step_op("undo")

    target = state._history[-1]["objects"] if state._history else state._undo_baseline
    result = {"success": True, "steps": steps, "reverted": reverted,
              "history_remaining": len(state._history),
              "redo_available": len(state._redo_stack)}
    return _attach_verification(result, target)


def redo_steps(params):
    steps = params.get("steps", 1)
    if not isinstance(steps, int) or steps < 1:
        return {"error": "'steps' must be a positive integer"}
    if steps > len(state._redo_stack):
        return {"error": f"Cannot redo {steps} step(s) — only {len(state._redo_stack)} "
                         "available. Scene left untouched."}

    redone = []
    for _ in range(steps):
        entry = state._redo_stack.pop()
        state._history.append(entry)
        redone.append(entry["label"])
        _step_op("redo")

    target = state._history[-1]["objects"] if state._history else None
    result = {"success": True, "steps": steps, "redone": redone,
              "history_remaining": len(state._history),
              "redo_available": len(state._redo_stack)}
    return _attach_verification(result, target)


def undo_to(params):
    target_id = params.get("id")
    idx = next((i for i, h in enumerate(state._history) if h["id"] == target_id), None)
    if idx is None:
        return {"error": f"ID '{target_id}' not found in history"}
    steps = len(state._history) - idx - 1
    if steps <= 0:
        return {"success": True, "steps": 0, "note": f"already at history point [{target_id}]"}
    return undo_steps({"steps": steps})


TOOLS = {
    "get_history": get_history,
    "undo_steps":  undo_steps,
    "redo_steps":  redo_steps,
    "undo_to":     undo_to,
}

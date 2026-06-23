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


def _rebaseline_after_history(action):
    """SPEC-15 / G110: undo & redo CHANGE the scene, but they are the server's OWN ops —
    not an external edit. Without re-grounding, the next mutating call's
    detect_external_mutation sees the undo's vert/face delta and wrongly latches the
    dirty-world lock, forcing a needless acknowledge round-trip. So re-baseline to the
    post-undo scene here — but ONLY when we're not already locked, so a genuine external
    edit (which freezes the baseline by design) is never silently erased."""
    if state._world_locked:
        return
    head = state._history[-1] if state._history else None
    state.set_clean_baseline(ref={
        "op": head["id"] if head else None,
        "label": f"after {action} to [{head['id'] if head else 'baseline'}]",
    })


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
    _rebaseline_after_history("undo")
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
    _rebaseline_after_history("redo")
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


def mark_checkpoint(params):
    """G12 — name the current history head so a later `restore` rolls back to exactly
    here. NOT a parallel snapshot store: it records the head op_id and leans on the
    existing op-log / Blender-undo 1:1 mapping. The workflow the gap asks for — mark
    before a risky edit, try it, restore if the modifier stack screams."""
    name = (params.get("name") or "").strip()
    if not name:
        return {"error": "history op=mark needs name=<checkpoint>"}
    head_id = state._history[-1]["id"] if state._history else None
    state._marks[name] = head_id
    return {"success": True, "mark": name, "at": head_id,
            "history_depth": len(state._history)}


def restore_checkpoint(params):
    """Roll the scene back to a named mark — undo to the op that was the history head
    when the mark was set. Verifies the landed scene like undo_to; refuses if newer
    edits have already replaced the marked op (it forked off the live branch)."""
    name = (params.get("name") or "").strip()
    if not name:
        return {"error": "history op=restore needs name=<checkpoint>"}
    if name not in state._marks:
        return {"error": f"no checkpoint '{name}' — set one with "
                         f"history op=mark name={name}"}
    head_id = state._marks[name]
    if head_id is None:
        # Marked at the empty baseline → undo everything back to it.
        steps = len(state._history)
        if steps == 0:
            return {"success": True, "steps": 0,
                    "note": f"already at checkpoint '{name}' (empty baseline)"}
        result = undo_steps({"steps": steps})
        result["restored"] = name
        return result
    if not any(h["id"] == head_id for h in state._history):
        return {"error": f"checkpoint '{name}' (op [{head_id}]) is no longer in the "
                         "history log — newer edits forked past it, so restore is "
                         "unavailable. Recover from a save_design checkpoint instead."}
    result = undo_to({"id": head_id})
    result["restored"] = name
    return result


def acknowledge_mutation(params):
    """SPEC-15: clear the external-mutation lock and re-baseline to the live scene, so
    world-mutating tools work again. Call only after re-grounding via reads (select/feel/
    diff/render) — it accepts the current scene as the new ground truth."""
    return state.acknowledge_mutation()


def inspect_changes(params):
    """SPEC-15: the lock's 'tell me more' affordance. Detailed per-object breakdown of
    everything that differs between the clean baseline and the live scene — transform,
    verts/edges/faces, modifier stack, deformation. Snapshot-derived, so it reports WHAT
    changed, not the operation sequence (Blender doesn't expose that for UI edits). When
    nothing meaningful differs it says so plainly. Read-only; works locked or not."""
    name = (params.get("name") or "").strip()
    if state._clean_snapshot is None:
        return {"success": True, "objects": [], "since": {},
                "note": "no baseline yet — make an edit through the server first, "
                        "then there's something to compare against."}
    after = state.capture_geometry_snapshot()
    objs = state.rich_diff(state._clean_snapshot, after, only=name or None)
    return {"success": True, "since": state._baseline_ref or {},
            "locked": state._world_locked, "filter": name, "objects": objs}


TOOLS = {
    "get_history": get_history,
    "undo_steps":  undo_steps,
    "redo_steps":  redo_steps,
    "undo_to":     undo_to,
    "mark_checkpoint":    mark_checkpoint,
    "restore_checkpoint": restore_checkpoint,
    "acknowledge_mutation": acknowledge_mutation,
    "inspect_changes":    inspect_changes,
}

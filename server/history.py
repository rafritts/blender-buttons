from server._core import mcp, call_blender, _status


@mcp.tool()
def get_history() -> str:
    """
    Return the full operation history log. Each entry has:
    id (8-char hash), label (human name), tool, params.
    Use with undo_to(id) to roll back to any named point, or redo() to step forward.
    """
    result = call_blender("get_history")
    entries = result.get("history", [])
    if not entries:
        return "No history yet."
    lines = [f"[{e['id']}] {e['label']}  ({e['tool']})" for e in entries]
    redo_n = result.get("redo_available", 0)
    if redo_n:
        lines.append(f"({redo_n} undone op(s) available to redo)")
    return "\n".join(lines)


def _undo_redo_summary(verb, result):
    """Shared formatting for undo/redo: report what moved and whether the scene
    actually matches the expected state afterward (loud on mismatch)."""
    if not result.get("success"):
        return result.get("error", "failed")
    moved = result.get("reverted" if verb == "Undid" else "redone", [])
    main = (f"{verb} {result['steps']} step(s): {moved}. "
            f"History: {result['history_remaining']}, "
            f"redo available: {result.get('redo_available', 0)}")
    if result.get("verified") is False:
        main += "\n⚠ " + result.get("warning", "post-op scene verification FAILED")
    elif result.get("verified") is True:
        main += "\n✓ scene verified against history snapshot"
    return main


@mcp.tool()
def undo(steps: int = 1) -> str:
    """
    Undo the last N operations — one MCP tool call == one undo step. The history
    log and Blender's undo stack stay 1:1, and after undoing, the live scene is
    verified against the snapshot recorded for the point you land on; a mismatch
    is reported loudly (never as silent success).

    Undoing more steps than exist returns an error and leaves the scene untouched.
    Undone operations can be re-applied with redo(). Check get_history() first.
    """
    result = call_blender("undo_steps", {"steps": steps})
    return _undo_redo_summary("Undid", result) + _status(result)


@mcp.tool()
def redo(steps: int = 1) -> str:
    """
    Re-apply the last N undone operations (inverse of undo). Available only until
    a NEW mutating operation is run, which forks history and discards the redo
    branch — same as Blender's own redo. Verified against the history snapshot.
    """
    result = call_blender("redo_steps", {"steps": steps})
    return _undo_redo_summary("Redid", result) + _status(result)


@mcp.tool()
def undo_to(id: str) -> str:
    """
    Undo back to a specific operation by its ID (from get_history).
    Everything after that ID is undone; the target operation itself is kept.
    Verified against the history snapshot, like undo().
    """
    result = call_blender("undo_to", {"id": id})
    if result.get("success"):
        if result.get("steps", 0) == 0:
            main = result.get("note", f"already at [{id}]")
        else:
            main = f"Undid {result['steps']} step(s) to reach [{id}]"
            if result.get("verified") is False:
                main += "\n⚠ " + result.get("warning", "verification FAILED")
            elif result.get("verified") is True:
                main += "\n✓ scene verified against history snapshot"
    else:
        main = result.get("error", "failed")
    return main + _status(result)

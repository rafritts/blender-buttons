from server._core import mcp, call_blender, _status


@mcp.tool()
def get_history() -> str:
    """
    Return the full operation history log. Each entry has:
    id (8-char hash), label (human name), tool, params.
    Use with undo_to(id) to roll back to any named point.
    """
    result = call_blender("get_history")
    entries = result.get("history", [])
    if not entries:
        return "No history yet."
    lines = [f"[{e['id']}] {e['label']}  ({e['tool']})" for e in entries]
    return "\n".join(lines)


@mcp.tool()
def undo(steps: int = 1) -> str:
    """
    Undo the last N operations. Updates history log to match.
    Check get_history() first to see what will be undone.
    """
    result = call_blender("undo_steps", {"steps": steps})
    if result.get("success"):
        main = f"Undid {result['steps']} step(s). History remaining: {result['history_remaining']}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def undo_to(id: str) -> str:
    """
    Undo back to a specific operation by its ID (from get_history).
    Everything after that ID is undone. The target operation itself is kept.
    """
    result = call_blender("undo_to", {"id": id})
    if result.get("success"):
        main = f"Undid {result['steps']} step(s) to reach [{id}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)

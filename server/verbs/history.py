"""history — the top Edit menu (Undo / Redo) + the operation log (SPEC-05).

Time travel over the operation history. `op` selects.
"""

from typing import Literal

from server._core import mcp
from server import history as _h, introspect
from ._common import tag, unknown

_OPS = ["log", "undo", "redo", "undo_to", "mark", "restore", "diff", "acknowledge",
        "changes"]


@mcp.tool(name="history")
def history(
    op: Literal["log", "undo", "redo", "undo_to", "mark", "restore", "diff",
                "acknowledge", "changes"] = "log",
    steps: tag(int, "[undo/redo] number of steps") = 1,
    id: tag(str, "[undo_to] op id to undo back to") = "",
    name: tag(str, "[mark/restore] checkpoint name; [changes] focus one object (substring)") = "",
    checkpoint: tag(str, "[diff] checkpoint op id (empty = last)") = "",
) -> str:
    """
    Undo / redo / inspect the operation history — the top **Edit** menu. `op` selects:

      log     — list the operation history (default)
      undo    — undo N steps               (steps)
      redo    — redo N steps               (steps)
      undo_to — undo back to an op id      (id)
      mark    — name the current point as a checkpoint, to restore to later  (name)
      restore — roll the scene back to a named checkpoint (mark, try, restore) (name)
      diff    — what changed since a checkpoint op id (checkpoint; empty = last)
      acknowledge — clear the SPEC-15 external-mutation lock after re-grounding, so
                    world-mutating tools work again (—)
      changes — detailed per-object breakdown of what differs from the clean baseline
                (transform / verts·edges·faces / modifiers); name= to focus one object.
                What the lock points you to when it says the world is dirty.
    """
    o = op.lower().strip()
    if o in ("acknowledge", "ack"):
        return _h.acknowledge_mutation()
    if o == "changes":
        return _h.inspect_changes(name)
    if o == "log":
        return _h.get_history()
    if o == "undo":
        return _h.undo(steps)
    if o == "redo":
        return _h.redo(steps)
    if o == "undo_to":
        return _h.undo_to(id)
    if o == "mark":
        return _h.mark_checkpoint(name)
    if o == "restore":
        return _h.restore_checkpoint(name)
    if o == "diff":
        return introspect.diff_since(checkpoint)
    return unknown("history", "op", op, _OPS)

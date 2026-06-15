"""history — the top Edit menu (Undo / Redo) + the operation log (SPEC-05).

Time travel over the operation history. `op` selects.
"""

from server._core import mcp
from server import history as _h, introspect
from ._common import unknown

_OPS = ["log", "undo", "redo", "undo_to", "diff"]


@mcp.tool(name="history")
def history(
    op: str = "log",
    steps: int = 1,
    id: str = "",
    checkpoint: str = "",
) -> str:
    """
    Undo / redo / inspect the operation history — the top **Edit** menu. `op` selects:

      log     — list the operation history (default)
      undo    — undo N steps               (steps)
      redo    — redo N steps               (steps)
      undo_to — undo back to an op id      (id)
      diff    — what changed since a checkpoint op id (checkpoint; empty = last)
    """
    o = op.lower().strip()
    if o == "log":
        return _h.get_history()
    if o == "undo":
        return _h.undo(steps)
    if o == "redo":
        return _h.redo(steps)
    if o == "undo_to":
        return _h.undo_to(id)
    if o == "diff":
        return introspect.diff_since(checkpoint)
    return unknown("history", "op", op, _OPS)

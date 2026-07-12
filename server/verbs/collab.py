"""collab — action recording journal (Collab N-panel).

The human Start/Stop Recording button lives in the Blender Collab panel; this
verb is the agent half over the same socket.
"""

from typing import Literal

from server._core import mcp, call_blender
from ._common import tag, unknown

_OPS = ["status", "session", "record"]


@mcp.tool(name="collab")
def collab(
    op: Literal["status", "session", "record"] = "status",
    action: tag(str, "[record] start|stop|clear|status — mirror the panel button") = "",
    clear: tag(bool, "[session] True = drop the journal after reading is done") = False,
) -> str:
    """
    Action recording via the in-Blender Collab panel. `op` selects:

      status  — whether recording is on + step count + a short tail of the journal
                (last ~12 steps). Call after the human models to see if a session
                is ready.
      session — full action journal as a markdown transcript (and structured steps).
                clear=True drops the journal after you pull it.
      record  — start|stop|clear the recorder from the agent side (same as the
                panel button). action=start|stop|clear|status.

    Workflow for teach-by-doing: human clicks Start Recording → models (e.g. a
    mug handle with Extrude) → Stop → you `collab op=session` and match the steps.
    """
    o = op.lower().strip()

    if o == "status":
        result = call_blender("collab_status")
        if result.get("error"):
            return result["error"]
        return _format_status(result)

    if o == "session":
        result = call_blender("collab_session", {"clear": bool(clear)})
        if result.get("error"):
            return result["error"]
        return result.get("transcript") or f"steps: {result.get('steps', 0)}"

    if o == "record":
        act = (action or "status").lower().strip()
        result = call_blender("collab_record", {"action": act})
        if result.get("error"):
            return result["error"]
        rec = "ON" if result.get("recording") else "OFF"
        return f"recording: {rec} · steps: {result.get('steps', 0)}"

    return unknown("collab", "op", op, _OPS)


def _format_status(r):
    rec = "ON" if r.get("recording") else "OFF"
    n = r.get("session_steps", 0)
    lines = [f"action recording: {rec} · {n} step(s)"]
    tail = r.get("session_tail") or []
    if tail:
        lines.append(f"session tail (last {len(tail)}):")
        for s in tail:
            props = s.get("props") or {}
            prop_s = ", ".join(f"{k}={v!r}" for k, v in list(props.items())[:6])
            ctx = s.get("context") or {}
            lines.append(
                f"  {s.get('i', '?')}. {s.get('name') or s.get('op')} "
                f"({prop_s or '—'}) · {ctx.get('selection', '?')}"
            )
    elif n == 0:
        lines.append("session: empty — human uses Collab ▸ Start recording")
    return "\n".join(lines)

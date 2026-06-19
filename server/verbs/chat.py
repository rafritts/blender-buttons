"""chat — talk to the human through the in-Blender panel (SPEC-11).

The collaboration pipe. MCP is client-driven (agent → server → Blender), so the
conversation rides as ordinary tool I/O: a message the human types in the Blender
chat panel arrives here as a tool RESULT (`op=poll`), and the agent's reply travels
back as a tool CALL (`op=say`). No new transport — the same socket every other verb
uses. See docs/SPEC-11-in-blender-chat.md.

The long-poll lives HERE, in the MCP server process (which is free to block); the
addon's chat_poll stays instant so Blender's main thread never stalls.
"""

import time
from typing import Literal

from server._core import mcp, call_blender
from ._common import tag, unknown

_OPS = ["poll", "say", "history"]


@mcp.tool(name="chat")
def chat(
    op: Literal["poll", "say", "history"],
    text: tag(str, "[say] the reply to show in the Blender chat panel") = "",
    window: tag(float, "[poll] seconds to long-poll before returning a timeout "
                       "sentinel (keep < the MCP client's per-tool timeout)") = 25.0,
) -> str:
    """
    Talk to the human through the in-Blender chat panel (SPEC-11). `op` selects:

      poll    — wait for the next message the human typed. Long-polls up to
                `window` seconds (the wait is in the server process; the addon stays
                instant), returning the moment a message arrives, or a
                '(no message — re-poll)' sentinel on timeout. Loop on this.
      say     — send a reply (text=) to the panel; the human sees it appear.
      history — dump the full transcript (debug).

    The loop: poll → (think / call add|edit|feel|… to do what was asked) → say → poll.
    It is all one conversation, so earlier turns are simply earlier in your context.
    """
    o = op.lower().strip()

    if o == "poll":
        deadline = time.monotonic() + max(1.0, window)
        while True:
            result = call_blender("chat_poll")
            if result.get("error"):
                return result["error"]
            if not result.get("empty"):
                return f"human: {result['message']}"
            if time.monotonic() >= deadline:
                return "(no message — re-poll)"
            time.sleep(1.0)

    if o == "say":
        if not text.strip():
            return ("chat say: needs text= — the reply to show. "
                    'e.g. chat op=say text="Done — the sphere is 10cm tall."')
        result = call_blender("chat_say", {"text": text})
        if result.get("error"):
            return result["error"]
        return "sent"

    if o == "history":
        result = call_blender("chat_history")
        if result.get("error"):
            return result["error"]
        msgs = result.get("transcript", [])
        return "\n".join(f"{m['role']}: {m['text']}" for m in msgs) or "(empty transcript)"

    return unknown("chat", "op", op, _OPS)

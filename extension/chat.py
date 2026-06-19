"""In-Blender chat: the human↔agent conversation carried as ordinary addon
commands over the existing socket + main-thread queue (SPEC-11).

The collaboration pipe. Two FIFO queues plus a displayed log:

  _inbound   — messages the human typed in the panel, awaiting the agent's poll.
  _outbound  — replies the agent sent, awaiting display by the drain timer.
  _log       — the rendered transcript the N-panel draws (human + agent).

All four touch points run on Blender's MAIN THREAD:
  • the agent's chat_poll / chat_say arrive via the socket → state._request_queue
    → process_queue timer (main thread);
  • the panel's Send operator and the drain timer are UI code (main thread).
So the plain containers below need no locking.

THE ONE DISCIPLINE: chat_poll / chat_say MUST return instantly — they run on the
main thread and a block would freeze Blender. The long-poll wait lives in the MCP
server process (server/verbs/chat.py), never here.
"""

from collections import deque

# Human → agent: typed messages awaiting a poll.
_inbound = deque()
# Agent → human: replies awaiting the drain timer.
_outbound = deque()
# The displayed transcript the panel draws + chat_history returns.
_log = []            # list of {"role": "human"|"agent", "text": str}
# A coarse "is the agent busy?" hint for the panel status line (V1 vibe, not state).
_status = "idle"     # "idle" | "working"


# ── human side (panel Send + drain timer; both main thread) ──────────────────

def push_inbound(text):
    """Panel Send → enqueue a human message for the agent and show it in the log."""
    text = (text or "").strip()
    if not text:
        return False
    _inbound.append(text)
    _log.append({"role": "human", "text": text})
    global _status
    _status = "working"
    return True


def drain_outbound():
    """Drain timer → move every pending agent reply into the displayed log.
    Returns the number drained (0 = nothing changed, so no redraw needed)."""
    n = 0
    while _outbound:
        _log.append({"role": "agent", "text": _outbound.popleft()})
        n += 1
    if n:
        global _status
        _status = "idle"
    return n


def status_text():
    """Panel status line."""
    return "Claude is working…" if _status == "working" else "waiting"


def log():
    return _log


# ── agent side (via the socket — MUST be instant) ────────────────────────────

def chat_poll(params):
    """Pop the next human message, or an {empty: true} sentinel. Instant —
    the long-poll wait lives in the MCP server process, not on this thread."""
    if _inbound:
        return {"success": True, "empty": False, "message": _inbound.popleft()}
    return {"success": True, "empty": True}


def chat_say(params):
    """Push an agent reply onto the outbound queue for the panel to display."""
    text = (params.get("text") or "").strip()
    if not text:
        return {"error": "chat_say: 'text' is required"}
    _outbound.append(text)
    return {"success": True}


def chat_history(params):
    """Dump the full transcript (debug)."""
    return {"success": True, "transcript": list(_log), "count": len(_log)}


TOOLS = {
    "chat_poll": chat_poll,
    "chat_say": chat_say,
    "chat_history": chat_history,
}

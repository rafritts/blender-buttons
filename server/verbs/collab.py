"""collab — shared-state collaboration surface (SPEC-12).

Read the shared collab state (phase + sign-off queue + decisions) and surface an
applied edit for the human's Accept/Reject. The in-Blender Collab panel is the
human half; this verb is the agent half, over the same socket every other verb
uses. See docs/SPEC-12-collab-panel.md.

Decisions flow back ON DEMAND — call `op=status` whenever you want to check in.
There is no long-poll loop (the SPEC-11 chat had one; this deliberately doesn't).
"""

from typing import Literal

from server._core import mcp, call_blender
from ._common import tag, unknown

_OPS = ["status", "submit"]


@mcp.tool(name="collab")
def collab(
    op: Literal["status", "submit"] = "status",
    label: tag(str, '[submit] what the human is signing off on, '
                    'e.g. "extrude nub +0.04"') = "",
    op_id: tag(str, "[submit] the op to sign off (default: your last logged op)") = "",
) -> str:
    """
    Shared-state collaboration with the human, through the in-Blender Collab panel
    (SPEC-12). `op` selects:

      status — read the shared state: the current PHASE the human set (blockout →
               secondary → detail → retopo → uv → bake — a signal, not a lock), the
               sign-off queue (edits awaiting Accept/Reject), and any DECISIONS the
               human made since your last read (each reported once — this call
               DRAINS them). A rejected edit was undone in the viewport; if it
               wasn't the most recent op, later ops were rewound too (listed in
               `rewound`) — rebuild the ones you still want. Call this to check in;
               no loop, no waiting.
      submit — surface an edit you just applied for the human's sign-off. label= is
               what they're signing off on; op_id= defaults to your last logged op.

    The flow: apply an edit → `collab op=submit label="…"` → later `collab op=status`
    to learn the verdict. It is all one conversation; you decide when to check in.
    """
    o = op.lower().strip()

    if o == "status":
        result = call_blender("collab_status")
        if result.get("error"):
            return result["error"]
        return _format_status(result)

    if o == "submit":
        if not label.strip():
            return ('collab submit: needs label= — what the human is signing off on. '
                    'e.g. collab op=submit label="extrude nub +0.04"')
        result = call_blender("collab_submit", {"label": label, "op_id": op_id})
        if result.get("error"):
            return result["error"]
        return (f'submitted for sign-off: "{result["label"]}" [{result["op_id"]}] — '
                f'{result["pending_count"]} awaiting the human\'s call')

    return unknown("collab", "op", op, _OPS)


def _format_status(r):
    lines = [f"phase: {r.get('phase', '?')}"]

    pending = r.get("pending") or []
    if pending:
        lines.append(f"awaiting sign-off ({len(pending)}):")
        for e in pending:
            lines.append(f'  • "{e["label"]}" [{e["op_id"]}]')
    else:
        lines.append("awaiting sign-off: (none)")

    decided = r.get("decided") or []
    if decided:
        lines.append(f"decided since last read ({len(decided)}):")
        for e in decided:
            mark = "✓ accepted" if e["verdict"] == "accepted" else "✗ rejected"
            line = f'  {mark}: "{e["label"]}" [{e["op_id"]}]'
            rewound = e.get("rewound") or []
            if rewound:
                line += (f" — also rewound {len(rewound)} later op(s): "
                         + ", ".join(f'"{l}"' for l in rewound)
                         + " (rebuild if still wanted)")
            if e.get("verified") is False:
                line += " ⚠ POST-UNDO MISMATCH — verify the scene before trusting it"
            lines.append(line)
    else:
        lines.append("decided since last read: (none)")

    return "\n".join(lines)

"""The verb layer — SPEC-05 (the verb collapse).

The 137 flat tools in `server/*.py` stay defined and callable, but stop being
MCP tools. Instead ~15 **verbs** — one per Blender menu — are the entire MCP
surface. Each verb is a free-standing tool with a fat, flat signature that
dispatches on a discriminator (`type` / `op` / `method`) to the *same* flat
helper functions the old tools used. The engine (`extension/`) is untouched:
verbs route to the exact handler names that already exist.

Importing this package registers the verbs. `main.py` then calls
`prune_to_verbs(mcp)` to unregister everything else, so `tools/list` is ~15
schemas instead of 137.
"""

# Import each verb module to register its @mcp.tool. Order is irrelevant; each
# verb imports the flat helpers it needs (idempotent — already imported by main).
from . import (  # noqa: F401
    add,
    obj,
    edit,
    select,
    transform,
    modifier,
    material,
    sculpt,
    pose,
    scene,
    view,
    render,
    history,
    file,
    feel,
    chat,
)

# The complete MCP surface after the collapse. Every name here is a verb module's
# registered tool name; everything NOT here is pruned.
VERB_NAMES = {
    "add", "object", "edit", "select", "transform", "modifier", "material",
    "sculpt", "pose", "scene", "view", "render", "history", "file", "feel",
    "chat",
}


def prune_to_verbs(mcp) -> list:
    """Unregister every tool that isn't a verb (the SPEC-05 cutover).

    The flat functions remain importable/callable — only their MCP registration
    is dropped, so the verbs that dispatch to them keep working. Returns the list
    of names removed (for logging / tests).
    """
    tm = mcp._tool_manager
    removed = [name for name in list(tm._tools) if name not in VERB_NAMES]
    for name in removed:
        tm.remove_tool(name)
    return removed

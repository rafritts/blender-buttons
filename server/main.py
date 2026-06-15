"""Entry point for the blender-buttons MCP server.

The actual tools live in themed submodules (viewport, queries, primitives, ...).
Importing them here registers their @mcp.tool() handlers against the shared
FastMCP instance in `_core`. The pyproject entrypoint `server.main:mcp.run`
resolves to the same instance.
"""

import sys
from pathlib import Path

# Support `python server/main.py` invocation (MCP host config) in addition to
# `python -m server.main` / pyproject entrypoint. When run as a script, the
# `server/` directory is on sys.path but its parent isn't, so `from server
# import ...` fails. Prepend the parent so the package resolves either way.
_PARENT = str(Path(__file__).resolve().parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from server._core import mcp

# Importing each flat module defines its functions. Under SPEC-05 (the verb
# collapse) these are no longer the MCP surface — they're the internal adapter
# layer the verbs dispatch to — but they must be imported so the verbs can call
# them, and so their @mcp.tool registrations exist to be pruned below.
from server import (  # noqa: F401
    viewport,
    queries,
    history,
    primitives,
    objects,
    transforms,
    editmode,
    rings,
    modifiers,
    relational,
    groups,
    finishes,
    bands,
    armature,
    shaders,
    textures,
    scene,
    designs,
    sculpt,
    lint,
    introspect,
    topology,
)

# SPEC-05: register the ~15 verbs (one per Blender menu), then prune everything
# else so `tools/list` is ~15 schemas instead of 137. Flip EXPOSE_FLAT_TOOLS in
# _core to keep the flat tools registered alongside the verbs (debug / staging).
from server import verbs  # noqa: F401  — registers the verbs
from server._core import EXPOSE_FLAT_TOOLS

if not EXPOSE_FLAT_TOOLS:
    verbs.prune_to_verbs(mcp)


if __name__ == "__main__":
    mcp.run()

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

# Importing each module triggers its @mcp.tool() registrations.
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
    scene,
    designs,
    sculpt,
)


if __name__ == "__main__":
    mcp.run()

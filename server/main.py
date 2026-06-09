"""Entry point for the blender-buttons MCP server.

The actual tools live in themed submodules (viewport, queries, primitives, ...).
Importing them here registers their @mcp.tool() handlers against the shared
FastMCP instance in `_core`. The pyproject entrypoint `server.main:mcp.run`
resolves to the same instance.
"""

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

"""MCP resources — pull-on-demand docs an agent can read when IT chooses.

Resources differ from the `instructions` bootstrap (server/_instructions.py): the
bootstrap is PUSHED once at initialize and kept tight; a resource is PULLED by the
client on demand and can be as deep as it likes. The full LLM-driving field notes
live here so the bootstrap can stay short and just point at this.

Imported by server.main so the @mcp.resource registration runs. Resources are a
separate registry from tools, so the SPEC-05 verb-pruning leaves them untouched.
"""

from pathlib import Path

from server._core import mcp

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GUIDANCE = _REPO_ROOT / "GUIDANCE_FOR_LLMS.md"


@mcp.resource(
    "guidance://llms",
    name="Guidance for LLMs driving blender-buttons",
    # Explicit description: FastMCP's docstring parsing for resources is unreliable,
    # and this string is what the agent sees when listing resources to decide whether
    # to read it — so it has to sell the read.
    description="Battle-tested loops + the one rule (you cannot dead-reckon in 3D) for "
                "driving this server. Read BEFORE any multi-step task: locating geometry, "
                "constructing a form, or assembling parts. Distilled from real builds.",
    mime_type="text/markdown",
)
def guidance_for_llms() -> str:
    """Serve GUIDANCE_FOR_LLMS.md verbatim, read fresh on each request so edits to the
    doc take effect without restarting the server."""
    return _GUIDANCE.read_text(encoding="utf-8")

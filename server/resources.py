"""MCP resources — pull-on-demand docs an agent can read when IT chooses.

Resources differ from the `instructions` bootstrap (server/_instructions.py): the
bootstrap is PUSHED once at initialize and kept tight; a resource is PULLED by the
client on demand and can be as deep as it likes. The full LLM-driving field notes
live here so the bootstrap can stay short and just point at this.

Imported by server.main so the @mcp.resource registration runs. Resources are a
separate registry from tools, so the SPEC-05 verb-pruning leaves them untouched.
"""

from server._core import mcp
from server.guidance import TECHNIQUES, serve_guide, techniques_index, _TECHNIQUES_DIR


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
    return serve_guide("")


# ── the techniques shelf (SPEC-21 §5) ─────────────────────────────────────────────
# Named, reusable multi-step METHODS in native vocabulary — prose over primitives,
# applied differently each time (that adaptation is the agent's job; compiling it into
# code was the retired macros' defect). Indexed and served ON DEMAND, never preloaded:
# classify the form first, then pull the one matching technique. A technique promises
# an APPROACH; a recipe (recipes/) promises a RESULT.


@mcp.resource(
    "guidance://techniques",
    name="Techniques shelf — index",
    description="Named multi-step modeling METHODS in native Blender vocabulary. "
                "Before choosing tools for a form, read this index and pull the one "
                "technique whose condition matches. Approach docs, not recipes.",
    mime_type="text/markdown",
)
def techniques_index_resource() -> str:
    return techniques_index()


def _register_technique(slug: str, when: str):
    path = _TECHNIQUES_DIR / f"{slug}.md"

    @mcp.resource(
        f"guidance://techniques/{slug}",
        name=f"Technique: {slug}",
        description=when,
        mime_type="text/markdown",
    )
    def _technique() -> str:
        return path.read_text(encoding="utf-8")


for _slug, _when in TECHNIQUES.items():
    _register_technique(_slug, _when)
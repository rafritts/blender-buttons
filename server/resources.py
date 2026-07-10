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


# ── the techniques shelf (SPEC-21 §5) ─────────────────────────────────────────────
# Named, reusable multi-step METHODS in native vocabulary — prose over primitives,
# applied differently each time (that adaptation is the agent's job; compiling it into
# code was the retired macros' defect). Indexed and served ON DEMAND, never preloaded:
# classify the form first, then pull the one matching technique. A technique promises
# an APPROACH; a recipe (recipes/) promises a RESULT.

_TECHNIQUES_DIR = _REPO_ROOT / "techniques"

# slug → the WHEN, phrased as the form condition that should trigger the pull.
_TECHNIQUES = {
    "form-blockout": "Starting ANY new asset: classify the form BEFORE choosing a tool, "
                     "then block proportioned masses relationally. Read this one first.",
    "revolved-vessel": "The form's silhouette sweeps around an axis (goblet, vase, plate, "
                       "wheel): spin a profile / author ring radii directly.",
    "shell": "A surface that follows another at a distance (clothing, armor, icing, a "
             "case), or a solid to carve into a walled vessel (cup, bowl).",
    "smooth-union": "Two closed masses must read as ONE body (handle→mug, limb→torso): "
                    "hard union, filleted seam, or continuous flesh.",
    "ring-weld": "Two open rims must join into one continuous skin (neck→head, "
                 "spout→body, tubes between openings).",
    "drip": "Matter that flowed and set — icing/wax/paint hanging off a rim: drape, "
            "shape tongues, bulb tips, weld beads locally.",
    "npr-look": "A stylized cel/anime look: toon band material, inverted-hull outline, "
                "flat-color render settings.",
}


@mcp.resource(
    "guidance://techniques",
    name="Techniques shelf — index",
    description="Named multi-step modeling METHODS in native Blender vocabulary. "
                "Before choosing tools for a form, read this index and pull the one "
                "technique whose condition matches. Approach docs, not recipes.",
    mime_type="text/markdown",
)
def techniques_index() -> str:
    lines = ["# Techniques — pull the one whose condition matches the form",
             "",
             "Classify the form FIRST (see guidance://llms), then read exactly the",
             "matching technique via its resource URI. Each is an approach you adapt",
             "with perception reads between steps — not a fixed script.",
             ""]
    for slug, when in _TECHNIQUES.items():
        lines.append(f"- `guidance://techniques/{slug}` — {when}")
    return "\n".join(lines)


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


for _slug, _when in _TECHNIQUES.items():
    _register_technique(_slug, _when)

"""The teaching texts — GUIDANCE_FOR_LLMS.md and the techniques shelf.

No MCP dependency: the extension's headless tests (and `look op=guide`) read
these files without importing FastMCP. `server/resources.py` wraps the same
functions as `guidance://` resources.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GUIDANCE = _REPO_ROOT / "GUIDANCE_FOR_LLMS.md"
_TECHNIQUES_DIR = _REPO_ROOT / "techniques"

# slug → the WHEN, phrased as the form condition that should trigger the pull.
TECHNIQUES = {
    "form-blockout": "Starting ANY new asset: classify the form BEFORE choosing a tool, "
                     "then block proportioned masses relationally. Read this one first.",
    "revolved-vessel": "The form's silhouette sweeps around an axis (goblet, vase, plate, "
                       "wheel): trace a profile and spin it.",
    "shell": "A surface that follows another at a distance (clothing, armor, icing, a "
             "case), or a solid to carve into a walled vessel (cup, bowl).",
    "smooth-union": "Two closed masses must read as ONE body (handle→mug, limb→torso): "
                    "hard union, filleted seam, or continuous flesh.",
    "ring-weld": "Two open rims must join into one continuous skin (neck→head, "
                 "spout→body, tubes between openings).",
}


def techniques_index() -> str:
    lines = ["# Techniques — pull the one whose condition matches the form",
             "",
             "Classify the form FIRST (see guidance://llms), then read exactly the",
             "matching technique via its resource URI. Each is an approach you adapt",
             "with perception reads between steps — not a fixed script.",
             ""]
    for slug, when in TECHNIQUES.items():
        lines.append(f"- `guidance://techniques/{slug}` — {when}")
    return "\n".join(lines)


def serve_guide(topic: str = "") -> str:
    """G228 — the same text as the guidance:// resources, for clients with no
    resource reader. topic empty / 'llms' is the field manual; 'techniques' is
    the index; a slug is that technique. Unknown topics return a teaching error
    listing the known ones (never a throw)."""
    t = (topic or "").strip().lower().lstrip("/")
    if t.startswith("techniques/"):
        t = t[len("techniques/"):]
    if not t or t in ("llms", "guidance", "field-manual", "manual"):
        return _GUIDANCE.read_text(encoding="utf-8")
    if t in ("techniques", "index"):
        return techniques_index()
    if t in TECHNIQUES:
        path = _TECHNIQUES_DIR / f"{t}.md"
        return path.read_text(encoding="utf-8")
    known = ["(omit / llms)", "techniques", *sorted(TECHNIQUES)]
    return (f"unknown guide topic {topic!r}. "
            f"look op=guide topic=<one of: {', '.join(known)}>")

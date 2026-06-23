"""server settings — a small JSON config the MCP server reads at call time.

The file lives in the repo at server/settings.json and ships with the code. Today it
holds one key, `render_dir`: the single directory every render lands in, so renders
stop scattering across whatever path a caller happened to pass. Missing file or a bad
key falls back to _DEFAULTS — the server never hard-fails on a config problem.

Render naming is collision-free by construction: resolve_render_path() drops an 8-char
random tag before the extension (donut_hero.png -> donut_hero_gh75kddh.png), so the
server never has to check whether a file already exists.
"""

import json
import os
import secrets
import string

_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")

_DEFAULTS = {
    "render_dir": "~/blender-buttons-renders/",
}

# Lowercase letters + digits (matches the donut_hero_gh75kddh.png style — note 'g'/'k'
# are outside hex, so this is base36, not uuid.hex).
_TAG_ALPHABET = string.ascii_lowercase + string.digits


def load_settings() -> dict:
    """Read server/settings.json, layered over _DEFAULTS. A missing or malformed file
    yields the defaults rather than raising — a broken config must never block a render."""
    merged = dict(_DEFAULTS)
    try:
        with open(_SETTINGS_PATH) as f:
            data = json.load(f)
        if isinstance(data, dict):
            merged.update(data)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return merged


def render_dir() -> str:
    """The configured render output directory, ~-expanded to an absolute path."""
    return os.path.expanduser(load_settings()["render_dir"])


def _tag8() -> str:
    return "".join(secrets.choice(_TAG_ALPHABET) for _ in range(8))


def resolve_render_path(filepath: str, output_dir: str = "") -> str:
    """Map a caller's render name to the final on-disk path (extension-less — the
    extension appends it to match the format, keeping one source of truth for that).

    The directory is ALWAYS the configured render_dir; only an explicit output_dir
    override sends a render elsewhere. The caller's own directory component is dropped
    on purpose — that is what stops renders from scattering. The basename gets an
    8-char random tag so two renders can never collide.
    """
    name = os.path.basename((filepath or "").strip())
    stem = os.path.splitext(name)[0] or "render"
    base = os.path.expanduser(output_dir) if output_dir else render_dir()
    return os.path.join(base, f"{stem}_{_tag8()}")

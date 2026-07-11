"""Textured PBR materials wired from LOCAL image paths (no network here).

The server (server/polyhaven.py) downloads + caches Poly Haven maps and passes
their local file paths in; this module only wires the Principled BSDF node graph.
Box projection means no UV unwrap is needed or attempted.
"""

import json

import bpy

from .common import resolve_targets, has_material_slots


TOOLS = {
}

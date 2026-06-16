"""Handles (server side) — SPEC-07 Phase 1 wrappers for `feel op=handle/handles`.

These forward to the extension's `handles` module and render its result as text.
Minting mutates the scene (it creates an Empty + vgroup), so `mint_handle` carries
the status block; `list_handles` is a pure read-model scan and does not.
"""

from server._core import call_blender, _status


def mint_handle(name: str = "", source: str = "selection") -> str:
    """Snapshot the active mesh's current edit-mode selection as a named handle —
    an Empty in the `Handles` collection + a `HANDLE_<name>` vertex group on the
    mesh. Phase 1: mint + see (no drift/recompute yet)."""
    result = call_blender("mint_handle", {"name": name, "source": source})
    if not result.get("success"):
        return result.get("error", "failed")
    p = result["point"]
    return (
        f"handle '{result['name']}' minted ({result['vert_count']} verts) → "
        f"Handles collection\n"
        f"  owner:  {result['owner']}\n"
        f"  vgroup: {result['vgroup']}\n"
        f"  point:  [{p[0]}, {p[1]}, {p[2]}]\n"
        f"  → see it in the Outliner under 'Handles'; rename or delete it natively"
        + _status(result)
    )


def list_handles() -> str:
    """List every handle by scanning the `Handles` collection (the read-model)."""
    result = call_blender("list_handles", {})
    if not result.get("success"):
        return result.get("error", "failed")
    handles = result["handles"]
    if not handles:
        return ("no handles yet — mint one with `feel op=handle from=selection name=X` "
                "(select geometry in edit mode first), or right-click → Save as Handle")
    lines = [f"{result['count']} handle(s):"]
    for h in handles:
        p = h["point"]
        lines.append(
            f"  {h['name']:<22} {h['kind']:<10} owner={h['owner']:<18} "
            f"verts={h['vert_count']:<4} @ [{p[0]}, {p[1]}, {p[2]}]"
        )
    return "\n".join(lines)

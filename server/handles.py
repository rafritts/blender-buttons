"""Handles (server side) — SPEC-07 wrappers for `feel op=handle/handles/accept`.

These forward to the extension's `handles` module and render its result as text.
Minting mutates the scene (it creates an Empty + vgroup), so `mint_handle` carries
the status block; `list_handles` / `accept_handle` are read-model maintenance and
do not. Phase 3 adds the git-style integrity view (clean/dirty/orphaned + drift +
attribution) on list, an inline drift flag on consume, and the `accept` re-baseline.
"""

from server._core import call_blender, _status


def _state_glyph(h):
    """One compact git-status line tail for a validated handle dict."""
    state = h.get("state", "clean")
    if state == "orphaned":
        return f"✗ orphaned ({h.get('reason', 'vgroup gone')})"
    p = h.get("point")
    where = f"@ [{p[0]}, {p[1]}, {p[2]}]" if p else ""
    if state == "dirty":
        return f"⚠ dirty ({h.get('attribution', '?')})  {_drift_str(h)}  {where}".rstrip()
    return f"● clean  {where}".rstrip()


def _drift_str(h):
    """The two drift signals in cm, only the ones that actually tripped."""
    bits = []
    dcm, pcm = h.get("deform", 0) * 100, h.get("place", 0) * 100
    if dcm >= 0.01:
        bits.append(f"shape {dcm:.1f}cm")
    if pcm >= 0.01:
        bits.append(f"{'moved' if h.get('fiducial') else 'off-mint'} {pcm:.1f}cm")
    return "drift " + ", ".join(bits) if bits else "drift <ε"


def mint_handle(name: str = "", source: str = "selection", vertex_parent: bool = False) -> str:
    """Snapshot the active mesh's current edit-mode selection as a named handle —
    an Empty in the `Handles` collection + a `HANDLE_<name>` vertex group on the
    mesh — with a Phase-3 provenance snapshot (mint point + drift signatures) so it
    tracks clean/dirty/orphaned from here on."""
    result = call_blender("mint_handle",
                          {"name": name, "source": source, "vertex_parent": vertex_parent})
    if not result.get("success"):
        return result.get("error", "failed")
    p = result["point"]
    vp = "  ⚓ vertex-parented (rides deform)\n" if result.get("vertex_parent") else ""
    return (
        f"handle '{result['name']}' minted ({result['vert_count']} verts) → "
        f"Handles collection\n"
        f"  owner:  {result['owner']}\n"
        f"  vgroup: {result['vgroup']}\n"
        f"  point:  [{p[0]}, {p[1]}, {p[2]}]\n"
        f"{vp}"
        f"  → see it in the Outliner under 'Handles'; rename or delete it natively"
        + _status(result)
    )


def list_handles() -> str:
    """List every handle by scanning the `Handles` collection (the read-model), each
    VALIDATED (Phase 3): live point + git-style state, drift, and attribution."""
    result = call_blender("list_handles", {})
    if not result.get("success"):
        return result.get("error", "failed")
    handles = result["handles"]
    if not handles:
        return ("no handles yet — mint one with `feel op=handle from=selection name=X` "
                "(select geometry in edit mode first), or right-click → Save as Handle")
    lines = [f"{result['count']} handle(s):"]
    for h in handles:
        vp = " ⚓" if h.get("vertex_parent") else ""
        lines.append(
            f"  {h['name']:<20}{vp:<2} {h['kind']:<10} owner={h['owner']:<16} "
            f"verts={h['vert_count']:<4} {_state_glyph(h)}"
        )
    return "\n".join(lines)


def accept_handle(name: str) -> str:
    """Re-baseline a dirty handle — re-snapshot its provenance from current geometry,
    clearing the drift (the 'stage it' move)."""
    result = call_blender("accept_handle", {"name": name})
    if not result.get("success"):
        return result.get("error", "failed")
    p = result["point"]
    return (
        f"handle '{result['name']}' re-baselined → ● clean ({result['vert_count']} verts)\n"
        f"  point: [{p[0]}, {p[1]}, {p[2]}]\n"
        f"  snapshot updated to current geometry; drift cleared"
    )


def prune_handles() -> str:
    """G15 — delete every orphaned handle (owner/vgroup gone). Clean and dirty handles
    are kept; only the unresolvable Empties are collected."""
    result = call_blender("prune_handles", {})
    if not result.get("success"):
        return result.get("error", "failed")
    pruned = result.get("pruned", [])
    if not pruned:
        return "no orphaned handles to prune — registry is clean"
    return f"pruned {len(pruned)} orphaned handle(s): " + ", ".join(pruned)


def forget_handle(name: str) -> str:
    """Delete one named handle regardless of state (the targeted prune)."""
    result = call_blender("forget_handle", {"name": name})
    if not result.get("success"):
        return result.get("error", "failed")
    return f"forgot handle '{result['forgot']}' (Empty + vgroup removed)"


def resolve_point(name: str):
    """Resolve a handle to its live world point for a consuming verb. Returns
    (point_list, error_str, note_str): error on orphaned/missing; note is a drift
    flag (or None) so the consumer can surface that it landed on a *dirty* anchor —
    'recompute + flag' is the Phase-3 default; the agent can re-mint or `accept`."""
    result = call_blender("resolve_handle", {"name": name})
    if not result.get("success"):
        return None, result.get("error", f"handle '{name}' could not be resolved"), None
    note = None
    if result.get("state") == "dirty":
        h = {"deform": result.get("deform", 0), "place": result.get("place", 0),
             "fiducial": result.get("fiducial")}
        note = (f"⚠ handle '{name}' is dirty ({result.get('attribution', '?')}) — "
                f"{_drift_str(h)} since mint; consuming the recomputed point "
                f"(re-mint, or `feel op=accept name={name}` to re-baseline)\n")
    return result["point"], None, note

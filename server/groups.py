from server._core import mcp, call_blender, _status


@mcp.tool()
def group(name: str, parts: list, label: str = "") -> str:
    """
    Create (or extend) a named group containing the given parts.
    A group is a Blender collection — any tool that accepts `targets` can take the
    group name and act on all members.

    name: group name (unique).
    parts: list of object names to include.

    Example: group("chair", ["seat", "leg_front_left", "leg_front_right",
                              "leg_back_left", "leg_back_right", ...])
             then smooth_edges("chair") finishes every part in one call.
    """
    result = call_blender("group", {"name": name, "parts": parts}, label=label)
    if result.get("success"):
        return (f"group '{name}' now contains {len(result['members'])} parts "
                f"(added: {result['newly_added']}) [{result.get('op_id','')}]"
                + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def add_to_group(name: str, parts: list, label: str = "") -> str:
    """Add objects (or members of another group) to an existing group.

    Use this as the design grows so the group always represents the whole thing.
    Example: after adding a knocker_ring to a chest, call
    add_to_group("chest", ["knocker_plate", "knocker_ring"]) — then
    delete_object("chest") or nudge("chest", ...) acts on every part, not just the originals.

    name:  existing group name (create with `group` first).
    parts: list of object names or other group names (groups expand to their members).
    """
    result = call_blender("add_to_group", {"name": name, "parts": parts}, label=label)
    if result.get("success"):
        return (f"group '{name}' now contains {len(result['members'])} parts "
                f"(added: {result['newly_added']}) [{result.get('op_id','')}]"
                + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def parts_in(name: str) -> str:
    """List the parts inside a named group."""
    result = call_blender("parts_in", {"name": name})
    if not result.get("success"):
        return result.get("error", "failed")
    return f"group '{name}': {result['parts']}" + _status(result)


@mcp.tool()
def ungroup(name: str, label: str = "") -> str:
    """Remove a group. Its objects move back to the scene root; they are NOT deleted."""
    result = call_blender("ungroup", {"name": name}, label=label)
    if result.get("success"):
        return (f"removed group '{name}'; freed {result['members_freed']} "
                f"[{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")

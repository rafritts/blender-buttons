from server._core import mcp, call_blender


@mcp.tool()
def save_design(name: str) -> str:
    """
    Save the current Blender scene as a .blend file in ~/blender-designs/.
    Use to checkpoint a design so it can be reopened in a later session.

    name: design name. The .blend extension is added if omitted.
    """
    result = call_blender("save_design", {"name": name})
    if result.get("saved"):
        return f"saved: {result['saved']}"
    return result.get("error", "failed")


@mcp.tool()
def open_design(name: str) -> str:
    """
    Open a previously saved design from ~/blender-designs/. Replaces the
    current scene entirely.

    name: design name. The .blend extension is added if omitted.
    """
    result = call_blender("open_design", {"name": name})
    if result.get("opened"):
        return f"opened: {result['opened']}"
    return result.get("error", "failed")


@mcp.tool()
def list_designs() -> str:
    """List all saved designs in ~/blender-designs/."""
    result = call_blender("list_designs")
    designs = result.get("designs", [])
    if not designs:
        return f"No saved designs in {result.get('dir', '?')}."
    return f"{result['dir']}:\n" + "\n".join(f"  {d}" for d in designs)

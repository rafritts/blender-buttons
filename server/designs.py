from server._core import mcp, call_blender, _status


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
def new_scene(empty: bool = False) -> str:
    """
    Reset to a fresh scene — the MCP equivalent of File > New > General.

    Loads Blender's startup file: the default cube, camera, and light, with the
    world background, color management, and render settings all reset to
    defaults. Use this to "start over" cleanly instead of walking the scene tree
    deleting every object by hand and trying to un-do earlier world/render tweaks.

    empty: True → also delete the startup cube/camera/light, leaving a bare scene
           (a clean modelling slate). Default False = true File > New > General.

    The operation history log is cleared (the reload wipes Blender's undo stack),
    so undo() won't reach back past a new_scene.
    """
    result = call_blender("new_scene", {"empty": empty})
    if result.get("success"):
        objs = result.get("objects") or []
        main = f"reset to {result.get('reset_to')} — objects: {objs or '(none)'}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def list_designs() -> str:
    """List all saved designs in ~/blender-designs/."""
    result = call_blender("list_designs")
    designs = result.get("designs", [])
    if not designs:
        return f"No saved designs in {result.get('dir', '?')}."
    return f"{result['dir']}:\n" + "\n".join(f"  {d}" for d in designs)

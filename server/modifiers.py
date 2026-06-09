from server._core import mcp, call_blender, _status


@mcp.tool()
def add_modifier(type: str, name: str = "", levels: int = 2, render_levels: int = 2,
                 width: float = 0.1, segments: int = 1,
                 target: str = "", offset: float = None,
                 wrap_method: str = "NEAREST_SURFACEPOINT",
                 axis: str = "X", merge_threshold: float = None,
                 mirror_object: str = "",
                 label: str = "") -> str:
    """
    Add a modifier to the active object.
    type: SUBSURF | BEVEL | SOLIDIFY | MIRROR | ARRAY | SCREW | SHRINKWRAP
    levels: subdivision levels (SUBSURF)  |  width/segments: bevel params
    target: required for SHRINKWRAP — the object to wrap onto.
    offset: SHRINKWRAP only — surface offset in meters (skin distance).
    wrap_method: SHRINKWRAP only —
                 NEAREST_SURFACEPOINT (default) | PROJECT | NEAREST_VERTEX | TARGET_PROJECT.
    axis: MIRROR only — any combination of X, Y, Z (default "X"). E.g. "XY" mirrors on both.
    merge_threshold: MIRROR only — weld coincident verts at the mirror plane (typical 0.001).
    mirror_object: MIRROR only — use this object's local axes as the mirror plane (defaults to self).
    """
    params = {
        "type": type, "name": name or type.capitalize(),
        "levels": levels, "render_levels": render_levels,
        "width": width, "segments": segments,
        "wrap_method": wrap_method,
        "axis": axis,
    }
    if target:
        params["target"] = target
    if offset is not None:
        params["offset"] = offset
    if merge_threshold is not None:
        params["merge_threshold"] = merge_threshold
    if mirror_object:
        params["mirror_object"] = mirror_object
    result = call_blender("add_modifier", params, label=label)
    if result.get("success"):
        main = f"{result['modifier']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def modify_modifier(target: str, modifier_name: str,
                    levels: int = None, render_levels: int = None,
                    width: float = None, segments: int = None,
                    thickness: float = None, offset: float = None,
                    angle_limit: float = None, count: int = None,
                    wrap_method: str = "", target_object: str = "",
                    label: str = "") -> str:
    """
    Tweak properties on an existing modifier without rebuilding it.
    Use this to dial in shrinkwrap offset, bevel width, subsurf levels, etc.

    target: object name. modifier_name: name of the modifier on that object.
    Each numeric param is optional — pass only the ones you want to change.
    angle_limit is in degrees (BEVEL). target_object re-points SHRINKWRAP/ARRAY to a different object.
    wrap_method (SHRINKWRAP): NEAREST_SURFACEPOINT | PROJECT | NEAREST_VERTEX | TARGET_PROJECT.
    """
    params = {"target": target, "modifier_name": modifier_name}
    for key, val in (("levels", levels), ("render_levels", render_levels),
                     ("width", width), ("segments", segments),
                     ("thickness", thickness), ("offset", offset),
                     ("angle_limit", angle_limit), ("count", count)):
        if val is not None:
            params[key] = val
    if wrap_method:
        params["wrap_method"] = wrap_method
    if target_object:
        params["target_object"] = target_object
    result = call_blender("modify_modifier", params, label=label)
    if result.get("success"):
        applied = result.get("applied", [])
        skipped = result.get("skipped", [])
        tail = f" (skipped: {skipped})" if skipped else ""
        main = f"{result['modifier']} ({result['type']}): {applied}{tail} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def remove_modifier(target: str, modifier_name: str, label: str = "") -> str:
    """
    Remove a modifier from an object by name. Pass modifier_name='ALL' to clear them all.
    Use list_modifiers first to see what's on the object.
    """
    result = call_blender("remove_modifier",
                          {"target": target, "modifier_name": modifier_name}, label=label)
    if result.get("success"):
        main = f"removed {result['removed']} from '{result['target']}' [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def list_modifiers(target: str) -> str:
    """
    List the modifier stack on an object (top → bottom = evaluation order).
    Each entry shows type, name, and the relevant numeric props.
    """
    result = call_blender("list_modifiers", {"target": target})
    if not result.get("success"):
        return result.get("error", "failed") + _status(result)
    mods = result["modifiers"]
    if not mods:
        return f"'{result['target']}': no modifiers" + _status(result)
    lines = [f"'{result['target']}' modifier stack ({len(mods)}):"]
    for i, m in enumerate(mods):
        extras = " ".join(f"{k}={v}" for k, v in m.items() if k not in ("name", "type"))
        lines.append(f"  {i}. {m['type']:12} '{m['name']}'  {extras}")
    return "\n".join(lines) + _status(result)


@mcp.tool()
def apply_modifiers(name: str = "") -> str:
    """
    Apply all modifiers on an object, collapsing them into the base mesh.
    name: object name — if omitted, applies to the active object.
    Required before export, boolean operations, or manual mesh editing on a modified object.
    Must be in Object Mode.
    """
    result = call_blender("apply_modifiers", {"name": name})
    if result.get("success"):
        applied = result.get("applied", [])
        main = (f"Applied {len(applied)} modifier(s) on '{result['object']}': {applied}"
                if applied else f"No modifiers on '{result['object']}'")
    else:
        main = result.get("error", "failed")
    return main + _status(result)

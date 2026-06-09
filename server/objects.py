from server._core import mcp, call_blender, _status


@mcp.tool()
def rename_object(old_name: str, new_name: str) -> str:
    """
    Rename an object (and its mesh data) to a new name.
    Use get_scene_tree first to find current names.
    """
    result = call_blender("rename_object", {"old_name": old_name, "new_name": new_name})
    if result.get("success"):
        main = f"Renamed '{result['old_name']}' → '{result['new_name']}'"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_object(name: str) -> str:
    """Select an object by name and make it active. Use get_scene_tree first to find names."""
    result = call_blender("select_object", {"name": name})
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_mode(mode: str) -> str:
    """
    Switch the active object's interaction mode.
    mode: OBJECT | EDIT | SCULPT
    """
    result = call_blender("set_mode", {"mode": mode})
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def delete_object(name: str, label: str = "") -> str:
    """Delete an object OR a group by name. If `name` is a group, every part inside
    (recursively, through nested sub-groups) is deleted and the empty group is removed.
    Use get_scene_tree to see object/group names."""
    result = call_blender("delete_object", {"name": name}, label=label)
    if result.get("success"):
        if "deleted_group" in result:
            members = result["deleted_members"]
            main = (f"Deleted group '{result['deleted_group']}' and {len(members)} part(s) "
                    f"[{result.get('op_id','')}]")
        else:
            main = f"Deleted '{result['deleted']}' [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def duplicate_object(name: str, new_name: str = "") -> str:
    """
    Duplicate an object in place. The duplicate becomes the active object.
    name: object to duplicate (must exist in the scene)
    new_name: name for the duplicate — if omitted, Blender appends .001
    Returns both the original and duplicate names.
    Must be in Object Mode.
    """
    result = call_blender("duplicate_object", {"name": name, "new_name": new_name})
    if result.get("success"):
        main = f"Duplicated '{result['original']}' → '{result['duplicate']}'"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def join_objects(names: list, merge_threshold: float = None) -> str:
    """
    Join multiple objects into one. The first name in the list becomes the surviving object.
    names: list of object names to join (minimum 2)
    merge_threshold: if set, weld coincident verts after joining (typical 0.001 = 1mm).
                     Eliminates seam-shading artifacts on a SubSurf'd joined mesh.
    All objects must be the same type (MESH). The result keeps the first object's name.
    Must be in Object Mode.
    """
    params = {"names": names}
    if merge_threshold is not None:
        params["merge_threshold"] = merge_threshold
    result = call_blender("join_objects", params)
    if result.get("success"):
        main = f"Joined {result['joined']} → '{result['result_object']}'"
        m = result.get("merged")
        if m:
            main += f"  merged {m['merged']} verts (welded to {m['verts_after']})"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def separate_selection(new_name: str = "", label: str = "") -> str:
    """
    Split the current edit-mode selection out as a new object (the 'P → Selection' shortcut).
    new_name: optional name for the new object. If omitted, Blender appends '.001'.
    Returns the new object's name. The original stays in edit mode; the new object is in object mode.
    """
    params = {}
    if new_name:
        params["new_name"] = new_name
    result = call_blender("separate_selection", params, label=label)
    if result.get("success"):
        main = f"separated '{result['source']}' → '{result['new_object']}' [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def split_by_part(label: str = "") -> str:
    """Split the active mesh into separate objects, one per connected component
    (P → By Loose Parts). Restores per-part addressability after a join_objects."""
    result = call_blender("split_by_part", {}, label=label)
    if result.get("success"):
        main = (f"split '{result['source']}' into {result['part_count']} parts; "
                f"new objects: {result['new_objects']}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)

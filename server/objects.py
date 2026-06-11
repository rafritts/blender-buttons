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
def duplicate_mirrored(target: str, axis: str = "X", pivot: str = "WORLD",
                       new_name: str = "", label: str = "") -> str:
    """
    Bake a mirrored copy of an object across a world axis plane — the one-shot
    "make the other half" verb for symmetry that's already finalized (a left
    boot → right boot, one earring → the pair). For LIVE symmetry while you're
    still editing, prefer the MIRROR modifier (add_modifier type='MIRROR') or the
    placement DSL's mirror_of; this bakes a static, independent copy.

    target:   object to mirror.
    axis:     X | Y | Z — plane perpendicular to this axis. Default X
              (mirror left↔right across the Y-Z plane).
    pivot:    "WORLD" (default — reflect across the axis=0 plane at the world
              origin) | "SELF" (about the object's own origin) | an object name
              (across the plane through that object's center).
    new_name: name for the copy (default "<target>_mirror").

    Normals are recalculated outward after the reflection, and the transform is
    applied so the copy ships with clean [1,1,1] scale.

    Example: duplicate_mirrored("boot_L", axis="X", new_name="boot_R")
    """
    result = call_blender("duplicate_mirrored", {
        "target": target, "axis": axis, "pivot": pivot, "new_name": new_name,
    }, label=label)
    if result.get("success"):
        main = (f"mirrored '{result['original']}' → '{result['mirror']}' across {result['axis']} "
                f"(pivot={result['pivot']}) dims={result['dimensions']} [{result.get('op_id','')}]")
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
def get_custom_properties(name: str, bone: str = None) -> str:
    """
    List the user-defined custom properties on an object — or on one of its pose
    bones (bone=...). Read-only. Production rigs drive IK/FK switches and panel
    toggles through these; addons and game-export pipelines stash metadata here too.

    Examples:
      get_custom_properties("char_rig", bone="properties_arm.L")   # IK/FK switch
      get_custom_properties("hero_prop")                            # export metadata
    """
    params = {"name": name}
    if bone is not None:
        params["bone"] = bone
    result = call_blender("get_custom_properties", params)
    if not result.get("success"):
        return result.get("error", "failed")
    props = result.get("properties", {})
    if not props:
        where = f"{name}.{bone}" if bone else name
        return f"{where}: no custom properties"
    where = f"{name}.{bone}" if bone else name
    lines = [f"{where}: {result['count']} custom propert(y/ies)"]
    for k, v in props.items():
        lines.append(f"  {k} = {v}")
    return "\n".join(lines)


@mcp.tool()
def set_custom_property(name: str, key: str, value, bone: str = None,
                        label: str = "") -> str:
    """
    Set (or create) a custom property on an object or one of its pose bones
    (bone=...). The way to drive a rig's IK/FK switch, a panel toggle, or any
    addon/export metadata.

    name:  object name.
    key:   property name.
    value: new value (number, string, or list).
    bone:  optional pose-bone name to target instead of the object.

    Example: set_custom_property("char_rig", "ik_fk_arm.L", 1.0,
                                 bone="properties_arm.L")
    """
    params = {"name": name, "key": key, "value": value}
    if bone is not None:
        params["bone"] = bone
    result = call_blender("set_custom_property", params, label=label)
    if result.get("success"):
        verb = "created" if result.get("created") else "set"
        where = f"{name}.{bone}" if bone else name
        main = f"{verb} {where}['{key}'] = {result['value']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_particle_visibility(name: str, show: bool = False, label: str = "") -> str:
    """
    Show or hide an object's particle systems (hair/fur) in the viewport. Strands
    often bury the underlying mesh, making a hair-bearing asset hard to work on;
    this toggles show_viewport on every particle-system modifier.

    Example: set_particle_visibility("spring_body", show=False)   # hide the hair
    """
    result = call_blender("set_particle_visibility", {"name": name, "show": show},
                          label=label)
    if result.get("success"):
        state = "shown" if result["show"] else "hidden"
        main = (f"{state} {len(result['particle_systems'])} particle system(s) on "
                f"'{result['name']}' [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_object_visibility(name: str, viewport: bool = None, render: bool = None,
                          label: str = "") -> str:
    """
    Show or hide an object in the viewport and/or render — without deleting or
    unbinding it. Hiding an armature hides its bones from the user's live view while
    the Armature modifier keeps deforming the bound mesh; hiding a cutter/guide
    declutters a hero shot.

    Example: set_object_visibility("char_rig", viewport=False)   # hide the bones
    """
    params = {"name": name}
    if viewport is not None:
        params["viewport"] = viewport
    if render is not None:
        params["render"] = render
    result = call_blender("set_object_visibility", params, label=label)
    if result.get("success"):
        main = (f"'{result['name']}': viewport={'shown' if result['viewport_visible'] else 'hidden'}, "
                f"render={'shown' if result['render_visible'] else 'hidden'} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def list_shape_keys(name: str) -> str:
    """
    List an object's shape keys (morph targets) and their current values — facial
    expressions, correctives, blendshapes. Read-only.

    Example: list_shape_keys("face_mesh")
    """
    result = call_blender("list_shape_keys", {"name": name})
    if not result.get("success"):
        return result.get("error", "failed")
    keys = result.get("shape_keys", [])
    if not keys:
        return f"{name}: no shape keys"
    lines = [f"{name}: {result['count']} shape key(s)"]
    for k in keys:
        lines.append(f"  {k['name']} = {k['value']}  (range {k['min']}..{k['max']})")
    return "\n".join(lines)


@mcp.tool()
def set_shape_key(name: str, key: str, value: float, label: str = "") -> str:
    """
    Set a shape key's value (0..1 typical) to drive a morph/corrective.

    Example: set_shape_key("face_mesh", "smile", 0.8)
    """
    result = call_blender("set_shape_key", {"name": name, "key": key, "value": value},
                          label=label)
    if result.get("success"):
        main = f"set {name} shape key '{result['key']}' = {result['value']} [{result.get('op_id','')}]"
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

"""Groups = Blender collections. group/parts_in/ungroup."""

import bpy


def group(params):
    """Create a named collection containing the given parts (and any existing children).
    Operations that accept 'targets' can be given a group name to act on all members."""
    name = params.get("name")
    parts = params.get("parts", [])
    if not name:
        return {"error": "'name' is required"}
    if not isinstance(parts, list) or not parts:
        return {"error": "'parts' must be a non-empty list of object names"}

    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)

    added = []
    for p in parts:
        obj = bpy.data.objects.get(p)
        if obj is None:
            return {"error": f"Object '{p}' not found"}
        if obj.name not in coll.objects:
            coll.objects.link(obj)
            added.append(p)
        if obj.name in bpy.context.scene.collection.objects:
            try:
                bpy.context.scene.collection.objects.unlink(obj)
            except Exception:
                pass
    return {"success": True, "group": name, "members": [o.name for o in coll.objects],
            "newly_added": added}


def add_to_group(params):
    """Add objects (or members of another group) to an existing group.
    Use this as the design grows so the group always represents the whole thing —
    so 'delete chest' or 'nudge chest' acts on every part, not just the originals."""
    name = params.get("name")
    parts = params.get("parts", [])
    if not name:
        return {"error": "'name' is required"}
    if not isinstance(parts, list) or not parts:
        return {"error": "'parts' must be a non-empty list of object or group names"}
    coll = bpy.data.collections.get(name)
    if coll is None:
        return {"error": f"Group '{name}' not found — use 'group' to create it first"}

    to_add = []
    for p in parts:
        obj = bpy.data.objects.get(p)
        sub = bpy.data.collections.get(p)
        if obj is None and sub is None:
            return {"error": f"'{p}' is neither an object nor a group"}
        if obj is not None:
            to_add.append(obj)
        if sub is not None:
            to_add.extend(sub.all_objects)

    added = []
    for o in to_add:
        if o.name not in coll.objects:
            coll.objects.link(o)
            added.append(o.name)
        if o.name in bpy.context.scene.collection.objects:
            try:
                bpy.context.scene.collection.objects.unlink(o)
            except Exception:
                pass
    return {"success": True, "group": name, "newly_added": added,
            "members": [o.name for o in coll.objects]}


def parts_in(params):
    """List the parts inside a named group (collection)."""
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    coll = bpy.data.collections.get(name)
    if coll is None:
        return {"error": f"Group '{name}' not found"}
    return {"success": True, "group": name, "parts": [o.name for o in coll.all_objects]}


def ungroup(params):
    """Remove a group (collection) — its objects move back to the scene root, they are NOT deleted."""
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    coll = bpy.data.collections.get(name)
    if coll is None:
        return {"error": f"Group '{name}' not found"}
    members = [o.name for o in coll.all_objects]
    for o in list(coll.objects):
        if o.name not in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.link(o)
        coll.objects.unlink(o)
    bpy.data.collections.remove(coll)
    return {"success": True, "removed_group": name, "members_freed": members}


TOOLS = {
    "group":        group,
    "add_to_group": add_to_group,
    "parts_in":     parts_in,
    "ungroup":      ungroup,
}

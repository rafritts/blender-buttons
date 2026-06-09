"""Groups = Blender collections. group/parts_in/ungroup."""

import bpy


def group(params):
    """Create a named collection containing the given parts.
    Parts may be object names or other group names — groups become nested
    sub-collections. Operations that accept 'targets' get all members recursively."""
    name = params.get("name")
    parts = params.get("parts", [])
    if not name:
        return {"error": "'name' is required"}
    if not isinstance(parts, list) or not parts:
        return {"error": "'parts' must be a non-empty list of object or group names"}

    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)

    added = []
    for p in parts:
        if p == name:
            return {"error": f"Cannot nest group '{name}' inside itself"}
        obj = bpy.data.objects.get(p)
        sub = bpy.data.collections.get(p)
        if obj is None and sub is None:
            return {"error": f"'{p}' is neither an object nor a group"}
        if obj is not None and obj.name not in coll.objects:
            coll.objects.link(obj)
            added.append(p)
            if obj.name in bpy.context.scene.collection.objects:
                try:
                    bpy.context.scene.collection.objects.unlink(obj)
                except Exception:
                    pass
        if sub is not None and sub.name not in {c.name for c in coll.children}:
            try:
                bpy.context.scene.collection.children.unlink(sub)
            except Exception:
                pass
            coll.children.link(sub)
            added.append(p)
    return {"success": True, "group": name,
            "members": [o.name for o in coll.all_objects],
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

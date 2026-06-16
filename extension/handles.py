"""Handles — named spatial anchors backed by native Blender datablocks (SPEC-07).

Phase 1: mint + see. A handle IS a Blender object — an **Empty** in a dedicated
`Handles` collection (visible in the Outliner, selectable / renamable / deletable
with native tools) plus a `HANDLE_<name>` **vertex group** on the owning mesh
(Blender's native "named set of verts"). Provenance lives in the Empty's custom
properties. The "registry" is a read-model over these datablocks (`list_handles`
scans the collection) — there is no parallel server-side store.

No drift / recompute / signatures yet — that's Phase 3. This is just: read the
current edit-mode selection, snapshot it as an Empty + vgroup, name it, show it,
delete it natively. The smallest tryable loop: select → save → see it.

`mint_from_active_selection` is the shared core — both the socket tool
(`mint_handle`) and the addon's right-click `Save as Handle` operator call it, so
human-made and agent-made handles are identical citizens.
"""

import bpy
from mathutils import Vector

HANDLES_COLLECTION = "Handles"
VGROUP_PREFIX = "HANDLE_"


def _handles_collection():
    """The `Handles` collection, created and linked to the scene on first use."""
    coll = bpy.data.collections.get(HANDLES_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(HANDLES_COLLECTION)
        bpy.context.scene.collection.children.link(coll)
    return coll


def mint_from_active_selection(name=""):
    """Snapshot the active mesh's current edit-mode vertex selection as a handle.

    Returns a result dict (`success` / `error`). Callable from both the socket
    dispatcher and the `Save as Handle` operator — one code path, identical output.

    name: handle name. Empty → auto-named `handle`/`handle.001`-style by Blender's
          own object-name uniqueing. The `HANDLE_<name>` vgroup is keyed to the
          Empty's FINAL (possibly suffixed) name, so the two stay in sync at mint.
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "active object is not a mesh — select a mesh and enter edit mode"}
    if obj.mode != 'EDIT':
        return {"error": "must be in edit mode with a vertex selection to mint a handle"}

    bm = bmesh.from_edit_mesh(obj.data)
    # Read geometry (position/normal/select) first — no deform layer needed yet.
    sel = [v for v in bm.verts if v.select]
    if not sel:
        return {"error": "no vertices selected — select the geometry to anchor first"}

    mw = obj.matrix_world
    world = [mw @ v.co for v in sel]
    n = len(world)
    centroid = Vector((
        sum(p.x for p in world) / n,
        sum(p.y for p in world) / n,
        sum(p.z for p in world) / n,
    ))
    nrm = Vector((0.0, 0.0, 0.0))
    for v in sel:
        nrm += (mw.to_3x3() @ v.normal)
    nrm = nrm.normalized() if nrm.length > 1e-9 else Vector((0.0, 0.0, 1.0))

    # Empty marks the resolved point; Blender auto-suffixes a duplicate name (.001).
    empty = bpy.data.objects.new(name.strip() or "handle", None)
    empty.empty_display_type = 'ARROWS'
    empty.empty_display_size = 0.05
    empty.location = centroid
    empty.rotation_euler = nrm.to_track_quat('Z', 'Y').to_euler()
    _handles_collection().objects.link(empty)

    # Vertex group keyed to the Empty's FINAL name, so they stay paired. Create the
    # group BEFORE verify()-ing the deform layer (so the layer includes it) and
    # re-collect the selection AFTER — verify() can reallocate and invalidate the
    # BMVerts gathered above (the assign_weight caveat).
    vgname = f"{VGROUP_PREFIX}{empty.name}"
    vg = obj.vertex_groups.new(name=vgname)
    deform = bm.verts.layers.deform.verify()
    gi = vg.index
    for v in bm.verts:
        if v.select:
            v[deform][gi] = 1.0
    bmesh.update_edit_mesh(obj.data)

    # Provenance in custom properties (the source of truth Phase 3 will recompute from).
    empty["bb_handle"] = True
    empty["bb_kind"] = "selection"
    empty["bb_owner"] = obj.name
    empty["bb_vgroup"] = vgname
    empty["bb_vert_count"] = n
    empty["bb_normal"] = [round(c, 4) for c in nrm]

    return {
        "success": True,
        "name": empty.name,
        "kind": "selection",
        "owner": obj.name,
        "vgroup": vgname,
        "vert_count": n,
        "point": [round(c, 5) for c in centroid],
        "normal": [round(c, 4) for c in nrm],
    }


def mint_handle(params):
    """Mint a handle from the active mesh's current edit-mode selection (SPEC-07 P1).

    name:   handle name (optional — auto-named if empty).
    source: addressing mode. Phase 1 supports only `selection` (the live edit-mode
            vertex selection). `aim` / `boundary` / `point` land in later phases.
    """
    source = str(params.get("source") or "selection").lower().strip()
    if source != "selection":
        return {"error": f"only source=selection is supported in Phase 1 (got '{source}')"}
    return mint_from_active_selection(params.get("name", ""))


def list_handles(params):
    """List every handle by scanning the `Handles` collection — the read-model.

    The collection IS the registry; there is no separate store to drift from it.
    A handle's resolved point is the Empty's current world location (Phase 1: the
    frozen mint point — depsgraph tracking / recompute arrives in Phase 3)."""
    coll = bpy.data.collections.get(HANDLES_COLLECTION)
    handles = []
    if coll is not None:
        for o in coll.objects:
            if not o.get("bb_handle"):
                continue
            loc = o.matrix_world.translation
            handles.append({
                "name": o.name,
                "kind": o.get("bb_kind", "?"),
                "owner": o.get("bb_owner", "?"),
                "vgroup": o.get("bb_vgroup", ""),
                "vert_count": o.get("bb_vert_count", 0),
                "point": [round(c, 5) for c in loc],
            })
    handles.sort(key=lambda h: h["name"])
    return {"success": True, "count": len(handles), "handles": handles}


TOOLS = {
    "mint_handle":  mint_handle,
    "list_handles": list_handles,
}

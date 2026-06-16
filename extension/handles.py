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


def _find_handle(name):
    """The handle Empty by name, or None. Scans the `Handles` collection."""
    coll = bpy.data.collections.get(HANDLES_COLLECTION)
    if coll is None:
        return None
    o = coll.objects.get(name)
    return o if (o is not None and o.get("bb_handle")) else None


def _resolve_vgroup(obj, vgname):
    """Recompute (centroid, normal, n) in WORLD space from the named vertex group
    against current CAGE geometry — so the point survives a mesh edit instead of
    going stale. Returns (None, None, 0) when the group is gone or empty (the
    unresolvable case; Phase 3 names it 'orphaned'). Reads the live bmesh when the
    owning mesh is in edit mode (its `data.vertices` would be stale), else the cage.
    Pose/deform tracking (evaluated mesh) is Phase 3."""
    if obj is None or obj.type != 'MESH':
        return None, None, 0
    vg = obj.vertex_groups.get(vgname)
    if vg is None:
        return None, None, 0
    gi = vg.index
    mw = obj.matrix_world
    nm = mw.to_3x3()
    cos, nrms = [], []
    if obj.mode == 'EDIT':
        import bmesh
        bm = bmesh.from_edit_mesh(obj.data)
        deform = bm.verts.layers.deform.verify()
        for v in bm.verts:
            if gi in v[deform]:
                cos.append(mw @ v.co)
                nrms.append(nm @ v.normal)
    else:
        for v in obj.data.vertices:
            if any(g.group == gi for g in v.groups):
                cos.append(mw @ v.co)
                nrms.append(nm @ v.normal)
    if not cos:
        return None, None, 0
    n = len(cos)
    centroid = Vector((
        sum(c.x for c in cos) / n,
        sum(c.y for c in cos) / n,
        sum(c.z for c in cos) / n,
    ))
    nrm = Vector((0.0, 0.0, 0.0))
    for nv in nrms:
        nrm += nv
    nrm = nrm.normalized() if nrm.length > 1e-9 else Vector((0.0, 0.0, 1.0))
    return centroid, nrm, n


def resolve_handle(params):
    """Resolve a handle to its LIVE world point + normal (SPEC-07 Phase 2).

    Recomputes from the `HANDLE_<name>` vertex group against current geometry —
    NOT the frozen mint point — so consuming a handle after a mesh edit lands on
    where the feature is now. Read-only."""
    name = params.get("name")
    empty = _find_handle(name)
    if empty is None:
        return {"error": f"handle '{name}' not found in the Handles collection"}
    owner = bpy.data.objects.get(empty.get("bb_owner", ""))
    vgname = empty.get("bb_vgroup", "")
    point, normal, n = _resolve_vgroup(owner, vgname)
    if point is None:
        return {"error": f"handle '{name}' is unresolvable — its vertex group "
                         f"'{vgname}' is gone or empty (re-mint or discard it)"}
    return {
        "success": True,
        "name": name,
        "owner": owner.name,
        "point": [round(c, 5) for c in point],
        "normal": [round(c, 4) for c in normal],
        "vert_count": n,
    }


def list_handles(params):
    """List every handle by scanning the `Handles` collection — the read-model.

    The collection IS the registry; there is no separate store to drift from it.
    Each handle's `point` is RESOLVED live from its vertex group (Phase 2), so the
    list reflects current geometry, not the frozen mint location of the Empty."""
    coll = bpy.data.collections.get(HANDLES_COLLECTION)
    handles = []
    if coll is not None:
        for o in coll.objects:
            if not o.get("bb_handle"):
                continue
            owner = bpy.data.objects.get(o.get("bb_owner", ""))
            vgname = o.get("bb_vgroup", "")
            point, _normal, n = _resolve_vgroup(owner, vgname)
            resolved = point is not None
            handles.append({
                "name": o.name,
                "kind": o.get("bb_kind", "?"),
                "owner": o.get("bb_owner", "?"),
                "vgroup": vgname,
                "vert_count": n if resolved else o.get("bb_vert_count", 0),
                "point": [round(c, 5) for c in point] if resolved else None,
                "resolved": resolved,
            })
    handles.sort(key=lambda h: h["name"])
    return {"success": True, "count": len(handles), "handles": handles}


TOOLS = {
    "mint_handle":    mint_handle,
    "list_handles":   list_handles,
    "resolve_handle": resolve_handle,
}

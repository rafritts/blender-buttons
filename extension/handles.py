"""Handles — named spatial anchors backed by native Blender datablocks (SPEC-07).

A handle IS a Blender object — an **Empty** in a dedicated `Handles` collection
(visible in the Outliner, selectable / renamable / deletable with native tools)
plus a `HANDLE_<name>` **vertex group** on the owning mesh (Blender's native
"named set of verts"). Provenance lives in the Empty's custom properties. The
"registry" is a read-model over these datablocks (`list_handles` scans the
collection) — there is no parallel server-side store.

Phase 1 minted + showed; Phase 2 resolved + consumed. **Phase 3 — integrity:**
a handle stores not just its point but a *provenance snapshot* at mint, and on
list/consume it recomputes from that provenance and **diffs**, reporting one of
three git-style states:

  • clean    — recompute matches the snapshot (within ε); use silently.
  • dirty    — geometry moved under it beyond ε but the feature still resolves;
               flagged with TWO rigid-invariant drift signals kept diagnostically
               apart — `deform` (intrinsic: its own shape changed) and `place`
               (extrinsic: it slid relative to its fiducial neighbours) — plus
               *attribution* (self = an agent op explains it; external = the human
               or a side-effect moved it, the loud alarm).
  • orphaned — provenance won't replay (vgroup gone, or verts added/deleted);
               can't resolve, must re-derive or discard.

`feel op=accept` re-baselines a dirty handle (stage the drift → clean again).
An opt-in `vertex_parent` rides the Empty on its mesh's deform via the depsgraph,
so the marker visibly tracks pose (the vgroup recompute stays the source of truth).

`mint_from_active_selection` is the shared core — both the socket tool
(`mint_handle`) and the addon's right-click `Save as Handle` operator call it, so
human-made and agent-made handles are identical citizens.
"""

import json

import bpy
from mathutils import Vector

HANDLES_COLLECTION = "Handles"
VGROUP_PREFIX = "HANDLE_"

# Drift threshold. Absolute metres — a handle whose recompute moves less than this
# (in either signature) reads clean. 1 mm is tight at character scale; the spec
# leaves ε a knob (absolute vs handle-relative), and absolute-mm is the simple start.
DRIFT_EPS = 0.001

_ISAMPLE = 32   # intrinsic signature is bounded to this many vert-to-centroid distances
_FID_K = 3      # extrinsic signature keeps distances to the k nearest neighbour handles

# Registry ops never count as "geometry touched" for attribution — minting/accepting
# a handle writes a vgroup + props but moves no verts. `feel_assembly` auto-mints
# boundary handles the same way, so it's excluded too (else it would falsely mark
# its own target meshes as agent-touched).
_HANDLE_TOOLS = {"mint_handle", "list_handles", "resolve_handle", "accept_handle",
                 "feel_assembly"}


def _handles_collection():
    """The `Handles` collection, created and linked to the scene on first use."""
    coll = bpy.data.collections.get(HANDLES_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(HANDLES_COLLECTION)
        bpy.context.scene.collection.children.link(coll)
    return coll


# ── geometry primitives over a vertex group ──────────────────────────────────

def _vgroup_geo(obj, vgname):
    """World-space (cos, normals) of the named vgroup's verts; ([], []) when the
    group is gone or empty. Reads the live bmesh when the owning mesh is in edit
    mode (its `data.vertices` would be stale), else the cage. Pose/deform tracking
    (evaluated mesh) is left to the optional vertex-parent — the vgroup recompute
    here is the integrity source of truth."""
    if obj is None or obj.type != 'MESH':
        return [], []
    vg = obj.vertex_groups.get(vgname)
    if vg is None:
        return [], []
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
    return cos, nrms


def _centroid(cos):
    n = len(cos)
    return Vector((sum(c.x for c in cos) / n,
                   sum(c.y for c in cos) / n,
                   sum(c.z for c in cos) / n))


def _avg_normal(nrms):
    nrm = Vector((0.0, 0.0, 0.0))
    for nv in nrms:
        nrm += nv
    return nrm.normalized() if nrm.length > 1e-9 else Vector((0.0, 0.0, 1.0))


def _resolve_vgroup(obj, vgname):
    """Recompute (centroid, normal, n) in WORLD space, or (None, None, 0) if the
    group is gone/empty. The Phase 2 resolver — kept thin over `_vgroup_geo`."""
    cos, nrms = _vgroup_geo(obj, vgname)
    if not cos:
        return None, None, 0
    return _centroid(cos), _avg_normal(nrms), len(cos)


# ── the two rigid-invariant drift signatures ─────────────────────────────────

def _intrinsic_sig(cos, centroid):
    """**Shape** signature: the sorted set of vert-to-centroid distances, bounded to
    _ISAMPLE samples. Distances to the centroid are invariant under rigid motion
    (translate/rotate) by construction, so a change here means the region itself
    *deformed* (got squished/stretched) — not that it merely moved."""
    dists = sorted((c - centroid).length for c in cos)
    if len(dists) > _ISAMPLE:
        step = len(dists) / _ISAMPLE
        dists = [dists[int(i * step)] for i in range(_ISAMPLE)]
    return [round(d, 5) for d in dists]


def _fiducials(my_centroid, exclude_name):
    """**Place** signature: distances from this handle's centroid to its _FID_K
    nearest *provenance-backed* neighbour handles, as {name: distance}. On validate
    these neighbours self-resolve and the distances are re-diffed — catching a rigid
    *displacement* (the handle slid as a whole) that the intrinsic check can't see,
    while staying invariant to a whole-scene rigid move (every distance unchanged)."""
    coll = bpy.data.collections.get(HANDLES_COLLECTION)
    cand = []
    if coll is not None:
        for o in coll.objects:
            if not o.get("bb_handle") or o.name == exclude_name:
                continue
            owner = bpy.data.objects.get(o.get("bb_owner", ""))
            c, _n, _k = _resolve_vgroup(owner, o.get("bb_vgroup", ""))
            if c is None:
                continue
            cand.append((o.name, (c - my_centroid).length))
    cand.sort(key=lambda t: t[1])
    return {nm: round(d, 5) for nm, d in cand[:_FID_K]}


def _snapshot_provenance(empty, centroid, normal, cos, n, name):
    """Write the integrity snapshot the validate path diffs against — the mint point,
    both signatures, and the op-log mark for attribution. Shared by mint and accept."""
    from . import state
    empty["bb_vert_count"] = n
    empty["bb_normal"] = [round(c, 4) for c in normal]
    empty["bb_mint_point"] = [round(c, 5) for c in centroid]
    empty["bb_intrinsic"] = json.dumps(_intrinsic_sig(cos, centroid))
    empty["bb_extrinsic"] = json.dumps(_fiducials(centroid, name))
    # Attribution baseline: ops logged from here on are candidates for "self" drift.
    empty["bb_mint_op_count"] = len(state._history)


# ── mint ─────────────────────────────────────────────────────────────────────

def mint_from_active_selection(name="", vertex_parent=False):
    """Snapshot the active mesh's current edit-mode vertex selection as a handle.

    Returns a result dict (`success` / `error`). Callable from both the socket
    dispatcher and the `Save as Handle` operator — one code path, identical output.

    name: handle name. Empty → auto-named `handle`/`handle.001`-style by Blender's
          own object-name uniqueing. The `HANDLE_<name>` vgroup is keyed to the
          Empty's FINAL (possibly suffixed) name, so the two stay in sync at mint.
    vertex_parent: opt-in — parent the Empty to a tracking vert (its nearest-centroid
          one) so Blender's depsgraph rides it through pose/deform for free. The
          vgroup recompute stays the source of truth; this is the visible marker.
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "active object is not a mesh — select a mesh and enter edit mode"}
    if obj.mode != 'EDIT':
        return {"error": "must be in edit mode with a vertex selection to mint a handle"}

    bm = bmesh.from_edit_mesh(obj.data)
    sel = [v for v in bm.verts if v.select]
    if not sel:
        return {"error": "no vertices selected — select the geometry to anchor first"}

    mw = obj.matrix_world
    world = [mw @ v.co for v in sel]
    n = len(world)
    centroid = _centroid(world)
    nrm = Vector((0.0, 0.0, 0.0))
    for v in sel:
        nrm += (mw.to_3x3() @ v.normal)
    nrm = nrm.normalized() if nrm.length > 1e-9 else Vector((0.0, 0.0, 1.0))

    # Capture the tracking-anchor index BEFORE any verify()/update — BMVert refs
    # can be reallocated by the deform-layer verify below, but vert *indices* are
    # stable across this position-preserving edit.
    anchor_index = min(sel, key=lambda v: (mw @ v.co - centroid).length).index

    # Empty marks the resolved point; Blender auto-suffixes a duplicate name (.001).
    empty = bpy.data.objects.new(name.strip() or "handle", None)
    empty.empty_display_type = 'ARROWS'
    empty.empty_display_size = 0.05
    empty.location = centroid
    empty.rotation_euler = nrm.to_track_quat('Z', 'Y').to_euler()
    _handles_collection().objects.link(empty)

    # Vertex group keyed to the Empty's FINAL name. Create it BEFORE verify()-ing the
    # deform layer (so the layer includes it) and iterate `bm.verts` fresh for the
    # assignment — verify() can reallocate the BMVerts gathered above (assign_weight
    # caveat).
    vgname = f"{VGROUP_PREFIX}{empty.name}"
    vg = obj.vertex_groups.new(name=vgname)
    vgname = vg.name  # Blender suffixes .001 on collision with an orphaned vgroup
                      # (a deleted handle leaves its group behind — G15); track the
                      # ACTUAL name so bb_vgroup never points at the stale leftover.
    deform = bm.verts.layers.deform.verify()
    gi = vg.index
    for v in bm.verts:
        if v.select:
            v[deform][gi] = 1.0
    bmesh.update_edit_mesh(obj.data)

    # Provenance: identity + Phase-3 integrity snapshot.
    empty["bb_handle"] = True
    empty["bb_kind"] = "selection"
    empty["bb_owner"] = obj.name
    empty["bb_vgroup"] = vgname
    _snapshot_provenance(empty, centroid, nrm, world, n, empty.name)

    if vertex_parent:
        # Single-vertex parent to the tracking anchor: the marker sits on that vert
        # and rides any deform. parent_vertices is a fixed 3-int array; for type
        # 'VERTEX' only the first is used. Identity inverse + zero location → the
        # Empty lands exactly on the vert.
        empty.parent = obj
        empty.parent_type = 'VERTEX'
        empty.parent_vertices = (anchor_index, anchor_index, anchor_index)
        empty.matrix_parent_inverse.identity()
        empty.location = (0.0, 0.0, 0.0)
        empty["bb_vertex_parent"] = True
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass

    return {
        "success": True,
        "name": empty.name,
        "kind": "selection",
        "owner": obj.name,
        "vgroup": vgname,
        "vert_count": n,
        "point": [round(c, 5) for c in centroid],
        "normal": [round(c, 4) for c in nrm],
        "vertex_parent": bool(vertex_parent),
    }


def _newell_normal(cos, centroid, outward_from=None):
    """Newell's plane normal of an ordered loop polygon (world space) — the axis
    *through* the opening, unlike the average vert normal which lies along the
    surface near the rim. Oriented to point away from `outward_from` (the owner's
    centre) so a boundary handle's arrow reads 'out through the hole'."""
    nrm = Vector((0.0, 0.0, 0.0))
    m = len(cos)
    for i in range(m):
        a, b = cos[i], cos[(i + 1) % m]
        nrm.x += (a.y - b.y) * (a.z + b.z)
        nrm.y += (a.z - b.z) * (a.x + b.x)
        nrm.z += (a.x - b.x) * (a.y + b.y)
    nrm = nrm.normalized() if nrm.length > 1e-9 else Vector((0.0, 0.0, 1.0))
    if outward_from is not None and nrm.dot(centroid - outward_from) < 0:
        nrm = -nrm
    return nrm


def _vgroup_vertset(obj, vgname):
    """The set of vertex indices in a vgroup (OBJECT-mode read). Used to dedupe
    auto-minted boundary handles — two mints of the same loop share a vert-set."""
    if obj is None or obj.type != 'MESH':
        return frozenset()
    vg = obj.vertex_groups.get(vgname)
    if vg is None:
        return frozenset()
    gi = vg.index
    return frozenset(v.index for v in obj.data.vertices
                     if any(g.group == gi for g in v.groups))


def find_handle_by_vertset(owner_name, indices):
    """An existing handle on `owner_name` whose vgroup is exactly this vert-set, or
    None. The idempotency key for auto-mint: re-reading an assembly must reuse the
    boundary handles it already minted, not spawn `.001` duplicates."""
    coll = bpy.data.collections.get(HANDLES_COLLECTION)
    if coll is None:
        return None
    owner = bpy.data.objects.get(owner_name)
    target = frozenset(int(i) for i in indices)
    for o in coll.objects:
        if not o.get("bb_handle") or o.get("bb_owner") != owner_name:
            continue
        if _vgroup_vertset(owner, o.get("bb_vgroup", "")) == target:
            return o.name
    return None


def mint_from_vert_indices(obj, indices, name, kind="boundary"):
    """Mint a handle from an explicit vert-index set on `obj` (OBJECT mode) — the
    auto-mint path for Class-A structural features (boundary loops) that perception
    finds, where there's no live edit-mode selection to read. The vgroup is assigned
    directly by index via the object-mode API (no bmesh deform-layer dance), and the
    handle normal is the loop's plane normal (the axis through the opening).

    Returns the same result shape as `mint_from_active_selection`. Callers that want
    idempotency should go through `mint_boundary_handle`."""
    if obj is None or obj.type != 'MESH':
        return {"error": "owner is not a mesh"}
    if obj.mode == 'EDIT':
        return {"error": f"'{obj.name}' is in edit mode — exit to object mode to auto-mint"}
    indices = list(dict.fromkeys(int(i) for i in indices))   # dedup, preserve order
    if not indices:
        return {"error": "no vertices to anchor"}

    mw = obj.matrix_world
    world = [mw @ obj.data.vertices[i].co for i in indices]
    n = len(world)
    centroid = _centroid(world)
    owner_center = sum((mw @ Vector(c) for c in obj.bound_box), Vector()) / 8.0
    nrm = _newell_normal(world, centroid, owner_center)

    empty = bpy.data.objects.new(name.strip() or "handle", None)
    empty.empty_display_type = 'ARROWS'
    empty.empty_display_size = 0.05
    empty.location = centroid
    empty.rotation_euler = nrm.to_track_quat('Z', 'Y').to_euler()
    _handles_collection().objects.link(empty)

    vgname = f"{VGROUP_PREFIX}{empty.name}"
    vg = obj.vertex_groups.new(name=vgname)
    vgname = vg.name  # see mint_from_active_selection: a .001 suffix on collision with
                      # an orphaned leftover vgroup (G15) must not desync bb_vgroup.
    vg.add(indices, 1.0, 'REPLACE')

    empty["bb_handle"] = True
    empty["bb_kind"] = kind
    empty["bb_owner"] = obj.name
    empty["bb_vgroup"] = vgname
    _snapshot_provenance(empty, centroid, nrm, world, n, empty.name)

    return {
        "success": True, "name": empty.name, "kind": kind, "owner": obj.name,
        "vgroup": vgname, "vert_count": n,
        "point": [round(c, 5) for c in centroid],
        "normal": [round(c, 4) for c in nrm],
    }


def mint_boundary_handle(obj, indices, base_name):
    """Idempotent Class-A auto-mint: reuse an existing handle on the same vert-set,
    else mint a fresh one. Returns a dict with `name` and `reused` (bool)."""
    existing = find_handle_by_vertset(obj.name, indices)
    if existing is not None:
        return {"success": True, "name": existing, "reused": True}
    res = mint_from_vert_indices(obj, indices, base_name, kind="boundary")
    if res.get("success"):
        res["reused"] = False
    return res


def mint_handle(params):
    """Mint a handle from the active mesh's current edit-mode selection (SPEC-07).

    name:   handle name (optional — auto-named if empty).
    source: addressing mode. Only `selection` (the live edit-mode vertex selection)
            so far; `aim` / `boundary` / `point` land in later phases.
    vertex_parent: opt-in deform tracking (see mint_from_active_selection).
    """
    source = str(params.get("source") or "selection").lower().strip()
    if source != "selection":
        return {"error": f"only source=selection is supported so far (got '{source}')"}
    return mint_from_active_selection(params.get("name", ""),
                                      bool(params.get("vertex_parent")))


def _find_handle(name):
    """The handle Empty by name, or None. Scans the `Handles` collection."""
    coll = bpy.data.collections.get(HANDLES_COLLECTION)
    if coll is None:
        return None
    o = coll.objects.get(name)
    return o if (o is not None and o.get("bb_handle")) else None


# ── validate: git-style state + drift + attribution ──────────────────────────

def _max_sig_diff(a, b):
    """Max abs element-wise diff of two equal-length signatures (None if mismatched)."""
    if len(a) != len(b):
        return None
    return max((abs(x - y) for x, y in zip(a, b)), default=0.0)


def _attribution(empty):
    """On detected drift, ask *who*: intersect the handle's dependency mesh (its
    owner) with the meshes agent ops touched since mint (the G12 op-log). Explained
    by an agent op → 'self'; nothing the agent did → 'external' (the human moved it)."""
    from . import state
    owner = empty.get("bb_owner", "")
    start = int(empty.get("bb_mint_op_count", 0) or 0)
    touched = set()
    for entry in state._history[start:]:
        if entry.get("tool") in _HANDLE_TOOLS:
            continue
        a = entry.get("active")
        if a:
            touched.add(a)
        p = entry.get("params") or {}
        for key in ("targets", "name", "mesh", "object"):
            val = p.get(key)
            if isinstance(val, str):
                for nm in val.split(","):
                    nm = nm.strip()
                    if nm:
                        touched.add(nm)
    return "self" if owner in touched else "external"


def _validate(empty):
    """Recompute the handle from provenance and diff the snapshot → git-style state.

    Returns a dict: state (clean|dirty|orphaned), point (live centroid or None),
    vert_count, deform + place drift (metres), fiducial (whether place used
    neighbours), and — only when dirty — attribution (self|external)."""
    owner = bpy.data.objects.get(empty.get("bb_owner", ""))
    vgname = empty.get("bb_vgroup", "")
    cos, nrms = _vgroup_geo(owner, vgname)
    mint_n = int(empty.get("bb_vert_count", 0) or 0)

    if not cos:
        return {"state": "orphaned", "reason": "vertex group gone or empty",
                "point": None, "vert_count": 0, "deform": 0.0, "place": 0.0}
    n = len(cos)
    if n != mint_n:
        return {"state": "orphaned",
                "reason": f"vert count changed {mint_n}→{n} (verts added or deleted)",
                "point": None, "vert_count": n, "deform": 0.0, "place": 0.0}

    centroid = _centroid(cos)

    # deform (intrinsic) — its own shape vs the mint snapshot
    try:
        mint_intr = json.loads(empty.get("bb_intrinsic") or "[]")
    except Exception:
        mint_intr = []
    deform = _max_sig_diff(mint_intr, _intrinsic_sig(cos, centroid)) if mint_intr else 0.0
    if deform is None:
        deform = 0.0

    # place (extrinsic) — fiducial distances to neighbours; fall back to absolute
    # displacement from the mint point when no neighbours existed/survive (e.g. the
    # first/only handle in the scene).
    try:
        mint_fid = json.loads(empty.get("bb_extrinsic") or "{}")
    except Exception:
        mint_fid = {}
    fid_diffs = []
    for nm, d0 in mint_fid.items():
        nb = _find_handle(nm)
        if nb is None:
            continue
        c, _n, _k = _resolve_vgroup(bpy.data.objects.get(nb.get("bb_owner", "")),
                                    nb.get("bb_vgroup", ""))
        if c is None:
            continue
        fid_diffs.append(abs((centroid - c).length - d0))
    if fid_diffs:
        place = max(fid_diffs)
        used_fid = True
    else:
        mp = empty.get("bb_mint_point")
        place = (centroid - Vector(tuple(mp))).length if mp is not None else 0.0
        used_fid = False

    drift = max(deform, place)
    out = {"state": "dirty" if drift > DRIFT_EPS else "clean",
           "point": [round(c, 5) for c in centroid], "vert_count": n,
           "normal": _avg_normal(nrms), "deform": round(deform, 5),
           "place": round(place, 5), "fiducial": used_fid}
    if out["state"] == "dirty":
        out["attribution"] = _attribution(empty)
    return out


def resolve_handle(params):
    """Resolve a handle to its LIVE world point + normal, with its Phase-3 integrity
    state. Recomputes from the vgroup against current geometry (not the frozen mint
    point), so consuming lands on where the feature is now. Orphaned → error;
    dirty → resolves AND carries the drift/attribution flags for the consumer to
    surface. Read-only."""
    name = params.get("name")
    empty = _find_handle(name)
    if empty is None:
        return {"error": f"handle '{name}' not found in the Handles collection"}
    v = _validate(empty)
    if v["state"] == "orphaned":
        return {"error": f"handle '{name}' is orphaned — {v.get('reason')}; "
                         f"re-derive or discard it"}
    return {
        "success": True, "name": name, "owner": empty.get("bb_owner", ""),
        "point": v["point"], "normal": [round(c, 4) for c in v["normal"]],
        "vert_count": v["vert_count"], "state": v["state"],
        "deform": v["deform"], "place": v["place"], "fiducial": v["fiducial"],
        "attribution": v.get("attribution"),
    }


def accept_handle(params):
    """Re-baseline a handle: re-snapshot its provenance (mint point + both signatures
    + op-log mark) from current geometry, clearing any drift. The 'stage it' move —
    accept that the anchor's new position IS where you want it. Metadata only."""
    name = params.get("name")
    empty = _find_handle(name)
    if empty is None:
        return {"error": f"handle '{name}' not found in the Handles collection"}
    owner = bpy.data.objects.get(empty.get("bb_owner", ""))
    vgname = empty.get("bb_vgroup", "")
    cos, nrms = _vgroup_geo(owner, vgname)
    if not cos:
        return {"error": f"handle '{name}' is unresolvable — its vertex group "
                         f"'{vgname}' is gone or empty (re-mint or discard it)"}
    centroid = _centroid(cos)
    _snapshot_provenance(empty, centroid, _avg_normal(nrms), cos, len(cos), name)
    if not empty.get("bb_vertex_parent"):
        empty.location = centroid  # re-place the free-standing marker on the feature
    return {"success": True, "name": name, "point": [round(c, 5) for c in centroid],
            "vert_count": len(cos), "state": "clean"}


def list_handles(params):
    """List every handle by scanning the `Handles` collection — the read-model.

    Each handle is VALIDATED (Phase 3): point resolved live from its vgroup, plus its
    git-style state, drift signals, and attribution. The collection IS the registry;
    there is no separate store to drift from it."""
    coll = bpy.data.collections.get(HANDLES_COLLECTION)
    handles = []
    if coll is not None:
        for o in coll.objects:
            if not o.get("bb_handle"):
                continue
            v = _validate(o)
            handles.append({
                "name": o.name, "kind": o.get("bb_kind", "?"),
                "owner": o.get("bb_owner", "?"), "vgroup": o.get("bb_vgroup", ""),
                "vert_count": v["vert_count"] if v["point"] is not None
                else int(o.get("bb_vert_count", 0) or 0),
                "point": v["point"], "state": v["state"],
                "deform": v["deform"], "place": v["place"],
                "attribution": v.get("attribution"), "reason": v.get("reason"),
                "vertex_parent": bool(o.get("bb_vertex_parent")),
            })
    handles.sort(key=lambda h: h["name"])
    return {"success": True, "count": len(handles), "handles": handles}


TOOLS = {
    "mint_handle":    mint_handle,
    "list_handles":   list_handles,
    "resolve_handle": resolve_handle,
    "accept_handle":  accept_handle,
}

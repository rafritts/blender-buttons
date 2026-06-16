"""assembly — multi-object perception (SPEC-07 Phase 4, "multi-feel").

`feel` reads one mesh deeply; assembly reads the relationships *between* meshes —
the cross-object axis character work is irreducibly about. Two ops:

  • `feel op=assembly` — one read over a SET of objects (or a collection): per-object
    size, each object's open **boundary loops** (the catalog: verts, circumference,
    region), and the pairwise **gaps** between them. Every open boundary is auto-minted
    as a Class-A handle `<object>.<region>` (deduped by vert-set), so the relationships
    the agent just learned are addressable by name for the rest of the session.
  • `feel op=map` — from a boundary loop's centre, cast a ray along the loop's plane
    normal and report **what other mesh it hits and how far** (or a clean miss). Loose
    spatial adjacency as a perception primitive — "this opening, raycast from its
    centre, hits that mesh ~6 cm away."

Class-A only. An open boundary loop is a topological *fact* (edges with one adjacent
face), so naming it exposes what's there. The raycast HIT is returned as a transient
coordinate, **never** auto-minted — a point on a smooth face has no topological
signature (Class B, agent-minted only). That's the legible-vs-divination line.
"""

import bmesh
import numpy as np

import bpy
from mathutils import Vector

from . import handles
from .common import region_words, world_bbox, world_center
from .topology import _boundary_loops


# ── target resolution ─────────────────────────────────────────────────────────

def _mesh_targets(targets, group):
    """Resolve the object set: explicit `targets` (comma names) > `group` (collection)
    > all visible scene meshes. Returns (objects, error)."""
    if targets:
        objs, missing = [], []
        for nm in (t.strip() for t in targets.split(",")):
            if not nm:
                continue
            o = bpy.data.objects.get(nm)
            if o is None or o.type != 'MESH':
                missing.append(nm)
            else:
                objs.append(o)
        if missing:
            return [], f"not a mesh / not found: {', '.join(missing)}"
        return objs, None
    if group:
        coll = bpy.data.collections.get(group)
        if coll is None:
            return [], f"collection '{group}' not found"
        return [o for o in coll.objects if o.type == 'MESH'], None
    return [o for o in bpy.context.scene.objects if o.type == 'MESH'], None


# ── op=assembly ────────────────────────────────────────────────────────────────

def _object_loops(obj):
    """Open boundary loops of obj's cage, each as {indices, centroid (world),
    circ_cm, region}. Indices are into obj.data.vertices (the mint path reads them
    back the same way)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    mw = obj.matrix_world
    bbox = world_bbox(obj)
    out = []
    for lv in sorted(_boundary_loops(bm), key=len, reverse=True):
        co = [mw @ bm.verts[i].co for i in lv]
        per = sum((co[k] - co[(k + 1) % len(co)]).length for k in range(len(co)))
        centroid = handles._centroid(co)
        out.append({"indices": lv, "centroid": centroid,
                    "circ_cm": round(per * 100, 1),
                    "region": region_words(bbox, centroid)})
    bm.free()
    return out


def feel_assembly(params):
    """The relational map over a set of objects — bounds + boundary catalog + pairwise
    gaps — auto-minting each open boundary as a Class-A handle."""
    objs, err = _mesh_targets(params.get("targets") or "", params.get("group") or "")
    if err:
        return {"error": err}
    if not objs:
        return {"error": "no mesh objects to read"}

    per_object = []
    for obj in objs:
        if obj.mode == 'EDIT':
            per_object.append({"name": obj.name, "skipped": "in edit mode (exit to read)"})
            continue
        bb = world_bbox(obj)
        size = [round(bb[3] - bb[0], 3), round(bb[4] - bb[1], 3), round(bb[5] - bb[2], 3)]
        loops = []
        for lp in _object_loops(obj):
            base = f"{obj.name}.{lp['region']}"
            m = handles.mint_boundary_handle(obj, lp["indices"], base)
            loops.append({"handle": m.get("name", base), "reused": m.get("reused", False),
                          "verts": len(lp["indices"]), "circ_cm": lp["circ_cm"],
                          "region": lp["region"],
                          "point": [round(c, 5) for c in lp["centroid"]]})
        per_object.append({"name": obj.name, "size_m": size, "boundaries": loops})

    pairs = []
    for i in range(len(objs)):
        for j in range(i + 1, len(objs)):
            a, b = objs[i], objs[j]
            ax, bx = world_bbox(a), world_bbox(b)
            gx = max(bx[0] - ax[3], ax[0] - bx[3])
            gy = max(bx[1] - ax[4], ax[1] - bx[4])
            gz = max(bx[2] - ax[5], ax[2] - bx[5])
            sep = (max(gx, 0.0) ** 2 + max(gy, 0.0) ** 2 + max(gz, 0.0) ** 2) ** 0.5
            touching = [n for n, g in zip("XYZ", (gx, gy, gz)) if abs(g) < 1e-4]
            pairs.append({"a": a.name, "b": b.name, "gap": round(sep, 4),
                          "touching": touching})

    return {"success": True, "objects": per_object, "pairs": pairs}


# ── op=map ─────────────────────────────────────────────────────────────────────

def _plane_normal(cos, centroid, outward_from):
    """PCA plane normal of an UNORDERED loop vert-set (direction of least variance) —
    order-independent, so it recomputes live from the vgroup. Oriented away from the
    owner centre (out through the opening)."""
    pts = np.array([[c.x, c.y, c.z] for c in cos], dtype=float)
    pts = pts - np.array([centroid.x, centroid.y, centroid.z])
    if len(pts) < 3:
        n = Vector((0.0, 0.0, 1.0))
    else:
        _u, _s, vh = np.linalg.svd(pts, full_matrices=False)
        n = Vector((float(vh[2][0]), float(vh[2][1]), float(vh[2][2])))
    if n.length < 1e-9:
        n = Vector((0.0, 0.0, 1.0))
    n = n.normalized()
    if n.dot(centroid - outward_from) < 0:
        n = -n
    return n


def _cast_from_handle(name, margin):
    """Cast OUTWARD from one boundary handle's loop (along its plane normal, oriented
    away from the owner centre — the direction the opening faces) and report the
    nearest non-self hit. One direction only: "what does this opening look out onto."
    A bottom hole looks DOWN onto nothing → a clean miss, not the plate the upward
    ray would thread to through the hollow body."""
    empty = handles._find_handle(name)
    if empty is None:
        return {"handle": name, "error": "not found"}
    owner = bpy.data.objects.get(empty.get("bb_owner", ""))
    cos, _nrms = handles._vgroup_geo(owner, empty.get("bb_vgroup", ""))
    if not cos:
        return {"handle": name, "error": "orphaned (vgroup gone/empty)"}

    centroid = handles._centroid(cos)
    normal = _plane_normal(cos, centroid, Vector(world_center(owner)))
    scene = bpy.context.scene
    deps = bpy.context.evaluated_depsgraph_get()
    origin = centroid + normal * max(float(margin or 0.0), 1e-3)
    hit, loc, _nrm, _idx, hitobj, _mat = scene.ray_cast(deps, origin, normal, distance=1000.0)
    if hit and hitobj is not None and hitobj.name != owner.name:
        loc = Vector(loc)
        return {"handle": name, "hit": True, "object": hitobj.name,
                "distance_cm": round((loc - centroid).length * 100, 1),
                "point": [round(c, 5) for c in loc],
                "region": region_words(world_bbox(hitobj), loc)}
    return {"handle": name, "hit": False}


def feel_map(params):
    """Raycast adjacency from boundary handle(s). `handle=<name>` maps one; `target=
    <mesh>` maps every boundary handle on that mesh (run `feel op=assembly` first to
    mint them). Read-only — reports hits as coordinates, mints nothing."""
    name = (params.get("handle") or "").strip()
    target = (params.get("target") or "").strip()
    margin = params.get("margin", 0.0)

    if name:
        names = [name]
    elif target:
        coll = bpy.data.collections.get(handles.HANDLES_COLLECTION)
        names = [o.name for o in coll.objects
                 if o.get("bb_handle") and o.get("bb_owner") == target
                 and o.get("bb_kind") == "boundary"] if coll else []
        if not names:
            return {"error": f"no boundary handles on '{target}' — "
                             f"run `feel op=assembly` first to mint them"}
    else:
        return {"error": "feel op=map needs handle=<name> or target=<mesh>"}

    return {"success": True, "casts": [_cast_from_handle(n, margin) for n in names]}


TOOLS = {
    "feel_assembly": feel_assembly,
    "feel_map":      feel_map,
}

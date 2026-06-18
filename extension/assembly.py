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

import math

import bmesh
import numpy as np

import bpy
from mathutils import Vector

from . import handles
from .common import region_words, world_bbox, world_center
from .topology import _boundary_loops


# ── target resolution ─────────────────────────────────────────────────────────

# G64 — types that yield a surface via to_mesh(): a live curve/surface/text/meta can
# be READ (its beveled boundaries reported) without a destructive object op=convert.
_MESHABLE = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}


def _mesh_targets(targets, group):
    """Resolve the object set: explicit `targets` (comma names) > `group` (collection)
    > all visible scene meshes/curves. Returns (objects, error). Includes meshable
    non-mesh types (curves &c) so assembly can read a live connector's surface."""
    if targets:
        objs, missing = [], []
        for nm in (t.strip() for t in targets.split(",")):
            if not nm:
                continue
            o = bpy.data.objects.get(nm)
            if o is None or o.type not in _MESHABLE:
                missing.append(nm)
            else:
                objs.append(o)
        if missing:
            return [], f"not a mesh/curve / not found: {', '.join(missing)}"
        return objs, None
    if group:
        coll = bpy.data.collections.get(group)
        if coll is None:
            return [], f"collection '{group}' not found"
        return [o for o in coll.objects if o.type in _MESHABLE], None
    return [o for o in bpy.context.scene.objects if o.type in _MESHABLE], None


# ── op=assembly ────────────────────────────────────────────────────────────────

def _object_loops(obj):
    """Open boundary loops of obj's surface, each as {indices, centroid (world),
    circ_cm, region}. For a MESH the indices are into obj.data.vertices (the mint
    path reads them back the same way). For a CURVE/SURFACE/&c (G64) the surface is
    its evaluated, beveled `to_mesh()` — read non-destructively, so the indices are
    EPHEMERAL (eval-only) and must NOT be used to mint a persistent handle."""
    bm = bmesh.new()
    eval_obj = None
    if obj.type == 'MESH':
        bm.from_mesh(obj.data)
    else:
        dg = bpy.context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(dg)
        me = eval_obj.to_mesh()
        if me is None:
            bm.free()
            return []
        bm.from_mesh(me)
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
    if eval_obj is not None:
        eval_obj.to_mesh_clear()
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
        # G64 — a non-mesh surface (curve/&c) is read from an ephemeral evaluated mesh,
        # so its loops can be REPORTED but not minted (no persistent vgroup to anchor).
        meshable_nonmesh = obj.type != 'MESH'
        loops = []
        for lp in _object_loops(obj):
            if meshable_nonmesh:
                loops.append({"handle": None, "evaluated": True,
                              "verts": len(lp["indices"]), "circ_cm": lp["circ_cm"],
                              "region": lp["region"],
                              "point": [round(c, 5) for c in lp["centroid"]]})
                continue
            base = f"{obj.name}.{lp['region']}"
            m = handles.mint_boundary_handle(obj, lp["indices"], base)
            loops.append({"handle": m.get("name", base), "reused": m.get("reused", False),
                          "verts": len(lp["indices"]), "circ_cm": lp["circ_cm"],
                          "region": lp["region"],
                          "point": [round(c, 5) for c in lp["centroid"]]})
        rec = {"name": obj.name, "size_m": size, "boundaries": loops}
        if meshable_nonmesh:
            rec["kind"] = f"{obj.type.lower()} (evaluated, read-only — object op=convert to mint/bridge)"
        per_object.append(rec)

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


# ── op=relate ────────────────────────────────────────────────────────────────

def _handle_loop(name):
    """Resolve a boundary handle to its live world-space loop summary —
    (centroid, outward plane normal, mean radius, vert count) — or (None, error)."""
    empty = handles._find_handle(name)
    if empty is None:
        return None, f"handle '{name}' not found"
    owner = bpy.data.objects.get(empty.get("bb_owner", ""))
    if owner is None:
        return None, f"handle '{name}' owner is gone (orphaned)"
    cos, _n = handles._vgroup_geo(owner, empty.get("bb_vgroup", ""))
    if not cos:
        return None, f"handle '{name}' is orphaned (vgroup gone/empty)"
    centroid = handles._centroid(cos)
    normal = _plane_normal(cos, centroid, Vector(world_center(owner)))
    radius = sum((c - centroid).length for c in cos) / len(cos)
    return {"centroid": centroid, "normal": normal, "radius": radius,
            "count": len(cos)}, None


def _open_edge_count(owner, vgname):
    """G62 — does this handle's vert-set lie on an OPEN boundary (a weldable rim:
    edges with one adjacent face) or on CLOSED geometry (a cap / interior face-ring —
    nothing to weld into)? Computed LIVE, not stored: capping/uncapping changes the
    answer, so a stored flag would go stale. Returns the count of open-boundary edges
    within the set, or None if unresolvable."""
    import bmesh
    if owner is None or owner.type != 'MESH':
        return None
    vset = handles._vgroup_vertset(owner, vgname)
    if not vset:
        return None
    bm = bmesh.new()
    bm.from_mesh(owner.data)
    n = 0
    for e in bm.edges:
        if (len(e.link_faces) == 1
                and e.verts[0].index in vset and e.verts[1].index in vset):
            n += 1
    bm.free()
    return n


def feel_relate(params):
    """G16 — the boundary-to-boundary relation: do TWO named openings line up? The
    read a bridge/weld needs *before* it tries. Reports centre-to-centre gap, axis
    alignment (do the loop planes face each other?), and the radius/size match. This
    is op=map's loop-plane math applied to a named handle PAIR instead of a raycast
    into the scene — measuring two specific openings, not whatever a ray happens to
    hit. G62: each endpoint is classified open-rim vs closed-cap, and a closed cap
    forces join_ready false with a warning — you can't weld into a wall."""
    a_name = (params.get("a") or "").strip()
    b_name = (params.get("b") or "").strip()
    if not a_name or not b_name:
        return {"error": "feel op=relate needs a=<handle> and b=<handle> "
                         "(mint boundary handles with feel op=assembly)"}
    a, err = _handle_loop(a_name)
    if err:
        return {"error": err}
    b, err = _handle_loop(b_name)
    if err:
        return {"error": err}

    gap = (b["centroid"] - a["centroid"]).length
    # Both normals point OUT of their owners. Two openings that face each other have
    # OPPOSED outward normals (dot ≈ -1); coaxial-same (dot ≈ +1) face the same way.
    dot = max(-1.0, min(1.0, a["normal"].dot(b["normal"])))
    angle = math.degrees(math.acos(abs(dot)))   # axis misalignment: 0 = parallel axes
    if angle <= 10.0:
        facing = "opposed (face each other)" if dot < 0 else "coaxial (face same way)"
    else:
        facing = f"skew ({round(angle, 1)}° off-axis)"

    ra, rb = a["radius"], b["radius"]
    ratio = (min(ra, rb) / max(ra, rb)) if max(ra, rb) > 1e-9 else 0.0

    # G62 — open rim vs closed cap. A handle on a closed cap has no boundary edges to
    # bridge into; relate must say so rather than green-light a weld onto a wall.
    ha, hb = handles._find_handle(a_name), handles._find_handle(b_name)
    owner_a = bpy.data.objects.get(ha.get("bb_owner", "")) if ha else None
    owner_b = bpy.data.objects.get(hb.get("bb_owner", "")) if hb else None
    oea = _open_edge_count(owner_a, ha.get("bb_vgroup", "")) if ha else None
    oeb = _open_edge_count(owner_b, hb.get("bb_vgroup", "")) if hb else None
    a_open = oea is None or oea > 0   # unknown → don't cry wolf
    b_open = oeb is None or oeb > 0
    a_bnd = "open rim" if a_open else "closed cap"
    b_bnd = "open rim" if b_open else "closed cap"

    # A weld candidate: planes roughly parallel, facing each other, similar size —
    # AND both endpoints are open rims (can't bridge into a wall).
    join_ready = (angle <= 15.0 and dot < 0 and ratio >= 0.8 and a_open and b_open)

    out = {
        "success": True, "a": a_name, "b": b_name,
        "center_gap_cm": round(gap * 100, 2),
        "axis_angle_deg": round(angle, 1),
        "facing": facing,
        "diam_a_cm": round(ra * 2 * 100, 2),
        "diam_b_cm": round(rb * 2 * 100, 2),
        "size_match": round(ratio, 3),
        "a_boundary": a_bnd,
        "b_boundary": b_bnd,
        "join_ready": join_ready,
    }
    if not (a_open and b_open):
        which = ", ".join(n for n, ok in ((a_name, a_open), (b_name, b_open)) if not ok)
        out["warning"] = (f"{which} sits on a CLOSED cap — no open rim to weld into. "
                          f"Uncap it (delete the cap face) before bridging.")
    return out


TOOLS = {
    "feel_assembly": feel_assembly,
    "feel_map":      feel_map,
    "feel_relate":   feel_relate,
}

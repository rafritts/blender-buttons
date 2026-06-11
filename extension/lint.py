"""Pre-render / pre-delivery quality lints.

find_coplanar_overlaps (P3) — z-fight detector across objects.
validate_scene        (P5) — compiler-style scene lint (z-fights, normals, degenerate, below floor).
check_mesh            (P6) — single-mesh soundness: non-manifold, self-intersection, zero-area, thin walls.
audit_asset           (P12) — game-readiness audit: materials, tri budget, unapplied transforms, loose verts.

All four reason about EVALUATED geometry (modifiers applied) and report short
semantic verdicts in mm / object names — never coordinate dumps.
"""

import bmesh
import mathutils

from .common import (
    camera_coverage,
    eval_world_bmesh,
    object_bvh,
    resolve_targets,
    scene_mesh_objects,
    world_bbox,
)

_AXES = "XYZ"


# ─────────────────────────── coplanar (P3) ───────────────────────────

def _flat_panels(obj, eps_n=1e-3, eps_coord=1e-4):
    """Collapse an object's axis-aligned faces into 'panels': one merged 2D
    footprint per (axis, outward-sign, plane-coordinate). A panel is a flat face
    lying perpendicular to a world axis — the only thing that can z-fight another
    object's coplanar panel. Returns [] for non-mesh or non-axis-aligned shapes."""
    bm = eval_world_bmesh(obj)
    if bm is None:
        return []
    panels = {}
    for f in bm.faces:
        n = f.normal
        comps = (abs(n.x), abs(n.y), abs(n.z))
        axis = max(range(3), key=lambda i: comps[i])
        if comps[axis] < 1.0 - eps_n:
            continue
        if any(comps[i] > eps_n for i in range(3) if i != axis):
            continue
        others = [i for i in range(3) if i != axis]
        center = f.calc_center_median()
        coord = center[axis]
        sign = 1 if n[axis] >= 0 else -1
        us = [v.co[others[0]] for v in f.verts]
        vs = [v.co[others[1]] for v in f.verts]
        area = f.calc_area()
        key = (axis, sign, round(coord / max(eps_coord, 1e-9)))
        if key not in panels:
            panels[key] = [min(us), max(us), min(vs), max(vs), coord * area, area]
        else:
            p = panels[key]
            p[0] = min(p[0], min(us)); p[1] = max(p[1], max(us))
            p[2] = min(p[2], min(vs)); p[3] = max(p[3], max(vs))
            p[4] += coord * area; p[5] += area
    bm.free()
    out = []
    for (axis, sign, bucket), p in panels.items():
        coord = p[4] / p[5] if p[5] > 1e-12 else bucket * eps_coord
        out.append({"obj": obj.name, "axis": axis, "sign": sign, "coord": coord,
                    "u": (p[0], p[1]), "v": (p[2], p[3])})
    return out


def _coplanar_pairs(objs, eps):
    """All cross-object coplanar overlapping panel pairs (z-fight candidates)."""
    all_panels = [_flat_panels(o, eps_coord=eps) for o in objs]
    pairs = []
    for i in range(len(objs)):
        for j in range(i + 1, len(objs)):
            for a in all_panels[i]:
                for b in all_panels[j]:
                    if a["axis"] != b["axis"] or a["sign"] != b["sign"]:
                        continue
                    if abs(a["coord"] - b["coord"]) > eps:
                        continue
                    ou = min(a["u"][1], b["u"][1]) - max(a["u"][0], b["u"][0])
                    ov = min(a["v"][1], b["v"][1]) - max(a["v"][0], b["v"][0])
                    if ou > eps and ov > eps:
                        pairs.append({
                            "a": a["obj"], "b": b["obj"],
                            "axis": _AXES[a["axis"]],
                            "coord": round(a["coord"], 4),
                            "overlap_mm": [round(ou * 1000, 1), round(ov * 1000, 1)],
                        })
    return pairs


def find_coplanar_overlaps(params):
    """Report pairs of faces from DIFFERENT objects that are coplanar and overlap
    in-plane — the classic invisible-until-render z-fight (a solid cap sitting
    exactly on another part's face). targets: optional restrict; default whole scene."""
    targets = params.get("targets")
    eps = float(params.get("epsilon", 1e-4))
    if targets:
        objs, err = resolve_targets(targets)
        if err:
            return {"error": err}
        objs = [o for o in objs if o.type == 'MESH']
    else:
        objs = scene_mesh_objects()
    pairs = _coplanar_pairs(objs, eps)
    return {"success": True, "epsilon": eps, "count": len(pairs), "overlaps": pairs,
            "checked": [o.name for o in objs]}


# ─────────────────────────── validate (P5) ───────────────────────────

def _normals_inward_fraction(bm):
    """Fraction of faces whose normal points toward the mesh centroid. High on a
    roughly-convex closed mesh ⇒ normals are flipped. Heuristic, lint-grade only."""
    if not bm.faces:
        return 0.0
    center = mathutils.Vector((0, 0, 0))
    for f in bm.faces:
        center += f.calc_center_median()
    center /= len(bm.faces)
    inward = 0
    for f in bm.faces:
        if (f.calc_center_median() - center).dot(f.normal) < 0:
            inward += 1
    return inward / len(bm.faces)


def validate_scene(params):
    """Pre-render lint across the scene. Findings: cross-object z-fights, likely
    inverted normals, degenerate (zero-area) faces, and objects below the floor.
    Compiler-style: PASS, or one finding per line."""
    eps = float(params.get("epsilon", 1e-4))
    targets = params.get("targets")
    excluded = []
    if targets:
        objs, err = resolve_targets(targets, include_non_mesh=True)
        if err:
            return {"error": err}
        # Curves, empties, lights etc. have no faces to lint — name what we drop
        # rather than silently shrinking the count (no-silent-caps). include_non_mesh
        # keeps collection members in scope so a group's non-mesh parts get reported
        # here too, not just explicitly-named ones (gaps.md S1b).
        excluded = [o.name for o in objs if o.type != 'MESH']
        objs = [o for o in objs if o.type == 'MESH']
    else:
        objs = scene_mesh_objects()

    findings = []

    for pair in _coplanar_pairs(objs, eps):
        findings.append({
            "kind": "z_fight",
            "message": (f"'{pair['a']}' and '{pair['b']}' have coplanar faces at "
                        f"{pair['axis']}={pair['coord']} overlapping "
                        f"{pair['overlap_mm'][0]}×{pair['overlap_mm'][1]}mm — z-fighting risk"),
        })

    for o in objs:
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
        if zmin < -eps:
            findings.append({
                "kind": "below_floor",
                "message": f"'{o.name}' dips {round(-zmin * 1000, 1)}mm below the floor (z=0)",
            })
        bm = eval_world_bmesh(o)
        if bm is None:
            continue
        degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
        if degenerate:
            findings.append({
                "kind": "degenerate",
                "message": f"'{o.name}' has {degenerate} zero-area face(s)",
            })
        if len(bm.faces) >= 8 and _normals_inward_fraction(bm) > 0.7:
            findings.append({
                "kind": "inverted_normals",
                "message": f"'{o.name}' normals appear inverted (most faces point inward)",
            })
        bm.free()

    return {"success": True, "passed": not findings, "count": len(findings),
            "findings": findings, "checked": [o.name for o in objs],
            "excluded_non_mesh": excluded}


# ─────────────────────────── check_mesh (P6) ───────────────────────────

def _self_intersections(bm, bvh):
    """Count real self-intersections: BVH overlap pairs that DON'T merely share a
    vertex (adjacency). Pure adjacency 'touches' are excluded so only genuine
    crossing geometry is reported."""
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    face_vids = [set(v.index for v in f.verts) for f in bm.faces]
    count = 0
    for i, j in bvh.overlap(bvh):
        if i >= j:
            continue
        if face_vids[i] & face_vids[j]:
            continue
        count += 1
    return count


def _thinnest_wall(bm, bvh, max_samples=400):
    """Ray-probe wall thickness: from each sampled face shoot inward (−normal) and
    measure the distance to the opposite surface. The min is the thinnest wall —
    the 'pinch test' before booleans / for shell soundness. Returns metres or None."""
    faces = bm.faces
    step = max(1, len(faces) // max_samples)
    thinnest = None
    for idx in range(0, len(faces), step):
        f = faces[idx]
        n = f.normal
        if n.length < 1e-9:
            continue
        origin = f.calc_center_median() - n * 1e-5
        hit = bvh.ray_cast(origin, -n)
        if hit[0] is None:
            continue
        dist = hit[3]
        if dist > 1e-6 and (thinnest is None or dist < thinnest):
            thinnest = dist
    return thinnest


def check_mesh(params):
    """Single-mesh soundness for printing / booleans / game shells. Reports
    non-manifold edges, self-intersections, zero-area faces, and thinnest wall —
    computed directly with bmesh + BVH (no external add-on dependency)."""
    targets = params.get("target") or params.get("targets")
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}
    objs = [o for o in objs if o.type == 'MESH']
    if not objs:
        return {"error": "check_mesh needs a mesh target"}

    reports = []
    for o in objs:
        bm = eval_world_bmesh(o)
        if bm is None:
            continue
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
        zero_area = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
        bvh = object_bvh(o)
        self_x = _self_intersections(bm, bvh) if bvh else 0
        thin = _thinnest_wall(bm, bvh) if bvh else None
        watertight = (non_manifold == 0)
        bm.free()
        reports.append({
            "object": o.name,
            "watertight": watertight,
            "non_manifold_edges": non_manifold,
            "self_intersections": self_x,
            "zero_area_faces": zero_area,
            "thinnest_wall_mm": round(thin * 1000, 2) if thin is not None else None,
            "clean": watertight and self_x == 0 and zero_area == 0,
        })
    return {"success": True, "reports": reports}


# ─────────────────────────── audit (P12) ───────────────────────────

def audit_asset(params):
    """Game-readiness audit over a group/selection. Per object: missing material,
    triangle count (with screen coverage when a camera exists), unapplied
    scale/rotation, and loose (face-less) verts. Turns 'is this game-ready?' from
    vibes into countable findings."""
    import bpy
    targets = params.get("group") or params.get("targets")
    objs, err = resolve_targets(targets, include_non_mesh=True)
    if err:
        return {"error": err}
    # Curves/empties carry no auditable geometry — name them, don't swallow them.
    # include_non_mesh keeps group members in scope so non-mesh parts of a group are
    # reported, not dropped at expansion (gaps.md S1b).
    excluded = [o.name for o in objs if o.type != 'MESH']
    objs = [o for o in objs if o.type == 'MESH']
    if not objs:
        return {"error": "audit_asset needs at least one mesh"}

    scene = bpy.context.scene
    cam = scene.camera if scene.camera and scene.camera.type == 'CAMERA' else None
    tri_budget = int(params.get("tri_budget", 5000))

    reports = []
    total_tris = 0
    for o in objs:
        issues = []
        bm = eval_world_bmesh(o)
        tris = 0
        loose = 0
        if bm is not None:
            tris = sum(len(f.verts) - 2 for f in bm.faces)
            loose = sum(1 for v in bm.verts if not v.link_faces)
            bm.free()
        total_tris += tris

        has_material = bool(o.data.materials) and any(m is not None for m in o.data.materials)
        if not has_material:
            issues.append("no material slot")
        if loose:
            issues.append(f"{loose} loose vert(s)")
        if any(abs(s - 1.0) > 1e-3 for s in o.scale):
            issues.append(f"unapplied scale {[round(s, 3) for s in o.scale]}")
        if any(abs(r) > 1e-3 for r in o.rotation_euler):
            issues.append("unapplied rotation")

        coverage = None
        if cam is not None:
            cov = camera_coverage(scene, cam, o)
            if cov["in_front"]:
                coverage = round(max(cov["frac_w"], cov["frac_h"]) * 100, 1)
                # Overbuilt = lots of tris for a small slice of the frame.
                if coverage < 15 and tris > tri_budget // 2:
                    issues.append(f"{tris} tris for {coverage}% of frame — overbuilt")
        if tris > tri_budget:
            issues.append(f"{tris} tris over budget ({tri_budget})")

        reports.append({
            "object": o.name, "tris": tris, "screen_pct": coverage,
            "has_material": has_material, "issues": issues, "clean": not issues,
        })

    return {"success": True, "total_tris": total_tris,
            "object_count": len(reports), "tri_budget": tri_budget,
            "reports": reports, "passed": all(r["clean"] for r in reports),
            "excluded_non_mesh": excluded}


TOOLS = {
    "find_coplanar_overlaps": find_coplanar_overlaps,
    "validate_scene":         validate_scene,
    "check_mesh":             check_mesh,
    "audit_asset":            audit_asset,
}

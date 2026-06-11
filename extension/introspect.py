"""Tactile introspection — "braille for the agent".

The agent's vision can JUDGE but not MEASURE. These tools convert geometry into
short semantic verdicts in scene vocabulary (object names, mm/deg deltas, frame
percentages) — never coordinate dumps, which the agent can't reason over.

check_contacts (P4)  — per part: connected / floating(gap) / penetrating(depth).
trace_profile  (P7)  — a fingertip run along an axis: a feature narrative, not points.
check_framing  (P9)  — camera-space coverage, clipping, occlusion (no render needed).
check_resting  (P10) — gravity sanity: contacts, float/sink, center-of-mass over support.
diff_since     (P11) — what changed since a history checkpoint (moved/rotated/deformed/where).
"""

import math

import bpy
import mathutils
from mathutils.bvhtree import BVHTree

from . import state
from .common import (
    camera_coverage,
    eval_world_bmesh,
    region_words as _region_words,
    resolve_targets,
    scene_mesh_objects,
    world_bbox,
    world_center,
)

_AXES = "XYZ"
_TOUCH = 0.0005  # 0.5 mm — below this two surfaces are "touching", not floating


def _prepare(obj, cap=250):
    """World-space BVH + downsampled world vertices + bbox for one object."""
    bm = eval_world_bmesh(obj)
    if bm is None or not bm.verts:
        if bm:
            bm.free()
        return None
    bvh = BVHTree.FromBMesh(bm)
    n = len(bm.verts)
    step = max(1, n // cap)
    sample = [bm.verts[i].co.copy() for i in range(0, n, step)]
    bm.free()
    return {"name": obj.name, "bvh": bvh, "verts": sample, "bbox": world_bbox(obj)}


def _bbox_separation(a, b):
    """Euclidean separation between two world bboxes (0 if they overlap). Cheap
    prefilter for picking the few nearest candidates before exact surface tests."""
    gx = max(b[0] - a[3], a[0] - b[3], 0.0)
    gy = max(b[1] - a[4], a[1] - b[4], 0.0)
    gz = max(b[2] - a[5], a[2] - b[5], 0.0)
    return math.sqrt(gx * gx + gy * gy + gz * gz)


# ─────────────────────────── contacts (P4) ───────────────────────────

def _report_targets(params):
    """Resolve the report set: explicit targets, or every scene mesh. Returns
    (objs, error)."""
    targets = params.get("targets")
    if targets:
        objs, err = resolve_targets(targets)
        if err:
            return None, err
        return [o for o in objs if o.type == 'MESH'], None
    return scene_mesh_objects(), None


def _surface_gap(src, dst):
    """Min distance from any of src's sampled verts to dst's surface (≈0 if they
    touch or cross)."""
    gap = float("inf")
    for v in src["verts"]:
        loc, normal, idx, dist = dst["bvh"].find_nearest(v)
        if loc is not None and dist < gap:
            gap = dist
    return gap


def _bbox_overlaps(a, b):
    """Per-axis overlap of two world bboxes (negative ⇒ separated on that axis)."""
    return (min(a[3], b[3]) - max(a[0], b[0]),
            min(a[4], b[4]) - max(a[1], b[1]),
            min(a[5], b[5]) - max(a[2], b[2]))


def check_contacts(params):
    """Per target part, the nearest other part and how they relate: connected
    (touching), floating (gap in mm), or penetrating (depth in mm). Reports facts,
    makes no judgement — interpenetration is correct for chain links and sunk markers."""
    report_objs, err = _report_targets(params)
    if err:
        return {"error": err}
    prepared = {o.name: _prepare(o) for o in scene_mesh_objects()}
    prepared = {k: v for k, v in prepared.items() if v is not None}

    results = []
    for o in report_objs:
        me = prepared.get(o.name)
        if me is None:
            continue
        others = [p for name, p in prepared.items() if name != o.name]
        if not others:
            results.append({"object": o.name, "relation": "alone", "other": None})
            continue
        others.sort(key=lambda p: _bbox_separation(me["bbox"], p["bbox"]))
        best = None
        for p in others[:5]:
            gap = min(_surface_gap(me, p), _surface_gap(p, me))
            ox, oy, oz = _bbox_overlaps(me["bbox"], p["bbox"])
            # Penetration = surfaces cross AND the bboxes overlap on every axis.
            # Vertex-inside tests fail for matched footprints (verts land on shared
            # planes); all-axis bbox overlap is the robust signal at hobby scale.
            penetrating = gap <= _TOUCH and ox > _TOUCH and oy > _TOUCH and oz > _TOUCH
            depth = min(ox, oy, oz) if penetrating else 0.0
            if penetrating:
                key = (0, -depth)
            elif gap <= _TOUCH:
                key = (1, 0.0)
            else:
                key = (2, gap)
            if best is None or key < best["key"]:
                best = {"key": key, "other": p["name"], "gap": gap,
                        "depth": depth, "penetrating": penetrating}
        if best["penetrating"]:
            rel = {"object": o.name, "relation": "penetrating", "other": best["other"],
                   "depth_mm": round(best["depth"] * 1000, 1)}
        elif best["gap"] <= _TOUCH:
            rel = {"object": o.name, "relation": "connected", "other": best["other"]}
        else:
            rel = {"object": o.name, "relation": "floating", "other": best["other"],
                   "gap_mm": round(best["gap"] * 1000, 1)}
        results.append(rel)
    return {"success": True, "contacts": results}


# ─────────────────────────── resting (P10) ───────────────────────────

def _support_below(obj, prepared, zmin):
    """Object whose top sits at obj's bottom with an xy overlap, or None (floor)."""
    o_bb = world_bbox(obj)
    best = None
    for name, p in prepared.items():
        if name == obj.name:
            continue
        b = p["bbox"]
        xy_overlap = (o_bb[0] < b[3] and o_bb[3] > b[0] and o_bb[1] < b[4] and o_bb[4] > b[1])
        if not xy_overlap:
            continue
        # its top near our bottom (within 5mm above or below)
        if abs(b[5] - zmin) < 0.005 or (b[5] >= zmin - 0.005 and b[2] <= zmin + 0.005):
            if best is None or b[5] > best[1]:
                best = (name, b[5])
    return best


def check_resting(params):
    """Gravity sanity per part: floor/support contact points, sink/float height,
    and whether the centre of mass sits over the support footprint (else it tips)."""
    report_objs, err = _report_targets(params)
    if err:
        return {"error": err}
    prepared = {o.name: _prepare(o) for o in scene_mesh_objects()}
    prepared = {k: v for k, v in prepared.items() if v is not None}

    results = []
    for o in report_objs:
        me = prepared.get(o.name)
        if me is None:
            continue
        bb = me["bbox"]
        zmin = bb[2]
        support = _support_below(o, prepared, zmin)
        support_name = support[0] if support else "floor"
        support_z = support[1] if support else 0.0
        clearance = zmin - support_z  # >0 floats, <0 sinks

        contacts = [v for v in me["verts"] if abs(v.z - support_z) < _TOUCH]
        com = mathutils.Vector((0, 0, 0))
        for v in me["verts"]:
            com += v
        com /= len(me["verts"])

        # support footprint: xy span of the contact verts (fall back to bbox footprint)
        if len(contacts) >= 1:
            sx = [v.x for v in contacts]; sy = [v.y for v in contacts]
            sxmin, sxmax, symin, symax = min(sx), max(sx), min(sy), max(sy)
        else:
            sxmin, sxmax, symin, symax = bb[0], bb[3], bb[1], bb[4]

        margin = _TOUCH
        tip_dir = None
        if com.x < sxmin - margin: tip_dir = "-X (left)"
        elif com.x > sxmax + margin: tip_dir = "+X (right)"
        elif com.y < symin - margin: tip_dir = "-Y (front)"
        elif com.y > symax + margin: tip_dir = "+Y (back)"
        com_over = tip_dir is None

        results.append({
            "object": o.name,
            "support": support_name,
            "contacts": len(contacts),
            "clearance_mm": round(clearance * 1000, 1),
            "state": ("floating" if clearance > _TOUCH else
                      "sunk" if clearance < -_TOUCH else "resting"),
            "com_over_support": com_over,
            "tip_direction": tip_dir,
        })
    return {"success": True, "resting": results}


# ─────────────────────────── framing (P9) ───────────────────────────

def _occlusion_fraction(scene, depsgraph, cam, obj, cap=120):
    """Fraction of sampled target points hidden behind OTHER objects from the camera."""
    bm = eval_world_bmesh(obj)
    if bm is None or not bm.verts:
        if bm:
            bm.free()
        return 0.0
    origin = cam.matrix_world.translation
    n = len(bm.verts)
    step = max(1, n // cap)
    total = occ = 0
    for i in range(0, n, step):
        w = bm.verts[i].co
        d = w - origin
        dist = d.length
        if dist < 1e-6:
            continue
        total += 1
        hit, loc, nrm, idx, hitobj, mat = scene.ray_cast(
            depsgraph, origin, d.normalized(), distance=dist - 1e-4)
        if hit and hitobj is not None and hitobj.name != obj.name:
            occ += 1
    bm.free()
    return occ / total if total else 0.0


def check_framing(params):
    """Camera-space report per target: frame coverage %, which edges clip (and by
    how much), whether it's behind the camera, and % occluded by other objects.
    The deterministic answer to 'is it still cropped?' — no test render required."""
    cam_name = params.get("camera")
    scene = bpy.context.scene
    cam = bpy.data.objects.get(cam_name) if cam_name else scene.camera
    if cam is None or cam.type != 'CAMERA':
        return {"error": "no camera (pass camera=<name> or set the scene camera)"}

    report_objs, err = _report_targets(params)
    if err:
        return {"error": err}
    depsgraph = bpy.context.evaluated_depsgraph_get()

    results = []
    for o in report_objs:
        cov = camera_coverage(scene, cam, o)
        clip = {}
        umin, umax = cov["u_range"]; vmin, vmax = cov["v_range"]
        if umin < 0: clip["left"] = round(-umin * 100, 1)
        if umax > 1: clip["right"] = round((umax - 1) * 100, 1)
        if vmin < 0: clip["bottom"] = round(-vmin * 100, 1)
        if vmax > 1: clip["top"] = round((vmax - 1) * 100, 1)
        occ = _occlusion_fraction(scene, depsgraph, cam, o)
        results.append({
            "object": o.name,
            "frame_pct": [round(cov["frac_w"] * 100, 1), round(cov["frac_h"] * 100, 1)],
            "behind_camera": not cov["in_front"],
            "clipped": clip,
            "occluded_pct": round(occ * 100, 1),
        })
    return {"success": True, "camera": cam.name, "framing": results}


# ─────────────────────────── trace_profile (P7) ───────────────────────────

def trace_profile(params):
    """Run a fingertip along an axis and narrate the form: per-section radius and
    centre drift, plus detected features (rise / taper / flat / crease / bulge).
    The curvature SEQUENCE, the way a blind sculptor reads a shape — not points."""
    target = params.get("target") or params.get("targets")
    objs, err = resolve_targets(target)
    if err:
        return {"error": err}
    objs = [o for o in objs if o.type == 'MESH']
    if not objs:
        return {"error": "trace_profile needs a single mesh target"}
    obj = objs[0]
    axis = params.get("axis", "Z").upper()
    axis_idx = {"X": 0, "Y": 1, "Z": 2}.get(axis)
    if axis_idx is None:
        return {"error": "axis must be X, Y, or Z"}
    nsec = max(6, min(64, int(params.get("sections", 24))))

    bm = eval_world_bmesh(obj)
    if bm is None or not bm.verts:
        if bm:
            bm.free()
        return {"error": f"'{obj.name}' has no usable geometry"}
    others = [i for i in range(3) if i != axis_idx]
    coords = [v.co[axis_idx] for v in bm.verts]
    lo, hi = min(coords), max(coords)
    span = hi - lo
    if span < 1e-6:
        bm.free()
        return {"error": f"'{obj.name}' is flat on {axis} — nothing to trace"}

    buckets = [[] for _ in range(nsec)]
    for v in bm.verts:
        k = min(nsec - 1, int((v.co[axis_idx] - lo) / span * nsec))
        buckets[k].append(v.co)
    bm.free()

    sections = []
    for k, verts in enumerate(buckets):
        if not verts:
            continue
        cu = sum(v[others[0]] for v in verts) / len(verts)
        cv = sum(v[others[1]] for v in verts) / len(verts)
        radii = [math.hypot(v[others[0]] - cu, v[others[1]] - cv) for v in verts]
        sections.append({
            "pct": round((k + 0.5) / nsec * 100, 1),
            "radius_mm": round(sum(radii) / len(radii) * 1000, 1),
            "center_uv": (cu, cv),
        })
    if len(sections) < 3:
        return {"error": "not enough populated sections to trace a profile"}

    r = [s["radius_mm"] for s in sections]
    pct = [s["pct"] for s in sections]
    mean_r = sum(r) / len(r)
    flat_eps = max(0.3, 0.04 * mean_r)  # mm

    # Segment by slope sign into rise / taper / flat runs.
    features = []
    seg_type, seg_start = None, 0
    for i in range(1, len(r)):
        d = r[i] - r[i - 1]
        t = "flat" if abs(d) < flat_eps else ("rise" if d > 0 else "taper")
        if t != seg_type:
            if seg_type is not None:
                features.append({"kind": seg_type, "from_pct": pct[seg_start], "to_pct": pct[i - 1]})
            seg_type, seg_start = t, i - 1
    features.append({"kind": seg_type, "from_pct": pct[seg_start], "to_pct": pct[-1]})

    # Bulges: local maxima notably above the lo→hi radius trend.
    bulge_eps = max(0.5, 0.06 * mean_r)
    for i in range(1, len(r) - 1):
        trend = r[0] + (r[-1] - r[0]) * (i / (len(r) - 1))
        if r[i] >= r[i - 1] and r[i] >= r[i + 1] and (r[i] - trend) > bulge_eps:
            features.append({"kind": "bulge", "at_pct": pct[i],
                             "over_trend_mm": round(r[i] - trend, 1)})

    # Creases: sharp slope reversals (second-difference spikes).
    crease_eps = max(0.6, 0.08 * mean_r)
    for i in range(1, len(r) - 1):
        dd = (r[i + 1] - r[i]) - (r[i] - r[i - 1])
        if abs(dd) > crease_eps:
            features.append({"kind": "crease", "at_pct": pct[i],
                             "concave": dd > 0})

    # Centre drift across the run, in mm, named by dominant axis.
    cus = [s["center_uv"][0] for s in sections]
    cvs = [s["center_uv"][1] for s in sections]
    drift_u = (max(cus) - min(cus)) * 1000
    drift_v = (max(cvs) - min(cvs)) * 1000
    drift = {"axis": _AXES[others[0]] if drift_u >= drift_v else _AXES[others[1]],
             "mm": round(max(drift_u, drift_v), 1)}

    features.sort(key=lambda f: f.get("at_pct", f.get("from_pct", 0)))
    return {
        "success": True, "object": obj.name, "axis": axis,
        "section_count": len(sections),
        "radius_range_mm": [round(min(r), 1), round(max(r), 1)],
        "center_drift": drift,
        "features": features,
        "sections": [{"pct": s["pct"], "radius_mm": s["radius_mm"]} for s in sections],
    }


# ─────────────────────────── diff_since (P11) ───────────────────────────

def diff_since(params):
    """Narrate what changed since a history checkpoint: objects added/deleted, and
    per object moved (mm) / rotated (deg) / scaled / deformed (max displacement +
    where). Closes the loop on the sculpt brushes, which are otherwise open-loop."""
    cp = params.get("checkpoint") or params.get("id")
    if not cp:
        if not state._history:
            return {"error": "no history yet — nothing to diff against"}
        cp = state._history[0]["id"]
    old = state._snapshots.get(cp)
    if old is None:
        recent = [h["id"] for h in state._history][-8:]
        return {"error": f"no snapshot for checkpoint '{cp}'. Recent op ids: {recent}"}

    new = state.capture_geometry_snapshot()
    old_names, new_names = set(old), set(new)
    added = sorted(new_names - old_names)
    deleted = sorted(old_names - new_names)

    changed = []
    for name in sorted(old_names & new_names):
        o, n = old[name], new[name]
        c = []
        dloc = math.dist(o["loc"], n["loc"])
        if dloc > _TOUCH:
            c.append({"kind": "moved", "mm": round(dloc * 1000, 1)})
        drot = max((abs(a - b) for a, b in zip(o["rot"], n["rot"])), default=0.0)
        if drot > 0.1:
            c.append({"kind": "rotated", "deg": round(drot, 1)})
        dscale = max((abs(a - b) for a, b in zip(o["scale"], n["scale"])), default=0.0)
        if dscale > 0.001:
            c.append({"kind": "scaled", "to": [round(s, 3) for s in n["scale"]]})
        if "vcount" in o and "vcount" in n:
            if o["vcount"] != n["vcount"]:
                c.append({"kind": "topology", "delta_verts": n["vcount"] - o["vcount"]})
            elif o.get("vsample") and n.get("vsample") and len(o["vsample"]) == len(n["vsample"]):
                maxd, arg = 0.0, None
                for ov, nv in zip(o["vsample"], n["vsample"]):
                    d = math.dist(ov, nv)
                    if d > maxd:
                        maxd, arg = d, nv
                if maxd > _TOUCH:
                    region = None
                    obj = bpy.data.objects.get(name)
                    if obj is not None and arg is not None:
                        wp = obj.matrix_world @ mathutils.Vector(arg)
                        region = _region_words(world_bbox(obj), wp)
                    c.append({"kind": "deformed", "mm": round(maxd * 1000, 1), "where": region})
        if c:
            changed.append({"object": name, "changes": c})

    return {"success": True, "checkpoint": cp,
            "added": added, "deleted": deleted, "changed": changed,
            "unchanged": len(old_names & new_names) - len(changed)}


TOOLS = {
    "check_contacts": check_contacts,
    "check_resting":  check_resting,
    "check_framing":  check_framing,
    "trace_profile":  trace_profile,
    "diff_since":     diff_since,
}

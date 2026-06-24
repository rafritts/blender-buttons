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
    measurement_provenance,
    region_words as _region_words,
    resolve_targets,
    scene_mesh_objects,
    world_bbox,
    world_center,
)

_AXES = "XYZ"
_TOUCH = 0.0005  # 0.5 mm — below this two surfaces are "touching", not floating


# A deliberately off-axis unit ray for inside-by-parity tests. Axis-aligned rays graze
# the coplanar faces of boxes/quads and miscount; this direction hits cleanly.
_PARITY_DIR = mathutils.Vector((0.5612, 0.3791, 0.7363)).normalized()


def _prepare(obj, cap=250):
    """World-space BVH + bbox + sample points for one object. Two sample sets:
      verts   — vertex-only downsample, for nearest-surface gap/distance reads.
      samples — verts PLUS face centroids, for the signed inside test: a matched-footprint
                interpenetration (chain link, sunk marker, two boxes sharing a wall) lives
                at FACE CENTERS, where every vertex sits on the shared wall and is sign-
                ambiguous — so a vert-only test misses it.
    `closed` records whether the mesh is watertight (every edge has two faces), which
    decides the inside test: robust ray-parity for a closed solid, the nearest-face
    normal for an open shell (where 'inside' is only locally defined)."""
    bm = eval_world_bmesh(obj)
    if bm is None or not bm.verts:
        if bm:
            bm.free()
        return None
    bvh = BVHTree.FromBMesh(bm)
    closed = bool(bm.edges) and all(len(e.link_faces) == 2 for e in bm.edges)
    verts = [v.co.copy() for v in bm.verts]
    faces = [f.calc_center_median() for f in bm.faces]
    vstep = max(1, len(verts) // cap)
    vsample = verts[::vstep]
    allpts = verts + faces
    astep = max(1, len(allpts) // cap)
    sample = allpts[::astep]
    bm.free()
    return {"name": obj.name, "bvh": bvh, "verts": vsample, "samples": sample,
            "bbox": world_bbox(obj), "closed": closed}


def _bbox_contains(point, bbox, pad):
    """Is point within bbox (expanded by pad)? A point OUTSIDE a mesh's bbox is provably
    OUTSIDE its solid — the cheap, exact gate that kills the long-range false 'inside'
    behind the old fictional penetration depths (a part's far interior point reading as
    buried tens of mm inside a distant neighbour)."""
    return (bbox[0] - pad <= point.x <= bbox[3] + pad and
            bbox[1] - pad <= point.y <= bbox[4] + pad and
            bbox[2] - pad <= point.z <= bbox[5] + pad)


def _inside_parity(bvh, point):
    """Robust inside test for a CLOSED mesh: count surface crossings along a fixed ray
    from `point`; odd ⇒ inside. Re-casts just past each hit until the ray exits. Stable
    where the single nearest-face normal fails — far points and non-convex shells."""
    origin = point.copy()
    eps = 1e-6
    crossings = 0
    for _ in range(64):                      # backstop: no real mesh crosses a ray 64×
        hit = bvh.ray_cast(origin, _PARITY_DIR)
        if hit[0] is None:
            break
        crossings += 1
        origin = hit[0] + _PARITY_DIR * eps
    return (crossings % 2) == 1


def _signed_distance(point, dst):
    """Signed nearest-surface distance from `point` to dst's mesh: + outside, − inside.
    The ONE primitive both check_clearance and the penetration read are built on, so the
    two can never disagree on clears-vs-penetrates. In-bbox gate first (provably outside),
    then ray-parity for a closed solid / nearest-face normal for an open shell."""
    loc, normal, idx, dist = dst["bvh"].find_nearest(point)
    if loc is None:
        return None
    if not _bbox_contains(point, dst["bbox"], _TOUCH):
        return dist                          # outside the bbox ⇒ outside the solid
    if dst["closed"]:
        inside = _inside_parity(dst["bvh"], point)
    else:
        inside = (point - loc).dot(normal) < 0.0
    return -dist if inside else dist


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


def _penetration_depth(src, dst):
    """How far src crosses INSIDE dst's solid, in metres (0 = no crossing). The deepest of
    src's SURFACE samples (verts + face centroids) that lies inside dst, measured by the
    shared signed-distance primitive — so it reconciles with check_clearance by
    construction (same test), and a SEATED part (donut in a well — interior in the open
    cavity, OUTSIDE dst's solid) reads 0 (G107). Capped at the thinnest axis of the bbox
    overlap, the hard physical ceiling on how deep the shared volume can be — this is what
    kills the fictional 'penetrating 80mm' on an 8mm part."""
    worst = 0.0
    for p in src["samples"]:
        sd = _signed_distance(p, dst)
        if sd is not None and sd < 0.0 and -sd > worst:
            worst = -sd
    if worst <= 0.0:
        return 0.0
    ox, oy, oz = _bbox_overlaps(src["bbox"], dst["bbox"])
    cap = min(ox, oy, oz)
    return min(worst, cap) if cap > 0 else worst


def auto_proximity_note(obj_name):
    """G77 — after a placement op, the single highest-signal spatial fact the agent would
    otherwise hand-compute: does the just-placed object now PENETRATE a neighbour? Surfaced
    UNASKED in the status block so verification is effortless — the agent never has to
    remember to run `feel op=contacts`. Cheap: AABB pre-filter, then a BVH only on the few
    candidates whose bbox actually overlaps. Factual, not alarmist — interpenetration is
    correct for a seated / sunk / linked part; the note lets the agent JUDGE. Returns a note
    string, or None when the part sits clear (no note → no noise)."""
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != 'MESH':
        return None
    me = _prepare(obj)
    if me is None:
        return None
    cands = [o for o in scene_mesh_objects()
             if o.name != obj_name
             and _bbox_separation(me["bbox"], world_bbox(o)) <= _TOUCH]
    pens = []
    for o in cands[:8]:                     # bound the BVH builds on dense scenes
        p = _prepare(o)
        if p is None:
            continue
        # Real crossing: bboxes overlap on every axis (the robust old signal, kept) AND the
        # solids actually cross (signed inside-distance). A part SEATED in a recess overlaps
        # bboxes without crossing, so it no longer false-flags 'penetrates Nmm' unasked on
        # every placement (G107).
        ox, oy, oz = _bbox_overlaps(me["bbox"], p["bbox"])
        pen = max(_penetration_depth(me, p), _penetration_depth(p, me))
        if ox > _TOUCH and oy > _TOUCH and oz > _TOUCH and pen > _TOUCH:
            depth_mm = round(pen * 1000, 1)
            if depth_mm >= 0.3:             # ignore sub-0.3mm grazes
                pens.append((o.name, depth_mm))
    if not pens:
        return None
    pens.sort(key=lambda t: -t[1])
    parts = ", ".join(f"{n} {d}mm" for n, d in pens[:3])
    return (f"spatial: '{obj_name}' now penetrates {parts} — intended for a seated/sunk/"
            f"linked part, a bug (overlap / z-fight) if not. `feel op=contacts` for the full read.")


def check_contacts(params):
    """Per target part, how it relates to its neighbours: connected (touching),
    floating (gap in mm), or penetrating (depth in mm). Reports facts, makes no
    judgement — interpenetration is correct for chain links and sunk markers.

    G32: ALL penetrating neighbours are surfaced (not just the single nearest), so a
    deep cross can't hide behind a closer touch, and each part gets a combined one-line
    read ('connected to base · penetrating peg 6mm')."""
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
            results.append({"object": o.name, "relation": "alone", "other": None,
                            "summary": "alone in scene"})
            continue
        others.sort(key=lambda p: _bbox_separation(me["bbox"], p["bbox"]))

        # Exact surface test only for bbox-overlapping candidates — penetration and
        # touch both require near-zero bbox separation, and the list is sorted, so we
        # stop at the first clearly-separated neighbour. This is where a hidden
        # penetration would otherwise be capped away.
        penetrations, touching = [], []
        for p in others:
            if _bbox_separation(me["bbox"], p["bbox"]) > _TOUCH:
                break
            gap = min(_surface_gap(me, p), _surface_gap(p, me))
            ox, oy, oz = _bbox_overlaps(me["bbox"], p["bbox"])
            # Penetration requires BOTH the bboxes to overlap on every axis (the old robust
            # signal — kept, so nothing new is ever flagged) AND the solids to actually
            # CROSS, measured as a signed inside-distance. The signed gate is what stops a
            # part merely SEATED in a recess (a donut in a plate well) from reading
            # 'penetrating <well-depth>mm' off the bbox overlap alone (G107). A genuine
            # matched-footprint interpenetration (sunk marker / chain link, G32) still
            # crosses, so it stays caught — now reported with a true inside-depth.
            pen = max(_penetration_depth(me, p), _penetration_depth(p, me))
            if ox > _TOUCH and oy > _TOUCH and oz > _TOUCH and pen > _TOUCH:
                penetrations.append({"other": p["name"],
                                     "depth_mm": round(pen * 1000, 1)})
            elif gap <= _TOUCH:
                touching.append(p["name"])

        # Nearest neighbour by bbox separation, for the floating context/fallback.
        nearest = others[0]
        near_gap = min(_surface_gap(me, nearest), _surface_gap(nearest, me))

        # Primary single-read relation (back-compat): penetration takes priority over
        # a touch, a touch over a float.
        if penetrations:
            deepest = max(penetrations, key=lambda d: d["depth_mm"])
            rel = {"object": o.name, "relation": "penetrating",
                   "other": deepest["other"], "depth_mm": deepest["depth_mm"]}
        elif touching:
            rel = {"object": o.name, "relation": "connected", "other": touching[0]}
        else:
            rel = {"object": o.name, "relation": "floating", "other": nearest["name"],
                   "gap_mm": round(near_gap * 1000, 1)}

        # Every penetration surfaced, plus a combined one-line picture (G32).
        if penetrations:
            rel["penetrating"] = penetrations
        seg = []
        if touching:
            seg.append("connected to " + ", ".join(touching))
        for d in sorted(penetrations, key=lambda d: -d["depth_mm"]):
            seg.append(f"penetrating {d['other']} {d['depth_mm']}mm")
        if not touching and not penetrations:
            seg.append(f"nearest {nearest['name']} floating {round(near_gap * 1000, 1)}mm")
        rel["summary"] = " · ".join(seg)
        results.append(rel)
    return {"success": True, "contacts": results,
            "provenance": measurement_provenance(report_objs)}


# ─────────────────────────── resting (P10) ───────────────────────────

def _support_below(obj, prepared, zmin):
    """Object whose top sits at obj's bottom with an xy overlap, or None (floor).

    Skips any candidate fully CONTAINED within obj's bbox — a vessel's own contents
    (coffee inside a mug). A part cannot rest on something it encloses, so without this
    the contained object hijacks the support read and reports a phantom 'sunk Nmm'
    against its top while the real external support (the table) is ignored (G165). The
    container then correctly falls through to its true support below.
    """
    o_bb = world_bbox(obj)
    eps = 0.002
    best = None
    for name, p in prepared.items():
        if name == obj.name:
            continue
        b = p["bbox"]
        contained = (b[0] >= o_bb[0] - eps and b[3] <= o_bb[3] + eps and
                     b[1] >= o_bb[1] - eps and b[4] <= o_bb[4] + eps and
                     b[2] >= o_bb[2] - eps and b[5] <= o_bb[5] + eps)
        if contained:
            continue
        xy_overlap = (o_bb[0] < b[3] and o_bb[3] > b[0] and o_bb[1] < b[4] and o_bb[4] > b[1])
        if not xy_overlap:
            continue
        # its top near our bottom (within 5mm above or below)
        if abs(b[5] - zmin) < 0.005 or (b[5] >= zmin - 0.005 and b[2] <= zmin + 0.005):
            if best is None or b[5] > best[1]:
                best = (name, b[5])
    return best


def _surface_under(low_verts, bvh):
    """The actual height the part rests ON: cast straight DOWN from the part's lowest
    verts onto the support's BVH and take the highest hit. Unlike a candidate's bbox TOP,
    this is the real load-bearing surface — the well FLOOR a donut sits in, not the plate
    RIM that merely overlaps its footprint and reads 5mm higher (G107). Returns the
    highest hit z, or None if nothing lies below any sampled vert."""
    down = mathutils.Vector((0.0, 0.0, -1.0))
    best = None
    for v in low_verts:
        loc = bvh.ray_cast(mathutils.Vector((v.x, v.y, v.z + 0.05)), down)[0]
        if loc is not None and (best is None or loc.z > best):
            best = loc.z
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
        bbox_top_z = support[1] if support else 0.0

        # _support_below picks the support by bbox overlap and hands back its bbox TOP.
        # For a CONCAVE support (a plate well, a bowl, a recessed seat) that top is the
        # RIM, not the floor the part actually rests on — so measuring clearance against it
        # reports a properly-seated part as "sunk" by the well depth, a confident wrong
        # number with no hint of the assumption (G107). Recast the datum to the real
        # load-bearing surface: the highest geometry of that object directly BENEATH the
        # part's own lowest verts.
        support_z = bbox_top_z
        rim_above = 0.0
        if support is not None:
            low = [v for v in me["verts"] if v.z <= zmin + 0.002]
            surf_z = _surface_under(low or me["verts"], prepared[support_name]["bvh"])
            if surf_z is not None:
                support_z = surf_z
                rim_above = bbox_top_z - surf_z  # how far the rim sits above the floor
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

        result = {
            "object": o.name,
            "support": support_name,
            "support_z": round(support_z, 4),
            "contacts": len(contacts),
            "clearance_mm": round(clearance * 1000, 1),
            "state": ("floating" if clearance > _TOUCH else
                      "sunk" if clearance < -_TOUCH else "resting"),
            "com_over_support": com_over,
            "tip_direction": tip_dir,
        }
        # Legibility (G107): when the support is concave — its rim sits well above the
        # surface the part rests on — name BOTH the datum used AND the rim it is NOT, so a
        # rim/floor mix-up can never again pass as a confident "sunk Nmm". Silent for flat
        # supports (rim_above≈0), keeping the common case noise-free.
        if rim_above > _TOUCH:
            result["note"] = (
                f"measured against {support_name}'s surface beneath the part "
                f"(z={round(support_z, 4)}m); its rim/bbox-top is {round(rim_above * 1000, 1)}mm "
                f"higher (z={round(bbox_top_z, 4)}m) and is not load-bearing here")
        # G145: a subdivided support (cup/bowl with no bottom loop cut) has an evaluated
        # interior floor that can sit off the cage, so a "resting (0 mm)" read can be a
        # faithful measurement of a wrong floor. Flag it.
        from .common import subdiv_floor_caveat
        caveat = subdiv_floor_caveat(bpy.data.objects.get(support_name))
        if caveat:
            result["warning"] = caveat
        results.append(result)
    return {"success": True, "resting": results,
            "provenance": measurement_provenance(report_objs)}


# ─────────────────────────── clearance (G98) ───────────────────────────

def check_clearance(params):
    """G98: SIGNED nearest-surface clearance — 'is my shell everywhere OUTSIDE the
    surface it wraps?'. The one read a bbox-overlap `contacts` number can't give: a
    garment that correctly envelops a torso and one that stabs through the ribs produce
    the SAME alarming bbox figure, because the wrapped body is supposed to live inside
    the shell's bounding box. This signs the distance instead.

    For each sampled SHELL vert, find the nearest point on the SURFACE and sign the
    distance by the surface's outward normal: positive ⇒ the shell vert sits OUTSIDE the
    surface (correct clearance), negative ⇒ the shell dips INSIDE the surface (it's
    stabbing through). Reports min/mean clearance over the clearing verts, the fraction of
    the shell outside the surface, and the worst penetration patches with locations.

    General past clothing: armor over a body, a phone case over a phone, a lid over a jar,
    a press-fit sleeve — anything that must clear the surface it claddes.

    shell:     the cladding object (garment / case / armor / plating).
    surface:   the surface being wrapped (body / phone / jar).
    threshold: optional minimum clearance in mm; when given, adds a pass/fail `clears`.
    samples:   cap on shell verts sampled (default 2000).
    """
    shell_name = params.get("shell")
    surface_name = params.get("surface")
    threshold = params.get("threshold")
    shell = bpy.data.objects.get(shell_name) if shell_name else None
    surface = bpy.data.objects.get(surface_name) if surface_name else None
    if shell is None or surface is None:
        return {"error": f"need existing 'shell' and 'surface' meshes "
                         f"(shell={shell_name}, surface={surface_name})"}
    if shell.type != 'MESH' or surface.type != 'MESH':
        return {"error": "both 'shell' and 'surface' must be mesh objects"}
    if shell_name == surface_name:
        return {"error": "'shell' and 'surface' must be different objects"}

    # The surface is the `dst` solid (full-res BVH + bbox + closedness); the shell is
    # sampled (verts + face centroids) and each sample signed against it via the SHARED
    # _signed_distance primitive — the same one check_contacts uses, so a clearance read
    # and a contacts read can never disagree on clears-vs-penetrates.
    surf = _prepare(surface)
    if surf is None:
        return {"error": f"surface '{surface_name}' has no mesh geometry"}
    cap = max(1, int(params.get("samples", 2000)))
    shell_p = _prepare(shell, cap=cap)
    if shell_p is None:
        return {"error": f"shell '{shell_name}' has no mesh geometry"}

    outside = []          # signed distances (m) for shell samples OUTSIDE the surface
    inside = []           # (depth_mm, [x,y,z]) for shell samples INSIDE the surface
    for p in shell_p["samples"]:
        sd = _signed_distance(p, surf)
        if sd is None:
            continue
        if sd >= 0:
            outside.append(sd)
        else:
            inside.append((round(-sd * 1000, 2), [round(c, 4) for c in p]))

    total = len(outside) + len(inside)
    if total == 0:
        return {"error": "no shell verts could be sampled against the surface"}
    frac_outside = len(outside) / total
    min_clear_mm = round(min(outside) * 1000, 2) if outside else None
    mean_clear_mm = round(sum(outside) / len(outside) * 1000, 2) if outside else None
    inside.sort(key=lambda t: -t[0])
    worst = [{"depth_mm": d, "at": loc} for d, loc in inside[:8]]

    result = {
        "success": True,
        "shell": shell_name,
        "surface": surface_name,
        "samples": total,
        "fraction_outside": round(frac_outside, 4),
        "min_clearance_mm": min_clear_mm,
        "mean_clearance_mm": mean_clear_mm,
        "penetrations": len(inside),
        "worst_penetrations": worst,
        "provenance": measurement_provenance([shell, surface]),
    }
    if threshold is not None:
        thr = float(threshold)
        result["threshold_mm"] = thr
        result["clears"] = bool(len(inside) == 0 and min_clear_mm is not None
                                and min_clear_mm >= thr)
    return result


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


def _visible_surface(scene, depsgraph, cam, obj, cap=160):
    """G131 — visibility of the surface a viewer would actually SEE, not the whole bbox.
    Samples only FRONT-FACING verts (normal pointing toward the camera) and counts how many
    are unoccluded. A submerged coffee surface is mostly back-faces + sides buried in opaque
    ceramic — counting those as 'occluded' made it read 100% hidden even with its top plainly
    visible through the mouth. Returns (front_facing_count, visible_count)."""
    bm = eval_world_bmesh(obj)
    if bm is None or not bm.verts:
        if bm:
            bm.free()
        return 0, 0
    bm.normal_update()
    origin = cam.matrix_world.translation
    n = len(bm.verts)
    step = max(1, n // cap)
    front = vis = 0
    for i in range(0, n, step):
        v = bm.verts[i]
        w = v.co
        to_cam = origin - w
        dist = to_cam.length
        if dist < 1e-6:
            continue
        # front-facing: the vertex normal points toward the camera
        if v.normal.dot(to_cam) <= 0:
            continue
        front += 1
        hit, loc, nrm, idx, hitobj, mat = scene.ray_cast(
            depsgraph, origin, (-to_cam).normalized(), distance=dist - 1e-4)
        if not (hit and hitobj is not None and hitobj.name != obj.name):
            vis += 1
    bm.free()
    return front, vis


def check_visible(params):
    """G131 — answer 'would a viewer SEE this object's surface from the camera?' yes/no, plus
    the fraction of its FRONT-FACING surface that's unoccluded. The read for a recessed part
    (liquid in a vessel, a gem in a setting) whose whole-bbox occlusion says 'hidden' but
    whose visible face is the point. target= object(s); camera= optional."""
    scene = bpy.context.scene
    from .common import resolve_camera
    cam, err = resolve_camera(params.get("camera"), scene)
    if err:
        return {"error": err}
    report_objs, err = _report_targets(params)
    if err:
        return {"error": err}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    thresh = float(params.get("min_pct", 2.0)) / 100.0
    results = []
    for o in report_objs:
        front, vis = _visible_surface(scene, depsgraph, cam, o)
        frac = (vis / front) if front else 0.0
        results.append({
            "object": o.name,
            "visible": front > 0 and frac > thresh,
            "visible_surface_pct": round(frac * 100, 1),
            "front_facing_sampled": front,
        })
    return {"success": True, "camera": cam.name, "visibility": results}


def _parse_aspect(spec):
    """Parse a target-frame spec 'WxH' (pixels) or 'W:H' (ratio) → (res_x, res_y) or
    None. A ratio keeps a 1000-px long edge so the numbers stay readable."""
    spec = (spec or "").strip().lower()
    if not spec:
        return None
    sep = "x" if "x" in spec else (":" if ":" in spec else None)
    if sep is None:
        return None
    try:
        a, b = (float(p) for p in spec.split(sep, 1))
    except (ValueError, TypeError):
        return None
    if a <= 0 or b <= 0:
        return None
    if sep == "x":
        return int(round(a)), int(round(b))
    # ratio → scale so the long edge is 1000 px
    scale = 1000.0 / max(a, b)
    return int(round(a * scale)), int(round(b * scale))


def _frame_ref(scene):
    """The reference frame the coverage % is measured against — resolution + a word.
    G22: world_to_camera_view fits to the RENDER aspect, so the same camera reads a
    different frame_pct once the resolution changes. Make that reference explicit so
    readings are comparable call-to-call instead of silently shifting underfoot."""
    r = scene.render
    rx = int(r.resolution_x * (r.pixel_aspect_x or 1.0))
    ry = int(r.resolution_y * (r.pixel_aspect_y or 1.0))
    if rx == ry:
        word = "square"
    elif rx > ry:
        word = "landscape"
    else:
        word = "portrait"
    return {"resolution": [r.resolution_x, r.resolution_y], "aspect": word,
            "aspect_ratio": round(rx / ry, 3) if ry else None}


def check_framing(params):
    """Camera-space report per target: frame coverage %, which edges clip (and by
    how much), whether it's behind the camera, and % occluded by other objects.
    The deterministic answer to 'is it still cropped?' — no test render required.
    `aspect`='WxH'|'W:H' validates framing against an INTENDED output before a render
    (temporarily, then restores the scene's own resolution)."""
    scene = bpy.context.scene
    # G36: resolve the default camera the SAME way render does — named → scene camera
    # → sole/first camera. Previously this preflight errored "no camera" on an unset
    # scene.camera while render happily fell back and shot the frame, so the preflight
    # couldn't be trusted as the render's ground truth.
    from .common import resolve_camera
    cam, err = resolve_camera(params.get("camera"), scene)
    if err:
        return {"error": err}

    report_objs, err = _report_targets(params)
    if err:
        return {"error": err}
    depsgraph = bpy.context.evaluated_depsgraph_get()

    # Optional target aspect: temporarily retarget the render frame so coverage is
    # computed for the output the agent intends, then restore exactly what was there.
    want = _parse_aspect(params.get("aspect"))
    saved = None
    if want is not None:
        r = scene.render
        saved = (r.resolution_x, r.resolution_y)
        r.resolution_x, r.resolution_y = want

    try:
        frame_ref = _frame_ref(scene)
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
            front, vis = _visible_surface(scene, depsgraph, cam, o)
            vis_pct = round((vis / front) * 100, 1) if front else 0.0
            results.append({
                "object": o.name,
                "frame_pct": [round(cov["frac_w"] * 100, 1), round(cov["frac_h"] * 100, 1)],
                "behind_camera": not cov["in_front"],
                "clipped": clip,
                "occluded_pct": round(occ * 100, 1),
                # G131: the meaningful 'can a viewer see it' number — front-facing surface
                # visible — distinct from the whole-bbox occluded_pct (which a recessed part
                # like liquid-in-a-vessel pegs at ~100% even when its top is plainly visible).
                "visible_surface_pct": vis_pct,
            })
    finally:
        if saved is not None:
            scene.render.resolution_x, scene.render.resolution_y = saved

    return {"success": True, "camera": cam.name, "framing": results,
            "frame_ref": frame_ref}


# ─────────────────────────── check_focus (G115) ───────────────────────────

_FSTOPS = [1.0, 1.4, 2.0, 2.8, 4.0, 5.6, 8.0, 11.0, 16.0, 22.0, 32.0]


def _dof_limits(f_mm, n_fstop, coc_mm, focus_m):
    """Near/far depth-of-field limits (m) + hyperfocal (m), thin-lens model. Df is None
    when the far limit is at/beyond infinity (subject focus ≥ hyperfocal)."""
    f = f_mm / 1000.0
    c = coc_mm / 1000.0
    s = max(focus_m, f + 1e-6)
    H = (f * f) / (n_fstop * c) + f
    sf = s - f
    dn = (H * s) / (H + sf)
    df = (H * s) / (H - sf) if sf < H else None      # None = ∞
    return dn, df, H


def _axis_depth_range(corners, cam_loc, forward):
    ds = [(p - cam_loc).dot(forward) for p in corners]
    return min(ds), max(ds)


def check_focus(params):
    """G115 — VALIDATE depth of field: at the camera's current (or a hypothetical) lens +
    aperture + focus, where do the near/far SHARP limits fall, and does each target's full
    depth sit inside that in-focus slab? The deterministic sharpness check the 'don't read
    the render back' rule otherwise leaves blind. Can also RESOLVE the widest aperture
    (smallest f-number) that keeps a subject fully sharp.

    camera:          camera name (empty = scene cam).
    targets:         objects to test (empty = the camera's focus_object, else all meshes).
    aperture:        hypothetical f-stop to test (empty = the camera's current f-stop).
    focus_distance / focus_object: hypothetical focus (empty = the camera's current focus).
    resolve_for:     object name — also return the widest aperture that keeps it fully sharp.
    """
    import mathutils
    from .common import resolve_camera, world_bbox_corners, scene_mesh_objects
    scene = bpy.context.scene
    cam, err = resolve_camera(params.get("camera"), scene)
    if err:
        return {"error": err}
    cd = cam.data
    dof = cd.dof

    f_mm = float(cd.lens)
    coc_mm = float(cd.sensor_width) / 1500.0          # acceptable circle of confusion
    n_fstop = params.get("aperture")
    n_fstop = float(n_fstop) if n_fstop is not None else float(dof.aperture_fstop)

    cam_mat = cam.matrix_world
    cam_loc = cam_mat.translation
    forward = (cam_mat.to_3x3() @ mathutils.Vector((0, 0, -1))).normalized()

    def _obj_focus_distance(name):
        o = bpy.data.objects.get(name)
        if o is None:
            return None
        corners = world_bbox_corners(o)
        center = sum(corners, mathutils.Vector()) / 8.0
        return (center - cam_loc).dot(forward)

    fo_name = params.get("focus_object") or (dof.focus_object.name if dof.focus_object else None)
    if params.get("focus_distance") is not None:
        focus_m = float(params["focus_distance"])
    elif fo_name:
        focus_m = _obj_focus_distance(fo_name)
        if focus_m is None:
            return {"error": f"focus_object '{fo_name}' not found"}
    else:
        focus_m = float(dof.focus_distance)

    # which objects to test
    tnames = params.get("targets")
    if tnames:
        report_objs, terr = _report_targets(params)
        if terr:
            return {"error": terr}
    elif fo_name and bpy.data.objects.get(fo_name):
        report_objs = [bpy.data.objects[fo_name]]
    else:
        report_objs = scene_mesh_objects()

    dn, df, H = _dof_limits(f_mm, n_fstop, coc_mm, focus_m)
    dof_slab = None if df is None else round((df - dn) * 1000, 1)   # mm

    targets = []
    for o in report_objs:
        near_t, far_t = _axis_depth_range(world_bbox_corners(o), cam_loc, forward)
        depth_mm = round((far_t - near_t) * 1000, 1)
        in_front = far_t > 0
        within_near = near_t >= dn - 1e-6
        within_far = (df is None) or (far_t <= df + 1e-6)
        sharp = in_front and within_near and within_far
        # fraction of the object's own depth that lands inside the slab
        lo = max(near_t, dn)
        hi = far_t if df is None else min(far_t, df)
        overlap = max(0.0, hi - lo)
        span = max(far_t - near_t, 1e-9)
        frac = max(0.0, min(1.0, overlap / span)) if in_front else 0.0
        # Other ways a frame goes soft, without reading the render (SPEC-17):
        #  • effective resolution — a subject this small in frame reads soft however well-focused
        #  • motion — flag whether this object is animated (smear risk; see scene 'motion_blur')
        cov = camera_coverage(scene, cam, o)
        rx, ry = int(scene.render.resolution_x), int(scene.render.resolution_y)
        frame_px = [int(round(cov["frac_w"] * rx)), int(round(cov["frac_h"] * ry))]
        animated = bool(o.animation_data and o.animation_data.action)
        targets.append({
            "object": o.name,
            "depth_mm": depth_mm,
            "near_m": round(near_t, 4), "far_m": round(far_t, 4),
            "in_focus": bool(sharp),
            "in_focus_pct": round(frac * 100, 1),
            "frame_px": frame_px,
            "undersized": max(frame_px) < 64,
            "animated": animated,
        })

    result = {
        "success": True, "camera": cam.name,
        "use_dof": bool(dof.use_dof),
        "lens_mm": round(f_mm, 2),
        "aperture_fstop": round(n_fstop, 2),
        "focus_distance_m": round(focus_m, 4),
        "focus_object": fo_name,
        "dof_near_m": round(dn, 4),
        "dof_far_m": None if df is None else round(df, 4),
        "dof_slab_mm": dof_slab,
        "hyperfocal_m": round(H, 4),
        "motion_blur": {
            "enabled": bool(getattr(scene.render, "use_motion_blur", False)),
            "shutter": round(float(getattr(scene.render, "motion_blur_shutter", 0.0)), 3),
        },
        "targets": targets,
    }

    # aperture resolver: the widest aperture (smallest f) that keeps resolve_for fully sharp.
    resolve_for = params.get("resolve_for")
    if resolve_for:
        ro = bpy.data.objects.get(resolve_for)
        if ro is None:
            result["resolve_error"] = f"resolve_for '{resolve_for}' not found"
        else:
            near_t, far_t = _axis_depth_range(world_bbox_corners(ro), cam_loc, forward)
            chosen = None
            for n in _FSTOPS:
                rdn, rdf, _ = _dof_limits(f_mm, n, coc_mm, focus_m)
                if near_t >= rdn - 1e-6 and (rdf is None or far_t <= rdf + 1e-6):
                    chosen = n
                    break
            result["resolve_for"] = resolve_for
            result["resolved_aperture"] = chosen   # None = even f/32 can't hold it sharp
    return result


# ─────────────────────────── check_exposure (SPEC-17) ───────────────────────────

# Nominal "well-exposed" irradiance anchor (relative W/m²). NOT a calibrated photometric
# value — a reference point so stops-over/under are comparable. The verdict bands around it
# are deliberately WIDE: this flags GROSS over/under-exposure, never fine aesthetic taste.
_EXPOSURE_REF = 5.0
_BLOWN_STOPS = 4.0      # > +4 stops over nominal (≈16×) → likely blown
_CRUSH_STOPS = -4.0     # < −4 stops under nominal (≈1/16×) → likely crushed


def _scene_lights(scene):
    return [o for o in scene.objects if o.type == 'LIGHT']


def _light_irradiance(light_obj, point):
    """Estimated direct irradiance (relative W/m²) a light delivers to a world point —
    ignoring the surface normal (treats the point as facing the light, an upper bound) and
    any occlusion (shadow is reported separately). Returns (irradiance, in_cone)."""
    ld = light_obj.data
    energy = float(getattr(ld, "energy", 0.0))
    lt = ld.type
    lpos = light_obj.matrix_world.translation
    to_point = point - lpos
    dist = to_point.length

    if lt == 'SUN':
        # A sun's 'energy' IS irradiance (W/m²), distance-independent.
        return energy, True
    if dist < 1e-6:
        return 0.0, True

    # Point-source inverse-square falloff: P / (4π d²). Spot/area share this model
    # (area-light directionality is an explicit unmodeled limit).
    e = energy / (4.0 * math.pi * dist * dist)

    in_cone = True
    if lt == 'SPOT':
        forward = (light_obj.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))).normalized()
        cos_ang = max(-1.0, min(1.0, forward.dot(to_point.normalized())))
        ang = math.acos(cos_ang)
        half = float(getattr(ld, "spot_size", math.pi)) * 0.5
        if ang > half:
            return 0.0, False
        blend = float(getattr(ld, "spot_blend", 0.0))
        inner = half * (1.0 - blend)
        if ang > inner and half > inner:
            e *= max(0.0, 1.0 - (ang - inner) / (half - inner))
    return e, in_cone


def _shadow_fraction(scene, depsgraph, light_obj, obj, cap=80):
    """Fraction of sampled points on obj that are blocked from the light by OTHER objects —
    how much of the subject the light fails to reach."""
    bm = eval_world_bmesh(obj)
    if bm is None or not bm.verts:
        if bm:
            bm.free()
        return 0.0
    lt = light_obj.data.type
    lpos = light_obj.matrix_world.translation
    sun_to = None
    if lt == 'SUN':
        # parallel rays arrive from the direction opposite the sun's forward (-Z).
        sun_to = -(light_obj.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1))).normalized()
    n = len(bm.verts)
    step = max(1, n // cap)
    total = blocked = 0
    for i in range(0, n, step):
        w = bm.verts[i].co
        if sun_to is not None:
            d = sun_to
            dist = 1e4
        else:
            d = lpos - w
            dist = d.length
            if dist < 1e-6:
                continue
            d = d.normalized()
        total += 1
        hit, loc, nrm, idx, hitobj, mat = scene.ray_cast(
            depsgraph, w + d * 1e-4, d, distance=dist - 2e-4)
        if hit and hitobj is not None and hitobj.name != obj.name:
            blocked += 1
    bm.free()
    return blocked / total if total else 0.0


def _world_ambient(scene):
    """Ambient irradiance from the world background (relative W/m²): π·strength·luminance.
    An HDRI/linked color can't be cheaply averaged, so it's proxied at mid-luminance 1.0."""
    world = scene.world
    if world is None:
        return 0.0
    if not world.use_nodes:
        col = getattr(world, "color", (0.0, 0.0, 0.0))
        lum = 0.2126 * col[0] + 0.7152 * col[1] + 0.0722 * col[2]
        return math.pi * lum
    bg = next((n for n in world.node_tree.nodes if n.type == 'BACKGROUND'), None)
    if bg is None:
        return 0.0
    strength = float(bg.inputs['Strength'].default_value)
    if bg.inputs['Color'].is_linked:
        lum = 1.0
    else:
        col = bg.inputs['Color'].default_value
        lum = 0.2126 * col[0] + 0.7152 * col[1] + 0.0722 * col[2]
    return math.pi * strength * lum


def check_exposure(params):
    """SPEC-17 — VALIDATE the lighting LEVEL deterministically, without reading the render
    back. Estimates the direct irradiance each light delivers to every target, the key:fill
    ratio, and how much of the subject sits in shadow. Flags GROSS over/under-exposure;
    whether the result actually LOOKS right is the human's call.

    ESTIMATE, with stated limits: direct light only (no indirect/GI bounce), no surface
    albedo, no area-light directionality, and the view-transform rolloff (AgX/Filmic) is NOT
    applied. It reliably catches a light 100× too strong, a subject lit only by a faint
    ambient floor, a runaway key:fill, or a subject in shadow — not whether a given highlight
    is pleasingly clipped.

    targets:      objects to test (empty = every visible mesh).
    resolve_for:  light name — also solve the energy that brings the first target to ~0 stops.
    """
    scene = bpy.context.scene
    if params.get("targets"):
        report_objs, err = _report_targets(params)
        if err:
            return {"error": err}
    else:
        report_objs = scene_mesh_objects()
    if not report_objs:
        return {"error": "no target meshes to check"}

    lights = _scene_lights(scene)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ambient = _world_ambient(scene)
    vs = scene.view_settings
    exposure_stops = float(getattr(vs, "exposure", 0.0))
    view_xf = getattr(vs, "view_transform", "")

    targets = []
    for o in report_objs:
        center = mathutils.Vector(world_center(o))
        contribs = []
        for L in lights:
            e, in_cone = _light_irradiance(L, center)
            if e <= 0.0:
                contribs.append({"light": L.name, "type": L.data.type, "irradiance": 0.0,
                                 "in_cone": in_cone, "shadow_pct": None, "_eff": 0.0})
                continue
            shadow = _shadow_fraction(scene, depsgraph, L, o)
            contribs.append({"light": L.name, "type": L.data.type, "irradiance": round(e, 4),
                             "in_cone": in_cone, "shadow_pct": round(shadow * 100, 1),
                             "_eff": e * (1.0 - shadow)})
        eff = [c["_eff"] for c in contribs]
        total = ambient + sum(eff)
        eff_sorted = sorted(eff, reverse=True)
        ratio = (round(eff_sorted[0] / eff_sorted[1], 1)
                 if len(eff_sorted) >= 2 and eff_sorted[1] > 1e-9 else None)
        stops = math.log2(total / _EXPOSURE_REF) + exposure_stops if total > 1e-9 else -99.0
        key = max(contribs, key=lambda c: c["_eff"], default=None)
        key_shadow = key["shadow_pct"] if key and key["_eff"] > 0 else None
        for c in contribs:
            c.pop("_eff", None)
        targets.append({
            "object": o.name,
            "irradiance": round(total, 4),
            "stops": round(stops, 2),
            "likely_blown": stops > _BLOWN_STOPS,
            "likely_crushed": stops < _CRUSH_STOPS,
            "key_fill_ratio": ratio,
            "key_shadow_pct": key_shadow,
            "lit_by": sorted(contribs, key=lambda c: c["irradiance"], reverse=True),
        })

    result = {
        "success": True,
        "view_transform": view_xf,
        "exposure": round(exposure_stops, 3),
        "ambient": round(ambient, 4),
        "ref_irradiance": _EXPOSURE_REF,
        "lights": [{"name": L.name, "type": L.data.type,
                    "energy": round(float(getattr(L.data, "energy", 0.0)), 2)} for L in lights],
        "targets": targets,
        "note": ("direct-light estimate — no GI bounce, no albedo, no area directionality, "
                 "view-transform rolloff not applied; flags gross over/under + ratio + shadow"),
    }

    resolve_for = params.get("resolve_for")
    if resolve_for:
        L = bpy.data.objects.get(resolve_for)
        if L is None or L.type != 'LIGHT':
            result["resolve_error"] = f"resolve_for light '{resolve_for}' not found"
        else:
            o = report_objs[0]
            center = mathutils.Vector(world_center(o))
            e, _ = _light_irradiance(L, center)
            e_eff = e * (1.0 - _shadow_fraction(scene, depsgraph, L, o)) if e > 0 else 0.0
            total = result["targets"][0]["irradiance"]
            target_total = _EXPOSURE_REF * (2.0 ** (-exposure_stops))
            e_other = total - e_eff
            e_needed = target_total - e_other
            old_energy = float(getattr(L.data, "energy", 0.0))
            result["resolve_for"] = resolve_for
            if e_needed <= 0:
                result["resolved_energy"] = None   # other lights already exceed the target
            elif e_eff > 1e-9:
                result["resolved_energy"] = round(old_energy * (e_needed / e_eff), 1)
            else:
                result["resolved_energy"] = None   # this light reaches nothing (out of cone / shadowed)
    return result


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
    "check_clearance": check_clearance,
    "check_resting":  check_resting,
    "check_framing":  check_framing,
    "check_focus":    check_focus,
    "check_visible":  check_visible,
    "check_exposure": check_exposure,
    "trace_profile":  trace_profile,
    "diff_since":     diff_since,
}

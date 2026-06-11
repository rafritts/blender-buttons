"""Shared geometry/selection helpers used by most tool modules."""

import math

import bpy
import mathutils


def world_bbox(obj):
    """World-space bounding box: (xmin, ymin, zmin, xmax, ymax, zmax)."""
    bb = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    xs = [v.x for v in bb]; ys = [v.y for v in bb]; zs = [v.z for v in bb]
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def world_center(obj):
    """World-space bbox center of an object."""
    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    return ((xmin + xmax) * 0.5, (ymin + ymax) * 0.5, (zmin + zmax) * 0.5)


def nearby_objects(world_pos, exclude_names=(), max_count=3):
    """Return up to max_count nearest mesh objects to world_pos, sorted by distance."""
    px, py, pz = world_pos
    cands = []
    for o in bpy.context.scene.objects:
        if o.name in exclude_names or o.type != 'MESH':
            continue
        cx, cy, cz = world_center(o)
        d = math.sqrt((cx - px) ** 2 + (cy - py) ** 2 + (cz - pz) ** 2)
        cands.append((d, o.name, (cx, cy, cz)))
    cands.sort()
    return [
        {"name": n, "center": [round(c[0], 3), round(c[1], 3), round(c[2], 3)], "dist": round(d, 4)}
        for d, n, c in cands[:max_count]
    ]


def resolve_targets(targets, include_non_mesh=False):
    """Resolve a target spec into a list of bpy mesh objects.

    targets: str (single object or collection name), list[str], or None (-> active object).
    Collection names expand to all mesh objects inside (recursively).
    include_non_mesh: when True, collection expansion keeps non-mesh members too
        (curves, empties, armatures). Explicitly-named objects are always kept
        regardless of type; only collection expansion filtered them out, which let
        non-mesh members slip past the lint tools' excluded_non_mesh accounting
        (gaps.md S1b). Lint tools that report what they skipped pass True.
    Returns (objects, error). On error, objects is None.
    """
    if targets is None:
        obj = bpy.context.active_object
        if obj is None:
            return None, "No active object and no targets specified"
        return [obj], None

    if isinstance(targets, str):
        targets = [targets]

    if not isinstance(targets, list) or not targets:
        return None, "'targets' must be a non-empty string or list of strings"

    objs = []
    seen = set()
    for name in targets:
        obj = bpy.data.objects.get(name)
        coll = bpy.data.collections.get(name)
        if obj is None and coll is None:
            return None, f"Target '{name}' not found (no object or collection by that name)"
        if obj is not None and obj.name not in seen:
            objs.append(obj)
            seen.add(obj.name)
        if coll is not None:
            for o in coll.all_objects:
                if (include_non_mesh or o.type == 'MESH') and o.name not in seen:
                    objs.append(o)
                    seen.add(o.name)
    return objs, None


def has_material_slots(obj):
    """True if obj's data can carry material slots — i.e. it renders with a
    material. MESH, CURVE, SURFACE, FONT, and META all qualify; a beveled curve
    renders as a solid tube with ordinary material slots, so material tools must
    accept it, not just meshes."""
    return obj.data is not None and hasattr(obj.data, "materials")


def material_summary(obj):
    """Readable summary of an object's material slots — name plus the Principled
    BSDF values set_material writes. Setters need matching getters: this is what
    lets describe()/get_object_info() answer 'what material is on X?'."""
    if obj.data is None or not hasattr(obj.data, "materials"):
        return []
    out = []
    for slot_idx, mat in enumerate(obj.data.materials):
        if mat is None:
            out.append({"slot": slot_idx, "name": None})
            continue
        entry = {"slot": slot_idx, "name": mat.name}
        toon = mat.get("bb_toon")
        if toon is not None:
            # Toon materials are reported from their stored params, not by
            # parsing the cel node graph (which has no Principled BSDF).
            try:
                import json as _json
                entry["toon"] = _json.loads(toon)
            except (ValueError, TypeError):
                pass
        tex = mat.get("bb_texture")
        if tex is not None:
            try:
                import json as _json
                entry["texture"] = _json.loads(tex)
            except (ValueError, TypeError):
                pass
        if mat.use_nodes:
            bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if bsdf is not None:
                def _inp(key):
                    return bsdf.inputs[key].default_value if key in bsdf.inputs else None
                bc = _inp("Base Color")
                if bc is not None:
                    entry["base_color"] = [round(c, 3) for c in tuple(bc)[:4]]
                for key, label in (("metallic", "Metallic"), ("roughness", "Roughness"),
                                   ("alpha", "Alpha")):
                    v = _inp(label)
                    if v is not None:
                        entry[key] = round(float(v), 3)
                es = _inp("Emission Strength")
                if es is not None and float(es) > 0:
                    entry["emission_strength"] = round(float(es), 3)
                    ec = _inp("Emission Color")
                    if ec is None:
                        ec = _inp("Emission")
                    if ec is not None:
                        entry["emission_color"] = [round(c, 3) for c in tuple(ec)[:4]]
        out.append(entry)
    return out


def eval_world_bmesh(obj):
    """Return a NEW bmesh of obj's EVALUATED mesh (modifiers applied) with verts
    in WORLD space. Caller owns it and must call .free(). Returns None for objects
    that yield no mesh (empties, cameras, lights). This is the analysis primitive
    behind the tactile-introspection tools — they reason about final rendered
    geometry, so modifiers must be applied and the transform baked in."""
    import bmesh
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    try:
        me = obj_eval.to_mesh()
    except (RuntimeError, AttributeError):
        return None
    if me is None:
        return None
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(obj.matrix_world)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    obj_eval.to_mesh_clear()
    return bm


def object_bvh(obj):
    """World-space BVHTree for obj's evaluated mesh, or None if it has no mesh.
    BVH nearest-point / ray queries are milliseconds-cheap at hobby poly counts —
    the workhorse for contacts, resting, symmetry, and intersection checks."""
    from mathutils.bvhtree import BVHTree
    bm = eval_world_bmesh(obj)
    if bm is None:
        return None
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    return tree


def scene_mesh_objects():
    """All visible MESH objects in the active scene."""
    return [o for o in bpy.context.scene.objects if o.type == 'MESH']


def world_bbox_corners(obj):
    """The 8 world-space corners of obj's local bounding box."""
    return [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]


def region_words(bbox, p):
    """Name where a world point sits inside a bbox — e.g. 'top-left-front'. Lets
    introspection tools say WHERE something happened without leaking coordinates."""
    xmin, ymin, zmin, xmax, ymax, zmax = bbox

    def frac(v, lo, hi):
        return (v - lo) / (hi - lo) if (hi - lo) > 1e-9 else 0.5
    fx, fy, fz = frac(p.x, xmin, xmax), frac(p.y, ymin, ymax), frac(p.z, zmin, zmax)
    w = []
    if fz > 0.66: w.append("top")
    elif fz < 0.33: w.append("bottom")
    if fx > 0.66: w.append("right")
    elif fx < 0.33: w.append("left")
    if fy > 0.66: w.append("back")
    elif fy < 0.33: w.append("front")
    return "-".join(w) if w else "center"


def camera_coverage(scene, cam, obj):
    """Project obj's world bbox into camera view. Returns a dict:
      frac_w / frac_h : fraction of the frame width/height the bbox spans (0..1+),
      u_range / v_range : normalised frame extents (0..1 is on-frame),
      depth_range     : near/far corner depth (>0 is in front of the camera),
      in_front        : any corner is in front of the camera,
      clipped         : list of frame edges the bbox spills past (left/right/top/bottom).
    Pure matrix math — the deterministic answer to "is it framed?" without a render."""
    from bpy_extras.object_utils import world_to_camera_view
    us, vs, depths = [], [], []
    for c in world_bbox_corners(obj):
        co = world_to_camera_view(scene, cam, c)
        us.append(co.x); vs.append(co.y); depths.append(co.z)
    umin, umax = min(us), max(us)
    vmin, vmax = min(vs), max(vs)
    clipped = []
    if umin < 0.0: clipped.append("left")
    if umax > 1.0: clipped.append("right")
    if vmin < 0.0: clipped.append("bottom")
    if vmax > 1.0: clipped.append("top")
    return {
        "frac_w": umax - umin, "frac_h": vmax - vmin,
        "u_range": (umin, umax), "v_range": (vmin, vmax),
        "depth_range": (min(depths), max(depths)),
        "in_front": any(d > 0 for d in depths),
        "clipped": clipped,
    }


def activate(obj):
    """Make obj the sole selected + active object."""
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_scale(obj):
    """Bake object scale into mesh data so obj.scale becomes [1,1,1].
    Required for bevel and other width-based modifiers to behave uniformly."""
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

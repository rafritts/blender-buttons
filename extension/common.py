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


def eval_world_bbox(obj):
    """World-space bbox of obj's EVALUATED geometry — modifiers AND armature pose
    applied. `world_bbox` reads the base-mesh `bound_box`, so it reports REST
    placement; this reflects the deformed/posed shape, answering 'where is the
    posed part actually?' (gaps.md T6, also fixes the T2 DOF case). Computed from
    the evaluated mesh verts (correct under deform, where `bound_box` can lag).
    Falls back to `world_bbox` for objects with no evaluable mesh."""
    # X6: force a fresh re-evaluation of this object. An orphaned (timed-out) op can
    # leave the evaluated-mesh cache wedged so `evaluated_depsgraph_get()` hands back
    # a stale eval; retagging + updating makes the measured bounds reflect the real
    # geometry, never the ghost. Cheap at hobby poly counts.
    try:
        obj.update_tag()
        bpy.context.view_layer.update()
    except Exception:
        pass
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    try:
        me = obj_eval.to_mesh()
    except (RuntimeError, AttributeError):
        return world_bbox(obj)
    if me is None or not me.vertices:
        if me is not None:
            obj_eval.to_mesh_clear()
        return world_bbox(obj)
    mw = obj_eval.matrix_world
    xs, ys, zs = [], [], []
    for v in me.vertices:
        w = mw @ v.co
        xs.append(w.x); ys.append(w.y); zs.append(w.z)
    obj_eval.to_mesh_clear()
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def eval_world_center(obj):
    """World-space center of obj's EVALUATED (posed/deformed) geometry."""
    xmin, ymin, zmin, xmax, ymax, zmax = eval_world_bbox(obj)
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


def linked_status(obj):
    """Library-link status of an object, or None if it's local. Returns a short
    tag like 'lib:Spring.blend' (linked, read-only) or 'override:Spring.blend'
    (a local library override, editable). Library-linked DATA can't be edited in
    place without an override (gaps.md U10)."""
    import os
    data = getattr(obj, "data", None)
    lib = obj.library or (data.library if data is not None else None)
    if lib is None:
        return None
    fname = os.path.basename(lib.filepath) if lib.filepath else "?"
    tag = "override" if obj.override_library is not None else "lib"
    return f"{tag}:{fname}"


def is_linked_data(obj):
    """True if obj's data is library-linked and NOT locally overridden — i.e. it
    cannot be edited in place. A library override makes it writable, so overrides
    return False."""
    if obj.override_library is not None:
        return False
    data = getattr(obj, "data", None)
    return obj.library is not None or (data is not None and data.library is not None)


def linked_guard(obj):
    """Error string if obj is read-only library-linked data, else None. The shared
    'you can't edit this in place' check for the geometry/material mutators."""
    if not is_linked_data(obj):
        return None
    status = linked_status(obj) or "linked"
    return (f"'{obj.name}' is linked library data ({status}) and can't be edited in "
            f"place. Make a library override first (Object > Library Override > "
            f"Make Local), then edit the override.")


def linked_guard_any(objs):
    """First linked_guard error across objs, or None — for tools that act on a
    resolved list of objects (material setters)."""
    for o in objs:
        err = linked_guard(o)
        if err:
            return err
    return None


def deform_binds(obj):
    """Vert-count-dependent BOUND modifiers on obj — (name, type) tuples.

    MESH_DEFORM / SURFACE_DEFORM / CORRECTIVE_SMOOTH store bind data keyed to the
    base mesh's vertex count + order. A topology edit that changes the vert count
    silently invalidates the bind: the modifier keeps reporting is_bound True but
    stops deforming, with no error anywhere (gaps.md V2). We can't see the dead
    bind directly, so callers detect the CAUSE — a vert-count change on a mesh
    carrying one of these. Empty list if none are bound."""
    binds = []
    for m in getattr(obj, "modifiers", ()):
        if m.type in ('MESH_DEFORM', 'SURFACE_DEFORM') and getattr(m, "is_bound", False):
            binds.append((m.name, m.type))
        elif m.type == 'CORRECTIVE_SMOOTH' and getattr(m, "is_bind", False):
            binds.append((m.name, m.type))
    return binds


def deform_bind_warning(binds, cause="topology"):
    """Loud warning string for an action that invalidated bound deform modifiers.

    cause='topology' — a vertex-count change from an edit (V2): the bind is keyed
    to the vert count, so the count delta is the documented bind-killer.
    cause='stackmove' — a stack-order move changed the modifier's evaluated input
    (a different stack position feeds it different geometry), so the bind computed
    at the old position no longer matches (W1). The mesh vert-count is UNCHANGED
    here, so the V2 count check can't catch it — move_modifier raises this itself.

    Both prescribe the SAME cure: rebind_deform (W3), which rebinds whichever of
    MESH_DEFORM / CORRECTIVE_SMOOTH / SURFACE_DEFORM are bound."""
    names = ", ".join(f"{n} ({t})" for n, t in binds)
    if cause == "stackmove":
        lead = ("this stack-order move changed the modifier's evaluated input "
                "(a different position in the stack feeds it different geometry), "
                "so the bind data computed at the old position no longer matches")
    else:
        lead = ("this topology edit changed the vertex count, so the bound "
                "modifier(s) no longer match the mesh")
    return (f"⚠ DEFORM BIND INVALIDATED — {lead}: [{names}] have silently stopped "
            f"deforming. The mesh looks fine at rest but won't follow the rig when "
            f"posed. Rebind required: rebind_deform('<mesh>') rebinds every bound "
            f"deform modifier, or rebind_deform('<mesh>', modifier='<name>') for one "
            f"(gaps.md V2/W1/W3).")


def rest_shadow_warning(binds):
    """Warning when a VALID reconstruct-from-bind modifier makes a position-only
    rest-shape edit invisible (gaps.md X4).

    MESH_DEFORM / SURFACE_DEFORM reconstruct each bound vertex's position from their
    driver (cage / surface) via the bind-time mapping; CORRECTIVE_SMOOTH(BIND)
    smooths toward the captured rest. So editing the BASE mesh moves nothing in the
    evaluated output — the bind pins it — until the bind is recomputed. There's no
    vert-count change, so the topology guard stays (correctly) silent; this is the
    one that catches it. Only fires when the bind is still valid: a dead bind is
    inert and shows base-mesh edits 1:1."""
    names = ", ".join(f"{n} ({t})" for n, t in binds)
    return (f"⚠ EDIT SHADOWED BY A LIVE BIND — [{names}] reconstruct vertex positions "
            f"from their bind, so this rest-shape edit will NOT show in the posed / "
            f"evaluated mesh (the base mesh moved, but the modifier output is pinned "
            f"to the bind). Run rebind_deform('<mesh>') to recompute the bind against "
            f"the new rest shape (gaps.md X4).")


def active_shape_key_shadow(obj):
    """Y1: if obj carries shape keys and the ACTIVE key would swallow an edit-mode
    position edit, return a dict describing it; else None.

    Edit-mode vertex moves (and sculpt strokes) write to whatever shape key is
    ACTIVE, not to the displayed mesh. The Basis (reference) key always contributes,
    so editing it shows in the rest mesh. A NON-basis key contributes only in
    proportion to its `value`: at value 0 the edit is completely invisible AND a
    landmine (it deforms the mesh the instant that key is ever dialed up); between 0
    and 1 it shows scaled, not 1:1. Returns {name, value, index, shadowed} where
    `shadowed` is True for the fully-invisible value-0 case."""
    data = getattr(obj, "data", None)
    sk = getattr(data, "shape_keys", None) if data is not None else None
    if sk is None or len(sk.key_blocks) < 2:
        return None
    kb = obj.active_shape_key
    if kb is None:
        return None
    # Editing the Basis (reference) key shows in the rest mesh — never shadowed.
    if obj.active_shape_key_index == 0 or kb == sk.reference_key:
        return None
    return {"name": kb.name, "value": round(kb.value, 4),
            "index": obj.active_shape_key_index, "shadowed": kb.value == 0.0}


def shape_key_shadow_warning(shadow, mesh_name):
    """Loud warning string for an edit landing on a non-Basis active shape key (Y1).

    The value-0 case is the documented landmine: the edit is invisible in the
    evaluated mesh now, and silently deforms the character if an animator ever dials
    that morph. A non-zero value still means the edit shows SCALED by the key blend,
    not 1:1. Both point at set_active_shape_key to aim the edit deliberately."""
    nm, val = shadow["name"], shadow["value"]
    if shadow["shadowed"]:
        return (f"⚠ EDIT LANDING ON SHAPE KEY '{nm}' (value 0.0) — this edit-mode "
                f"change is being written into a morph target that is NOT visible in "
                f"the evaluated mesh, so nothing will appear to change. Worse, it is a "
                f"LANDMINE: the deformation triggers the moment that key is dialed up. "
                f"To edit the rest shape, aim at Basis first: "
                f"set_active_shape_key('{mesh_name}', key='Basis'). To edit this morph "
                f"on purpose, ignore this (gaps.md Y1).")
    return (f"⚠ EDIT LANDING ON SHAPE KEY '{nm}' (value {val}) — this edit-mode change "
            f"is written into a morph target, not the base mesh, and shows only SCALED "
            f"by the key's blend, not 1:1. Aim at Basis with "
            f"set_active_shape_key('{mesh_name}', key='Basis') to edit the rest shape "
            f"(gaps.md Y1).")


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
                def _sock(label):
                    return bsdf.inputs[label] if label in bsdf.inputs else None

                # A LINK-DRIVEN socket's default_value is meaningless — it's whatever
                # was last typed, not what renders. Reporting it as truth is how the
                # summary called Spring's node-graph skin "black and glowing"
                # (gaps.md U5). So trace links instead of trusting defaults.
                bc = _sock("Base Color")
                if bc is not None:
                    if bc.is_linked:
                        src = bc.links[0].from_node
                        if (src.type == 'MIX' and getattr(src, "blend_type", "") == 'MULTIPLY'
                                and "B" in src.inputs):
                            # set_textured_material wires diffuse → MULTIPLY(B=tint) →
                            # Base Color; read the live tint back, the honest
                            # instrument for "did the tint land?" (gaps.md T3).
                            entry["base_color_tint"] = [
                                round(c, 3) for c in tuple(src.inputs["B"].default_value)[:4]]
                        else:
                            entry["base_color_driven"] = "nodegraph"
                    else:
                        entry["base_color"] = [round(c, 3) for c in tuple(bc.default_value)[:4]]
                for key, label in (("metallic", "Metallic"), ("roughness", "Roughness"),
                                   ("alpha", "Alpha")):
                    s = _sock(label)
                    if s is None:
                        continue
                    if s.is_linked:
                        entry[f"{key}_driven"] = "nodegraph"
                    else:
                        entry[key] = round(float(s.default_value), 3)
                # Only a real (non-black) emission counts. The Principled default is
                # strength 1.0 with a BLACK emission color — which renders no glow, so
                # reporting "glow=1.0" off the default is the U5 misread again.
                es = _sock("Emission Strength")
                ec = _sock("Emission Color") or _sock("Emission")
                if (es is not None and not es.is_linked and float(es.default_value) > 0
                        and ec is not None and not ec.is_linked
                        and any(c > 1e-4 for c in tuple(ec.default_value)[:3])):
                    entry["emission_strength"] = round(float(es.default_value), 3)
                    entry["emission_color"] = [round(c, 3) for c in tuple(ec.default_value)[:4]]
        out.append(entry)
    return out


def eval_world_bmesh(obj):
    """Return a NEW bmesh of obj's EVALUATED mesh (modifiers applied) with verts
    in WORLD space. Caller owns it and must call .free(). Returns None for objects
    that yield no mesh (empties, cameras, lights). This is the analysis primitive
    behind the tactile-introspection tools — they reason about final rendered
    geometry, so modifiers must be applied and the transform baked in."""
    import bmesh
    # X6/G19: force a fresh re-evaluation before reading. Socket-driven ops don't run
    # Blender's normal post-operator depsgraph update, so a prior `transform nudge`
    # can leave `evaluated_depsgraph_get()` handing back a STALE evaluated mesh — the
    # symptom G19 caught (contacts reported an unchanged 1.7 mm gap after a 6 mm move).
    # `eval_world_bbox` already does this; the bmesh path must too, or every tactile
    # read built on it (contacts, resting, symmetry, overlaps) can lie. Cheap at hobby
    # poly counts.
    try:
        obj.update_tag()
        bpy.context.view_layer.update()
    except Exception:
        pass
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


def resolve_camera(name=None, scene=None):
    """Resolve the camera a camera-consuming op should act on — one rule, shared by
    every such op so a preflight (check_framing) and the action (render, camera_position)
    can never disagree on the default (G35/G36).

    Order: an explicitly-named camera → the scene's active camera → the sole/first
    camera in the scene. Returns (cam, error_msg); exactly one is non-None. A named
    camera that's missing or not a CAMERA is an error (no silent fallback) — but an
    UNSET scene camera falls back to an available one, matching what render does.
    """
    scene = scene or bpy.context.scene
    if name:
        cam = bpy.data.objects.get(name)
        if cam is None or cam.type != 'CAMERA':
            return None, f"Camera '{name}' not found"
        return cam, None
    cam = scene.camera
    if cam is not None and cam.type == 'CAMERA':
        return cam, None
    cam = next((o for o in scene.objects if o.type == 'CAMERA'), None)
    if cam is None:
        return None, "no camera in scene (add_camera first, or pass camera=<name>)"
    return cam, None


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

"""Armature / rigging primitives — the spine of character work.

create_armature: build a bone skeleton from named head/tail joints + parenting.
auto_weight:     bind a mesh to an armature with automatic weights (vertex groups
                 + an Armature modifier), so posing bones deforms the mesh.
pose_bone:       rotate a pose bone (the per-pose articulation verb).

This is deliberately the GENERIC armature layer, not a Rigify metarig generator:
an agent describes joints in world space ("shoulder here, elbow here, wrist
here") and gets a riggable, auto-weightable skeleton. Rigify-style control rigs
can be layered on top later.
"""

import math

import bpy
import mathutils

from .common import activate, world_bbox, region_words


def _orphan_islands(obj):
    """Cluster the mesh's unweighted (no vertex group) verts into connected
    islands by mesh edges. Returns (total_verts, orphan_count, islands) where
    islands is a list of (vert_count, region_word) sorted largest-first — so the
    verdict can say WHERE the orphans are without dumping coordinates."""
    me = obj.data
    total = len(me.vertices)
    orphan = {v.index for v in me.vertices if not v.groups}
    if not orphan:
        return total, 0, []

    adj = {i: [] for i in orphan}
    for e in me.edges:
        a, b = e.vertices
        if a in orphan and b in orphan:
            adj[a].append(b)
            adj[b].append(a)

    bbox = world_bbox(obj)
    mw = obj.matrix_world
    seen = set()
    islands = []
    for start in orphan:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        comp = []
        while stack:
            n = stack.pop()
            comp.append(n)
            for m in adj[n]:
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
        c = mathutils.Vector((0.0, 0.0, 0.0))
        for i in comp:
            c += mw @ me.vertices[i].co
        c /= len(comp)
        islands.append((len(comp), region_words(bbox, c)))
    islands.sort(reverse=True)
    return total, len(orphan), islands


def create_armature(params):
    """Create an armature object from a list of bones.

    name:  armature object name (required, unique).
    bones: list of bone specs (required). Each:
             {"name": str,
              "head": [x, y, z],          # joint start, world coords
              "tail": [x, y, z],          # joint end, world coords
              "parent": str (optional),   # name of a bone defined earlier/here
              "connected": bool (optional)}  # snap head to parent's tail + connect
    """
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    if bpy.data.objects.get(name) is not None:
        return {"error": f"Object '{name}' already exists"}
    bones = params.get("bones") or []
    if not bones:
        return {"error": "'bones' must be a non-empty list of bone specs"}

    names = [b.get("name") for b in bones]
    if not all(names):
        return {"error": "every bone needs a 'name'"}
    if len(set(names)) != len(names):
        return {"error": "bone names must be unique"}

    arm_data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, arm_data)
    bpy.context.scene.collection.objects.link(obj)
    activate(obj)
    bpy.ops.object.mode_set(mode='EDIT')

    try:
        made = {}
        for b in bones:
            head = b.get("head")
            tail = b.get("tail")
            if not (isinstance(head, (list, tuple)) and len(head) == 3):
                return {"error": f"bone '{b['name']}': 'head' must be [x, y, z]"}
            if not (isinstance(tail, (list, tuple)) and len(tail) == 3):
                return {"error": f"bone '{b['name']}': 'tail' must be [x, y, z]"}
            length = sum((tail[i] - head[i]) ** 2 for i in range(3)) ** 0.5
            if length < 1e-5:
                return {"error": f"bone '{b['name']}': head and tail coincide (zero length)"}
            eb = arm_data.edit_bones.new(b["name"])
            eb.head = tuple(float(c) for c in head)
            eb.tail = tuple(float(c) for c in tail)
            # deform=false → bone.use_deform off, so this bone never competes in
            # the auto-weight heat solve (the catapult fix: root/control bones near
            # the meshes were stealing weights; the workaround was burying them
            # below the floor — this flag replaces that hack).
            eb.use_deform = bool(b.get("deform", True))
            made[b["name"]] = eb

        for b in bones:
            parent = b.get("parent")
            if parent:
                if parent not in made:
                    return {"error": f"bone '{b['name']}': parent '{parent}' not defined"}
                eb = made[b["name"]]
                eb.parent = made[parent]
                if b.get("connected"):
                    eb.use_connect = True
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.context.view_layer.update()
    return {
        "success": True,
        "object_name": obj.name,
        "bones": [bn.name for bn in arm_data.bones],
        "bone_count": len(arm_data.bones),
        "non_deform_bones": [bn.name for bn in arm_data.bones if not bn.use_deform],
    }


def auto_weight(params):
    """Bind a mesh to an armature with automatic weights.

    mesh:     mesh object to bind (required).
    armature: armature object to bind to (required).

    Parents the mesh to the armature with ARMATURE_AUTO — Blender computes per-
    vertex bone weights from bone proximity and adds an Armature modifier, so
    posing the armature now deforms the mesh."""
    mesh_name = params.get("mesh")
    arm_name = params.get("armature")
    if not mesh_name or not arm_name:
        return {"error": "'mesh' and 'armature' are required"}
    mesh = bpy.data.objects.get(mesh_name)
    arm = bpy.data.objects.get(arm_name)
    if mesh is None or mesh.type != 'MESH':
        return {"error": f"mesh '{mesh_name}' not found or not a mesh"}
    if arm is None or arm.type != 'ARMATURE':
        return {"error": f"armature '{arm_name}' not found or not an armature"}

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm  # parent target must be active
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')

    vgroups = [vg.name for vg in mesh.vertex_groups]
    mod = next((m for m in mesh.modifiers if m.type == 'ARMATURE'), None)

    # Bone-heat weighting can silently come back empty (it loses conditioning on
    # geometry far from the origin, or on non-manifold meshes) — the modifier is
    # there but posing won't deform anything. It can also weight MOST of the mesh
    # but orphan islands (e.g. thin rings the solver couldn't reach), which float
    # in place when posed. Report coverage as N/total + locate orphan islands by
    # region word, and WARN — the same verdict-in-scene-vocabulary contract the
    # introspection tools use.
    total, orphans, islands = _orphan_islands(mesh)
    weighted = total - orphans
    warnings = []
    if weighted == 0:
        warnings.append(
            "auto-weighting produced NO vertex weights — posing won't deform this "
            "mesh. Bone-heat weighting fails on geometry far from the world origin "
            "or non-manifold meshes. Move the mesh+armature near the origin "
            "(apply_transform first) and retry, or weight by hand."
        )
    elif orphans > 0:
        where = ", ".join(f"{n} verts {region}" for n, region in islands[:4])
        more = f" (+{len(islands) - 4} more)" if len(islands) > 4 else ""
        warnings.append(
            f"{weighted}/{total} weighted — {orphans} orphaned vert(s) in "
            f"{len(islands)} island(s): {where}{more}. These float in place when "
            f"posed. Rigid parts (rings/bolts) want weight_to_bone(); for organic "
            f"geometry add loop cuts or weight the gaps by hand."
        )

    return {
        "success": True,
        "mesh": mesh.name,
        "armature": arm.name,
        "vertex_groups": len(vgroups),
        "weighted_vertices": weighted,
        "total_vertices": total,
        "orphaned_vertices": orphans,
        "orphan_islands": [{"verts": n, "region": region} for n, region in islands],
        "armature_modifier": mod.name if mod else None,
        "warnings": warnings,
    }


def weight_to_bone(params):
    """Rigid-bind every vertex of a mesh to ONE named bone at full weight.

    mesh:     mesh object to bind (required).
    armature: armature that owns the bone (required).
    bone:     bone name — gets 100% weight on every vertex (required).

    This is the standard game workflow for MECHANICAL parts (wheels, doors,
    levers, turrets, throwing arms) where bone-heat's blending is actively wrong:
    a rigid part should follow exactly one bone with no falloff. Creates a vertex
    group named after the bone with weight 1.0 on all verts, strips any existing
    weights for this armature's OTHER bones (so the named bone is the sole
    influence), and creates/reuses the Armature modifier — the same plumbing
    auto_weight lays down, minus the heat solve that orphans thin detail."""
    mesh_name = params.get("mesh")
    arm_name = params.get("armature")
    bone = params.get("bone")
    if not mesh_name or not arm_name or not bone:
        return {"error": "'mesh', 'armature', and 'bone' are all required"}
    mesh = bpy.data.objects.get(mesh_name)
    arm = bpy.data.objects.get(arm_name)
    if mesh is None or mesh.type != 'MESH':
        return {"error": f"mesh '{mesh_name}' not found or not a mesh"}
    if arm is None or arm.type != 'ARMATURE':
        return {"error": f"armature '{arm_name}' not found or not an armature"}
    if bone not in arm.data.bones:
        return {"error": f"bone '{bone}' not found on '{arm_name}'. "
                         f"Available: {[b.name for b in arm.data.bones]}"}

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Strip existing weights for THIS armature's bones so the named bone is the
    # sole influence (true rigid bind). Non-bone vertex groups are left alone.
    bone_names = {b.name for b in arm.data.bones}
    for vg in list(mesh.vertex_groups):
        if vg.name in bone_names:
            mesh.vertex_groups.remove(vg)

    vg = mesh.vertex_groups.new(name=bone)
    all_idx = [v.index for v in mesh.data.vertices]
    vg.add(all_idx, 1.0, 'REPLACE')

    mod = next((m for m in mesh.modifiers if m.type == 'ARMATURE'), None)
    if mod is None:
        mod = mesh.modifiers.new(name="Armature", type='ARMATURE')
    mod.object = arm
    mod.use_vertex_groups = True

    bpy.context.view_layer.update()
    return {
        "success": True,
        "mesh": mesh.name,
        "armature": arm.name,
        "bone": bone,
        "weighted_vertices": len(all_idx),
        "total_vertices": len(mesh.data.vertices),
        "armature_modifier": mod.name,
    }


def pose_bone(params):
    """Pose a bone — rotate and/or translate it (local bone space).

    armature: armature object name (required).
    bone:     bone name (required).
    rot:      optional [x, y, z] rotation in degrees.
    loc:      optional [x, y, z] translation in meters — production rigs are posed
              mostly by TRANSLATING IK controls (hand/foot targets, pole vectors),
              which a rotation-only verb can't drive.
    additive: if True, ADD rot/loc to the bone's CURRENT pose instead of replacing
              it — nudge one axis without re-deriving the whole pose. Default False.
    At least one of rot/loc is required. The pose persists; returns to OBJECT mode."""
    arm_name = params.get("armature")
    bone = params.get("bone")
    rot = params.get("rot")
    loc = params.get("loc")
    additive = bool(params.get("additive", False))
    if not arm_name or not bone:
        return {"error": "'armature' and 'bone' are required"}
    if rot is None and loc is None:
        return {"error": "at least one of 'rot' (degrees) or 'loc' (meters) is required"}
    if rot is not None and not (isinstance(rot, (list, tuple)) and len(rot) == 3):
        return {"error": "'rot' must be [x, y, z] degrees"}
    if loc is not None and not (isinstance(loc, (list, tuple)) and len(loc) == 3):
        return {"error": "'loc' must be [x, y, z] meters"}
    arm = bpy.data.objects.get(arm_name)
    if arm is None or arm.type != 'ARMATURE':
        return {"error": f"armature '{arm_name}' not found or not an armature"}

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    activate(arm)
    bpy.ops.object.mode_set(mode='POSE')

    pbone = arm.pose.bones.get(bone)
    if pbone is None:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": f"bone '{bone}' not found on '{arm_name}'. "
                         f"Available: {[b.name for b in arm.pose.bones]}"}
    if rot is not None:
        pbone.rotation_mode = 'XYZ'
        new_rot = [math.radians(float(a)) for a in rot]
        if additive:
            pbone.rotation_euler = tuple(c + n for c, n in zip(pbone.rotation_euler, new_rot))
        else:
            pbone.rotation_euler = tuple(new_rot)
    if loc is not None:
        new_loc = [float(a) for a in loc]
        if additive:
            pbone.location = tuple(c + n for c, n in zip(pbone.location, new_loc))
        else:
            pbone.location = tuple(new_loc)
    bpy.context.view_layer.update()
    final_rot = [round(math.degrees(a), 2) for a in pbone.rotation_euler]
    final_loc = [round(a, 4) for a in pbone.location]
    bpy.ops.object.mode_set(mode='OBJECT')

    return {
        "success": True,
        "armature": arm.name,
        "bone": bone,
        "additive": additive,
        "rot_deg": final_rot,
        "loc": final_loc,
    }


def get_bone_tree(params):
    """Hierarchy tree of an armature's bones — the read-side complement of
    create_armature. Filterable, because production rigs have hundreds of bones.

    armature:    armature object name (required).
    filter:      optional substring — show only bones whose name contains it
                 (ancestors are kept for context).
    deform_only: optional — show only deform bones (skip control/widget bones).
    max_depth:   optional int — cap tree depth.
    """
    from .common import world_bbox  # noqa: F401  (kept symmetric with describe_bone)
    arm_name = params.get("armature")
    arm = bpy.data.objects.get(arm_name)
    if arm is None or arm.type != 'ARMATURE':
        return {"error": f"armature '{arm_name}' not found or not an armature"}
    bones = arm.data.bones
    total = len(bones)
    flt = (params.get("filter") or "").lower()
    deform_only = bool(params.get("deform_only"))
    md = params.get("max_depth")
    max_depth = int(md) if md is not None else None

    def keep(b):
        if deform_only and not b.use_deform:
            return False
        if flt and flt not in b.name.lower():
            return False
        return True

    matched = set()

    def subtree_matches(b):
        m = keep(b)
        for c in b.children:
            if subtree_matches(c):
                m = True
        if m:
            matched.add(b.name)
        return m

    roots = [b for b in bones if b.parent is None]
    for r in roots:
        subtree_matches(r)

    shown = [0]
    lines = []

    def walk(b, depth):
        if b.name not in matched:
            return
        if max_depth is not None and depth > max_depth:
            return
        shown[0] += 1
        pad = "│   " * depth
        marker = "" if b.use_deform else "  (control)"
        lines.append(f"{pad}├── {b.name}{marker}")
        for c in b.children:
            walk(c, depth + 1)

    for r in roots:
        walk(r, 0)

    header = f"{arm_name}: {total} bones"
    if flt or deform_only or max_depth is not None:
        bits = []
        if flt:
            bits.append(f"filter='{flt}'")
        if deform_only:
            bits.append("deform-only")
        if max_depth is not None:
            bits.append(f"max_depth={max_depth}")
        header += f" ({shown[0]} shown — {', '.join(bits)})"
    return {"success": True, "armature": arm_name, "bone_count": total,
            "shown": shown[0], "tree": header + ("\n" + "\n".join(lines) if lines else "")}


def _bone_constraints(holder):
    out = []
    for c in holder.constraints:
        e = {"name": c.name, "type": c.type, "influence": round(c.influence, 3),
             "mute": c.mute}
        tgt = getattr(c, "target", None)
        if tgt is not None:
            e["target"] = tgt.name if tgt else None
            sub = getattr(c, "subtarget", "")
            if sub:
                e["subtarget"] = sub
        out.append(e)
    return out


def describe_bone(params):
    """Per-bone description in scene vocabulary: parent/children, head & tail region
    words, length, deform flag, pose locks, constraints (type→target), and custom
    properties. No raw coordinates."""
    from .common import world_bbox, region_words
    arm_name = params.get("armature")
    bone_name = params.get("bone")
    arm = bpy.data.objects.get(arm_name)
    if arm is None or arm.type != 'ARMATURE':
        return {"error": f"armature '{arm_name}' not found or not an armature"}
    bone = arm.data.bones.get(bone_name)
    if bone is None:
        avail = [b.name for b in arm.data.bones][:20]
        return {"error": f"bone '{bone_name}' not found on '{arm_name}'. "
                         f"First bones: {avail}"}
    pbone = arm.pose.bones.get(bone_name)
    mw = arm.matrix_world
    bbox = world_bbox(arm)
    head_region = region_words(bbox, mw @ bone.head_local)
    tail_region = region_words(bbox, mw @ bone.tail_local)
    length_mm = round((bone.tail_local - bone.head_local).length * 1000, 1)

    locks = []
    constraints = []
    props = {}
    if pbone is not None:
        for axis, l in zip("XYZ", pbone.lock_location):
            if l:
                locks.append(f"loc{axis}")
        for axis, l in zip("XYZ", pbone.lock_rotation):
            if l:
                locks.append(f"rot{axis}")
        constraints = _bone_constraints(pbone)
        from .objects import _user_props
        props = _user_props(pbone)

    kids = [c.name for c in bone.children]
    parts = ["root bone" if bone.parent is None else f"child of {bone.parent.name}"]
    if kids:
        parts.append(f"{len(kids)} child(ren)")
    parts.append(f"head {head_region}, tail {tail_region}, length {length_mm}mm")
    parts.append("deform" if bone.use_deform else "control (no deform)")
    if locks:
        parts.append("locked " + ",".join(locks))
    if constraints:
        parts.append(f"{len(constraints)} constraint(s): " + ", ".join(
            f"{c['type']}→{c.get('target', '?')}"
            + (f"/{c['subtarget']}" if c.get("subtarget") else "")
            for c in constraints))
    if props:
        parts.append("props: " + ", ".join(f"{k}={v}" for k, v in props.items()))

    return {"success": True, "armature": arm_name, "bone": bone_name,
            "parent": bone.parent.name if bone.parent else None, "children": kids,
            "deform": bone.use_deform, "length_mm": length_mm,
            "head_region": head_region, "tail_region": tail_region, "locks": locks,
            "constraints": constraints, "custom_properties": props,
            "description": f"{arm_name}.{bone_name}: " + "; ".join(parts)}


def list_constraints(params):
    """List constraints on an object, or on one of its pose bones (bone=...), plus
    object-level drivers. Read-only. Reports type + target(+subtarget) + influence
    + mute — the BlenRig/IK control graph an agent otherwise can't see."""
    name = params.get("name")
    bone = params.get("bone")
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}
    if bone:
        if obj.type != 'ARMATURE':
            return {"error": f"'{name}' is not an armature; 'bone' only applies to armatures"}
        holder = obj.pose.bones.get(bone)
        if holder is None:
            return {"error": f"bone '{bone}' not found on '{name}'"}
    else:
        holder = obj

    constraints = _bone_constraints(holder)

    drivers = []
    if bone is None and obj.animation_data is not None:
        for d in obj.animation_data.drivers:
            drivers.append({
                "data_path": d.data_path, "array_index": d.array_index,
                "expression": d.driver.expression,
                "variables": [v.name for v in d.driver.variables],
            })

    target = f"{name}.{bone}" if bone else name
    summary = f"{target}: {len(constraints)} constraint(s)"
    if drivers:
        summary += f", {len(drivers)} driver(s) on object"
    return {"success": True, "name": name, "bone": bone,
            "constraints": constraints, "drivers": drivers, "summary": summary}


TOOLS = {
    "create_armature": create_armature,
    "auto_weight":     auto_weight,
    "weight_to_bone":  weight_to_bone,
    "pose_bone":       pose_bone,
    "get_bone_tree":   get_bone_tree,
    "describe_bone":   describe_bone,
    "list_constraints": list_constraints,
}

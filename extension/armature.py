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
    """Rotate a pose bone (degrees, local XYZ euler).

    armature: armature object name (required).
    bone:     bone name (required).
    rot:      [x, y, z] rotation in degrees (required). Replaces the bone's
              current pose rotation.
    The pose is stored on the bone and persists; the call returns to OBJECT mode."""
    arm_name = params.get("armature")
    bone = params.get("bone")
    rot = params.get("rot")
    if not arm_name or not bone:
        return {"error": "'armature' and 'bone' are required"}
    if not (isinstance(rot, (list, tuple)) and len(rot) == 3):
        return {"error": "'rot' must be [x, y, z] degrees"}
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
    pbone.rotation_mode = 'XYZ'
    pbone.rotation_euler = tuple(math.radians(float(a)) for a in rot)
    bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode='OBJECT')

    return {
        "success": True,
        "armature": arm.name,
        "bone": bone,
        "rot_deg": [round(float(a), 2) for a in rot],
    }


TOOLS = {
    "create_armature": create_armature,
    "auto_weight":     auto_weight,
    "weight_to_bone":  weight_to_bone,
    "pose_bone":       pose_bone,
}

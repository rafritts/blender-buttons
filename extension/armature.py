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

from .common import activate


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
    # there but posing won't deform anything. Detect and warn rather than leave a
    # dead rig.
    weighted = sum(1 for v in mesh.data.vertices if v.groups)
    warnings = []
    if weighted == 0:
        warnings.append(
            "auto-weighting produced NO vertex weights — posing won't deform this "
            "mesh. Bone-heat weighting fails on geometry far from the world origin "
            "or non-manifold meshes. Move the mesh+armature near the origin "
            "(apply_transform first) and retry, or weight by hand."
        )

    return {
        "success": True,
        "mesh": mesh.name,
        "armature": arm.name,
        "vertex_groups": len(vgroups),
        "weighted_vertices": weighted,
        "armature_modifier": mod.name if mod else None,
        "warnings": warnings,
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
    "pose_bone":       pose_bone,
}

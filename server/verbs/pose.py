"""pose — Pose Mode / armature, weights, binding, shape keys (SPEC-05).

Everything rig-related: build an armature, weight a mesh to it, pose bones, bind a
mesh-deform cage, drive shape keys, and read the bone tree. `op` selects.
"""

from typing import Literal

from server._core import mcp
from server import armature as _arm, editmode, modifiers, objects
from ._common import tag, unknown

_OPS = ["create_armature", "auto_weight", "weight_to_bone", "assign_weight",
        "pose_bone", "bone_tree", "describe_bone", "constraints", "bind", "rebind",
        "shape_keys", "shape_key_set", "shape_key_active", "shape_key_delete",
        "shape_key_bake"]


@mcp.tool(name="pose")
def pose(
    op: Literal["create_armature", "auto_weight", "weight_to_bone", "assign_weight",
                "pose_bone", "bone_tree", "describe_bone", "constraints", "bind",
                "rebind", "shape_keys", "shape_key_set", "shape_key_active",
                "shape_key_delete", "shape_key_bake"],
    # armature / mesh refs
    name: tag(str, "[create_armature/constraints/shape_*] object name") = "",
    armature: tag(str, "[auto_weight/weight_to_bone/pose_bone/bone_tree/describe_bone] armature name") = "",
    mesh: tag(str, "[auto_weight/weight_to_bone/bind/rebind/shape_*] mesh name") = "",
    bone: tag(str, "[weight_to_bone/pose_bone/describe_bone/constraints] bone name") = "",
    # create_armature
    bones: tag(list, "[create_armature] [{name, head, tail, parent}, …]") = None,
    # pose_bone
    rot: tag(list, "[pose_bone] rotation [x,y,z] degrees") = None,
    loc: tag(list, "[pose_bone] translation [x,y,z]") = None,
    additive: tag(bool, "[pose_bone] add to current pose") = False,
    # weights
    group: tag(str, "[assign_weight] vertex group / bone name") = "",
    weight: tag(float, "[assign_weight] weight 0..1") = 1.0,
    mode: tag(str, "[assign_weight] REPLACE|ADD|SUBTRACT") = "REPLACE",
    # bone_tree
    filter: tag(str, "[bone_tree] name-substring filter") = "",
    deform_only: tag(bool, "[bone_tree] only deform bones") = False,
    max_depth: tag(int, "[bone_tree] max hierarchy depth") = None,
    # bind / rebind
    cage: tag(str, "[bind] mesh-deform cage object") = "",
    action: tag(str, "[bind] bind | unbind") = "bind",
    modifier: tag(str, "[bind/rebind] modifier name") = "",
    precision: tag(int, "[bind] bind precision") = None,
    timeout: tag(int, "[bind/rebind] seconds before giving up") = 120,
    # shape keys
    key: tag(str, "[shape_key_set/shape_key_active/shape_key_delete] shape-key name (delete: ''/'ALL' = clear all)") = "",
    value: tag(float, "[shape_key_set] key value 0..1") = 0.0,
    label: str = "",
) -> str:
    """
    Rigging — **Pose Mode**, weights, binding, shape keys. `op` selects:

      create_armature — build bones   (name, bones=[{name, head, tail, parent}, …])
      auto_weight     — auto skin a mesh (mesh, armature)
      weight_to_bone  — assign full weight to one bone (mesh, armature, bone)
      assign_weight   — weight the edit-mode selection (group, weight, mode=REPLACE|ADD|SUBTRACT)
      pose_bone       — rotate/translate a bone (armature, bone, rot=[x,y,z]°, loc, additive)
      bone_tree       — read the bone hierarchy (armature, filter, deform_only, max_depth)
      describe_bone   — one bone's detail        (armature, bone)
      constraints     — list constraints         (name, bone)
      bind            — bind a mesh-deform cage   (mesh, cage, action=bind|unbind, modifier, precision)
      rebind          — rebind after edits        (mesh, modifier)
      shape_keys      — list shape keys           (name)
      shape_key_set   — set a key's value         (name, key, value)
      shape_key_active— make a key active for editing (name, key)
      shape_key_delete— delete one key, or ALL (key="" / "ALL") — unblocks
                        apply-Subsurf & dyntopo on a keyed mesh   (name, key)
      shape_key_bake  — flatten the current mix into Basis, drop all keys (name)
    """
    o = op.lower().strip()
    arm = armature or name
    if o == "create_armature":
        return _arm.create_armature(name, bones or [], label)
    if o == "auto_weight":
        return _arm.auto_weight(mesh, arm, label)
    if o == "weight_to_bone":
        return _arm.weight_to_bone(mesh, arm, bone, label)
    if o == "assign_weight":
        return editmode.assign_weight(group, weight, mode, label)
    if o == "pose_bone":
        return _arm.pose_bone(arm, bone, rot, loc, additive, label)
    if o == "bone_tree":
        return _arm.get_bone_tree(arm, filter, deform_only, max_depth)
    if o == "describe_bone":
        return _arm.describe_bone(arm, bone)
    if o == "constraints":
        return _arm.list_constraints(name or arm, bone or None)
    if o == "bind":
        return modifiers.bind_mesh_deform(mesh, cage, action, modifier, precision,
                                          timeout, label)
    if o == "rebind":
        return modifiers.rebind_deform(mesh, modifier, timeout, label)
    if o == "shape_keys":
        return objects.list_shape_keys(name or mesh)
    if o == "shape_key_set":
        return objects.set_shape_key(name or mesh, key, value, label)
    if o == "shape_key_active":
        return objects.set_active_shape_key(name or mesh, key, label)
    if o == "shape_key_delete":
        return objects.delete_shape_key(name or mesh, key, label)
    if o == "shape_key_bake":
        return objects.bake_shape_keys_to_basis(name or mesh, label)
    return unknown("pose", "op", op, _OPS)

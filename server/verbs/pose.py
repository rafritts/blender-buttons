"""pose — Pose Mode / armature, weights, binding, shape keys (SPEC-05).

Everything rig-related: build an armature, weight a mesh to it, pose bones, bind a
mesh-deform cage, drive shape keys, and read the bone tree. `op` selects.
"""

from typing import Literal

from server._core import mcp
from server import armature as _arm, editmode, modifiers, objects
from ._common import tag, unknown

_OPS = ["auto_weight", "assign_weight",
        "pose_bone", "bone_tree", "describe_bone", "constraints", "rebind",
        "shape_keys", "shape_key_set", "shape_key_active", "shape_key_delete"]


@mcp.tool(name="pose")
def pose(
    op: Literal["auto_weight", "assign_weight",
                "pose_bone", "bone_tree", "describe_bone", "constraints",
                "rebind", "shape_keys", "shape_key_set", "shape_key_active",
                "shape_key_delete"],
    # armature / mesh refs
    name: tag(str, "[constraints/shape_*] object name") = "",
    armature: tag(str, "[auto_weight/pose_bone/bone_tree/describe_bone] armature name") = "",
    mesh: tag(str, "[auto_weight/rebind/shape_*] mesh name") = "",
    bone: tag(str, "[pose_bone/describe_bone/constraints] bone name") = "",
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
    # rebind
    modifier: tag(str, "[rebind] modifier name") = "",
    timeout: tag(int, "[rebind] seconds before giving up") = 120,
    # shape keys
    key: tag(str, "[shape_key_set/shape_key_active/shape_key_delete] shape-key name (delete: ''/'ALL' = clear all)") = "",
    value: tag(float, "[shape_key_set] key value 0..1") = 0.0,
    label: str = "",
) -> str:
    """
    Rigging — **Pose Mode**, weights, binding, shape keys. `op` selects:

      auto_weight     — auto skin a mesh (mesh, armature)
      assign_weight   — weight the edit-mode selection (group, weight, mode=REPLACE|ADD|SUBTRACT)
      pose_bone       — rotate/translate a bone (armature, bone, rot=[x,y,z]°, loc, additive)
      bone_tree       — read the bone hierarchy (armature, filter, deform_only, max_depth)
      describe_bone   — one bone's detail        (armature, bone)
      constraints     — list constraints         (name, bone)
      rebind          — rebind a mesh-deform / surface-deform / corrective-smooth
                        modifier after edits      (mesh, modifier)
      shape_keys      — list shape keys           (name)
      shape_key_set   — set a key's value         (name, key, value)
      shape_key_active— make a key active for editing (name, key)
      shape_key_delete— delete one key, or ALL (key="" / "ALL") — unblocks
                        apply-Subsurf & dyntopo on a keyed mesh   (name, key)
    """
    o = op.lower().strip()
    arm = armature or name
    if o == "auto_weight":
        return _arm.auto_weight(mesh, arm, label)
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
    return unknown("pose", "op", op, _OPS)

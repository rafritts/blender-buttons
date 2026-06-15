"""pose — Pose Mode / armature, weights, binding, shape keys (SPEC-05).

Everything rig-related: build an armature, weight a mesh to it, pose bones, bind a
mesh-deform cage, drive shape keys, and read the bone tree. `op` selects.
"""

from server._core import mcp
from server import armature as _arm, editmode, modifiers, objects
from ._common import unknown

_OPS = ["create_armature", "auto_weight", "weight_to_bone", "assign_weight",
        "pose_bone", "bone_tree", "describe_bone", "constraints", "bind", "rebind",
        "shape_keys", "shape_key_set", "shape_key_active"]


@mcp.tool(name="pose")
def pose(
    op: str,
    # armature / mesh refs
    name: str = "", armature: str = "", mesh: str = "", bone: str = "",
    # create_armature
    bones: list = None,
    # pose_bone
    rot: list = None, loc: list = None, additive: bool = False,
    # weights
    group: str = "", weight: float = 1.0, mode: str = "REPLACE",
    # bone_tree
    filter: str = "", deform_only: bool = False, max_depth: int = None,
    # bind / rebind
    cage: str = "", action: str = "bind", modifier: str = "",
    precision: int = None, timeout: int = 120,
    # shape keys
    key: str = "", value: float = 0.0,
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
    return unknown("pose", "op", op, _OPS)

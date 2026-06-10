from server._core import mcp, call_blender, _status


@mcp.tool()
def create_armature(name: str, bones: list, label: str = "") -> str:
    """
    Create an armature (skeleton) from a list of named bones — the foundation for
    rigging and posing a character. Describe each joint by its head/tail in world
    coordinates and its parent; you get a riggable skeleton back.

    name:  armature object name (unique).
    bones: list of bone specs. Each is a dict:
             {"name": "upper_arm_L",
              "head": [0.2, 0, 1.4],     # joint start (world coords, meters)
              "tail": [0.5, 0, 1.4],     # joint end
              "parent": "shoulder_L",    # optional — name of another bone in this list
              "connected": true}         # optional — snap head to parent's tail & connect
           Define parents before or alongside children (resolved in a second pass).

    Then bind a mesh with auto_weight(mesh, armature) and articulate with
    pose_bone(armature, bone, rot=[x,y,z]).

    Example — a 3-bone arm:
      create_armature("arm_rig", bones=[
        {"name": "upper_arm", "head": [0.2,0,1.4], "tail": [0.5,0,1.4]},
        {"name": "forearm",   "head": [0.5,0,1.4], "tail": [0.8,0,1.4],
         "parent": "upper_arm", "connected": true},
        {"name": "hand",      "head": [0.8,0,1.4], "tail": [0.95,0,1.4],
         "parent": "forearm", "connected": true},
      ])
    """
    result = call_blender("create_armature", {"name": name, "bones": bones}, label=label)
    if result.get("success"):
        main = (f"Created armature '{result['object_name']}' with {result['bone_count']} "
                f"bone(s): {result['bones']} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def auto_weight(mesh: str, armature: str, label: str = "") -> str:
    """
    Bind a mesh to an armature with automatic weights so posing the skeleton
    deforms the mesh. Parents the mesh to the armature (ARMATURE_AUTO): Blender
    computes per-vertex bone weights and adds an Armature modifier.

    mesh:     mesh object to bind.
    armature: armature object to bind it to.

    Run this after create_armature and before pose_bone. For clean deformation the
    mesh should have enough loop cuts across each joint to bend smoothly.

    Example: auto_weight(mesh="character_body", armature="arm_rig")
    """
    result = call_blender("auto_weight", {"mesh": mesh, "armature": armature}, label=label)
    if result.get("success"):
        main = (f"bound '{result['mesh']}' to '{result['armature']}' — "
                f"{result['vertex_groups']} vertex group(s), "
                f"{result.get('weighted_vertices', '?')} weighted vert(s), "
                f"modifier '{result['armature_modifier']}' [{result.get('op_id','')}]")
        for w in result.get("warnings", []):
            main += f"\n⚠ {w}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def pose_bone(armature: str, bone: str, rot: list, label: str = "") -> str:
    """
    Rotate a pose bone — the articulation verb. Bends an auto-weighted mesh at
    that joint.

    armature: armature object name.
    bone:     bone name (from create_armature).
    rot:      [x, y, z] rotation in degrees (local bone space). Replaces the
              bone's current pose rotation.

    The pose persists on the bone; the call returns to Object Mode. Call repeatedly
    on different bones to build up a full pose.

    Example: pose_bone("arm_rig", "forearm", rot=[0, 0, 60])   # bend the elbow
    """
    result = call_blender("pose_bone", {"armature": armature, "bone": bone, "rot": rot},
                          label=label)
    if result.get("success"):
        main = (f"posed '{result['armature']}'.{result['bone']} → rot {result['rot_deg']}° "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)

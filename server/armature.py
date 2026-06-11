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
              "connected": true,         # optional — snap head to parent's tail & connect
              "deform": false}           # optional — exclude from the auto_weight heat
                                         #   solve (use for root/control bones so they
                                         #   don't steal weights from nearby meshes)
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
        nd = result.get("non_deform_bones") or []
        if nd:
            main += f"\n  non-deform (excluded from auto_weight): {nd}"
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
                f"{result.get('weighted_vertices', '?')}/{result.get('total_vertices', '?')} "
                f"weighted vert(s), "
                f"modifier '{result['armature_modifier']}' [{result.get('op_id','')}]")
        for w in result.get("warnings", []):
            main += f"\n⚠ {w}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def weight_to_bone(mesh: str, armature: str, bone: str, label: str = "") -> str:
    """
    Rigid-bind a whole mesh to ONE bone at 100% weight — the right tool for
    MECHANICAL parts (wheels, doors, levers, turrets, throwing arms, gun barrels)
    that should follow a single bone exactly, with no blending.

    mesh:     mesh object to bind.
    armature: armature that owns the bone.
    bone:     bone name — every vertex of the mesh gets full weight to it.

    Use this INSTEAD of auto_weight when a part is rigid. auto_weight's bone-heat
    solve blends weights from bone proximity, which is correct for skin/cloth but
    wrong for hard-surface parts: it smears geometry across a joint and orphans
    thin detail (rings, bolts) that the heat can't reach. weight_to_bone is
    deterministic — it strips any existing weights for this armature's other bones
    so the named bone is the sole influence, then adds/reuses the Armature
    modifier. Assign in the rig's rest pose.

    Example — bind a catapult throwing arm (with its joined detail rings) to the
    swing bone: weight_to_bone(mesh="throwing_arm", armature="catapult_rig",
                               bone="arm_swing")
    """
    result = call_blender("weight_to_bone",
                          {"mesh": mesh, "armature": armature, "bone": bone}, label=label)
    if result.get("success"):
        main = (f"rigid-bound '{result['mesh']}' → bone '{result['bone']}' on "
                f"'{result['armature']}': {result['weighted_vertices']}/"
                f"{result['total_vertices']} vert(s) at full weight, "
                f"modifier '{result['armature_modifier']}' [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def pose_bone(armature: str, bone: str, rot: list = None, loc: list = None,
              additive: bool = False, label: str = "") -> str:
    """
    Pose a bone — rotate AND/OR translate it. The articulation verb; bends/moves an
    auto-weighted mesh at that joint.

    armature: armature object name.
    bone:     bone name (from create_armature, or get_bone_tree on an imported rig).
    rot:      optional [x, y, z] rotation in degrees (local bone space).
    loc:      optional [x, y, z] translation in meters (local bone space). Production
              rigs are posed mostly by TRANSLATING IK controls — hand/foot targets,
              pole vectors — which rotation alone can't drive.
    additive: if True, ADD rot/loc to the bone's CURRENT pose instead of replacing
              it — nudge one axis without re-deriving the whole pose. Default False.

    Supply at least one of rot/loc. The pose persists; returns to Object Mode.

    Examples:
      pose_bone("arm_rig", "forearm", rot=[0, 0, 60])          # bend the elbow
      pose_bone("char_rig", "hand_ik.L", loc=[0, 0.2, 0.1])    # move the IK hand
      pose_bone("char_rig", "hand_ik.L", loc=[0, 0.05, 0], additive=True)  # nudge it
    """
    params = {"armature": armature, "bone": bone, "additive": additive}
    if rot is not None:
        params["rot"] = rot
    if loc is not None:
        params["loc"] = loc
    result = call_blender("pose_bone", params, label=label)
    if result.get("success"):
        main = (f"posed '{result['armature']}'.{result['bone']} → "
                f"rot {result['rot_deg']}° loc {result['loc']}"
                f"{' (additive)' if result.get('additive') else ''} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def get_bone_tree(armature: str, filter: str = "", deform_only: bool = False,
                  max_depth: int = None) -> str:
    """
    Print an armature's bone hierarchy — the read-side complement of
    create_armature, for posing a rig you imported rather than built.

    armature:    armature object name.
    filter:      optional substring — show only bones whose name contains it
                 (ancestors kept for context). Essential on production rigs with
                 hundreds of bones (e.g. filter="hand" or "ik").
    deform_only: show only deform bones, hiding control/widget bones.
    max_depth:   cap the tree depth.

    Use this to discover bone names, then describe_bone(armature, bone) for detail.
    """
    params = {"armature": armature, "filter": filter, "deform_only": deform_only}
    if max_depth is not None:
        params["max_depth"] = max_depth
    result = call_blender("get_bone_tree", params)
    if not result.get("success"):
        return result.get("error", "failed")
    return result["tree"]


@mcp.tool()
def describe_bone(armature: str, bone: str) -> str:
    """
    Describe one bone in scene vocabulary: parent/children, head & tail region
    (top-left-front…), length, deform flag, pose locks, constraints (type→target),
    and custom properties. No raw coordinates.

    Example: describe_bone("char_rig", "upper_arm.L")
    """
    result = call_blender("describe_bone", {"armature": armature, "bone": bone})
    if not result.get("success"):
        return result.get("error", "failed")
    return result["description"] + _status(result)


@mcp.tool()
def list_constraints(name: str, bone: str = None) -> str:
    """
    List the constraints on an object — or on one of its pose bones (bone=...) —
    plus object-level drivers. Read-only. Reports type, target (+subtarget bone),
    influence, and mute. The way to see an imported rig's IK chains / copy-transform
    graph, which pose_bone may otherwise silently fight.

    Examples:
      list_constraints("char_rig", bone="hand_ik.L")
      list_constraints("wheel_FL")
    """
    params = {"name": name}
    if bone is not None:
        params["bone"] = bone
    result = call_blender("list_constraints", params)
    if not result.get("success"):
        return result.get("error", "failed")
    lines = [result["summary"]]
    for c in result.get("constraints", []):
        tgt = c.get("target", "—")
        sub = f"/{c['subtarget']}" if c.get("subtarget") else ""
        muted = " [muted]" if c.get("mute") else ""
        lines.append(f"  • {c['type']} '{c['name']}' → {tgt}{sub} "
                     f"(influence {c['influence']}){muted}")
    for d in result.get("drivers", []):
        lines.append(f"  ⚙ driver: {d['data_path']}[{d['array_index']}] = "
                     f"{d['expression']!r}")
    return "\n".join(lines)

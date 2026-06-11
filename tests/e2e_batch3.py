"""E2E for batch-3 gap fixes (T6, T2) — evaluated/posed bounds. Headless.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_batch3.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import mathutils  # noqa: E402

from extension import server as bb_server     # noqa: E402
from extension.common import eval_world_center  # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok    {label}")
    else:
        failures.append(label)
        print(f"  FAIL  {label}  {detail}")


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


# ───────────────────────── build a posable limb ─────────────────────────
clean()
run("add_box", name="limb", width=0.3, depth=0.3, height=2.0, on={"at": [0, 0, 1.0]})
run("loop_cut", target="limb", axis="Z", cuts=8)
run("create_armature", name="limb_rig", bones=[
    {"name": "lower", "head": [0, 0, 0.0], "tail": [0, 0, 1.0]},
    {"name": "upper", "head": [0, 0, 1.0], "tail": [0, 0, 2.0],
     "parent": "lower", "connected": True},
])
run("auto_weight", mesh="limb", armature="limb_rig")

# Rest description (no pose yet)
rest = run("describe", name="limb")
rest_d = rest["dimensions"]["depth"]
rest_h = rest["dimensions"]["height"]

# A camera, made the scene camera, for the DOF test.
cam_data = bpy.data.cameras.new("camd")
cam = bpy.data.objects.new("cam", cam_data)
bpy.context.scene.collection.objects.link(cam)
cam.location = (6.0, -6.0, 2.0)
cam.rotation_euler = (1.1, 0.0, 0.78)
bpy.context.scene.camera = cam

# DOF focus before posing — baseline focal distance.
dof_rest = run("set_camera_dof", focus_object="limb", aperture=2.8)
fd_rest = dof_rest["focus_distance"]

# ───────────────────────── pose the upper bone ─────────────────────────
# A bone's local Y runs along its length, so bend around local X (rot=[80,0,0]);
# the upper half swings out in Y and drops in Z.
run("pose_bone", armature="limb_rig", bone="upper", rot=[80, 0, 0])

# ───────────────────────── T6: posed describe ─────────────────────────
print("== T6: describe(posed=True) reports evaluated geometry ==")
posed = run("describe", name="limb", posed=True)
check("posed describe success", posed.get("success") is True, str(posed))
check("posed flag set", posed.get("posed") is True, str(posed))
# Offset = evaluated geometry center vs UNDEFORMED base-mesh center → the pose
# displacement, the thing you'd otherwise dead-reckon from the bone pivot.
check("posed center offset reported and non-zero",
      (posed.get("posed_center_offset_mm") or 0) > 100.0, str(posed.get("posed_center_offset_mm")))
check("description mentions posed", "posed" in posed["description"], posed["description"])
# The bend swings the limb out in depth (Y) and shortens its height (Z).
check("posed depth exceeds rest depth",
      posed["dimensions"]["depth"] > rest_d + 0.3,
      f"posed={posed['dimensions']['depth']} rest={rest_d}")
check("posed height below rest height (bent over)",
      posed["dimensions"]["height"] < rest_h - 0.3,
      f"posed={posed['dimensions']['height']} rest={rest_h}")

# ───────────────────────── T2: DOF on posed geometry ─────────────────────────
print("== T2: set_camera_dof focuses on evaluated (posed) center ==")
dof_posed = run("set_camera_dof", focus_object="limb", aperture=2.8)
fd_posed = dof_posed["focus_distance"]
check("dof reports the focus target name", dof_posed.get("focus_object") == "limb", str(dof_posed))
check("posing changed the focal distance (not tracking the rest origin)",
      abs(fd_posed - fd_rest) > 1e-3, f"rest={fd_rest} posed={fd_posed}")

# The returned focus_distance must equal the projection of the EVALUATED center
# onto the camera axis — proving it used posed geometry, not the object origin.
center = mathutils.Vector(eval_world_center(bpy.data.objects["limb"]))
fwd = (cam.matrix_world.to_3x3() @ mathutils.Vector((0.0, 0.0, -1.0))).normalized()
expected_fd = (center - cam.matrix_world.translation).dot(fwd)
check("focus_distance == projection of evaluated center",
      abs(fd_posed - expected_fd) < 1e-3, f"got={fd_posed} expected={expected_fd}")

# And it must differ from focusing on the rest origin (the old, wrong behaviour).
origin = bpy.data.objects["limb"].matrix_world.translation
origin_fd = (origin - cam.matrix_world.translation).dot(fwd)
check("evaluated-center focus differs from object-origin focus",
      abs(expected_fd - origin_fd) > 1e-3, f"eval={expected_fd} origin={origin_fd}")

# dof.focus_object is cleared (we set a fixed plane, not Blender origin-tracking).
check("dof.focus_object cleared (fixed posed plane)",
      cam.data.dof.focus_object is None)

print()
if failures:
    print(f"BATCH3 E2E: {len(failures)} FAILED: {failures}")
    sys.exit(1)
else:
    print("BATCH3 E2E: ALL TESTS PASSED")

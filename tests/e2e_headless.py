"""E2E test for the blender-buttons extension — runs inside headless Blender.

Exercises the extension modules directly from the repo (not the installed
addon copy), so it verifies working-tree code before install.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_headless.py
       (flatpak resolves relative paths against its own sandbox — pass an absolute path)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension.common import world_bbox, world_center  # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok    {label}")
    else:
        failures.append(label)
        print(f"  FAIL  {label}  {detail}")


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


# Clean default scene (Cube etc.) for predictable relations
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

print("== dispatch registration ==")
for t in ("spline_tube", "bend", "scale_group"):
    check(f"{t} in dispatch", t in bb_server.TOOLS)

print("== placement: at ==")
r = run("add_box", name="t_box", width=0.2, depth=0.2, height=0.2, on={"at": [1, 2, 3]})
check("add_box at success", r.get("success"), r.get("error"))
c = world_center(bpy.data.objects["t_box"])
check("t_box center == (1,2,3)", all(abs(c[i] - (1, 2, 3)[i]) < 1e-5 for i in range(3)), c)

print("== placement: unknown key rejected ==")
r = run("add_box", name="t_bad", width=0.1, depth=0.1, height=0.1, on={"att": [0, 0, 0]})
check("unknown key errors", "error" in r and "Valid keys" in r["error"], r)
check("no object created on error", bpy.data.objects.get("t_bad") is None)

print("== add_primitives: bulk rot_y honored ==")
r = run("add_primitives", specs=[
    {"type": "cylinder", "name": "t_cyl", "radius": 0.05, "height": 0.5, "rot_y": 14},
])
check("bulk add success", r.get("success"), r.get("error"))
rot_y = math.degrees(bpy.data.objects["t_cyl"].rotation_euler.y)
check("t_cyl rot_y == 14", abs(rot_y - 14) < 1e-3, rot_y)

print("== resize: rotation warning ==")
r = run("resize", targets="t_cyl", height=0.6)
check("resize success", r.get("success"), r.get("error"))
check("rotation warning present", any("rotated" in w for w in r.get("warnings", [])),
      r.get("warnings"))
r = run("resize", targets="t_box", height=0.3)
check("no warning on unrotated", not r.get("warnings"), r.get("warnings"))

print("== spline_tube ==")
r = run("spline_tube", name="t_tube",
        points=[{"near": "t_box", "offset": [0.2, 0, 0]}, [1.5, 2.2, 2.5], [1.7, 2.0, 2.0]],
        radius=[0.03, 0.02, 0.005], resolution=8)
check("spline_tube success", r.get("success"), r.get("error"))
tube = bpy.data.objects.get("t_tube")
check("tube exists as mesh", tube is not None and tube.type == 'MESH',
      getattr(tube, "type", None))
check("tube has verts", tube is not None and len(tube.data.vertices) > 50,
      len(tube.data.vertices) if tube else 0)
check("through-points stored", tube is not None and tube.get("bb_spline_points") is not None)
check("length reported", r.get("length", 0) > 0.5, r.get("length"))
# first anchored point = t_box center + offset
p0 = r["points"][0]
expected0 = [1.2, 2.0, 3.0]
check("anchored point resolved", all(abs(p0[i] - expected0[i]) < 1e-3 for i in range(3)), p0)

print("== spline_tube validation ==")
r = run("spline_tube", name="t_tube2", points=[[0, 0, 0]])
check("1 point rejected", "error" in r, r)
r = run("spline_tube", name="t_tube2", points=[[0, 0, 0], {"near": "missing"}])
check("missing anchor rejected", "error" in r and "not found" in r["error"], r)
r = run("spline_tube", name="t_tube2", points=[[0, 0, 0], [1, 1, 1]], radius=[0.1])
check("radius count mismatch rejected", "error" in r, r)

print("== materials introspection ==")
r = run("set_material", target="t_tube", base_color=[0.9, 0.2, 0.2], roughness=0.4)
check("set_material success", r.get("success"), r.get("error"))
r = run("describe", name="t_tube")
check("describe success", r.get("success"), r.get("error"))
mats = r.get("materials", [])
check("describe reports material", mats and mats[0].get("name") == "t_tube_mat", mats)
check("describe reports color", mats and mats[0].get("base_color", [0])[0] == 0.9, mats)
check("describe mentions spline", "spline tube through" in r.get("description", ""),
      r.get("description"))
r = run("get_object_info", name="t_tube")
check("get_object_info materials", r["info"].get("materials") is not None,
      r["info"].keys())

print("== bend ==")
before = world_bbox(bpy.data.objects["t_tube"])
r = run("bend", targets="t_tube", angle=90, axis="X")
check("bend success", r.get("success"), r.get("error"))
after = world_bbox(bpy.data.objects["t_tube"])
changed = any(abs(before[i] - after[i]) > 1e-4 for i in range(6))
check("bend changed geometry", changed, (before, after))
check("bend applied (no modifier left)", len(bpy.data.objects["t_tube"].modifiers) == 0)
r = run("bend", targets="t_box", angle=45)  # box long axis warning not expected (cube)
check("bend works on box", r.get("success"), r.get("error"))

print("== scale_group ==")
run("add_box", name="g_a", width=0.2, depth=0.2, height=0.2, on={"at": [-0.5, 0, 1.0]})
run("add_box", name="g_b", width=0.2, depth=0.2, height=0.2, on={"at": [0.5, 0, 1.0]})
r = run("scale_group", targets=["g_a", "g_b"], factor=2.0, pivot="center")
check("scale_group success", r.get("success"), r.get("error"))
ca = world_center(bpy.data.objects["g_a"])
cb = world_center(bpy.data.objects["g_b"])
check("centers spread ×2", abs(ca[0] - (-1.0)) < 1e-4 and abs(cb[0] - 1.0) < 1e-4, (ca, cb))
da = world_bbox(bpy.data.objects["g_a"])
check("parts scaled ×2", abs((da[3] - da[0]) - 0.4) < 1e-4, da)
check("z preserved at pivot", abs(ca[2] - 1.0) < 1e-4, ca)
r = run("scale_group", targets=["g_a", "g_b"], factor=0.5, pivot="bottom_center")
check("bottom_center pivot works", r.get("success"), r.get("error"))

print("== mirror_across replace ==")
run("add_box", name="arm_R", width=0.1, depth=0.1, height=0.4, on={"at": [0.3, 0, 1]})
r = run("mirror_across", targets="arm_R", plane="X", replace=["_R", "_L"])
check("mirror replace success", r.get("success"), r.get("error"))
check("arm_L created", bpy.data.objects.get("arm_L") is not None,
      r.get("mirrored_to"))
cl = world_center(bpy.data.objects["arm_L"])
check("arm_L mirrored to -X", abs(cl[0] + 0.3) < 1e-4, cl)
r = run("mirror_across", targets="t_box", plane="X", replace=["_R", "_L"])
check("no-token falls back to suffix", "t_box_mirror" in r.get("mirrored_to", []), r)

print()
if failures:
    print(f"E2E: {len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("E2E: ALL TESTS PASSED")
sys.exit(0)

"""E2E for the P1-P12 manipulation + introspection tools, in headless Blender.

Usage: flatpak run org.blender.Blender --background --python /abs/path/tests/e2e_introspect.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension.common import world_center  # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok    {label}")
    else:
        failures.append(label)
        print(f"  FAIL  {label}  {detail}")


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def fresh():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


# ─────────────────────────── P1 array_radial ───────────────────────────
print("== P1 array_radial ==")
fresh()
run("add_box", name="marker", width=0.1, depth=0.1, height=0.1, on={"at": [1, 0, 0]})
r = run("array_radial", prototype="marker", count=12, center=[0, 0, 0], axis="Z")
check("array_radial success", r.get("success"), r.get("error"))
check("12 copies placed", len(r.get("placed", [])) == 12, r.get("placed"))
check("prototype removed", bpy.data.objects.get("marker") is None)
c1 = world_center(bpy.data.objects["marker_1"])
check("copy_1 at start angle (1,0,0)", abs(c1[0] - 1) < 1e-4 and abs(c1[1]) < 1e-4, c1)
c4 = world_center(bpy.data.objects["marker_4"])  # i=3 → 90°
check("copy_4 at 90° (~0,1,0)", abs(c4[0]) < 1e-4 and abs(c4[1] - 1) < 1e-4, c4)
# arc (not full circle): 5 copies 0→180 inclusive
fresh()
run("add_box", name="seg", width=0.1, depth=0.1, height=0.1, on={"at": [1, 0, 0]})
r = run("array_radial", prototype="seg", count=5, center=[0, 0, 0], axis="Z",
        start_angle=0, end_angle=180)
check("arc step 45°", abs(r.get("step_deg", 0) - 45) < 1e-3, r.get("step_deg"))
c5 = world_center(bpy.data.objects["seg_5"])  # i=4 → 180°
check("arc end at 180° (~-1,0,0)", abs(c5[0] + 1) < 1e-4 and abs(c5[1]) < 1e-4, c5)

# ─────────────────────────── P2 rotate pivot ───────────────────────────
print("== P2 rotate_object pivot ==")
fresh()
run("add_box", name="rp", width=0.2, depth=0.2, height=0.2, on={"at": [1, 0, 0]})
r = run("rotate_object", targets="rp", angle=90, axis="Z", pivot=[0, 0, 0])
check("rotate pivot success", r.get("success"), r.get("error"))
crp = world_center(bpy.data.objects["rp"])
check("box swung to (~0,1,0)", abs(crp[0]) < 1e-4 and abs(crp[1] - 1) < 1e-4, crp)
# no-pivot path unchanged: spins in place
fresh()
run("add_box", name="rp2", width=0.2, depth=0.2, height=0.2, on={"at": [1, 0, 0]})
r = run("rotate_object", targets="rp2", angle=45, axis="Z")
crp2 = world_center(bpy.data.objects["rp2"])
check("no-pivot keeps center", abs(crp2[0] - 1) < 1e-4 and abs(crp2[1]) < 1e-4, crp2)

# ─────────────────────────── P3 coplanar ───────────────────────────
print("== P3 find_coplanar_overlaps ==")
fresh()
# two slabs whose top faces are coplanar (both top at z=0.1) and overlap in xy
run("add_box", name="slabA", width=0.4, depth=0.4, height=0.1, on={"at": [0, 0, 0.05]})
run("add_box", name="slabB", width=0.3, depth=0.3, height=0.1, on={"at": [0.05, 0.05, 0.05]})
r = run("find_coplanar_overlaps")
check("coplanar detected", r.get("count", 0) >= 1, r)
# separate B in z so no coplanar faces remain
run("nudge", targets="slabB", up=0.5)
r = run("find_coplanar_overlaps")
check("coplanar cleared after lift", r.get("count", 0) == 0, r)

# ─────────────────────────── P5 validate_scene ───────────────────────────
print("== P5 validate_scene ==")
fresh()
run("add_box", name="ok", width=0.2, depth=0.2, height=0.2, on={"at": [0, 0, 0.1]})
run("add_box", name="sunk", width=0.2, depth=0.2, height=0.2, on={"at": [1, 0, 0.1]})
run("nudge", targets="sunk", down=0.3)  # now dips below floor
r = run("validate_scene")
kinds = [f["kind"] for f in r.get("findings", [])]
check("validate flags below_floor", "below_floor" in kinds, kinds)

# ─────────────────────────── P6 check_mesh ───────────────────────────
print("== P6 check_mesh ==")
fresh()
run("add_box", name="cube", width=0.2, depth=0.2, height=0.2, on={"at": [0, 0, 0.1]})
r = run("check_mesh", target="cube")
rep = r.get("reports", [{}])[0]
check("cube watertight", rep.get("watertight") is True, rep)
check("cube no self-intersections", rep.get("self_intersections") == 0, rep)
check("cube clean", rep.get("clean") is True, rep)
check("thinnest wall ~200mm", abs((rep.get("thinnest_wall_mm") or 0) - 200) < 5, rep.get("thinnest_wall_mm"))

# ─────────────────────────── P12 audit_asset ───────────────────────────
print("== P12 audit_asset ==")
fresh()
run("add_box", name="part", width=0.2, depth=0.2, height=0.2, on={"at": [0, 0, 0.1]})
r = run("audit_asset", group="part")
rep = r.get("reports", [{}])[0]
check("audit flags missing material", any("material" in i for i in rep.get("issues", [])), rep)
check("audit counts tris", rep.get("tris", 0) == 12, rep.get("tris"))

# ─────────────────────────── P4 check_contacts ───────────────────────────
print("== P4 check_contacts ==")
fresh()
run("add_box", name="A", width=0.2, depth=0.2, height=0.2, on={"at": [0, 0, 0.1]})
run("add_box", name="B", width=0.2, depth=0.2, height=0.2, on={"at": [0, 0, 0.3]})  # on top of A
r = run("check_contacts", targets=["A", "B"])
rels = {c["object"]: c for c in r.get("contacts", [])}
check("A connected to B", rels.get("A", {}).get("relation") == "connected", rels.get("A"))
run("nudge", targets="B", up=0.05)  # lift 50mm → floating
r = run("check_contacts", targets="B")
b = r["contacts"][0]
check("B floating ~50mm", b["relation"] == "floating" and abs(b["gap_mm"] - 50) < 2, b)
run("nudge", targets="B", down=0.15)  # sink into A → penetrating
r = run("check_contacts", targets="B")
b = r["contacts"][0]
check("B penetrating A", b["relation"] == "penetrating", b)

# ─────────────────────────── P10 check_resting ───────────────────────────
print("== P10 check_resting ==")
fresh()
run("add_box", name="grounded", width=0.2, depth=0.2, height=0.2, on={"at": [0, 0, 0.1]})
run("add_box", name="hover", width=0.2, depth=0.2, height=0.2, on={"at": [1, 0, 0.5]})
r = run("check_resting", targets=["grounded", "hover"])
rs = {x["object"]: x for x in r.get("resting", [])}
check("grounded rests on floor", rs.get("grounded", {}).get("state") == "resting", rs.get("grounded"))
check("grounded has contacts", rs.get("grounded", {}).get("contacts", 0) > 0, rs.get("grounded"))
check("grounded COM over support", rs.get("grounded", {}).get("com_over_support") is True, rs.get("grounded"))
check("hover floating ~400mm", rs.get("hover", {}).get("state") == "floating"
      and abs(rs.get("hover", {}).get("clearance_mm", 0) - 400) < 2, rs.get("hover"))

# ─────────────────────────── P9 check_framing ───────────────────────────
print("== P9 check_framing ==")
fresh()
run("add_box", name="hero", width=0.5, depth=0.5, height=0.5, on={"at": [0, 0, 0.25]})
cam_data = bpy.data.cameras.new("Cam")
cam_obj = bpy.data.objects.new("Cam", cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
cam_obj.location = (0, -3, 0.25)
cam_obj.rotation_euler = (math.radians(90), 0, 0)  # look toward +Y
bpy.context.scene.camera = cam_obj
bpy.context.view_layer.update()
r = run("check_framing", targets="hero")
fr = r.get("framing", [{}])[0]
check("framing reports coverage", fr.get("frame_pct", [0])[0] > 0, fr)
check("hero in front of camera", fr.get("behind_camera") is False, fr)

# ─────────────────────────── P7 trace_profile ───────────────────────────
print("== P7 trace_profile ==")
fresh()
# a sphere has verts distributed along the axis: radius rises then tapers
run("add_sphere", name="ball", radius=0.3, on={"at": [0, 0, 0.4]})
r = run("trace_profile", target="ball", axis="Z")
check("trace_profile success", r.get("success"), r.get("error"))
kinds = [f["kind"] for f in r.get("features", [])]
check("sphere shows rise then taper", "rise" in kinds and "taper" in kinds, kinds)

# ─────────────────────────── P11 diff_since ───────────────────────────
print("== P11 diff_since ==")
fresh()
r = run("add_box", name="d_box", width=0.2, depth=0.2, height=0.2, on={"at": [0, 0, 0.1]})
cp = r["op_id"]
run("nudge", targets="d_box", up=0.5)
r = run("diff_since", checkpoint=cp)
check("diff_since success", r.get("success"), r.get("error"))
moved = {c["object"]: c for c in r.get("changed", [])}
dbox = moved.get("d_box", {})
kinds = [c["kind"] for c in dbox.get("changes", [])]
check("diff sees move", "moved" in kinds, dbox)
mm = next((c["mm"] for c in dbox.get("changes", []) if c["kind"] == "moved"), 0)
check("move ~500mm", abs(mm - 500) < 2, mm)

# ─────────────────────────── P8 check_symmetry (mesh) ───────────────────────────
print("== P8 check_symmetry mesh-level ==")
fresh()
run("add_box", name="sym", width=0.4, depth=0.4, height=0.4, on={"at": [0, 0, 0.2]})
r = run("check_symmetry", target="sym", axis="X", plane=0.0)
check("centered box symmetric across X", r.get("is_symmetric") is True and r.get("level") == "mesh", r)
run("nudge", targets="sym", right=0.5)  # shift +X off the mirror plane
r = run("check_symmetry", target="sym", axis="X", plane=0.0)
check("shifted box asymmetric across X", r.get("is_symmetric") is False, r)

print()
if failures:
    print(f"E2E-INTROSPECT: {len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("E2E-INTROSPECT: ALL TESTS PASSED")
sys.exit(0)

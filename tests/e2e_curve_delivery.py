"""E2E for the S1-S2 curve-delivery gaps, in headless Blender.

S1 — material tools accept material-slot objects (curves), not just meshes;
     audit_asset / validate_scene name the non-mesh members they skip.

Usage: flatpak run org.blender.Blender --background --python /abs/path/tests/e2e_curve_delivery.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
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


# ─────────────────────────── S1 material tools accept curves ───────────────────────────
print("== S1 set_material on a beveled curve ==")
fresh()
r = run("add_curve", name="rope", type="NURBS", bevel_depth=0.05,
        points=[[0, 0, 0], [1, 0, 0], [2, 0, 0.5]])
check("add_curve ok", r.get("success"), r.get("error"))
curve = bpy.data.objects["rope"]
check("object is a CURVE", curve.type == 'CURVE')
r = run("set_material", target="rope", hex="#8b5a2b")
check("set_material accepts curve", r.get("success"), r.get("error"))
check("material in curve slot 0", len(curve.data.materials) >= 1 and curve.data.materials[0] is not None,
      [m.name if m else None for m in curve.data.materials])

# ─────────────────────────── S1b excluded non-mesh named ───────────────────────────
print("== S1b audit_asset / validate_scene name skipped curves ==")
fresh()
run("add_box", name="hull", width=0.5, depth=0.5, height=0.5, on={"at": [0, 0, 0.25]})
run("add_curve", name="cord", type="POLY", bevel_depth=0.02, points=[[0, 0, 0], [0.5, 0, 0.5]])
r = run("audit_asset", group=["hull", "cord"])
check("audit_asset success", r.get("success"), r.get("error"))
check("audit names the skipped curve", r.get("excluded_non_mesh") == ["cord"], r.get("excluded_non_mesh"))
check("audit still audits the mesh", r.get("object_count") == 1, r.get("object_count"))
r = run("validate_scene", targets=["hull", "cord"])
check("validate_scene success", r.get("success"), r.get("error"))
check("validate names the skipped curve", r.get("excluded_non_mesh") == ["cord"], r.get("excluded_non_mesh"))

print()
if failures:
    print(f"E2E-CURVE-DELIVERY: {len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("E2E-CURVE-DELIVERY: ALL TESTS PASSED")
sys.exit(0)

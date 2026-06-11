"""E2E for the S1-S2 curve-delivery gaps, in headless Blender.

S1 — material tools accept material-slot objects (curves), not just meshes;
     audit_asset / validate_scene name the non-mesh members they skip.
S2 — convert_to_mesh bakes a live curve (bevel + hooks) into a real mesh.

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

print("== S1 set_toon_material on a curve ==")
r = run("set_toon_material", target="rope", base_color=[0.5, 0.3, 0.1], bands=2)
check("set_toon_material accepts curve", r.get("success"), r.get("error"))

print("== S1 set_textured_material on a curve ==")
# Generate a tiny local PNG under the workspace (flatpak can't read /tmp).
tex_path = os.path.join(HERE, "_tmp_tex.png")
img = bpy.data.images.new("_tmp_tex", 2, 2)
img.filepath_raw = tex_path
img.file_format = 'PNG'
img.save()
r = run("set_textured_material", target="rope", maps={"diffuse": tex_path}, scale=1.0)
check("set_textured_material accepts curve", r.get("success"), r.get("error"))
if os.path.exists(tex_path):
    os.remove(tex_path)

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

# ─────────────────────────── S2 convert_to_mesh bakes curve ───────────────────────────
print("== S2 convert_to_mesh bakes bevel + hooks ==")
fresh()
# Live following rope: hooked to a bone, posed, then baked to a game-ready mesh.
run("create_armature", name="crig", bones=[{"name": "arm", "head": [0, 0, 1], "tail": [0.5, 0, 1]}])
run("add_curve", name="cable", type="POLY", bevel_depth=0.05, points=[
    [0, 0, 0],
    {"at": [0.5, 0, 1], "anchor": {"bone": "crig/arm"}},
])
cable = bpy.data.objects["cable"]
check("cable starts as CURVE", cable.type == 'CURVE')
run("pose_bone", armature="crig", bone="arm", rot=[0, 0, 90])
# Posed-cable end before bake (evaluated, hooks live).
deps = bpy.context.evaluated_depsgraph_get()
ev = cable.evaluated_get(deps)
me = ev.to_mesh()
end_live = max((ev.matrix_world @ v.co).y for v in me.vertices)  # Z-swing moves the tail to +Y
ev.to_mesh_clear()

r = run("convert_to_mesh", name="cable")
check("convert_to_mesh success", r.get("success"), r.get("error"))
check("reports CURVE → mesh", r.get("converted") and r.get("from_type") == "CURVE", r)
cable = bpy.data.objects["cable"]
check("object is now a MESH", cable.type == 'MESH')
check("baked mesh has bevel faces", len(cable.data.polygons) > 0, len(cable.data.polygons))
# The baked (static) mesh must carry the posed shape — its end stays where the
# live hook had swung it.
end_baked = max((cable.matrix_world @ v.co).y for v in cable.data.vertices)
check("baked mesh kept the posed (hook-deformed) shape", abs(end_baked - end_live) < 0.01,
      (end_live, end_baked))
# And the delivered mesh now takes a textured material with no complaint.
tex_path = os.path.join(HERE, "_tmp_tex2.png")
img = bpy.data.images.new("_tmp_tex2", 2, 2)
img.filepath_raw = tex_path
img.file_format = 'PNG'
img.save()
r = run("set_textured_material", target="cable", maps={"diffuse": tex_path})
check("baked mesh takes a textured material", r.get("success"), r.get("error"))
if os.path.exists(tex_path):
    os.remove(tex_path)

print()
if failures:
    print(f"E2E-CURVE-DELIVERY: {len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("E2E-CURVE-DELIVERY: ALL TESTS PASSED")
sys.exit(0)

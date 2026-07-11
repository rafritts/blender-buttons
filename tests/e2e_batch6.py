"""E2E for batch-6 gap fixes (T1, T5) — material targeting + viewport cleanup. Headless.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_batch6.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server            # noqa: E402
from extension.viewport import find_view3d_context   # noqa: E402

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
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)


def base_col(matname):
    m = bpy.data.materials[matname]
    bsdf = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    return [round(c, 2) for c in bsdf.inputs['Base Color'].default_value[:3]]


# ───────────────────── T1: address a shared material by name ─────────────────────
print("== T1: set_material(material=...) restyles a shared datablock ==")
clean()
run("add_box", name="wheel_FL", width=1.0, depth=1.0, height=1.0)
run("add_box", name="wheel_FR", width=1.0, depth=1.0, height=1.0)
run("set_material", target="wheel_FL", material_name="iron_mat", base_color=[1, 0, 0])
run("set_material", target="wheel_FR", material_name="iron_mat", base_color=[1, 0, 0])
check("both wheels share one material datablock",
      bpy.data.objects["wheel_FL"].data.materials[0] is bpy.data.objects["wheel_FR"].data.materials[0])
r = run("set_material", material="iron_mat", base_color=[0, 0, 1])
check("by-name set_material success", r.get("success") is True, str(r))
check("by-name edit reports in place", r.get("edited_in_place") is True, str(r))
check("shared material recolored once for all users", base_col("iron_mat") == [0, 0, 1], base_col("iron_mat"))
miss = run("set_material", material="ghost_mat", base_color=[1, 1, 1])
check("unknown material name errors", "error" in miss, str(miss))

# ───────────────────── T1: slot-index targeting ─────────────────────
print("== T1: set_material(target, slot=...) hits the secondary slot ==")
clean()
run("add_box", name="wheel", width=1.0, depth=1.0, height=1.0)
run("set_material", target="wheel", material_name="wood", base_color=[0.5, 0.3, 0.1])     # slot 0
run("set_material", target="wheel", slot=1, material_name="rim_iron", base_color=[0.2, 0.2, 0.2])  # slot 1
wheel = bpy.data.objects["wheel"]
check("two material slots now", len(wheel.data.materials) == 2, str([m.name for m in wheel.data.materials]))
check("slot 0 is wood, slot 1 is iron",
      wheel.data.materials[0].name == "wood" and wheel.data.materials[1].name == "rim_iron")
# Edit the secondary slot's material IN PLACE (no material_name).
rs = run("set_material", target="wheel", slot=1, base_color=[0, 0, 1])
check("slot edit success", rs.get("success") is True, str(rs))
check("slot edit reports in place", rs.get("edited_in_place") is True, str(rs))
check("secondary material recolored", base_col("rim_iron") == [0, 0, 1], base_col("rim_iron"))
check("primary material untouched", base_col("wood") == [0.5, 0.3, 0.1], base_col("wood"))
oob = run("set_material", target="wheel", slot=5, material_name="x", base_color=[1, 1, 1])
check("out-of-range slot errors", "error" in oob, str(oob))

# ───────────────────── T5: viewport overlays ─────────────────────
print("== T5: set_viewport_overlays ==")
ov = run("set_viewport_overlays", relationship_lines=False, cursor=False)
window, screen, area, region = find_view3d_context()
if area is not None:
    check("set_viewport_overlays success", ov.get("success") is True, str(ov))
    space = next(s for s in area.spaces if s.type == 'VIEW_3D')
    check("relationship lines turned off", space.overlay.show_relationship_lines is False)
    check("reports what changed", "relationship_lines" in ov.get("changed", {}), str(ov))
    none_given = run("set_viewport_overlays")
    check("no-flags call errors helpfully", "error" in none_given, str(none_given))
else:
    check("no-viewport handled gracefully", "error" in ov, str(ov))

print()
if failures:
    print(f"BATCH6 E2E: {len(failures)} FAILED: {failures}")
    sys.exit(1)
else:
    print("BATCH6 E2E: ALL TESTS PASSED")

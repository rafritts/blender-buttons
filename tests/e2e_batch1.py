"""E2E for batch-1 gap fixes (T7, T8, T4, S1b, U11) — runs inside headless Blender.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_batch1.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import state  # noqa: E402

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


# ───────────────────────── T7: delete a hidden object ─────────────────────────
print("== T7: delete frees hidden-object name ==")
clean()
run("add_box", name="t7_target", width=2.0, depth=2.0, height=2.0)
run("add_box", name="t7_cutter", width=0.5, depth=0.5, height=0.5)
b = run("boolean", target="t7_target", cutter="t7_cutter", op="DIFFERENCE",
        apply=True, hide_cutter=True)
check("cutter is hidden after boolean", bpy.data.objects["t7_cutter"].hide_get() is True)
d = run("delete_object", name="t7_cutter")
check("delete_object reports success", d.get("success") is True, str(d))
check("hidden cutter actually removed from bpy.data", "t7_cutter" not in bpy.data.objects)
re = run("add_box", name="t7_cutter", size=0.2)
check("name freed — re-add with same name succeeds", re.get("success") is True, str(re))

# ──────────────────────── T8: boolean refuses empty result ────────────────────
print("== T8: boolean refuses to bake a 0-vert result ==")
clean()
run("add_box", name="t8_target", width=0.5, depth=0.5, height=0.5)   # fully inside cutter
run("add_box", name="t8_cutter", width=2.0, depth=2.0, height=2.0)    # encloses the target
before_verts = len(bpy.data.objects["t8_target"].data.vertices)
r = run("boolean", target="t8_target", cutter="t8_cutter", op="DIFFERENCE",
        apply=True, hide_cutter=True)
check("boolean did NOT mark applied", r.get("applied") is False, str(r))
check("boolean flags empty_result", r.get("empty_result") is True, str(r))
check("boolean returns a loud warning", "REFUSED" in (r.get("warning") or ""), str(r))
check("modifier left live on target", r.get("modifier") is not None, str(r))
check("base mesh untouched (verts preserved)",
      len(bpy.data.objects["t8_target"].data.vertices) == before_verts)

# A normal, non-empty DIFFERENCE still applies cleanly (no false positive).
clean()
run("add_box", name="t8b_target", width=2.0, depth=2.0, height=2.0)
run("add_box", name="t8b_cutter", width=0.5, depth=0.5, height=0.5)
r2 = run("boolean", target="t8b_target", cutter="t8b_cutter", op="DIFFERENCE",
         apply=True, hide_cutter=True)
check("normal boolean still applies", r2.get("applied") is True, str(r2))
check("normal boolean has no empty_result flag", "empty_result" not in r2, str(r2))

# ──────────────────── S1b: group expansion reports non-mesh ───────────────────
print("== S1b: audit_asset/validate_scene report non-mesh group members ==")
clean()
run("add_box", name="s1b_mesh", width=1.0, depth=1.0, height=1.0)
# A real curve object linked into a collection alongside the mesh.
curve_data = bpy.data.curves.new("s1b_curve_data", type='CURVE')
curve_obj = bpy.data.objects.new("s1b_curve", curve_data)
coll = bpy.data.collections.new("s1b_group")
bpy.context.scene.collection.children.link(coll)
coll.objects.link(bpy.data.objects["s1b_mesh"])
coll.objects.link(curve_obj)
a = run("audit_asset", group="s1b_group")
check("audit_asset still audits the mesh", a.get("object_count") == 1, str(a))
check("audit_asset reports the curve as excluded_non_mesh",
      "s1b_curve" in (a.get("excluded_non_mesh") or []), str(a))
v = run("validate_scene", targets="s1b_group")
check("validate_scene reports the curve as excluded_non_mesh",
      "s1b_curve" in (v.get("excluded_non_mesh") or []), str(v))

# ──────────────────────── U11: history reset on (re)load ──────────────────────
print("== U11: reset_history_state clears all bookkeeping ==")
clean()
run("add_box", name="u11_box", width=1.0, depth=1.0, height=1.0)
check("history non-empty before reset", len(state._history) > 0)
state.reset_history_state()
check("history cleared", len(state._history) == 0)
check("redo stack cleared", len(state._redo_stack) == 0)
check("snapshots cleared", len(state._snapshots) == 0)
check("undo baseline reset", state._undo_baseline is None)
# The handler is wired through bpy.app.handlers — confirm the function exists and
# is import-clean (registration happens in register(), not in this direct-dispatch harness).
from extension import _on_load_post  # noqa: E402
check("_on_load_post handler is persistent", hasattr(_on_load_post, "_bpy_persistent"))

# ──────────────────────────── T4: status viewport key ─────────────────────────
print("== T4: status block carries viewport shading ==")
clean()
run("add_box", name="t4_box", width=1.0, depth=1.0, height=1.0)
s = run("get_blender_status")
check("get_blender_status ok", s.get("success") is True, str(s))
# The key is present iff a 3D viewport exists. When present it must be a real mode;
# absence (true headless / no window) is also valid — the point is it never lies.
vp = s.get("status", {}).get("viewport")
check("viewport shading is a known mode (or absent)",
      vp is None or vp in {"SOLID", "MATERIAL", "RENDERED", "WIREFRAME"}, str(vp))

print()
if failures:
    print(f"BATCH1 E2E: {len(failures)} FAILED: {failures}")
    sys.exit(1)
else:
    print("BATCH1 E2E: ALL TESTS PASSED")

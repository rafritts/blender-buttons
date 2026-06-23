"""E2E for G101 — shading-only ops must not read as a geometry no-op. Headless.

`smooth_edges` adds an angle-limited BEVEL then shade-smooths. On a surface with no edge
above the angle limit the bevel moves NOTHING, but the shade-smooth + autosmooth DO apply
— the op did its job. The geometry signature is byte-identical, so the old no-op detector
cried wolf. The fix pairs a SHADING signature with the geometry one: a shade change means
not-a-no-op; only when BOTH are unchanged is it a true no-op.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_gaps_g101.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FAIL '} {label}" + ("" if cond else f"   {detail}"))
    if not cond:
        failures.append(label)


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    state.reset_history_state()


def make_cube(name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


print("\nG101 — shading-only smooth_edges is not a no-op\n")

# angle_limit=180 → NO edge qualifies for the bevel, so geometry stays byte-identical;
# only the shade-smooth applies (a flat cube → all faces smooth). The old detector saw
# the identical geometry and wrongly flagged no_op.
clean()
cube = make_cube("Cube")
flat_before = sum(1 for p in cube.data.polygons if p.use_smooth)
check("cube starts flat-shaded", flat_before == 0)

r = run("smooth_edges", targets="Cube", width=0.002, segments=2, angle_limit=180.0)
check("smooth_edges succeeded", r.get("success"), str(r)[:160])
check("shading actually changed (faces now smooth)",
      sum(1 for p in bpy.data.objects['Cube'].data.polygons if p.use_smooth) == 6)
check("NOT flagged a no-op (the shade-smooth did its job)", not r.get("no_op"), str(r.get("no_op_warning")))

# Negative control: re-run on the now-all-smooth cube. The bevel still touches nothing AND
# the shade flags are already set, so NOTHING changes — a genuine no-op, still caught.
r2 = run("smooth_edges", targets="Cube", width=0.002, segments=2, angle_limit=180.0)
check("a genuinely-idempotent re-run IS still flagged no_op", r2.get("no_op") is True, str(r2)[:160])

# Sanity: a real bevel (angle_limit small enough that the cube's 90° edges qualify) changes
# geometry → not a no-op, as before.
clean()
make_cube("Cube2")
r3 = run("smooth_edges", targets="Cube2", width=0.05, segments=2, angle_limit=30.0)
check("a real bevel changes geometry → not a no-op", r3.get("success") and not r3.get("no_op"),
      str(r3.get("no_op_warning")))

print()
if failures:
    print(f"e2e_gaps_g101 :: FAILED — {len(failures)} failure(s): {failures}")
    sys.exit(1)
print("e2e_gaps_g101 :: PASSED — 0 failure(s)")

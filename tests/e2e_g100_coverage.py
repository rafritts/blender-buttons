"""E2E for Cluster 11 — G100 residual: model-free coverage read (feel op=coverage).

A flat grid with a punched-out interior hole reports its disjoint-piece count and the
interior hole over its own (u,v) plane — no generative model asserted.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g100_coverage.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import fit  # noqa: E402

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


# ---- a full flat grid → ~100% coverage, 1 piece, no interior holes -------------------
clean()
bpy.ops.mesh.primitive_grid_add(x_subdivisions=20, y_subdivisions=20, size=1.0)
bpy.context.active_object.name = "Sheet"
res = fit.coverage_region({"target": "Sheet", "na": 12, "nb": 12})
check("coverage read succeeds", res.get("success"), res.get("error", ""))
check("full sheet = 1 piece", res["pieces"] == 1, str(res.get("pieces")))
check("full sheet ~ fully covered", res["coverage_pct"] >= 95, str(res.get("coverage_pct")))
check("full sheet has no interior holes", res["interior_holes"] == 0, str(res.get("interior_holes")))


# ---- punch a hole in the middle → interior holes > 0 --------------------------------
clean()
bpy.ops.mesh.primitive_grid_add(x_subdivisions=24, y_subdivisions=24, size=1.0)
ob = bpy.context.active_object
ob.name = "Holed"
bm = bmesh.new(); bm.from_mesh(ob.data)
mid = [f for f in bm.faces if abs(f.calc_center_median().x) < 0.2 and abs(f.calc_center_median().y) < 0.2]
bmesh.ops.delete(bm, geom=mid, context='FACES')
# also delete the now-loose interior verts so the hole is real
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
bm.to_mesh(ob.data); bm.free()
res = fit.coverage_region({"target": "Holed", "na": 14, "nb": 14})
check("holed sheet detects interior holes", res["interior_holes"] > 0, str(res.get("interior_holes")))
check("holed sheet coverage < full", res["coverage_pct"] < 95, str(res.get("coverage_pct")))


# ---- two separate patches → 2 pieces ------------------------------------------------
clean()
bpy.ops.mesh.primitive_grid_add(x_subdivisions=8, y_subdivisions=8, size=0.5)
bpy.context.active_object.name = "P1"
bpy.ops.mesh.primitive_grid_add(x_subdivisions=8, y_subdivisions=8, size=0.5, location=(3, 0, 0))
p2 = bpy.context.active_object; p2.name = "P2"
# join into one object with two disjoint islands
bpy.ops.object.select_all(action='DESELECT')
bpy.data.objects["P1"].select_set(True)
p2.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects["P1"]
bpy.ops.object.join()
res = fit.coverage_region({"target": bpy.context.active_object.name})
check("two disjoint islands → 2 pieces", res["pieces"] == 2, str(res.get("pieces")))


print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

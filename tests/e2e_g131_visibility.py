"""E2E for Cluster 10 — render visibility reads (G131):

  A surface recessed in an opaque vessel reads ~100% whole-bbox occluded, but its top is
  visible through the mouth. check_visible / check_framing's visible_surface_pct reports the
  FRONT-FACING visible surface, so 'is the liquid visible?' gets a true yes.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g131_visibility.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402
import math  # noqa: E402

from extension import server as bb_server  # noqa: E402

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FAIL '} {label}" + ("" if cond else f"   {detail}"))
    if not cond:
        failures.append(label)


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


clean()
# an opaque open cup: a cylinder wall, no top cap (open mouth), closed bottom
bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=0.2, vertices=48, location=(0, 0, 0.1))
cup = bpy.context.active_object; cup.name = "Cup"
bm = bmesh.new(); bm.from_mesh(cup.data)
top = [f for f in bm.faces if all(v.co.z > 0.099 for v in f.verts)]
bmesh.ops.delete(bm, geom=top, context='FACES')
bm.to_mesh(cup.data); bm.free()

# liquid disk filling most of the cup, surface a bit below the rim
bpy.ops.mesh.primitive_cylinder_add(radius=0.09, depth=0.14, vertices=48, location=(0, 0, 0.08))
bpy.context.active_object.name = "Coffee"

# camera above, looking down into the cup (sees the liquid surface through the mouth)
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (0, -0.05, 0.6)
cam.rotation_euler = (math.radians(20), 0, 0)   # tilt down toward the cup
bpy.context.scene.camera = cam

res = run("check_visible", targets="Coffee", camera="Cam")
v = res["visibility"][0]
check("check_visible reports the liquid surface as VISIBLE", v["visible"], str(v))
check("visible_surface_pct is meaningfully > 0", v["visible_surface_pct"] > 5, str(v))

# whole-bbox occlusion (legacy) should still read mostly hidden — proving the new metric differs
fr = run("check_framing", targets="Coffee", camera="Cam")["framing"][0]
check("framing carries the new visible_surface_pct", "visible_surface_pct" in fr, str(fr))
check("new metric is higher than whole-bbox-visible would imply",
      fr["visible_surface_pct"] >= v["visible_surface_pct"] - 1e-6, str(fr))

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

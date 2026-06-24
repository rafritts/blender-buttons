"""E2E for Cluster 7 — relational placement (G123):

  rest_on a convex/domed base seats its true lowest point on the surface (no overshoot
  below) — the seat is computed over the FULL evaluated vert set, not a downsample.
  place on={right_of: X} preserves the mover's current Z (doesn't bury it at the target's
  level).

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g123_relational.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension.common import world_bbox  # noqa: E402

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


# ---- G123(1): rest_on a convex base seats the true low point, no overshoot ----------
clean()
bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0, 0, 0))
bpy.context.active_object.name = "Floor"
# a high-res UV sphere — its bottom pole is a SINGLE sparse vert (the sampling trap)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.1, segments=64, ring_count=48, location=(0, 0, 1.0))
bpy.context.active_object.name = "Ball"
run("rest_on", targets="Ball", target="Floor")
zmin = world_bbox(bpy.data.objects["Ball"])[2]
check("convex base rests AT the floor (zmin ≈ 0)", abs(zmin) < 1e-3, f"zmin={zmin:.5f}")
check("does NOT overshoot below the floor", zmin > -1e-3, f"zmin={zmin:.5f}")


# ---- G123(2): place right_of preserves the mover's Z ---------------------------------
clean()
bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0, 0, 0.55))   # elevated plate
bpy.context.active_object.name = "Plate"
bpy.ops.mesh.primitive_cube_add(size=0.1, location=(-0.5, 0, 0.05))  # mug resting on floor
bpy.context.active_object.name = "Mug"
z_before = world_bbox(bpy.data.objects["Mug"])[2]
run("place", targets="Mug", on={"right_of": "Plate"})
mb = world_bbox(bpy.data.objects["Mug"])
z_after = mb[2]
check("place right_of preserves the mover's Z (not buried)", abs(z_after - z_before) < 1e-4,
      f"z {z_before:.4f} -> {z_after:.4f}")
check("place right_of did move it in X (beside the plate)",
      mb[0] >= world_bbox(bpy.data.objects['Plate'])[3] - 1e-4,
      f"mug xmin {mb[0]:.4f} vs plate xmax {world_bbox(bpy.data.objects['Plate'])[3]:.4f}")


print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

"""E2E for Cluster 8 — instanced / shared-mesh ops:

  G103 — scale_group on instanced (shared-mesh) members keeps OBJECT-level scale instead of
         aborting at the mesh-data bake (and leaving the group half-applied); single-user
         members are still baked.
  G113 — material op=set on a shared-mesh instance makes it single-user so a per-object
         colour sticks (when the mesh is shared with objects outside the target).

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g103_g113_instanced.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

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


def instance_pair():
    bpy.ops.mesh.primitive_cube_add(size=0.1, location=(0, 0, 0))
    a = bpy.context.active_object
    a.name = "I0"
    b = bpy.data.objects.new("I1", a.data)   # SHARES a.data
    b.location = (0.3, 0, 0)
    bpy.context.collection.objects.link(b)
    return a, b


# ---- G103: scale_group on instances doesn't abort; keeps object scale ----------------
clean()
a, b = instance_pair()
res = run("scale_group", targets=["I0", "I1"], factor=1.5)
check("scale_group on instances succeeds (no abort)", res.get("success"), res.get("error", ""))
check("instanced members kept object-level scale", len(res.get("kept_object_scale", [])) == 2,
      str(res.get("kept_object_scale")))
check("object scale actually applied (~1.5)", abs(bpy.data.objects["I0"].scale.x - 1.5) < 1e-4,
      str(bpy.data.objects["I0"].scale.x))
check("shared mesh intact (still one datablock)", bpy.data.objects["I0"].data is bpy.data.objects["I1"].data)

# a single-user mesh IS baked (scale returns to 1)
clean()
bpy.ops.mesh.primitive_cube_add(size=0.1)
bpy.context.active_object.name = "Solo"
res = run("scale_group", targets=["Solo"], factor=2.0)
check("single-user member baked (scale reset to 1)", abs(bpy.data.objects["Solo"].scale.x - 1.0) < 1e-4,
      str(bpy.data.objects["Solo"].scale.x))


# ---- G113: per-instance material via an OBJECT-linked slot, mesh stays shared ------
clean()
a, b = instance_pair()
res = run("set_material", target="I0", base_color=[1.0, 0.0, 0.0], material_name="Red")
check("set_material on a shared instance succeeds", res.get("success"), res.get("error", ""))
check("targeted instance got an object-linked slot", "I0" in res.get("object_linked", []),
      str(res.get("object_linked")))
check("I0 and I1 STILL share one mesh (no geometry duplication)",
      bpy.data.objects["I0"].data is bpy.data.objects["I1"].data)
# I0 shows Red through its per-object slot override
i0_slot = bpy.data.objects["I0"].material_slots[0]
check("I0's slot is OBJECT-linked to Red", i0_slot.link == 'OBJECT' and i0_slot.material
      and i0_slot.material.name == "Red", f"link={i0_slot.link} mat={i0_slot.material}")
# I1 (untargeted) reads the shared DATA slot, which was left untouched → not Red
i1_slot = bpy.data.objects["I1"].material_slots[0]
check("untargeted instance did NOT get the material",
      i1_slot.material is None or i1_slot.material.name != "Red",
      f"link={i1_slot.link} mat={i1_slot.material}")


print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

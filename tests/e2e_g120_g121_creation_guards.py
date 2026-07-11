"""E2E for Cluster 6 — creation guards:

  G120 — modifier add SUBSURF on a capped primitive with no holding loop near the cap warns
         about doming (and a plain box does NOT false-warn).

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g120_g121_creation_guards.py
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


def notes(res):
    return " ".join(res.get("notes", []))


# ---- G120: subsurf doming warning ----------------------------------------------------
clean()
bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.1, vertices=32)  # n-gon caps, no loops
bpy.context.active_object.name = "Mug"
res = run("add_modifier", type="SUBSURF", target="Mug", levels=2)
check("SUBSURF on a capped cylinder warns about doming",
      "DOME" in notes(res) or "dome" in notes(res).lower(), notes(res) or "(no notes)")

clean()
bpy.ops.mesh.primitive_cube_add(size=0.1)   # quad caps — subsurf just rounds, no doming trap
bpy.context.active_object.name = "Box"
res = run("add_modifier", type="SUBSURF", target="Box", levels=2)
check("SUBSURF on a plain box does NOT false-warn", "dome" not in notes(res).lower(),
      notes(res))


print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

"""E2E for Cluster 9 — PBR alpha handling (G126):

  - set_textured_material does NOT wire a detected alpha map into transparency by default
    (it made an opaque material invisible); use_alpha=True opts in.
  - set_material on an existing material whose Alpha is node-driven reports that the scalar
    override is shadowed (pass a new material_name to replace the graph).

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g126_pbr_alpha.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402

failures = []
PNG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bush.png")


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


def alpha_is_linked(mat_name):
    mat = bpy.data.materials.get(mat_name)
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    return bsdf.inputs['Alpha'].is_linked


# ---- G126 part 1: alpha map NOT wired by default ------------------------------------
clean()
bpy.ops.mesh.primitive_cube_add(size=0.1)
bpy.context.active_object.name = "Coffee"
res = run("set_textured_material", target="Coffee", asset_id="t",
          maps={"diffuse": PNG, "alpha": PNG}, material_name="CoffeeMat")
check("textured material applied", res.get("success"), res.get("error", ""))
check("alpha map detected-but-skipped by default", res.get("alpha_skipped") is True, str(res))
check("BSDF Alpha is NOT node-driven (opaque)", not alpha_is_linked("CoffeeMat"))

# opt in → alpha wired
clean()
bpy.ops.mesh.primitive_cube_add(size=0.1)
bpy.context.active_object.name = "Decal"
res = run("set_textured_material", target="Decal", asset_id="t",
          maps={"diffuse": PNG, "alpha": PNG}, material_name="DecalMat", use_alpha=True)
check("use_alpha=True wires the alpha map", "alpha" in res.get("maps_wired", []), str(res.get("maps_wired")))
check("BSDF Alpha IS node-driven with use_alpha", alpha_is_linked("DecalMat"))


# ---- G126 part 2: set_material reports a shadowed scalar -----------------------------
# DecalMat (above) has Alpha node-driven; setting alpha=1 by name must report it's shadowed.
res = run("set_material", target="Decal", material_name="DecalMat", alpha=1.0)
check("set_material flags the node-shadowed Alpha override",
      "Alpha" in res.get("shadowed_inputs", []), str(res.get("shadowed_inputs")))
check("note points at passing a new material_name",
      any("material_name" in n for n in res.get("notes", [])), str(res.get("notes")))


print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

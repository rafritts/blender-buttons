"""E2E for batch-7 gap fixes (V1, V2) — mesh-deform bind + topology-edit bind guard. Headless.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_batch7.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server   # noqa: E402

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


def mods(name):
    return {m.name: m for m in bpy.data.objects[name].modifiers}


# ───────── V1: add_modifier reaches the deform-modifier door ─────────
print("== V1: add_modifier MESH_DEFORM / ARMATURE / LATTICE ==")
clean()
# A high-res mesh enclosed by a low-res cage that fully contains it.
run("add_sphere", name="cloth", radius=1.0, segments=24, rings=16)
run("add_box", name="cage", width=2.6, depth=2.6, height=2.6)

# add_modifier acts on the ACTIVE object — select the mesh that takes the deform.
run("select_object", name="cloth")
r = run("add_modifier", type="MESH_DEFORM", target="cage", name="MD")
check("MESH_DEFORM added", r.get("success") is True, str(r))
check("reported unbound", r.get("bound") is False, str(r))
md = mods("cloth").get("MD")
check("MESH_DEFORM modifier exists on cloth", md is not None and md.type == 'MESH_DEFORM')
check("cage wired as mod.object", md is not None and md.object is bpy.data.objects["cage"])

# Missing target is a loud failure, not a dangling unbound modifier (cloth active).
bad = run("add_modifier", type="MESH_DEFORM")
check("MESH_DEFORM without target errors", "error" in bad, str(bad))
# Wrong-type target rejected (cage must be a mesh).
run("add_camera", name="cam1")
run("select_object", name="cloth")
badt = run("add_modifier", type="MESH_DEFORM", target="cam1")
check("MESH_DEFORM with non-mesh target errors", "error" in badt, str(badt))

# ARMATURE + LATTICE share the same door.
run("create_armature", name="rig", bones=[{"name": "root", "head": [0, 0, 0], "tail": [0, 0, 1]}])
run("select_object", name="cloth")
ra = run("add_modifier", type="ARMATURE", target="rig", name="Arm")
check("ARMATURE modifier added", ra.get("success") is True, str(ra))
check("ARMATURE wired to rig", mods("cloth")["Arm"].object is bpy.data.objects["rig"])
# Lattice object (no MCP add_lattice — make one directly; the modifier wrapper is what we test).
lat_data = bpy.data.lattices.new("Lat")
lat_obj = bpy.data.objects.new("latt", lat_data)
bpy.context.scene.collection.objects.link(lat_obj)
run("select_object", name="cloth")
rl = run("add_modifier", type="LATTICE", target="latt", name="Latt")
check("LATTICE modifier added", rl.get("success") is True, str(rl))

# ───────── V1: bind_mesh_deform bind / rebind / unbind ─────────
print("== V1: bind_mesh_deform ==")
b = run("bind_mesh_deform", mesh="cloth", modifier="MD")
check("bind success", b.get("success") is True, str(b))
check("modifier reports bound", b.get("bound") is True, str(b))
check("mod.is_bound True", mods("cloth")["MD"].is_bound is True)

# Binding deforms: MESH_DEFORM follows the cage's GEOMETRY (not rigid object
# motion), so push the cage verts and the bound cloth's evaluated geometry moves.
from extension.common import eval_world_center  # noqa: E402
c0 = eval_world_center(bpy.data.objects["cloth"])
cage_me = bpy.data.objects["cage"].data
for v in cage_me.vertices:
    v.co.x += 0.5
cage_me.update()
bpy.context.view_layer.update()
c1 = eval_world_center(bpy.data.objects["cloth"])
check("bound cloth follows cage deformation", abs(c1[0] - c0[0]) > 0.1,
      f"dx={c1[0]-c0[0]:.3f}")
for v in cage_me.vertices:
    v.co.x -= 0.5
cage_me.update()
bpy.context.view_layer.update()

# rebind on an already-bound modifier stays bound.
rb = run("bind_mesh_deform", mesh="cloth", modifier="MD", action="rebind")
check("rebind success", rb.get("success") is True and rb.get("bound") is True, str(rb))

# unbind drops the bind data.
ub = run("bind_mesh_deform", mesh="cloth", modifier="MD", action="unbind")
check("unbind success", ub.get("success") is True, str(ub))
check("modifier reports unbound", ub.get("bound") is False, str(ub))
check("mod.is_bound False after unbind", mods("cloth")["MD"].is_bound is False)

# bind_mesh_deform creates the modifier when only a cage is given.
clean()
run("add_sphere", name="skin", radius=1.0, segments=20, rings=14)
run("add_box", name="cage2", width=2.6, depth=2.6, height=2.6)
bc = run("bind_mesh_deform", mesh="skin", cage="cage2")
check("auto-create + bind from cage only", bc.get("success") is True and bc.get("bound") is True, str(bc))
check("created a MESH_DEFORM modifier", any(m.type == 'MESH_DEFORM' for m in bpy.data.objects["skin"].modifiers))

# No modifier and no cage → loud error, not a silent no-op.
clean()
run("add_box", name="lonely", width=1, depth=1, height=1)
ne = run("bind_mesh_deform", mesh="lonely")
check("bind with no modifier and no cage errors", "error" in ne, str(ne))

# ───────── V2: topology edit warns when it kills a deform bind ─────────
print("== V2: topology edit invalidates the bind, loudly ==")
clean()
run("add_sphere", name="shirt", radius=1.0, segments=24, rings=16)
run("add_box", name="shirtcage", width=2.6, depth=2.6, height=2.6)
run("bind_mesh_deform", mesh="shirt", cage="shirtcage")
check("shirt bound before edit", mods("shirt")["MeshDeform"].is_bound is True)
before_verts = len(bpy.data.objects["shirt"].data.vertices)

# A topology edit (delete a chunk) must fire the bind-invalidation warning.
run("select_by_axis", target="shirt", axis="Z", factor=0.5, comparison="GREATER")
d = run("delete_geometry", target="shirt", mode="VERT")
check("delete_geometry success", d.get("success") is True, str(d))
check("vert count actually changed", len(bpy.data.objects["shirt"].data.vertices) != before_verts,
      f"{before_verts} -> {len(bpy.data.objects['shirt'].data.vertices)}")
check("V2 bind_invalidated flag set", d.get("bind_invalidated") is True, str(d))
check("V2 warning names the modifier + rebind path",
      "MeshDeform" in (d.get("bind_warning") or "") and "rebind" in (d.get("bind_warning") or "").lower(),
      str(d.get("bind_warning")))

# A position-only edit (no vert-count change) must NOT warn — the bind survives.
clean()
run("add_sphere", name="pants", radius=1.0, segments=24, rings=16)
run("add_box", name="pantscage", width=2.6, depth=2.6, height=2.6)
run("bind_mesh_deform", mesh="pants", cage="pantscage")
n_before = len(bpy.data.objects["pants"].data.vertices)
run("select_all", target="pants", action="SELECT")
mv = run("move_vertices", target="pants", z=0.05)
check("move_vertices success", mv.get("success") is True, str(mv))
check("position-only edit kept the vert count",
      len(bpy.data.objects["pants"].data.vertices) == n_before)
check("position-only edit does NOT warn (bind intact)", not mv.get("bind_invalidated"), str(mv))

# An edit on an UNBOUND mesh-deform mesh must not warn (nothing to invalidate).
clean()
run("add_sphere", name="loose", radius=1.0, segments=20, rings=14)
run("add_box", name="loosecage", width=2.6, depth=2.6, height=2.6)
run("add_modifier", type="MESH_DEFORM", target="loosecage", name="MD")  # added, never bound
run("select_by_axis", target="loose", axis="Z", factor=0.5, comparison="GREATER")
du = run("delete_geometry", target="loose", mode="VERT")
check("unbound mesh-deform edit does NOT warn", not du.get("bind_invalidated"), str(du))

print()
if failures:
    print(f"BATCH7 E2E: {len(failures)} FAILED: {failures}")
    sys.exit(1)
else:
    print("BATCH7 E2E: ALL TESTS PASSED")

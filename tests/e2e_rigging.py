"""E2E for the R1-R5 rigging/set-dressing gaps, in headless Blender.

Usage: flatpak run org.blender.Blender --background --python /abs/path/tests/e2e_rigging.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import mathutils  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension.armature import _orphan_islands  # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok    {label}")
    else:
        failures.append(label)
        print(f"  FAIL  {label}  {detail}")


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def fresh():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def eval_world_verts(obj):
    """Evaluated (post-modifier) world-space vertices of a mesh/curve object."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    pts = [(ev.matrix_world @ v.co).copy() for v in me.vertices]
    ev.to_mesh_clear()
    return pts


# ─────────────────────────── R3 deform flag ───────────────────────────
print("== R3 create_armature deform=false ==")
fresh()
r = run("create_armature", name="rig", bones=[
    {"name": "root", "head": [0, 0, 0], "tail": [0, 0, 0.2], "deform": False},
    {"name": "swing", "head": [0, 0, 0.2], "tail": [0, 0, 0.4], "parent": "root"},
])
check("create_armature success", r.get("success"), r.get("error"))
check("root reported non-deform", r.get("non_deform_bones") == ["root"], r.get("non_deform_bones"))
arm = bpy.data.objects["rig"]
check("root.use_deform is False", arm.data.bones["root"].use_deform is False)
check("swing.use_deform is True (default)", arm.data.bones["swing"].use_deform is True)

# ─────────────────────────── R1 weight_to_bone ───────────────────────────
print("== R1 weight_to_bone ==")
fresh()
run("add_box", name="lever", width=0.2, depth=0.2, height=0.4, on={"at": [0, 0, 1.0]})
run("create_armature", name="lrig", bones=[
    {"name": "b0", "head": [0, 0, 0.8], "tail": [0, 0, 1.2]},
])
r = run("weight_to_bone", mesh="lever", armature="lrig", bone="b0")
check("weight_to_bone success", r.get("success"), r.get("error"))
mesh = bpy.data.objects["lever"]
check("vertex group 'b0' created", "b0" in [vg.name for vg in mesh.vertex_groups])
check("all verts weighted", r.get("weighted_vertices") == r.get("total_vertices") == len(mesh.data.vertices),
      (r.get("weighted_vertices"), r.get("total_vertices")))
check("armature modifier present", any(m.type == 'ARMATURE' and m.object == bpy.data.objects["lrig"]
                                       for m in mesh.modifiers))
rest = eval_world_verts(mesh)
run("pose_bone", armature="lrig", bone="b0", rot=[0, 0, 90])
posed = eval_world_verts(mesh)
max_delta = max((a - b).length for a, b in zip(rest, posed))
check("posing the bone deforms the rigid-bound mesh", max_delta > 0.05, f"max_delta={max_delta:.4f}")

# ─────────────────────────── R2 orphan-island verdict ───────────────────────────
print("== R2 _orphan_islands ==")
fresh()
# Two separated boxes joined into one mesh → two connected islands. Weight only
# the verts of the first box; the second box's 8 verts are one orphan island.
run("add_box", name="part", width=0.2, depth=0.2, height=0.2, on={"at": [0, 0, 0.1]})
run("add_box", name="ring", width=0.2, depth=0.2, height=0.2, on={"at": [0, 0, 2.0]})
run("join_objects", names=["part", "ring"])
mesh = bpy.data.objects["part"]
vg = mesh.vertex_groups.new(name="b0")
lower = [v.index for v in mesh.data.vertices if (mesh.matrix_world @ v.co).z < 1.0]
vg.add(lower, 1.0, 'REPLACE')
total, orphans, islands = _orphan_islands(mesh)
check("total verts counted", total == len(mesh.data.vertices), total)
check("8 orphans found", orphans == 8, orphans)
check("one orphan island", len(islands) == 1, islands)
check("island located at top", islands and "top" in islands[0][1], islands)

# ─────────────────────────── R4 add_curve anchors ───────────────────────────
print("== R4 add_curve anchored hooks ==")
fresh()
# Object anchor: a curve end hooked to a box; moving the box drags the curve.
run("add_box", name="drum", width=0.2, depth=0.2, height=0.2, on={"at": [1, 0, 0.5]})
r = run("add_curve", name="rope", type="NURBS", bevel_depth=0.05, points=[
    {"anchor": {"object": "drum"}},
    [2, 0, 0.5],
])
check("add_curve anchored success", r.get("success"), r.get("error"))
check("one anchor reported", len(r.get("anchored", [])) == 1, r.get("anchored"))
rope = bpy.data.objects["rope"]
hook = next((m for m in rope.modifiers if m.type == 'HOOK'), None)
check("hook modifier present", hook is not None)
check("hook targets drum", hook and hook.object == bpy.data.objects["drum"], hook and hook.object)
zmax_before = max(p.z for p in eval_world_verts(rope))
bpy.data.objects["drum"].location.z += 1.0
bpy.context.view_layer.update()
zmax_after = max(p.z for p in eval_world_verts(rope))
check("curve follows moved anchor object", zmax_after - zmax_before > 0.5, (zmax_before, zmax_after))

# Bone anchor: setup + rest no-jump + follows on pose.
fresh()
run("create_armature", name="crig", bones=[{"name": "arm", "head": [0, 0, 1], "tail": [0.5, 0, 1]}])
r = run("add_curve", name="cable", type="POLY", bevel_depth=0.03, points=[
    [0, 0, 0],
    # anchor at the bone TAIL (offset from the head pivot) so a Z-swing translates it
    {"at": [0.5, 0, 1], "anchor": {"bone": "crig/arm"}},
])
check("bone anchor success", r.get("success"), r.get("error"))
cable = bpy.data.objects["cable"]
hook = next((m for m in cable.modifiers if m.type == 'HOOK'), None)
check("bone hook targets armature", hook and hook.object == bpy.data.objects["crig"], hook and hook.object)
check("bone hook subtarget set", hook and hook.subtarget == "arm", hook and hook.subtarget)
end_before = max(p.x for p in eval_world_verts(cable))
run("pose_bone", armature="crig", bone="arm", rot=[0, 0, 90])
end_after = max(p.x for p in eval_world_verts(cable))
check("curve end follows posed bone", abs(end_after - end_before) > 0.1, (end_before, end_after))

# ─────────────────────────── R5 scatter avoid zone ───────────────────────────
print("== R5 scatter_on_surface avoid ==")
fresh()
run("add_box", name="ground", width=4, depth=4, height=0.1, on={"at": [0, 0, 0]})
run("add_box", name="rock", width=0.1, depth=0.1, height=0.1, on={"at": [0, 0, 2]})
run("add_box", name="hero", width=1.0, depth=1.0, height=1.0, on={"at": [0, 0, 0.5]})
r = run("scatter_on_surface", target="ground", source="rock", count=300,
        avoid="hero", avoid_margin=0.1, seed=1, parent_to_target=False)
check("scatter avoid success", r.get("success"), r.get("error"))
insts = [o for o in bpy.data.objects if o.name.startswith("rock_inst")]
check("instances created", len(insts) > 0, len(insts))
# avoid rect: hero bbox [-0.5,0.5] + margin 0.1 → [-0.6,0.6]
inside = [o.name for o in insts if -0.6 <= o.location.x <= 0.6 and -0.6 <= o.location.y <= 0.6]
check("no instance inside avoid zone", not inside, inside[:5])

print()
if failures:
    print(f"E2E-RIGGING: {len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("E2E-RIGGING: ALL TESTS PASSED")
sys.exit(0)

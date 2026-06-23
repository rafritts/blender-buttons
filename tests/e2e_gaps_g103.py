"""E2E for G103 — scale_group on instanced/multi-user meshes. Headless.

Scatter makes linked instances sharing ONE mesh datablock. The old scale_group moved
every object's transform, then in a second pass baked the scale into mesh data with
transform_apply — which raises "Cannot apply to a multi user" on the first instanced
member, leaving the group HALF-applied and the world dirty. The fix skips the bake for
shared/linked meshes (object-level scale renders correctly and needs no bake), so the op
completes atomically and never dirties the world.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_gaps_g103.py
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
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    state.reset_history_state()


def make_shared_instances(prefix, n, mesh_name, half=0.1):
    """n objects that all share ONE mesh datablock (linked instances, like scatter)."""
    me = bpy.data.meshes.new(mesh_name)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2 * half); bm.to_mesh(me); bm.free()
    names = []
    for i in range(n):
        obj = bpy.data.objects.new(f"{prefix}_{i}", me)   # SAME mesh → multi-user
        obj.location = (i * 0.5, 0.0, 0.5)
        bpy.context.scene.collection.objects.link(obj)
        names.append(obj.name)
    bpy.context.view_layer.update()
    return me, names


def make_solo_box(name, cx, half=0.2):
    me = bpy.data.meshes.new(name + "_mesh")
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2 * half); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = (cx, 0.0, 0.5)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


print("\nG103 — scale_group on multi-user instances completes atomically\n")

# ── multi-user instances: no abort, object-level scale kept, mesh untouched ───
clean()
me, names = make_shared_instances("Inst", 5, "SharedDrop")
check("5 instances share one mesh", me.users == 5, f"users={me.users}")

r = run("scale_group", targets=names, factor=1.5, pivot="center")
check("scale_group succeeded (no multi-user abort)", r.get("success"), str(r)[:200])
check("no member was baked (all shared)", r.get("baked") == [], str(r.get("baked")))
check("all instanced members kept object-level scale",
      set(r.get("kept_object_scale", [])) == set(names), str(r.get("kept_object_scale")))
check("each instance now carries factor object-scale (~1.5)",
      all(abs(bpy.data.objects[n].scale.x - 1.5) < 1e-5 for n in names),
      str([round(bpy.data.objects[n].scale.x, 3) for n in names]))
check("the shared mesh datablock is UNTOUCHED (still one shared mesh, users=5)",
      me.users == 5 and len(bpy.data.meshes) == 1, f"users={me.users} meshes={len(bpy.data.meshes)}")
# relative layout preserved (spacing grew by factor about the center pivot)
xs = sorted(bpy.data.objects[n].location.x for n in names)
gaps = [round(xs[i + 1] - xs[i], 4) for i in range(len(xs) - 1)]
check("relative layout preserved & uniformly scaled (spacing 0.5×1.5=0.75)",
      all(abs(g - 0.75) < 1e-4 for g in gaps), str(gaps))

# ── atomicity: the world is NOT left dirty by the server's own op ─────────────
state.detect_external_mutation()
check("op did NOT trip the SPEC-15 external-mutation lock", not state._world_locked)

# ── single-user meshes: scale IS baked (object scale returns to 1) ────────────
clean()
make_solo_box("A", -1.0)
make_solo_box("B", 1.0)
r = run("scale_group", targets=["A", "B"], factor=2.0, pivot="center")
check("single-user scale_group succeeded", r.get("success"), str(r)[:160])
check("both single-user meshes were baked", set(r.get("baked", [])) == {"A", "B"}, str(r.get("baked")))
check("baked objects have object-scale reset to 1",
      all(abs(bpy.data.objects[n].scale.x - 1.0) < 1e-5 for n in ("A", "B")),
      str([round(bpy.data.objects[n].scale.x, 3) for n in ("A", "B")]))
check("no 'kept_object_scale' note for an all-single-user group", "kept_object_scale" not in r)

print()
if failures:
    print(f"e2e_gaps_g103 :: FAILED — {len(failures)} failure(s): {failures}")
    sys.exit(1)
print("e2e_gaps_g103 :: PASSED — 0 failure(s)")

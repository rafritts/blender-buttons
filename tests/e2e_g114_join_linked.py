"""E2E for G114 — `object op=join` on a SUBSET of linked instances must NOT corrupt
the shared mesh the survivors still depend on. Headless.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_g114_join_linked.py
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


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    state.reset_history_state()


def make_linked_instances(n, vcount_name="shared"):
    """n objects ALL sharing ONE mesh datablock — what scatter produces."""
    me = bpy.data.meshes.new(vcount_name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.1)
    bm.to_mesh(me)
    bm.free()
    objs = []
    for i in range(n):
        o = bpy.data.objects.new(f"inst{i}", me)   # same `me` for every instance
        o.location = (0.3 * i, 0, 0)
        bpy.context.scene.collection.objects.link(o)
        objs.append(o)
    bpy.context.view_layer.update()
    return me, objs


print("\nG114 — join on a subset of linked instances must not corrupt the survivors\n")

# ── join a SUBSET (2 of 4) — survivors must keep the pristine shared mesh ─────
clean()
me, objs = make_linked_instances(4)
orig_v = len(me.vertices)
check("setup: 4 instances share one 8-vert mesh", orig_v == 8 and me.users == 4,
      f"verts={orig_v} users={me.users}")
r = run("join_objects", names=["inst0", "inst1"])
check("join subset succeeds", r.get("success") is True, str(r.get("error")))
check("join made the target single-user (G114 guard fired)", r.get("made_single_user") is True, str(r))
# survivors inst2 / inst3 must still be the original single cube (8 verts), NOT the merged blob.
check("survivor inst2 still has the original 8 verts (not corrupted)",
      len(bpy.data.objects["inst2"].data.vertices) == 8,
      f"verts={len(bpy.data.objects['inst2'].data.vertices)}")
check("survivor inst3 still has the original 8 verts (not corrupted)",
      len(bpy.data.objects["inst3"].data.vertices) == 8)
# the join RESULT holds the merged two-cube geometry (16 verts).
res = bpy.data.objects.get(r["result_object"])
check("join result holds the merged geometry (16 verts)",
      res is not None and len(res.data.vertices) == 16, f"verts={len(res.data.vertices) if res else None}")

# ── joining ALL instances (no survivors) needs no copy ───────────────────────
clean()
me, objs = make_linked_instances(3)
r = run("join_objects", names=["inst0", "inst1", "inst2"])
check("join-all succeeds", r.get("success") is True, str(r.get("error")))
check("join-all does NOT needlessly make single-user (no survivors to protect)",
      not r.get("made_single_user"), str(r))
res = bpy.data.objects.get(r["result_object"])
check("join-all result holds all three cubes (24 verts)",
      res is not None and len(res.data.vertices) == 24, f"verts={len(res.data.vertices) if res else None}")

# ── a normal join of independent meshes is unaffected ────────────────────────
clean()
for i in range(2):
    me = bpy.data.meshes.new(f"indep{i}")
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=0.1); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(f"box{i}", me)
    o.location = (0.3 * i, 0, 0)
    bpy.context.scene.collection.objects.link(o)
bpy.context.view_layer.update()
r = run("join_objects", names=["box0", "box1"])
check("join of independent meshes succeeds", r.get("success") is True, str(r.get("error")))
check("independent join does not trip the single-user guard", not r.get("made_single_user"), str(r))


print(f"\n{'PASSED' if not failures else 'FAILED'} — {len(failures)} failure(s)")
for f in failures:
    print(f"   ✗ {f}")
sys.exit(1 if failures else 0)

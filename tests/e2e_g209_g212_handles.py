"""E2E for the handle/radial gap batch — runs the WORKING-TREE extension headless.

  G209 — feel op=handle source=selection re-enters edit mode itself (no mode dance).
  G210 — a handle SURVIVES a topology change that inherits its vgroup (subdivide), instead
         of orphaning on a vert-count checksum.
  G212 — feel op=radial crossing=rim lands ON the open boundary loop, LOWER than the wall
         a horizontal 'outer' cast hits.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_g209_g212_handles.py
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
    for c in list(bpy.data.collections):
        if c.name == "Handles":
            bpy.data.collections.remove(c)
    state.reset_history_state()


def make_grid(name, size=0.1, segs=6):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=segs, y_segments=segs, size=size / 2.0)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def select_central(obj, r):
    """Select verts within r of local origin, leave OBJECT mode (as a select op does)."""
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    n = 0
    for v in obj.data.vertices:
        if v.co.length < r:
            v.select = True
            n += 1
    return n


# ───────────────────────── G209: mint re-enters edit mode itself ─────────────────────────
print("== G209: feel op=handle re-enters edit mode on the selection's owner ==")
clean()
g = make_grid("Slab", size=0.2, segs=8)
nsel = select_central(g, 0.04)
check("selection captured some verts", nsel > 0, str(nsel))
check("mesh is in OBJECT mode before mint (as after a select op)", g.mode == 'OBJECT')
res = run("mint_handle", source="selection", name="anchorA")
check("mint SUCCEEDED from object mode (no 'must be in edit mode' refusal)",
      res.get("success"), str(res)[:200])
check("mint reports the vert count it captured", res.get("vert_count", 0) == nsel,
      f"minted {res.get('vert_count')} vs selected {nsel}")
check("mesh returned to OBJECT mode after mint", bpy.data.objects["Slab"].mode == 'OBJECT')


# ───────────────────────── G210: handle survives subdivide ─────────────────────────
print("== G210: a handle survives a topology change (subdivide inherits the vgroup) ==")
# subdivide the whole mesh — new verts inherit the HANDLE_ vgroup weights
bpy.context.view_layer.objects.active = g
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.subdivide(number_cuts=1)
bpy.ops.object.mode_set(mode='OBJECT')
res = run("resolve_handle", name="anchorA")
check("handle still RESOLVES after subdivide (not orphaned)", res.get("success"),
      str(res)[:200])
check("resolve returns a live point", res.get("point") is not None, str(res)[:160])
check("state is 'dirty' (flagged), NOT 'orphaned'", res.get("state") == "dirty",
      str(res.get("state")))
# accept re-baselines it back to clean
res2 = run("accept_handle", name="anchorA")
check("accept re-baselines the handle to clean", res2.get("state") == "clean",
      str(res2)[:160])


# ───────────────────────── G212: crossing=rim lands on the boundary loop ─────────────────────────
print("== G212: feel op=radial crossing=rim lands on the open boundary, below the wall ==")
clean()
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.05, segments=24, ring_count=16, location=(0, 0, 0))
dome = bpy.context.active_object
dome.name = "Dome"
# delete the lower half → an open hemisphere with a rim at z≈0
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.object.mode_set(mode='OBJECT')
for v in dome.data.vertices:
    if v.co.z < -0.002:
        v.select = True
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.delete(type='VERT')
bpy.ops.object.mode_set(mode='OBJECT')

rim = run("radial_landmark", anchor="Dome", angle=0.0, crossing="rim")
check("crossing=rim succeeds", rim.get("success"), str(rim)[:200])
check("crossing reported as 'rim'", rim.get("crossing") == "rim", str(rim.get("crossing")))
rim_z = rim["point"][2] if rim.get("point") else None
check("rim point sits at the boundary (z≈0)", rim_z is not None and abs(rim_z) < 0.012,
      f"rim_z={rim_z}")

outer = run("radial_landmark", anchor="Dome", angle=0.0, crossing="outer")
check("crossing=outer succeeds", outer.get("success"), str(outer)[:160])
outer_z = outer["point"][2] if outer.get("point") else None
check("outer (horizontal cast) lands HIGHER up the wall than the rim",
      outer_z is not None and rim_z is not None and outer_z > rim_z + 0.008,
      f"rim_z={rim_z} outer_z={outer_z}")

# a different clock angle picks a different boundary vert
rim90 = run("radial_landmark", anchor="Dome", angle=90.0, crossing="rim")
p0 = rim.get("point"); p90 = rim90.get("point")
check("angle=90 lands on a different rim point than angle=0",
      p0 and p90 and (abs(p0[0] - p90[0]) > 0.02 or abs(p0[1] - p90[1]) > 0.02),
      f"0°={p0} 90°={p90}")


print()
if failures:
    print(f"e2e_g209_g212_handles :: FAILED — {len(failures)}: {failures}")
    sys.exit(1)
print("e2e_g209_g212_handles :: PASSED — 0 failures")

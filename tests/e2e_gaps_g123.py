"""E2E for G123 — rest_on overshoot on a convex base + place rewriting Z. Headless.

(1) rest_on seated against a DOWNSAMPLED vert set, so a convex/subsurf-domed base whose
    true lowest point is a single vertex (missed by every-Nth sampling) ended up poking
    below the surface. _prepare(ensure_axis=) now forces the axis-extreme verts into the
    sample, so the part seats by its real lowest point.

(2) place on={right_of: …} (a horizontal-only relation) re-centred the mover's Z on the
    target, burying it. place now preserves the mover's current Z unless the spec authors
    a vertical relation (on/under/…).

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_gaps_g123.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402
from extension import introspect            # noqa: E402
from extension.common import world_bbox     # noqa: E402

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
    state.reset_history_state()


def make_floor(name, half=3.0, z=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bm.verts.new((-half, -half, z)); bm.verts.new((half, -half, z))
    bm.verts.new((half, half, z));   bm.verts.new((-half, half, z))
    bm.verts.ensure_lookup_table()
    bm.faces.new(bm.verts)
    bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def make_box(name, cx, cy, cz, half):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2 * half); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = (cx, cy, cz)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def make_spiky_stack(name, n=1100, low_index=537):
    """A vert cloud at xy=(0,0): all at z=1 except a UNIQUE lowest vert at z=0, placed at
    an ODD index so the every-2nd downsample (cap 500 over 1100 verts) MISSES it. The true
    lowest point is therefore invisible to the old sampling but caught by ensure_axis."""
    assert low_index % 2 == 1, "low vert must sit at an odd index to be missed by step=2"
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for i in range(n):
        bm.verts.new((0.0, 0.0, 0.0 if i == low_index else 1.0))
    bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def true_min_z(name):
    obj = bpy.data.objects[name]
    return min((obj.matrix_world @ v.co).z for v in obj.data.vertices)


print("\nG123 — rest_on seats by true lowest point; place keeps Z for horizontal relations\n")

# ── 1a. _prepare(ensure_axis) includes the global extreme verts ───────────────
print("[G123-1] rest_on uses the true axis-extreme vertex")
clean()
spiky = make_spiky_stack("Spiky")
plain = introspect._prepare(spiky, cap=500)
fixed = introspect._prepare(spiky, cap=500, ensure_axis=2)
check("plain downsample MISSES the unique low vert (reproduces the bug)",
      min(v.z for v in plain["verts"]) > 0.5, f"min={min(v.z for v in plain['verts'])}")
check("ensure_axis=Z includes the true lowest vert",
      min(v.z for v in fixed["verts"]) < 1e-6, f"min={min(v.z for v in fixed['verts'])}")

# ── 1b. rest_on seats the true lowest point on the floor, no overshoot ────────
make_floor("Floor")
r = run("rest_on", targets="Spiky", target="Floor")
check("rest_on succeeded", r.get("success"), str(r)[:160])
mz = true_min_z("Spiky")
check("source's TRUE lowest point rests at the floor (z≈0), not below",
      abs(mz) < 1e-4, f"true min z after rest_on = {mz}")

# ── 2. place right_of preserves the mover's Z (does not bury it) ──────────────
print("[G123-2] place horizontal relation preserves Z")
clean()
make_floor("Tbl")
# plate centred high up; mug resting on the floor (min z = 0).
plate = make_box("Plate", 0, 0, 1.0, 0.5)
mug = make_box("Mug", 0, 0, 0.2, 0.2)             # bottom at z=0 (on the floor)
z_before = true_min_z("Mug")
check("mug starts on the floor", abs(z_before) < 1e-6, f"z={z_before}")

r = run("place", targets="Mug", on={"right_of": "Plate"})
check("place succeeded", r.get("success"), str(r)[:160])
mb = world_bbox(bpy.data.objects["Mug"])
pb = world_bbox(bpy.data.objects["Plate"])
check("mug moved to the +X side of the plate", mb[0] >= pb[3] - 1e-6, f"mug.xmin={mb[0]} plate.xmax={pb[3]}")
check("mug's Z is PRESERVED (still on the floor, not reseated to plate level)",
      abs(true_min_z("Mug")) < 1e-6, f"z after = {true_min_z('Mug')}")

# regression: a VERTICAL relation (on:) still authors Z.
r = run("place", targets="Mug", on={"on": "Plate"})
check("place on={on:…} still seats Z on top of the target",
      abs(true_min_z("Mug") - pb[5]) < 1e-4, f"mug min z={true_min_z('Mug')} plate top={pb[5]}")

print()
if failures:
    print(f"e2e_gaps_g123 :: FAILED — {len(failures)} failure(s): {failures}")
    sys.exit(1)
print("e2e_gaps_g123 :: PASSED — 0 failure(s)")

"""E2E for the G107 fix — `feel op=resting` measures a cavity-seated part against the
support surface BENEATH it, not the support's rim/bbox-top, and names the datum.

  Before: a part resting on a well/bowl FLOOR was reported "sunk <well-depth>mm" because
          _support_below handed back the support's bbox TOP (the rim). A confident wrong
          number with no hint of the assumption.
  After:  the datum is recast (downward raycast) to the real load-bearing surface under
          the part's lowest verts → "resting"; and when the support is concave, a note
          names both the floor measured against and the rim it is NOT. Flat supports stay
          silent (no new noise).

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_gaps_g107.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402

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


def _mesh(name, verts, faces):
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in verts]
    for f in faces:
        bm.faces.new([vs[i] for i in f])
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    return ob


def make_tray(name, half, rim, floor_z=0.0):
    """Open box (a bowl): inner floor at floor_z, walls up to rim, no top. Its bbox TOP is
    the rim; the surface a part drops onto is the floor far below it."""
    b = [(-half, -half, floor_z), (half, -half, floor_z), (half, half, floor_z), (-half, half, floor_z)]
    t = [(-half, -half, rim), (half, -half, rim), (half, half, rim), (-half, half, rim)]
    faces = [(0, 1, 2, 3)]  # floor
    for i in range(4):       # walls
        j = (i + 1) % 4
        faces.append((i, j, 4 + j, 4 + i))
    return _mesh(name, b + t, faces)


def make_box(name, half, z0, z1):
    v = [(-half, -half, z0), (half, -half, z0), (half, half, z0), (-half, half, z0),
         (-half, -half, z1), (half, -half, z1), (half, half, z1), (-half, half, z1)]
    f = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return _mesh(name, v, f)


def _rest(name):
    res = run("check_resting", targets=name)
    return res["resting"][0] if res.get("resting") else res


# ── 1. concave support: part on the well FLOOR reads resting, not sunk ──────────────
clean()
make_tray("Bowl", half=0.08, rim=0.013, floor_z=0.0)   # rim 13mm above the floor
make_box("Biscuit", half=0.02, z0=0.0, z1=0.02)        # resting on the floor (z=0)

r = _rest("Biscuit")
check("G107 seated part reads 'resting', not 'sunk'", r.get("state") == "resting",
      f"state={r.get('state')} clearance_mm={r.get('clearance_mm')} (old bug: sunk 13mm)")
check("G107 clearance ~0 against the floor", abs(r.get("clearance_mm", 99)) <= 0.5,
      f"clearance_mm={r.get('clearance_mm')}")
check("G107 datum is the floor (z~0), not the rim (z~0.013)",
      abs(r.get("support_z", 9)) <= 0.001, f"support_z={r.get('support_z')}")
check("G107 concave support is flagged with a datum-naming note",
      bool(r.get("note")) and "rim" in r.get("note", ""), f"note={r.get('note')!r}")

# ── 2. flat support: no false 'sunk', and NO note (fix adds no noise) ───────────────
clean()
make_box("Slab", half=0.08, z0=0.0, z1=0.01)           # flat top at z=0.01
make_box("Cup", half=0.02, z0=0.01, z1=0.05)           # resting on the slab top

r = _rest("Cup")
check("flat support still reads 'resting'", r.get("state") == "resting",
      f"state={r.get('state')} clearance_mm={r.get('clearance_mm')}")
check("flat support emits NO note (no added noise)", not r.get("note"),
      f"note={r.get('note')!r}")

# ── 3. genuinely floating part is still caught ─────────────────────────────────────
clean()
make_box("Ground", half=0.08, z0=0.0, z1=0.01)
make_box("Hovering", half=0.02, z0=0.02, z1=0.04)      # 10mm above the slab top

r = _rest("Hovering")
check("real float still reported", r.get("state") == "floating",
      f"state={r.get('state')} clearance_mm={r.get('clearance_mm')}")

print()
if failures:
    print(f"FAILED: {len(failures)} — {failures}")
    sys.exit(1)
print("all G107 checks passed")

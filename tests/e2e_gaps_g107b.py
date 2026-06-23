"""E2E for the G107 contacts half — `check_contacts` / `auto_proximity_note` gate
penetration on a SIGNED surface crossing (interior point inside the other solid), not on a
bbox-axis overlap alone.

  Before: a part SEATED in a recess (a donut in a plate well) overlaps the support's bbox
          on every axis while only touching its floor → flagged 'penetrating <well-depth>mm',
          unasked, on every placement.
  After:  penetration requires bbox overlap (kept — nothing new is ever flagged) AND the
          solids to actually cross. A seated part reads connected; a genuine interpenetration
          (a part sunk into another — chain links, sunk markers, G32) still reads penetrating,
          now with a true inside-depth.

Closed bmesh geometry (no add_box placement DSL) so it runs under --factory-startup.
Usage: flatpak run org.blender.Blender --background --factory-startup --python /abs/path/tests/e2e_gaps_g107b.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension.introspect import auto_proximity_note  # noqa: E402

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
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)  # consistent OUTWARD normals
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    return ob


def make_box(name, half, z0, z1):
    v = [(-half, -half, z0), (half, -half, z0), (half, half, z0), (-half, half, z0),
         (-half, -half, z1), (half, -half, z1), (half, half, z1), (-half, half, z1)]
    f = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return _mesh(name, v, f)


def make_plate_well(name, outer=0.06, inner=0.04, rim=0.013, floor=0.008):
    """A CLOSED solid plate with a recessed well: outer box 0..rim, top inset down to a
    well floor — the real donut-plate shape (watertight, genus 0), so normals are defined."""
    ob = [(-outer, -outer, 0), (outer, -outer, 0), (outer, outer, 0), (-outer, outer, 0)]      # 0-3 outer bottom
    ot = [(-outer, -outer, rim), (outer, -outer, rim), (outer, outer, rim), (-outer, outer, rim)]  # 4-7 rim top
    ir = [(-inner, -inner, rim), (inner, -inner, rim), (inner, inner, rim), (-inner, inner, rim)]  # 8-11 inner rim
    wf = [(-inner, -inner, floor), (inner, -inner, floor), (inner, inner, floor), (-inner, inner, floor)]  # 12-15 well floor
    faces = [
        (0, 1, 2, 3),                                                        # bottom
        (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),              # outer walls
        (4, 5, 9, 8), (5, 6, 10, 9), (6, 7, 11, 10), (7, 4, 8, 11),          # rim-top annulus
        (8, 9, 13, 12), (9, 10, 14, 13), (10, 11, 15, 14), (11, 8, 12, 15),  # well walls
        (12, 13, 14, 15),                                                    # well floor
    ]
    return _mesh(name, ob + ot + ir + wf, faces)


def rel(obj):
    r = run("check_contacts", targets=obj)
    return next((x for x in r.get("contacts", []) if x["object"] == obj), {})


# ── 1. THE FIX: a part seated in a closed plate's well is NOT penetrating ────────────
clean()
make_plate_well("Plate")                                # well floor z=0.008, rim z=0.013
make_box("Disc", half=0.02, z0=0.008, z1=0.028)         # resting on the well floor, proud of rim

c = rel("Disc")
check("seated part is NOT penetrating (was 'penetrating 5mm')", c.get("relation") != "penetrating",
      f"relation={c.get('relation')} summary={c.get('summary')!r}")
check("seated part reads connected (touches the floor)", c.get("relation") == "connected",
      f"relation={c.get('relation')}")
check("auto-flag stays silent for a seated part (no false 'penetrates')",
      auto_proximity_note("Disc") is None, f"note={auto_proximity_note('Disc')!r}")

# ── 2. TRIPWIRE: a genuine matched-footprint interpenetration is STILL caught (G32) ──
clean()
make_box("Lower", half=0.03, z0=0.0, z1=0.04)           # z 0..0.04
make_box("Sunk", half=0.03, z0=0.02, z1=0.08)           # z 0.02..0.08, SAME xy → solids overlap

c = rel("Lower")
check("real interpenetration still reads penetrating", c.get("relation") == "penetrating",
      f"relation={c.get('relation')} summary={c.get('summary')!r}")
depth = next((p["depth_mm"] for p in c.get("penetrating", []) if p["other"] == "Sunk"), 0)
check("penetration depth is a real inside-distance (>0), not the bbox 20mm", 2 <= depth <= 15,
      f"depth_mm={depth}")
check("auto-flag DOES fire on a genuine crossing", auto_proximity_note("Sunk") is not None,
      f"note={auto_proximity_note('Sunk')!r}")

# ── 3. flush-stacked parts read connected, not penetrating ──────────────────────────
clean()
make_box("Base", half=0.03, z0=0.0, z1=0.04)
make_box("Top", half=0.03, z0=0.04, z1=0.08)            # flush on top

c = rel("Top")
check("flush stack reads connected, not penetrating", c.get("relation") == "connected",
      f"relation={c.get('relation')} summary={c.get('summary')!r}")

print()
if failures:
    print(f"FAILED: {len(failures)} — {failures}")
    sys.exit(1)
print("all G107b checks passed")

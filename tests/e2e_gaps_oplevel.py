"""E2E for the op-level gap batch — G102, G113, G120, G121, G122. Headless.

G113: material set on a scattered (shared-mesh) instance uses an OBJECT-linked slot, so the
      colour is per-instance and the other instances keep theirs (variety without un-sharing).
G122: select in_sphere can centre on an OBJECT's bbox or on the current SELECTION — no minted
      handle needed.
G102: feel radial with no radius lands on a named surface CROSSING (outer rim vs inner wall)
      of a ring/holed mesh, instead of find-nearest grabbing the inner wall.
G120: modifier add SUBSURF warns when a flat, unsupported cap will dome (capped cylinder),
      and stays quiet on a cube (quads, no round cap).
G121: add tube (beveled curve) warns when the centreline bends tighter than the tube radius
      (interior self-intersection), and stays quiet on a gentle path.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_gaps_oplevel.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import state, shading, editmode, queries, finishes, curves   # noqa: E402

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
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)
    state.reset_history_state()


def link(name, bm, loc=(0, 0, 0), me=None):
    if me is None:
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


# ── G113: per-instance material on shared mesh ───────────────────────────────
print("\n[G113] per-instance material via OBJECT-linked slot on shared meshes")
clean()
bm = bmesh.new(); bmesh.ops.create_cube(bm, size=0.4); shared = bpy.data.meshes.new("Drop")
bm.to_mesh(shared); bm.free()
insts = []
for i in range(3):
    o = bpy.data.objects.new(f"Spr_{i}", shared)   # all share one mesh
    o.location = (i * 0.5, 0, 0.5)
    bpy.context.scene.collection.objects.link(o); insts.append(o.name)
bpy.context.view_layer.update()

r0 = shading.set_material({"target": "Spr_0", "base_color": [1, 0, 0], "material_name": "red"})
check("set_material on a shared instance reports object_linked",
      r0.get("object_linked") == ["Spr_0"], str(r0.get("object_linked")))
check("Spr_0 slot is OBJECT-linked to red",
      bpy.data.objects["Spr_0"].material_slots[0].link == 'OBJECT'
      and bpy.data.objects["Spr_0"].material_slots[0].material.name == "red")
r1 = shading.set_material({"target": "Spr_1", "base_color": [0, 0, 1], "material_name": "blue"})
check("a SECOND instance gets its own colour", r1.get("success"))
check("Spr_0 stays red, Spr_1 is blue (per-instance variety holds)",
      bpy.data.objects["Spr_0"].material_slots[0].material.name == "red"
      and bpy.data.objects["Spr_1"].material_slots[0].material.name == "blue")
check("the shared mesh datablock was NOT recolored (still one shared mesh)",
      shared.users == 3 and (len(shared.materials) == 0 or shared.materials[0] is None),
      f"users={shared.users} mats={[m and m.name for m in shared.materials]}")

# ── G122: in_sphere center=object / selection ────────────────────────────────
print("[G122] select in_sphere centers on an object or the current selection")
clean()
bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=0.5)
obj = link("Ball", bm)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
r = editmode.select_in_sphere({"center": "Ball", "radius": 1.0, "action": "SELECT"})
check("center=<object> selects (whole ball within r=1 of its center)",
      r.get("success") and r["selected"] > 0, str(r)[:140])
# now select a small cap, then center on that SELECTION
editmode.select_in_sphere({"center": [0, 0, 0.5], "radius": 0.2, "action": "SELECT"})
r = editmode.select_in_sphere({"center": "selection", "radius": 0.25, "action": "SELECT"})
check("center='selection' resolves to the current selection's center",
      r.get("success") and r["selected"] > 0, str(r)[:140])
bad = editmode.select_in_sphere({"center": "nope_no_obj", "radius": 0.2})
check("center=<unknown> errors cleanly", "error" in bad, str(bad))
bpy.ops.object.mode_set(mode='OBJECT')

# ── G102: radial crossing on a ring ──────────────────────────────────────────
print("[G102] feel radial names the crossing (outer rim vs inner wall)")
clean()
R, rr = 0.6, 0.2
bm = bmesh.new()
seg, ring = 24, 12
grid = []
for i in range(seg):
    u = 2 * math.pi * i / seg
    row = []
    for j in range(ring):
        v = 2 * math.pi * j / ring
        x = (R + rr * math.cos(v)) * math.cos(u)
        y = (R + rr * math.cos(v)) * math.sin(u)
        z = rr * math.sin(v)
        row.append(bm.verts.new((x, y, z)))
    grid.append(row)
for i in range(seg):
    for j in range(ring):
        bm.faces.new((grid[i][j], grid[(i + 1) % seg][j],
                      grid[(i + 1) % seg][(j + 1) % ring], grid[i][(j + 1) % ring]))
link("Donut", bm)
outer = queries.radial_landmark({"anchor": "Donut", "angle": 0, "crossing": "outer", "snap": False})
inner = queries.radial_landmark({"anchor": "Donut", "angle": 0, "crossing": "inner", "snap": False})
check("outer crossing ~ R+r (outer rim)", abs(outer["radius"] - (R + rr)) < 0.05,
      f"outer r={outer['radius']} expected~{R + rr}")
check("inner crossing ~ R-r (hole wall)", abs(inner["radius"] - (R - rr)) < 0.05,
      f"inner r={inner['radius']} expected~{R - rr}")
check("outer is farther from center than inner", outer["radius"] > inner["radius"] + 0.1)

# ── G120: subsurf doming warning ─────────────────────────────────────────────
print("[G120] modifier add SUBSURF warns on an unsupported capped cylinder")
clean()
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32,
                      radius1=0.5, radius2=0.5, depth=2.0)
link("Cyl", bm)
r = finishes.add_modifier({"type": "SUBSURF", "target": "Cyl"})
check("SUBSURF on a capped cylinder → doming warning", bool(r.get("doming_warning")), str(r)[:160])

clean()
bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
link("Box", bm)
r = finishes.add_modifier({"type": "SUBSURF", "target": "Box"})
check("SUBSURF on a cube → NO doming warning (quads, not a round cap)",
      not r.get("doming_warning"), str(r.get("doming_warning")))

# ── G121: add tube min-bend self-intersection warning ────────────────────────
print("[G121] add tube warns when the centreline bends tighter than the tube radius")
clean()
# a hairpin: ~1cm turn radius with a 5cm tube → self-intersects
r = curves.add_curve({"name": "Hairpin", "type": "BEZIER", "bevel_depth": 0.05,
                      "points": [[0, 0, 0], [0.12, 0, 0], [0.12, 0.03, 0], [0, 0.03, 0]]})
check("tight tube → self_intersection warning", bool(r.get("self_intersection_warning")), str(r)[:180])

clean()
# a gentle long arc with a thin tube → feasible, no warning
r = curves.add_curve({"name": "Gentle", "type": "BEZIER", "bevel_depth": 0.01,
                      "points": [[0, 0, 0], [1, 0.1, 0], [2, 0, 0]]})
check("gentle tube → NO self-intersection warning", not r.get("self_intersection_warning"),
      str(r.get("self_intersection_warning")))

print()
if failures:
    print(f"e2e_gaps_oplevel :: FAILED — {len(failures)} failure(s): {failures}")
    sys.exit(1)
print("e2e_gaps_oplevel :: PASSED — 0 failure(s)")

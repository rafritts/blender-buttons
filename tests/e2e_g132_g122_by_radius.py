"""E2E for the G132/G122 fix — `select op=by_radius`: a radial BAND selector that
centres on a point / object / the current selection, in CYLINDER or SPHERE form.

This is the keystone that retires G132's in-place wall-thinning (select the inner shell
by a cylindrical radius band, then scale toward the axis — no cutter-cylinder CSG) and
G122's concentric-boundary-loop dance (centre on the selection's own bbox, no minted
handle first).

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g132_g122_by_radius.py
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


def make_double_wall_tube(name, r_inner, r_outer, height, segs=48):
    """Two concentric vertical tube walls (a thick annulus extruded in Z) — the inner
    wall at r_inner, the outer at r_outer, centred on the Z axis at the origin."""
    import math
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bm = bmesh.new()
    for r in (r_inner, r_outer):
        ring_b, ring_t = [], []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            ring_b.append(bm.verts.new((r * math.cos(a), r * math.sin(a), 0.0)))
            ring_t.append(bm.verts.new((r * math.cos(a), r * math.sin(a), height)))
        for i in range(segs):
            j = (i + 1) % segs
            bm.faces.new([ring_b[i], ring_b[j], ring_t[j], ring_t[i]])
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    return ob


# ---- 1. CYLINDER band isolates the inner wall, ignoring the outer wall -------------
clean()
ob = make_double_wall_tube("Tube", r_inner=0.030, r_outer=0.040, height=0.08)
total = len(ob.data.vertices)
res = run("select_by_radius", target="Tube", shape="CYLINDER", axis="Z",
          radius_inner=0.025, radius_outer=0.035)
check("by_radius CYLINDER succeeds", res.get("success"), res.get("error", ""))
inner_count = res.get("selected", 0)
# the inner wall has segs*2 verts (bottom+top ring); outer wall is outside the band
check("inner wall selected, outer excluded", inner_count == 96,
      f"selected {inner_count}, expected 96 (inner wall only)")

# verify geometrically: every selected vert is within the band radius of the Z axis
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
sel = [v for v in bm.verts if v.select]
import math
radii = [math.hypot((ob.matrix_world @ v.co).x, (ob.matrix_world @ v.co).y) for v in sel]
check("all selected verts in radial band", all(0.025 <= r <= 0.035 for r in radii),
      f"radii range {min(radii):.4f}..{max(radii):.4f}")
bpy.ops.object.mode_set(mode='OBJECT')


# ---- 2. SPHERE shape: a band around a point (inner shell of a ball region) ----------
clean()
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.05, segments=24, ring_count=16)
sp = bpy.context.active_object
sp.name = "Ball"
res = run("select_by_radius", target="Ball", shape="SPHERE",
          radius_inner=0.0, radius_outer=0.05, center=[0.0, 0.0, 0.0])
check("by_radius SPHERE solid (inner=0) selects whole surface", res.get("success") and
      res.get("selected") == len(sp.data.vertices),
      f"selected {res.get('selected')} of {len(sp.data.vertices)}")
# a thin outer shell band excludes nothing here (all verts at r=0.05); test exclusion
res = run("select_by_radius", target="Ball", shape="SPHERE",
          radius_inner=0.0, radius_outer=0.03, center=[0.0, 0.0, 0.0])
check("SPHERE band r<=0.03 selects nothing (surface is at r=0.05)",
      res.get("success") and res.get("selected") == 0, f"selected {res.get('selected')}")


# ---- 3. center_selection: centre on the current selection's bbox (G122) -------------
clean()
ob = make_double_wall_tube("Tube2", r_inner=0.030, r_outer=0.040, height=0.08)
# First select the inner wall's bottom boundary loop region by a coarse band, then
# re-centre a fresh band on THAT selection's bbox centre (which is the Z axis) — proving
# no handle needs minting first.
run("select_by_radius", target="Tube2", shape="CYLINDER", axis="Z",
    radius_inner=0.025, radius_outer=0.035)
res = run("select_by_radius", target="Tube2", shape="CYLINDER", axis="Z",
          radius_inner=0.0, radius_outer=0.045, center_selection=True)
check("center_selection resolves (no handle minted)", res.get("success"), res.get("error", ""))
check("center_selection centred on axis ~origin",
      res.get("success") and abs(res["center"][0]) < 1e-3 and abs(res["center"][1]) < 1e-3,
      f"center {res.get('center')}")


# ---- 4. error handling --------------------------------------------------------------
clean()
make_double_wall_tube("T3", 0.03, 0.04, 0.08)
res = run("select_by_radius", target="T3", radius_inner=0.05, radius_outer=0.04)
check("inner>=outer rejected", not res.get("success") and "radius_inner" in res.get("error", ""),
      res.get("error", ""))
res = run("select_by_radius", target="T3", radius_outer=0.0)
check("radius_outer required", not res.get("success"), res.get("error", ""))


print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

"""E2E for SPEC-19 Phase 3 — algebraic compose (edit op=graft / op=stitch).

  GRAFT — two overlapping closed masses merged by SDF smooth-min → marching-tetrahedra mesh:
    the result is a single WATERTIGHT manifold spanning both, the sources are replaced, and the
    smooth-min ADDS material at the concave seam (a fillet) → more volume than a hard union.
  STITCH — two surface patches sharing a boundary welded into one watertight quilt (matched
    sampling + boundary weld): the shared rim collapses to coincident verts, no crack.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_compose.py
"""
import math
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


def two_spheres(dx=0.2, r=0.35):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(-dx, 0, 0))
    bpy.context.active_object.name = "A"
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(dx, 0, 0))
    bpy.context.active_object.name = "B"


def volume(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        return 0.0
    bm = bmesh.new(); bm.from_mesh(obj.data)
    v = bm.calc_volume(signed=True); bm.free()
    return abs(v)


def watertight(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        return False
    bm = bmesh.new(); bm.from_mesh(obj.data)
    open_e = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    bm.free()
    return open_e == 0


# ───────────────── A. GRAFT — smooth-min union is a watertight manifold ─────────────────
print("== SPEC19-Phase3-A: graft smooth-min union → one watertight manifold ==")
clean()
two_spheres(dx=0.2, r=0.35)
r = run("graft", a="A", b="B", mode="smin", blend=0.12, resolution=36)
check("A: graft success", r.get("success"), r.get("error"))
g = bpy.data.objects.get("graft")
check("A: minted the graft object", g is not None)
check("A: result is watertight (manifold union — the clean merge)", r.get("watertight"),
      f"watertight={r.get('watertight')}")
check("A: independently confirmed watertight", g is not None and watertight("graft"))
check("A: sources A and B were replaced", bpy.data.objects.get("A") is None
      and bpy.data.objects.get("B") is None and set(r.get("removed", [])) == {"A", "B"},
      f"removed={r.get('removed')}")
if g is not None:
    xs = [v.co.x for v in g.data.vertices]
    check("A: spans both spheres (x ≈ [-0.55, 0.55])", min(xs) < -0.45 and max(xs) > 0.45,
          f"x=[{min(xs):.3f},{max(xs):.3f}]")


# ───────────────── B. the blend is real — smin fills the seam ─────────────────
print("== SPEC19-Phase3-B: blend=k adds a fillet (more volume than a hard union) ==")
# less overlap → a deeper crease the fillet visibly fills; bigger k → clear volume gain
clean(); two_spheres(dx=0.28, r=0.35)
run("graft", a="A", b="B", mode="smin", blend=0.0, resolution=44, name="Hard")
vol_hard, wt_hard = volume("Hard"), watertight("Hard")
clean(); two_spheres(dx=0.28, r=0.35)
run("graft", a="A", b="B", mode="smin", blend=0.25, resolution=44, name="Soft")
vol_soft, wt_soft = volume("Soft"), watertight("Soft")
check("B: hard union is watertight", wt_hard)
check("B: soft (filleted) union is watertight", wt_soft)
check("B: smooth-min ADDS material at the concave seam (vol_soft > vol_hard, a real fillet)",
      vol_soft > vol_hard * 1.01, f"hard={vol_hard:.5f} soft={vol_soft:.5f}")


# ───────────────── C. keep= retains the sources; mode guard ─────────────────
print("== SPEC19-Phase3-C: keep= retains sources; mode is guarded ==")
clean(); two_spheres()
r = run("graft", a="A", b="B", blend=0.1, resolution=28, name="Kept", keep=True)
check("C: keep=True retains both sources", bpy.data.objects.get("A") is not None
      and bpy.data.objects.get("B") is not None, f"removed={r.get('removed')}")
r2 = run("graft", a="A", b="B", mode="bogus", blend=0.1, name="X")
check("C: an unknown blend mode is refused", not r2.get("success"), f"r={r2}")


def flat_grid(name, x0, x1, y0, y1, sub=8):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=sub, y_subdivisions=sub, size=2.0)
    o = bpy.context.active_object; o.name = name
    o.scale = ((x1 - x0) / 2.0, (y1 - y0) / 2.0, 1.0)
    o.location = ((x0 + x1) / 2.0, (y0 + y1) / 2.0, 0.0)
    bpy.ops.object.transform_apply(scale=True, location=True, rotation=False)
    return o


# ───────────────── D. STITCH — weld two boundary-sharing patches ─────────────────
print("== SPEC19-Phase3-D: stitch welds two boundary-sharing patches into a quilt ==")
clean()
flat_grid("PA", 0, 1, 0, 1, sub=8)
flat_grid("PB", 1, 2, 0, 1, sub=8)          # shares the x=1 edge (coincident verts)
r = run("stitch", a="PA", b="PB")
check("D: stitch success", r.get("success"), r.get("error"))
s = bpy.data.objects.get("stitch")
check("D: minted the stitched object", s is not None)
check("D: welded the shared seam column (>0 verts)", r.get("seam_verts", 0) > 0,
      f"welded={r.get('seam_verts')}")
check("D: seam gap ≈ 0 (coincident boundary, matched sampling)", r.get("seam_gap_mm", 9) < 1e-2,
      f"gap={r.get('seam_gap_mm')}mm")
check("D: seam closed — no crack along the join", r.get("seam_closed"),
      f"seam_closed={r.get('seam_closed')}")
def seam_boundary_edges(name, xseam=1.0):
    obj = bpy.data.objects.get(name)
    if obj is None:
        return -1
    bm = bmesh.new(); bm.from_mesh(obj.data)
    n = sum(1 for e in bm.edges if len(e.link_faces) < 2
            and abs(e.verts[0].co.x - xseam) < 1e-4 and abs(e.verts[1].co.x - xseam) < 1e-4)
    bm.free()
    return n


check("D: the former seam is now INTERIOR (no boundary edge on x≈1)",
      seam_boundary_edges("stitch") == 0, f"boundary seam edges={seam_boundary_edges('stitch')}")
check("D: sources replaced", bpy.data.objects.get("PA") is None
      and bpy.data.objects.get("PB") is None)

# far-apart patches share no boundary → refuse honestly
clean()
flat_grid("FA", 0, 1, 0, 1, 8)
flat_grid("FB", 3, 4, 0, 1, 8)
r2 = run("stitch", a="FA", b="FB")
check("D: far-apart patches refuse (no shared boundary)",
      not r2.get("success") and "share" in r2.get("error", ""), f"r={r2}")


# ───────────────── summary ─────────────────
print()
if failures:
    print(f"FAILED ({len(failures)}): " + ", ".join(failures))
    sys.exit(1)
print("ALL SPEC-19 PHASE-3 COMPOSE CHECKS PASSED")

"""E2E for the G91-G95 (+G87) gap fixes — runs the WORKING-TREE extension headless.

  G87 — move_vertices/scale_vertices flush selection so it survives the edit round-trip
  G91 — feel op=linked: pierce-test linkage (threaded vs touching)
  G93 — array_radial: default end_angle = start+360 → full ring for any start_angle
  G94 — flute: meridional corrugation of a surface of revolution

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_gaps_g91_g95.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import relational as bb_rel  # noqa: E402

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FAIL '} {label}" + ("" if cond else f"   {detail}"))
    if not cond:
        failures.append(label)


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def ring_radii(obj, axis_idx=2, decimals=4):
    """Mean in-plane radius per ring (object measured in OBJECT mode)."""
    me = obj.data
    mat = obj.matrix_world
    buckets = {}
    for v in me.vertices:
        w = mat @ v.co
        buckets.setdefault(round(w[axis_idx], decimals), []).append(w)
    out = {}
    other = [i for i in range(3) if i != axis_idx]
    for pos, ws in sorted(buckets.items()):
        cu = sum(w[other[0]] for w in ws) / len(ws)
        cv = sum(w[other[1]] for w in ws) / len(ws)
        r = sum(math.hypot(w[other[0]] - cu, w[other[1]] - cv) for w in ws) / len(ws)
        out[pos] = r
    return out


# ───────────────────────── G93 — array_radial full ring offset ─────────────────────────
print("== G93: array_radial start_angle=45, default end_angle → full even ring ==")
clean()
run("add_box", name="post", width=0.1, depth=0.1, height=0.5, on={"on_floor": True})
bpy.data.objects["post"].location = (1.0, 0.0, 0.25)
r = run("array_radial", prototype="post", count=4, start_angle=45.0, axis="Z",
        center=[0, 0, 0], keep_original=False)
check("array_radial succeeds", r.get("success"), r.get("error"))
check("full_circle detected for start=45", r.get("full_circle") is True, r)
check("step is 90 deg (even spacing)", abs(r.get("step_deg", 0) - 90.0) < 1e-3, r.get("step_deg"))
check("placed 4 copies", r.get("count") == 4, r.get("count"))

print("== G93: explicit end_angle still makes a partial arc ==")
clean()
run("add_box", name="p2", width=0.1, depth=0.1, height=0.5)
bpy.data.objects["p2"].location = (1.0, 0.0, 0.0)
r = run("array_radial", prototype="p2", count=5, start_angle=0.0, end_angle=180.0,
        axis="Z", center=[0, 0, 0])
check("explicit arc not full_circle", r.get("full_circle") is False, r)
check("arc step is 45 deg (180/4)", abs(r.get("step_deg", 0) - 45.0) < 1e-3, r.get("step_deg"))


# ───────────────────────── G94 — flute ─────────────────────────
print("== G94: flute corrugates a surface of revolution ==")
clean()
run("add_cylinder", name="col", radius=0.2, height=1.0, segments=64)
run("loop_cut", target="col", axis="Z", cuts=6)
before = ring_radii(bpy.data.objects["col"])
mid_pos = sorted(before)[len(before) // 2]
# G96: flute now respects the live selection. loop_cut leaves only the new loops
# selected, so flute the WHOLE surface of revolution by selecting all first.
run("select_all", action="SELECT")
r = run("flute", target="col", axis="Z", count=8, depth=0.03, profile="concave")
check("flute succeeds", r.get("success"), r.get("error"))
check("flute moved verts", r.get("verts_affected", 0) > 0, r)
# 8 lobes ⇒ the radius around a mid ring should now vary at 8 angular periods.
obj = bpy.data.objects["col"]
mat = obj.matrix_world
ring_w = [mat @ v.co for v in obj.data.vertices if abs((mat @ v.co).z - mid_pos) < 1e-3]
cu = sum(w.x for w in ring_w) / len(ring_w)
cv = sum(w.y for w in ring_w) / len(ring_w)
radii_ang = [(math.atan2(w.y - cv, w.x - cu), math.hypot(w.x - cu, w.y - cv)) for w in ring_w]
rmin = min(r for _, r in radii_ang)
rmax = max(r for _, r in radii_ang)
check("flute created radial variation (lobes)", (rmax - rmin) > 0.01, f"min={rmin:.4f} max={rmax:.4f}")
check("concave flute cut inward (rmax ≈ base 0.2)", abs(rmax - 0.2) < 5e-3, f"rmax={rmax:.4f}")


# ───────────────────────── G91 — feel op=linked ─────────────────────────
def make_torus(name, loc, rot_deg):
    run("add_torus", name=name, major_radius=0.5, minor_radius=0.06)
    o = bpy.data.objects[name]
    o.rotation_euler = tuple(math.radians(a) for a in rot_deg)
    o.location = loc
    bpy.context.view_layer.update()
    return o


def linked(a, b):
    return bb_rel.check_linked({"a": a, "b": b})


print("== G91: two interlocking rings read as LINKED ==")
clean()
make_torus("ringA", (0, 0, 0), (0, 0, 0))         # XY plane, centerline circle r=0.5 / Z
make_torus("ringB", (0.5, 0, 0), (90, 0, 0))      # XZ plane, threads through A
r = linked("ringA", "ringB")
check("check_linked succeeds", r.get("success"), r.get("error"))
check("interlocked rings → linked True", r.get("linked") is True, r)
check("linking number >= 1", r.get("linking_number", 0) >= 1, r.get("linking_number"))

print("== G91: two coplanar separate rings read as NOT linked ==")
clean()
make_torus("c1", (0, 0, 0), (0, 0, 0))
make_torus("c2", (1.4, 0, 0), (0, 0, 0))          # far apart, same plane
r = linked("c1", "c2")
check("separate rings → linked False", r.get("linked") is False, r)

print("== G91: perpendicular rings TOUCHING outer faces (not threaded) → NOT linked ==")
clean()
make_torus("t1", (0, 0, 0), (0, 0, 0))            # XY, hole radius 0.5
make_torus("t2", (1.1, 0, 0), (90, 0, 0))         # XZ, tangent outside (inner reach x=0.6 > 0.5)
r = linked("t1", "t2")
check("touching-not-threaded → linked False", r.get("linked") is False, r)


# ───────────────────────── G87 — selection survives move_vertices ─────────────────────────
print("== G87: selection persists across move_vertices (edit round-trip) ==")
clean()
run("add_box", name="bx", width=0.4, depth=0.4, height=0.4)
obj = bpy.data.objects["bx"]
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
run("select_all", action="SELECT")
run("move_vertices", up=0.1)
# Exit + re-enter (what the next one-op-per-message edit triggers) and read selection.
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(obj.data)
sel = sum(1 for v in bm.verts if v.select)
check("all verts still selected after move + round-trip", sel == len(bm.verts),
      f"{sel}/{len(bm.verts)} selected")
bpy.ops.object.mode_set(mode='OBJECT')


print()
if failures:
    print(f"FAILED ({len(failures)}): " + ", ".join(failures))
    sys.exit(1)
print("ALL PASSED")

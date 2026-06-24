"""E2E for the low-hanging gap batch (G155, G159, G163, G165, G167). Headless.

Exercises the extension handlers directly (bypassing the socket), against fresh
factory-startup scenes, so it never touches a live design session.

Covers:
  • G165 — feel op=resting ignores objects the queried part ENCLOSES (coffee in a mug):
           reads the mug as resting on the table, not "sunk" onto its own contents.
  • G159 — transform op=seat lifts a source that spawns straddling/below the cavity clear
           of the mouth before casting, so it lands ON the floor instead of through it.
  • G155 — seat refuses on a target tilted off the seat axis (would latch a wrong floor);
           a pure yaw about the axis is still allowed.
  • G163 — transform op=scatter drops samples on an inner/occluded face (would bury or
           flip the instance) and reports the count, instead of emitting broken geometry.
  • G167 — modifier op=apply runs a degenerate-dissolve pass after a BEVEL and reports the
           sliver count; non-bevel applies are left untouched.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_low_hanging_gaps.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402
from mathutils import Matrix, Vector   # noqa: E402

from extension import state        # noqa: E402
from extension import introspect   # noqa: E402
from extension import transforms   # noqa: E402
from extension import scatter      # noqa: E402
from extension import finishes     # noqa: E402

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


def box(name, dx, dy, dz, loc):
    """Axis-aligned box of full dims (dx,dy,dz) centred at loc."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(dx, dy, dz), verts=bm.verts)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.location = loc
    return o


def cyl(name, r, h, loc):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=r, radius2=r, depth=h)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.location = loc
    return o


def world_z(o):
    bpy.context.view_layer.update()
    zs = [(o.matrix_world @ Vector(c)).z for c in o.bound_box]
    return min(zs), max(zs)


# ── G165 — resting ignores enclosed contents ─────────────────────────────────
print("[G165] resting ignores enclosed contents")
clean()
box("Table", 4, 4, 0.05, (0, 0, -0.025))         # top at z=0
cyl("Mug", 0.04, 0.10, (0, 0, 0.05))             # z[0,0.1], on the table
cyl("Coffee", 0.03, 0.035, (0, 0, 0.0225))       # z[0.005,0.04] — fully inside the mug
bpy.context.view_layer.update()
r = introspect.check_resting({"targets": "Mug"})
res = (r.get("resting") or [{}])[0]
check("mug rests on the Table, not its Coffee", res.get("support") == "Table", str(res)[:160])
check("mug reads resting (not sunk onto contents)", res.get("state") == "resting", str(res)[:160])

# ── G159 — seat lifts an interpenetrating source clear before casting ─────────
print("[G159] seat lifts a straddling source onto the floor")
clean()
box("Plate", 4, 4, 0.05, (0, 0, -0.025))         # top at z=0
cyl("Donut", 0.05, 0.04, (0, 0, 0.0))            # z[-0.02,0.02] — straddles the plate top
bpy.context.view_layer.update()
r = transforms.seat_into({"targets": "Donut", "target": "Plate"})
check("seat succeeded", r.get("success"), str(r)[:160])
zmin, _ = world_z(bpy.data.objects["Donut"])
check("donut bottom rests ON the plate top (~0), not driven below", abs(zmin) < 0.002,
      f"zmin={zmin:.4f}")

# ── G155 — seat refuses a tilted target; yaw is fine ─────────────────────────
print("[G155] seat refuses an off-axis-tilted target")
clean()
c = box("Cavity", 0.4, 0.4, 0.2, (0, 0, 0.0))    # top at z=0.1
c.rotation_euler = (0.5236, 0, 0)                # 30° about X — tilted off Z
box("Part", 0.04, 0.04, 0.04, (0, 0, 0.5))
bpy.context.view_layer.update()
r = transforms.seat_into({"targets": "Part", "target": "Cavity"})
check("tilted target refused", not r.get("success") and "tilted" in r.get("error", ""),
      str(r)[:160])
check("refusal cites G155 + points at rest_on",
      "G155" in r.get("error", "") and "rest_on" in r.get("error", ""), str(r)[:160])

print("[G155] pure yaw about the axis is still allowed")
clean()
c = box("Cavity", 0.4, 0.4, 0.2, (0, 0, 0.0))
c.rotation_euler = (0, 0, 0.5236)                # 30° about Z — a spin, floor still faces up
box("Part", 0.04, 0.04, 0.04, (0, 0, 0.5))
bpy.context.view_layer.update()
r = transforms.seat_into({"targets": "Part", "target": "Cavity"})
check("yawed target seats (no false tilt refusal)", r.get("success"), str(r)[:160])

# ── G163 — scatter drops inner/occluded-face samples ─────────────────────────
print("[G163] scatter drops samples on inner/occluded faces")
clean()
# Target = lower plate + a floating canopy over its left half: samples on the covered
# region cast outward (+Z) and re-hit the canopy → occluded → must be dropped.
me = bpy.data.meshes.new("Overhang")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal((2, 2, 0.1, 1)))               # lower
bmesh.ops.create_cube(bm, size=1.0,
                      matrix=Matrix.Translation((-0.5, 0, 0.5)) @ Matrix.Diagonal((1, 2, 0.1, 1)))  # canopy
bm.to_mesh(me); bm.free()
over = bpy.data.objects.new("Overhang", me)
bpy.context.collection.objects.link(over)
box("Sprinkle", 0.02, 0.02, 0.02, (0, 0, 5))
bpy.context.view_layer.update()
r = scatter.scatter_on_surface({"target": "Overhang", "source": "Sprinkle", "count": 300,
                                "seed": 0, "up_only": True, "max_slope": 20.0,
                                "align_normal": True, "seat": True})
check("scatter succeeded", r.get("success"), str(r)[:160])
check("dropped occluded-face samples", (r.get("dropped_defective") or 0) > 0,
      f"dropped_defective={r.get('dropped_defective')}")

print("[G163] no false drops on a clean convex surface")
clean()
box("Flat", 2, 2, 0.1, (0, 0, 1))
box("Sprinkle", 0.02, 0.02, 0.02, (0, 0, 5))
bpy.context.view_layer.update()
r = scatter.scatter_on_surface({"target": "Flat", "source": "Sprinkle", "count": 200,
                                "seed": 0, "up_only": True, "max_slope": 20.0,
                                "align_normal": True, "seat": True})
check("clean surface drops nothing", not r.get("dropped_defective"),
      f"dropped_defective={r.get('dropped_defective')}")


def mesh_with_degenerate(name):
    """A good quad + a disconnected zero-area triangle (two coincident verts)."""
    me = bpy.data.meshes.new(name)
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),   # quad
             (3, 0, 0), (3, 0, 0), (3, 1, 0)]              # 4==5 → degenerate tri (4,5,6)
    me.from_pydata(verts, [], [(0, 1, 2, 3), (4, 5, 6)])
    me.update()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    return o


def n_degenerate(o):
    return sum(1 for p in o.data.polygons if p.area < 1e-9)


# ── G167 — bevel apply dissolves degenerate slivers ──────────────────────────
print("[G167] _dissolve_degenerate_faces clears zero-area faces")
clean()
o = mesh_with_degenerate("Degen")
check("starts with a zero-area face", n_degenerate(o) == 1)
removed = finishes._dissolve_degenerate_faces(o)
check("dissolve reports the sliver removed", removed >= 1, f"removed={removed}")
check("no zero-area faces remain", n_degenerate(o) == 0)

print("[G167] modifier apply cleans slivers when a BEVEL was applied")
clean()
o = mesh_with_degenerate("DegenBevel")
o.modifiers.new("Bevel", "BEVEL").width = 1e-4
bpy.context.view_layer.objects.active = o
r = finishes.apply_modifiers({"name": "DegenBevel"})
check("apply succeeded", r.get("success"), str(r)[:160])
check("reports degenerate_dissolved", (r.get("degenerate_dissolved") or 0) >= 1,
      str(r)[:160])
check("mesh left with no zero-area faces", n_degenerate(o) == 0)

print("[G167] non-bevel apply leaves the cleanup untouched (bevel-scoped)")
clean()
o = mesh_with_degenerate("DegenEdgeSplit")
o.modifiers.new("ES", "EDGE_SPLIT")
bpy.context.view_layer.objects.active = o
r = finishes.apply_modifiers({"name": "DegenEdgeSplit"})
check("apply succeeded", r.get("success"), str(r)[:160])
check("no degenerate_dissolved key (not a bevel)", "degenerate_dissolved" not in r, str(r)[:160])
check("pre-existing degenerate face untouched", n_degenerate(o) >= 1)

# ── summary ──────────────────────────────────────────────────────────────────
print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASS")

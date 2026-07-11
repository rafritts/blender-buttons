"""E2E — scatter seating/spacing (G136, G137) + group no-op detection (G140). Headless.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_g136_g137_g140.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402
import mathutils  # noqa: E402

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
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    state.reset_history_state()


def make_box(name, cz, hx, hy, hz):
    """Axis-aligned box centred at (0,0,cz), half-extents hx,hy,hz. Origin at centre."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    for v in bm.verts:
        v.co.x *= hx; v.co.y *= hy; v.co.z *= hz
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = (0, 0, cz)
    bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    return o


def insts(prefix):
    return [o for o in bpy.data.objects if o.name.startswith(prefix)]


# ─────────────────────────────────────────────────────────────────────────────
# G136 — seat lifts a flat instance PROUD; offset is an explicit normal nudge.
# ─────────────────────────────────────────────────────────────────────────────
print("\nG136 — scatter seat/offset along the surface normal\n")

# Slab top face at z=0.1. Sprinkle is a flat box, half-thickness 0.02 (origin centred).
TOP = 0.1
HZ = 0.02
clean()
make_box("Slab", 0.05, 0.3, 0.3, 0.05)        # spans z[0,0.1], top at 0.1
make_box("Chip", 5.0, 0.03, 0.03, HZ)         # flat source, parked away

# Default (no seat): origin lands ON the surface, so half the chip sinks below it.
r = run("scatter_on_surface", target="Slab", source="Chip", count=20, up_only=True,
        align_normal=True, scale_min=1.0, scale_max=1.0, rotate_z=False, seed=3,
        name_prefix="bury_")
check("baseline scatter succeeds", r.get("success") is True, str(r.get("error")))
bz = [o.location.z for o in insts("bury_")]
check("WITHOUT seat the origin sits on the surface (z≈top, chip half-buried)",
      bz and abs(sum(bz) / len(bz) - TOP) < 1e-4, f"mean_z={sum(bz)/len(bz) if bz else None}")

# seat=True: lift each chip so its LOWEST point rests on the surface → origin at top+HZ.
clean()
make_box("Slab", 0.05, 0.3, 0.3, 0.05)
make_box("Chip", 5.0, 0.03, 0.03, HZ)
r = run("scatter_on_surface", target="Slab", source="Chip", count=20, up_only=True,
        align_normal=True, scale_min=1.0, scale_max=1.0, rotate_z=False, seat=True,
        seed=3, name_prefix="seat_")
check("seat scatter succeeds", r.get("success") is True, str(r.get("error")))
check("result echoes seat=True", r.get("seat") is True, str(r.get("seat")))
sz = [o.location.z for o in insts("seat_")]
check("WITH seat the origin is lifted by half-thickness (z≈top+HZ)",
      sz and abs(sum(sz) / len(sz) - (TOP + HZ)) < 1e-4,
      f"mean_z={sum(sz)/len(sz) if sz else None}, want={TOP+HZ}")
# The lowest world vertex of a seated chip should rest at the surface, not below it.
lowest = min((o.matrix_world @ v.co).z for o in insts("seat_") for v in o.data.vertices)
check("seated chips do NOT poke below the surface (lowest vertex ≈ top)",
      abs(lowest - TOP) < 1e-3, f"lowest_world_z={lowest}, top={TOP}")

# offset adds an explicit proud nudge on top of the origin-on-surface placement.
clean()
make_box("Slab", 0.05, 0.3, 0.3, 0.05)
make_box("Chip", 5.0, 0.03, 0.03, HZ)
r = run("scatter_on_surface", target="Slab", source="Chip", count=12, up_only=True,
        align_normal=True, scale_min=1.0, scale_max=1.0, offset=0.05, seed=3,
        name_prefix="off_")
oz = [o.location.z for o in insts("off_")]
check("offset lifts the origin proud by exactly offset (z≈top+0.05)",
      oz and abs(sum(oz) / len(oz) - (TOP + 0.05)) < 1e-4,
      f"mean_z={sum(oz)/len(oz) if oz else None}")


# ─────────────────────────────────────────────────────────────────────────────
# G137 — min_distance enforces spacing; jitter_tilt breaks coplanarity.
# ─────────────────────────────────────────────────────────────────────────────
print("\nG137 — scatter min_distance (Poisson) + jitter_tilt (anti z-fight)\n")

clean()
make_box("Slab", 0.05, 0.3, 0.3, 0.05)
make_box("Chip", 5.0, 0.02, 0.02, 0.005)
MD = 0.06
r = run("scatter_on_surface", target="Slab", source="Chip", count=200, up_only=True,
        align_normal=True, min_distance=MD, seed=7, name_prefix="md_")
check("min_distance scatter succeeds", r.get("success") is True, str(r.get("error")))
check("result echoes min_distance", abs((r.get("min_distance") or 0) - MD) < 1e-9, str(r.get("min_distance")))
pts = [o.location for o in insts("md_")]
pair_min = min((a - b).length for i, a in enumerate(pts) for b in pts[i + 1:]) if len(pts) > 1 else 9e9
check("NO two instances are closer than min_distance",
      pair_min >= MD - 1e-4, f"closest pair={pair_min}, min_distance={MD}")
check("over-dense request was thinned (fewer than the 200 asked, some skipped)",
      len(pts) < 200 and r.get("skipped", 0) > 0, f"placed={len(pts)}, skipped={r.get('skipped')}")

# jitter_tilt: on a flat +Z top, aligned instances would all have local +Z = world +Z.
# With tilt, their up-axes deviate — bounded by jitter_tilt — so they cross, not z-fight.
clean()
make_box("Slab", 0.05, 0.3, 0.3, 0.05)
make_box("Chip", 5.0, 0.02, 0.02, 0.005)
TILT = 25.0
r = run("scatter_on_surface", target="Slab", source="Chip", count=40, up_only=True,
        align_normal=True, jitter_tilt=TILT, rotate_z=False, seed=11, name_prefix="tl_")
check("jitter_tilt scatter succeeds", r.get("success") is True, str(r.get("error")))
up = mathutils.Vector((0, 0, 1))
tilts = [math.degrees((o.matrix_world.to_3x3() @ up).angle(up))
         for o in insts("tl_")]
check("at least one instance is tilted off the normal (not coplanar)",
      tilts and max(tilts) > 1.0, f"max_tilt_deg={max(tilts) if tilts else None}")
check("every tilt is bounded by jitter_tilt",
      tilts and max(tilts) <= TILT + 0.5, f"max_tilt_deg={max(tilts) if tilts else None}, cap={TILT}")
# A control with no tilt: instances stay flat on the +Z face.
clean()
make_box("Slab", 0.05, 0.3, 0.3, 0.05)
make_box("Chip", 5.0, 0.02, 0.02, 0.005)
r = run("scatter_on_surface", target="Slab", source="Chip", count=20, up_only=True,
        align_normal=True, jitter_tilt=0.0, rotate_z=False, seed=11, name_prefix="ft_")
ftilts = [math.degrees((o.matrix_world.to_3x3() @ up).angle(up)) for o in insts("ft_")]
check("without jitter_tilt instances stay flat (≈0° off normal)",
      ftilts and max(ftilts) < 1e-3, f"max_tilt_deg={max(ftilts) if ftilts else None}")


# ─────────────────────────────────────────────────────────────────────────────
# G140 — a real group move must NOT raise the byte-identical no-op warning, and a
# genuine no-op on the same group still MUST.
# ─────────────────────────────────────────────────────────────────────────────
print("\nG140 — group transform no-op detection acts on the moved members\n")

clean()
a = make_box("A", 0.0, 0.1, 0.1, 0.1)
b = make_box("B", 0.0, 0.1, 0.1, 0.1)
b.location = (0.5, 0, 0)
bpy.context.view_layer.update()
# Park an unrelated object as the viewport-active one — the old bug checked THIS.
c = make_box("Bystander", 0.0, 0.05, 0.05, 0.05)
c.location = (5, 5, 5)
bpy.context.view_layer.objects.active = c

g = run("group", name="Grp", parts=["A", "B"])
check("group created", g.get("success") is True, str(g.get("error")))

before = (a.location.copy(), b.location.copy(), c.location.copy())
r = run("nudge", targets="Grp", right=0.3, up=0.2)
check("group nudge succeeds", r.get("success") is True, str(r.get("error")))
check("members A and B actually moved",
      (a.location - before[0]).length > 1e-6 and (b.location - before[1]).length > 1e-6,
      f"dA={(a.location-before[0]).length}, dB={(b.location-before[1]).length}")
check("the unrelated viewport-active object did NOT move",
      (c.location - before[2]).length < 1e-9, f"dC={(c.location-before[2]).length}")
check("NO false no-op warning on a real group move (G140)",
      not r.get("no_op") and not r.get("no_op_warning"),
      f"no_op={r.get('no_op')}, warn={r.get('no_op_warning')}")

# A genuine no-op on the group (zero nudge) MUST still be caught — proves the detector
# is acting on the members, not silently disabled.
r0 = run("nudge", targets="Grp", right=0.0, up=0.0)
if r0.get("success"):
    check("a true zero-move group nudge IS still flagged as a no-op",
          bool(r0.get("no_op")), f"no_op={r0.get('no_op')}")
else:
    check("a zero-move group nudge is rejected up front (also acceptable)",
          True, str(r0.get("error")))


print(f"\n{'PASSED' if not failures else 'FAILED'} — {len(failures)} failure(s)")
for f in failures:
    print(f"   ✗ {f}")
sys.exit(1 if failures else 0)

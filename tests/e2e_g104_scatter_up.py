"""E2E for G104 — `transform op=scatter up_only=` gates scatter to up-facing faces.
Headless.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_g104_scatter_up.py
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
    state.reset_history_state()


def make_box(name, cz, hx, hy, hz):
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


def instance_zs(prefix):
    return [o.location.z for o in bpy.data.objects if o.name.startswith(prefix)]


print("\nG104 — scatter up_only gates to up-facing faces\n")

# Slab spans z[0, 0.1], top at 0.1, bottom at 0.0, center 0.05. Wide top/bottom faces.
clean()
make_box("Slab", 0.05, 0.3, 0.3, 0.05)
make_box("Bit", 5.0, 0.01, 0.01, 0.01)   # tiny source, parked away

# ── up_only: every instance lands on the TOP face ────────────────────────────
r = run("scatter_on_surface", target="Slab", source="Bit", count=60,
        up_only=True, align_normal=True, seed=1, name_prefix="up_")
check("up_only scatter succeeds", r.get("success") is True, str(r.get("error")))
zs = instance_zs("up_")
check("up_only produced instances", len(zs) > 0, f"n={len(zs)}")
check("EVERY up_only instance is on the top face (z≈0.1, above center)",
      zs and min(zs) > 0.08, f"min_z={min(zs) if zs else None}")

# ── default (no gate): instances also land on the underside ──────────────────
clean()
make_box("Slab", 0.05, 0.3, 0.3, 0.05)
make_box("Bit", 5.0, 0.01, 0.01, 0.01)
r = run("scatter_on_surface", target="Slab", source="Bit", count=120,
        up_only=False, align_normal=True, seed=1, name_prefix="all_")
zs = instance_zs("all_")
check("ungated scatter DOES hit the underside (some instances below center)",
      zs and min(zs) < 0.02, f"min_z={min(zs) if zs else None}")

# ── on a tall wall, up_only still finds and uses only the TOP cap ────────────
clean()
make_box("Wall", 0.5, 0.3, 0.01, 0.5)   # spans z[0,1], top cap at z=1.0
make_box("Bit", 5.0, 0.01, 0.01, 0.01)
r = run("scatter_on_surface", target="Wall", source="Bit", count=20,
        up_only=True, max_slope=10.0, name_prefix="w_")
check("up_only scatter on a tall wall succeeds", r.get("success") is True, str(r.get("error")))
zs = instance_zs("w_")
check("every instance landed on the top cap (z≈1.0), none on the side walls",
      zs and min(zs) > 0.9, f"min_z={min(zs) if zs else None}")

# ── a gate direction no face matches errors cleanly ──────────────────────────
clean()
make_box("Pan", 0.05, 0.3, 0.3, 0.05)    # axis-aligned cube — faces on ±X/±Y/±Z only
make_box("Bit", 5.0, 0.01, 0.01, 0.01)
# a corner-diagonal direction is ~54.7° from any cube face; max_slope=1° matches none.
r = run("scatter_on_surface", target="Pan", source="Bit", count=10,
        normal_dir=[1, 1, 1], max_slope=1.0, name_prefix="x_")
check("a gate direction with no matching face errors cleanly",
      r.get("success") is not True and "scatter onto" in r.get("error", ""), str(r))


print(f"\n{'PASSED' if not failures else 'FAILED'} — {len(failures)} failure(s)")
for f in failures:
    print(f"   ✗ {f}")
sys.exit(1 if failures else 0)

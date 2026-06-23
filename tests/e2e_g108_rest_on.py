"""E2E for G108 — `transform op=rest_on` must LIFT a plane-straddling part to rest,
not push it deeper. Headless. Builds geometry directly (no placement DSL) so it's
robust to the relational-only surface.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_g108_rest_on.py
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


def make_box(name, cx, cy, cz, hx, hy, hz):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    for v in bm.verts:
        v.co.x *= hx
        v.co.y *= hy
        v.co.z *= hz
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = (cx, cy, cz)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def zbounds(name):
    o = bpy.data.objects[name]
    zs = [(o.matrix_world @ v.co).z for v in o.data.vertices]
    return min(zs), max(zs)


print("\nG108 — rest_on resolves to genuine resting regardless of starting side\n")

# ── a part STRADDLING the target plane is LIFTED, not sunk ────────────────────
clean()
make_box("table", 0, 0, -0.05, 0.1, 0.1, 0.05)   # top at z=0
make_box("plate", 0, 0, 0.0, 0.05, 0.05, 0.0065)  # straddles z=0: [-0.0065, 0.0065]
z0min, _ = zbounds("plate")
check("setup: plate starts straddling the table top (zmin < 0)", z0min < -1e-4, f"zmin={z0min:.4f}")
r = run("rest_on", targets="plate", target="table", axis="Z")
check("rest_on a straddling part succeeds", r.get("success") is True, str(r))
moved = r.get("rested", [{}])[0].get("dropped_mm")
check("the part was LIFTED (negative dropped_mm), not dropped deeper", moved is not None and moved < 0,
      f"dropped_mm={moved}")
z1min, z1max = zbounds("plate")
check("plate bottom now rests ON the table top (zmin≈0)", abs(z1min) < 1e-4, f"zmin={z1min:.4f}")
check("plate is no longer below the floor", z1min >= -1e-4, f"zmin={z1min:.4f}")

# ── a part fully ABOVE the target still drops to rest (no regression) ─────────
clean()
make_box("table", 0, 0, -0.05, 0.1, 0.1, 0.05)   # top at z=0
make_box("cube", 0, 0, 0.2, 0.02, 0.02, 0.02)    # floating well above
r = run("rest_on", targets="cube", target="table", axis="Z")
check("rest_on above target still drops", r.get("success") is True, str(r))
moved = r.get("rested", [{}])[0].get("dropped_mm")
check("a floating part is DROPPED (positive dropped_mm)", moved is not None and moved > 0, f"dropped_mm={moved}")
zmin, _ = zbounds("cube")
check("dropped part rests on the table top (zmin≈0)", abs(zmin) < 1e-4, f"zmin={zmin:.4f}")

# ── a part fully BELOW the target is lifted up to rest on it ──────────────────
clean()
make_box("table", 0, 0, 0.5, 0.1, 0.1, 0.05)     # top at z=0.55, bottom z=0.45
make_box("chip", 0, 0, 0.1, 0.02, 0.02, 0.02)    # entirely below the table
r = run("rest_on", targets="chip", target="table", axis="Z")
check("rest_on a fully-below part succeeds", r.get("success") is True, str(r))
zmin, zmax = zbounds("chip")
check("the below part is lifted to rest on the table top (zmin≈0.55)", abs(zmin - 0.55) < 1e-4,
      f"zmin={zmin:.4f}")


print(f"\n{'PASSED' if not failures else 'FAILED'} — {len(failures)} failure(s)")
for f in failures:
    print(f"   ✗ {f}")
sys.exit(1 if failures else 0)

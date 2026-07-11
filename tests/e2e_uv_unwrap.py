"""E2E for SPEC-18 Phase 1 — uv op=unwrap + material space=uv. Headless.

Exercises the extension handlers directly (bypassing the socket), against a fresh
factory-startup scene, so it never touches a live design session.

Covers:
  • uv_unwrap creates a UV layer for each no-seam method (smart/cube/cylinder/sphere)
  • multi-target unwrap (each mesh gets its own UVs)
  • mode hygiene (G157): the scene is left in OBJECT mode
  • registration / categorization (mutating, not a read, not lock-exempt)

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_uv_unwrap.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402
from extension import uv as bb_uv           # noqa: E402

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


def make_cylinder(name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=1.0, radius2=1.0, depth=2.0)
    bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def make_cube(name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


# ── 0. registration + categorization ─────────────────────────────────────────
print("[0] registration & categorization")
check("uv_unwrap registered in TOOLS", "uv_unwrap" in bb_server.TOOLS)
check("uv_unwrap is a MUTATOR (not non-undoable)", "uv_unwrap" not in state.NON_UNDOABLE_TOOLS)
check("uv_unwrap is NOT lock-exempt", "uv_unwrap" not in bb_server.LOCK_EXEMPT_TOOLS)
check("uv_unwrap NOT in NOOP_CHECK (UV isn't geometry)", "uv_unwrap" not in bb_server.NOOP_CHECK_TOOLS)

# ── 1. unwrap each no-seam method ────────────────────────────────────────────
print("[1] unwrap methods")
for method in ("smart", "cube", "cylinder", "sphere"):
    clean()
    obj = make_cylinder(f"Cyl_{method}")
    r = bb_uv.uv_unwrap({"target": obj.name, "method": method})
    ok = r.get("success") and r.get("count") == 1
    check(f"{method}: unwrap ok", ok, str(r)[:160])
    if ok:
        check(f"{method}: mesh has a UV layer", len(obj.data.uv_layers) >= 1)
        # a non-degenerate unwrap writes non-zero UV spread (not all coords identical)
        uvs = [tuple(round(c, 4) for c in d.uv) for d in obj.data.uv_layers.active.data]
        check(f"{method}: UVs are non-degenerate", len(set(uvs)) > 1, f"distinct={len(set(uvs))}")
        check(f"{method}: left in OBJECT mode (G157)", bpy.context.mode == 'OBJECT')

# ── 2. multi-target unwrap (each mesh its own UVs) ───────────────────────────
print("[2] multi-target unwrap")
clean()
a, b = make_cylinder("MugA"), make_cube("PlateB")
r = bb_uv.uv_unwrap({"target": ["MugA", "PlateB"], "method": "smart"})
check("multi: both unwrapped", r.get("success") and r.get("count") == 2, str(r)[:160])
check("multi: MugA has UVs", len(a.data.uv_layers) >= 1)
check("multi: PlateB has UVs", len(b.data.uv_layers) >= 1)

# ── 3. unknown method refused ────────────────────────────────────────────────
print("[3] bad method")
clean()
make_cube("X")
r = bb_uv.uv_unwrap({"target": "X", "method": "angle"})
check("angle (Phase 2) refused with guidance", not r.get("success") and "Phase 2" in r.get("error", ""),
      str(r)[:160])

# ── summary ──────────────────────────────────────────────────────────────────
print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASS")

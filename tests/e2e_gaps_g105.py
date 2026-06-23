"""E2E for G105 — auto-flag a NEW open boundary after a topology edit. Headless.

A carve that opens a shell (a removed cap, a consumed face, an unexpected rim) used to
sail through silently — only an explicit feel op=topology caught it. Now a topology edit
that raises the focus object's open-boundary-loop count gets the same unasked one-line
flag penetration gets.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_gaps_g105.py
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


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    state.reset_history_state()


def make_cube(name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.context.view_layer.update()
    return obj


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


print("\nG105 — a new open boundary is auto-flagged\n")

# ── unit: the boundary counter ───────────────────────────────────────────────
clean()
cube = make_cube("Probe")
check("_open_boundary_loops: closed cube → 0", bb_server._open_boundary_loops(cube) == 0)
# remove a face by hand → one open boundary loop
bm = bmesh.new(); bm.from_mesh(cube.data); bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[0]], context='FACES_ONLY'); bm.to_mesh(cube.data); bm.free()
check("_open_boundary_loops: cube minus a face → 1", bb_server._open_boundary_loops(cube) == 1)

# ── integration: carving the top face opens the shell → warning ──────────────
clean()
make_cube("Cube")
run("set_component_mode", mode="FACE", target="Cube")
run("select_by_axis", axis="Z", factor=0.9, comparison="GREATER", target="Cube")
r = run("delete_geometry", mode="FACE", target="Cube")
check("delete succeeded", r.get("success"), str(r)[:160])
check("opening the shell raises a boundary_warning", bool(r.get("boundary_warning")), str(r)[:200])
check("boundary_opened delta 0 → 1 recorded",
      r.get("boundary_opened") == {"before": 0, "after": 1}, str(r.get("boundary_opened")))

# ── negative: an edit that keeps the shell closed → no warning ───────────────
clean()
make_cube("Closed")
run("select_all", action="SELECT", target="Closed")
r = run("subdivide_selection", cuts=1, target="Closed")
check("subdivide succeeded", r.get("success"), str(r)[:160])
check("a still-closed edit raises NO boundary_warning", not r.get("boundary_warning"),
      str(r.get("boundary_warning")))

print()
if failures:
    print(f"e2e_gaps_g105 :: FAILED — {len(failures)} failure(s): {failures}")
    sys.exit(1)
print("e2e_gaps_g105 :: PASSED — 0 failure(s)")

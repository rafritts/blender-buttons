"""E2E for the 2026-06-17 gap fixes (G24, G27, G29, G25, G26, G28) — headless Blender.

Usage: flatpak run --filesystem=home org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_gaps_b.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import state  # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok    {label}")
    else:
        failures.append(label)
        print(f"  FAIL  {label}  {detail}")


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    state.reset_history_state()


# ───────────── G27: set_material accepts a comma list of targets ─────────────
print("== G27: set_material target list ==")
clean()
run("add_box", name="a", width=1.0, depth=1.0, height=1.0)
run("add_box", name="b", width=1.0, depth=1.0, height=1.0)
run("move_to", targets="b", x=3.0)
r = run("set_material", target=["a", "b"], hex="#cf4233", material_name="shared_red")
check("set_material on a list succeeds", r.get("success") is True, str(r))
check("assigned to both objects", set(r.get("assigned_to", [])) == {"a", "b"}, str(r.get("assigned_to")))
check("both meshes carry the material",
      bpy.data.objects["a"].data.materials[0] is bpy.data.objects["b"].data.materials[0],
      "materials differ")
# default name path with a list must not stringify the list
r2 = run("set_material", target=["a", "b"], hex="#222222")
check("list target + default name succeeds", r2.get("success") is True, str(r2))
check("default name derived from a string, not the list repr",
      "[" not in r2.get("material", ""), str(r2.get("material")))

# ───────────── G24: available engines include the active engine ──────────────
print("== G24: render preflight truthfulness ==")
clean()
rs = run("render_settings")
check("render_settings succeeds", rs.get("success") is True, str(rs))
check("current engine is in available_engines (no false omission)",
      rs.get("engine") in rs.get("available_engines", []), str(rs))
# Setting an obviously-bogus engine is rejected with the real list, not a crash.
run("add_box", name="subj", width=1.0, depth=1.0, height=1.0)
run("add_camera", name="cam", x=0.0, y=-5.0, z=1.0, target_x=0.0, target_y=0.0, target_z=0.5)
rbad = run("render_to_file", filepath="/tmp/should_not_render.png", engine="NOT_A_REAL_ENGINE")
check("bogus engine rejected (authoritative set/try)", rbad.get("success") is not True
      and "not available" in rbad.get("error", ""), str(rbad))
# Cycles preflight only appears when engine is CYCLES; under factory-startup it's EEVEE,
# so just assert the read doesn't choke and reports eevee.
check("eevee block present under factory-startup", "eevee" in rs or "cycles" in rs, str(rs.keys()))

# ───────────── G29: distance ANY = nearest-surface, labeled ──────────────────
print("== G29: feel distance ANY nearest-surface ==")
clean()
run("add_box", name="a", width=1.0, depth=1.0, height=1.0)          # x: -0.5..0.5
run("add_box", name="b", width=1.0, depth=1.0, height=1.0)
run("move_to", targets="b", x=3.0)                                # x: 2.5..3.5
d_any = run("distance_between", a="a", b="b", axis="ANY")
check("ANY succeeds", d_any.get("success") is True, str(d_any))
check("ANY reports nearest-surface (~2.0), not centroid (3.0)",
      abs(d_any.get("distance", 0) - 2.0) < 0.05, str(d_any.get("distance")))
check("ANY labels what it measured", "surface" in d_any.get("measured", ""), str(d_any))
check("ANY reports the point pair", isinstance(d_any.get("between"), list)
      and len(d_any["between"]) == 2, str(d_any.get("between")))
d_x = run("distance_between", a="a", b="b", axis="X")
check("axis=X still centre-to-centre (3.0)", abs(d_x.get("distance", 0) - 3.0) < 1e-4, str(d_x))
check("axis=X labeled centre-to-centre", "centre" in d_x.get("measured", ""), str(d_x))

# ───────────── G25: aim_axis orients a local axis down a segment ─────────────
print("== G25: transform aim_axis ==")
clean()
run("add_cylinder", name="cyl", radius=0.2, height=2.0)             # local Z is the long axis
r = run("aim_axis", targets="cyl", axis="Z", **{"from": [0, 0, 0], "to": [1, 0, 0]})
check("aim_axis succeeds", r.get("success") is True, str(r))
# local +Z should now point along world +X
from mathutils import Vector  # noqa: E402
zw = bpy.data.objects["cyl"].matrix_world.to_3x3() @ Vector((0, 0, 1))
check("local Z now points along world X", (zw - Vector((1, 0, 0))).length < 1e-4,
      str([round(c, 3) for c in zw]))
# signed axis: -Z down the same segment flips orientation
r2 = run("aim_axis", targets="cyl", axis="-Z", **{"from": [0, 0, 0], "to": [1, 0, 0]})
zw2 = bpy.data.objects["cyl"].matrix_world.to_3x3() @ Vector((0, 0, 1))
check("axis=-Z points local +Z along world -X", (zw2 - Vector((-1, 0, 0))).length < 1e-4,
      str([round(c, 3) for c in zw2]))

# ───────────── G26: rest_on drops onto real geometry ─────────────────────────
print("== G26: transform rest_on ==")
clean()
run("add_box", name="floor", width=4.0, depth=4.0, height=0.2)      # top at z=0.1
run("add_box", name="crate", width=0.5, depth=0.5, height=0.5)
run("move_to", targets="crate", z=2.0)                              # bottom at 1.75, floating
r = run("rest_on", targets="crate", target="floor", axis="Z")
check("rest_on succeeds", r.get("success") is True, str(r))
zmin = min((bpy.data.objects["crate"].matrix_world @ v.co).z
           for v in bpy.data.objects["crate"].data.vertices)
check("crate bottom seats on floor top (~0.1)", abs(zmin - 0.1) < 1e-3, f"zmin={round(zmin,4)}")
# offset leaves a clearance gap
run("move_to", targets="crate", z=2.0)
run("rest_on", targets="crate", target="floor", axis="Z", offset=0.05)
zmin2 = min((bpy.data.objects["crate"].matrix_world @ v.co).z
            for v in bpy.data.objects["crate"].data.vertices)
check("offset=0.05 leaves a 5cm gap (~0.15)", abs(zmin2 - 0.15) < 1e-3, f"zmin={round(zmin2,4)}")
# resting an object that isn't above the target errors, not silently no-ops
run("move_to", targets="crate", x=20.0, z=2.0)
r3 = run("rest_on", targets="crate", target="floor", axis="Z")
check("rest_on off-target errors", r3.get("success") is not True, str(r3))

# ───────────── G28: jitter honors target auto-enter + whole-mesh default ─────
print("== G28: edit-mode contract (jitter) ==")
clean()
run("add_box", name="donut", width=1.0, depth=1.0, height=1.0)
run("subdivide_selection", target="donut", cuts=3)                 # give it verts to lump
# From OBJECT mode, jitter with target= must NOT error 'Must be in edit mode'.
before = [tuple(v.co) for v in bpy.data.objects["donut"].data.vertices]
r = run("jitter_vertices", target="donut", amount=0.02, seed=1)
check("jitter with target= succeeds from OBJECT mode", r.get("success") is True, str(r))
check("returned to OBJECT mode after jitter", bpy.context.active_object.mode == "OBJECT",
      bpy.context.active_object.mode)
after = [tuple(v.co) for v in bpy.data.objects["donut"].data.vertices]
check("jitter actually moved verts", before != after, "verts unchanged")
# Whole-mesh default: in edit mode with NOTHING selected, jitter the whole mesh
# instead of erroring 'No vertices selected'.
run("set_mode", mode="EDIT", target="donut")
import bmesh  # noqa: E402
_bm = bmesh.from_edit_mesh(bpy.data.objects["donut"].data)
for _v in _bm.verts:
    _v.select = False
bmesh.update_edit_mesh(bpy.data.objects["donut"].data)
r2 = run("jitter_vertices", amount=0.01, seed=2)
check("jitter with no selection jitters whole mesh (no error)", r2.get("success") is True, str(r2))
n_touched = r2.get("verts_randomized", r2.get("verts_jittered"))
check("whole-mesh jitter touched all verts",
      n_touched == len(bpy.data.objects["donut"].data.vertices),
      f"{n_touched} of {len(bpy.data.objects['donut'].data.vertices)}")
run("set_mode", mode="OBJECT", target="donut")

print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("GAPS-B PASSED")

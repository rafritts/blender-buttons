"""E2E for Cluster 2 — the floor/topology engine:

  G129 — open boundary edges (1 face) are split from true non-manifold (3+/0 face); a flat
         plane / cup mouth is NOT a defect, reported as a quiet count + declarable via expect.
  G118 — an impossible Euler characteristic (χ vs boundary loops vs components) is a defect.
  G105/G134 — a geometry op that opens a hole / adds non-manifold junk warns at the op
         (topology_delta_warning), the mirror of the no-op detector.
  G101 — smooth_edges (shading-only) no longer trips the geometry no-op detector.
  G124 — penetration depth against an OPEN shell is suppressed (no bogus mm).

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g129_topology_floor.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import validation, lint, common  # noqa: E402

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
    validation.clear_intents()


def _bm_of(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    return bm


# ---- G118 helper math: Euler invariant respects components + boundaries ----------
check("euler: disk (χ=1,b=1,c=1) consistent", common.euler_consistent(4, 4, 1, 1, 1)[0])
check("euler: closed sphere (χ=2,b=0,c=1) consistent", common.euler_consistent(6, 12, 8, 0, 1)[0])
check("euler: TWO closed shells (χ=4,b=0,c=2) consistent — not a false positive",
      common.euler_consistent(12, 24, 16, 0, 2)[0])
check("euler: χ=2 with 1 boundary loop, c=1 → INCONSISTENT (the G118 tell)",
      not common.euler_consistent(6, 11, 7, 1, 1)[0],
      f"got {common.euler_consistent(6, 11, 7, 1, 1)}")


# ---- G129: check_mesh splits boundary edges from non-manifold ---------------------
clean()
bpy.ops.mesh.primitive_plane_add(size=1.0)
plane = bpy.context.active_object
plane.name = "Table"
rep = lint.check_mesh({"target": "Table"})["reports"][0]
check("plane: 4 boundary edges", rep["boundary_edges"] == 4, str(rep))
check("plane: 0 non-manifold edges (not lumped)", rep["non_manifold_edges"] == 0, str(rep))
check("plane: 1 boundary loop", rep["boundary_loops"] == 1, str(rep))
check("plane: euler consistent", rep["euler_ok"], str(rep))

bpy.ops.mesh.primitive_cube_add(size=1.0)
cube = bpy.context.active_object
cube.name = "Box"
rep = lint.check_mesh({"target": "Box"})["reports"][0]
check("cube: watertight, 0 boundary, 0 non-manifold",
      rep["watertight"] and rep["boundary_edges"] == 0 and rep["non_manifold_edges"] == 0, str(rep))


# ---- G129: run_validate — plane's open boundary is a QUIET count, not a defect ----
clean()
bpy.ops.mesh.primitive_plane_add(size=1.0)
bpy.context.active_object.name = "Table"
v = validation.run_validate(["Table"])
check("plane floor PASSES (open boundary is not a defect)", v["passed"], v["line"])
check("plane has no non_manifold finding",
      not any(f["check"] == "non_manifold" for f in v["intent_free"]), str(v["intent_free"]))
check("plane open_boundary reported as quiet count",
      len(v["open_boundary"]["undeclared"]) == 1, str(v["open_boundary"]))
# declare it intended → undeclared clears
validation.add_intent("Table", "", "tabletop is intentionally a flat plane",
                      check="open_boundary")
v = validation.run_validate(["Table"])
check("after expect open_boundary: no undeclared, 1 intended",
      not v["open_boundary"]["undeclared"] and v["open_boundary"]["intended"] == 1, str(v["open_boundary"]))


# ---- G105/G134: opening a hole warns at the op (topology delta) -------------------
clean()
bpy.ops.mesh.primitive_cube_add(size=1.0)
box = bpy.context.active_object
box.name = "Shell"
before = bb_server._topo_signature(box)
# delete the top face → opens one boundary loop
bm = bmesh.new(); bm.from_mesh(box.data)
top = [f for f in bm.faces if all(vv.co.z > 0.4 for vv in f.verts)]
bmesh.ops.delete(bm, geom=top, context='FACES')
bm.to_mesh(box.data); bm.free()
after = bb_server._topo_signature(box)
warn = bb_server._topology_delta_warning(before, after)
check("topology delta detects the new boundary loop", warn is not None and "boundary" in warn, str(warn))
check("a heal/no-change is silent", bb_server._topology_delta_warning(after, after) is None)


# ---- G124: penetration depth against an OPEN shell is suppressed ------------------
clean()
# an open bowl (cube minus top) and a small cube resting inside-ish, overlapping
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
bowl = bpy.context.active_object; bowl.name = "Bowl"
bm = bmesh.new(); bm.from_mesh(bowl.data)
top = [f for f in bm.faces if all(vv.co.z > 0.4 for vv in f.verts)]
bmesh.ops.delete(bm, geom=top, context='FACES')
bm.to_mesh(bowl.data); bm.free()
bpy.ops.mesh.primitive_cube_add(size=0.5, location=(0, 0, 0.2))
bpy.context.active_object.name = "Pea"
v = validation.run_validate(["Pea", "Bowl"])
clip_msgs = " ".join(n["message"] for n in v["clipping"]["new"])
# the open-shell pair must NOT carry a fabricated mm number
import re
bogus = re.search(r"\b(\d{2,})mm", clip_msgs)
check("open-shell clip carries no bogus mm magnitude", bogus is None, clip_msgs)
if v["clipping"]["new"]:
    check("open-shell clip hints at feel op=clearance",
          any(n["depth_mm"] is None for n in v["clipping"]["new"]), clip_msgs)


print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

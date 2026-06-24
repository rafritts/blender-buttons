"""E2E for Cluster 5 — hollow vessel + boolean robustness:

  G106/G127 — object op=hollow carves a solid into an OPEN, watertight-walled vessel in
              one call (delete cap → SOLIDIFY inward), reports measured world wall thickness.
  G109      — boolean UNION auto-welds sliver/coincident verts (no degenerate-loop shatter).
  G127      — boolean flags a non-watertight operand.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g106_g109_g127_hollow_boolean.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import lint  # noqa: E402

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


def topo(name):
    """(boundary_loops, components, chi) for an object's mesh."""
    from extension.common import boundary_loop_count, mesh_components
    o = bpy.data.objects.get(name)
    bm = bmesh.new(); bm.from_mesh(o.data)
    loops = boundary_loop_count(bm)
    comps = mesh_components(bm)
    chi = len(bm.verts) - len(bm.edges) + len(bm.faces)
    bm.free()
    return loops, comps, chi


# ---- G106/G127: object op=hollow makes an open cup -----------------------------------
clean()
bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.10, vertices=48)
bpy.context.active_object.name = "Mug"
res = run("hollow", target="Mug", thickness=0.004, open="top")
check("hollow succeeds + applies", res.get("success") and res.get("applied"), res.get("error", ""))
check("hollow removed the top cap", res.get("cap_faces_removed", 0) >= 1, str(res))
# A thick-walled solid cup is WATERTIGHT: the mouth is a concave upward dimple, not an open
# edge. open=top → one connected genus-0 solid (χ=2) whose cavity opens to the outside.
loops, comps, chi = topo("Mug")
check("hollow cup is watertight (mouth is a cavity, not an open boundary)", loops == 0, str(loops))
check("hollow cup is one connected solid (cavity opens outward)", comps == 1, str(comps))
check("hollow cup is genus-0 (χ=2)", chi == 2, str(chi))
rep = lint.check_mesh({"target": "Mug"})["reports"][0]
check("hollow wall is manifold (no non-manifold edges)", rep["non_manifold_edges"] == 0, str(rep))
check("hollow result is Euler-consistent", rep["euler_ok"], str(rep))

# open=none → a SEALED double-wall shell: two separate closed surfaces (χ=4), cavity
# enclosed, no boundary. This is the topological tell that distinguishes it from open=top.
clean()
bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.10, vertices=48)
bpy.context.active_object.name = "Shell"
res = run("hollow", target="Shell", thickness=0.004, open="none")
loops, comps, chi = topo("Shell")
check("hollow open=none leaves no boundary", res.get("success") and loops == 0, str(loops))
check("hollow open=none is a sealed double shell (2 components)", comps == 2, str(comps))


# ---- G127: boolean flags a non-watertight operand -----------------------------------
clean()
bpy.ops.mesh.primitive_cube_add(size=0.1, location=(0, 0, 0))
bpy.context.active_object.name = "Body"
bpy.ops.mesh.primitive_cylinder_add(radius=0.01, depth=0.2, vertices=16, location=(0, 0, 0))
tube = bpy.context.active_object; tube.name = "Tube"
# open the tube ends → non-watertight operand
bm = bmesh.new(); bm.from_mesh(tube.data)
caps = [f for f in bm.faces if abs(f.calc_center_median().z) > 0.09]
bmesh.ops.delete(bm, geom=caps, context='FACES')
bm.to_mesh(tube.data); bm.free()
res = run("boolean", target="Body", cutter="Tube", op="UNION", apply=True)
notes = " ".join(res.get("notes", []))
check("boolean flags the non-watertight operand", "watertight" in notes, notes or "(no notes)")


# ---- G109: boolean UNION welds coincident verts (clean=True) -------------------------
clean()
bpy.ops.mesh.primitive_cube_add(size=0.1, location=(0, 0, 0))
bpy.context.active_object.name = "A"
bpy.ops.mesh.primitive_cube_add(size=0.1, location=(0.05, 0, 0))
bpy.context.active_object.name = "C"
res = run("boolean", target="A", cutter="C", op="UNION", apply=True)
check("boolean UNION applied", res.get("success") and res.get("applied"), res.get("error", ""))
rep = lint.check_mesh({"target": "A"})["reports"][0]
check("UNION result has no non-manifold edges (welded clean)", rep["non_manifold_edges"] == 0,
      str(rep))


print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

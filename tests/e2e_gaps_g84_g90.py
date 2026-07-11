"""E2E for the G84-G90 gap fixes — runs the WORKING-TREE extension in headless Blender.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_gaps_g84_g90.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import status as bb_status  # noqa: E402

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


def bsdf_of(obj):
    mat = obj.data.materials[0]
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), mat


# ───────────────────────── G89 — modifier add resolves target= ─────────────────────────
print("== G89: modifier add target= (non-partner type lands on named host) ==")
clean()
run("add_box", name="A", width=0.2, depth=0.2, height=0.2)
run("add_box", name="B", width=0.2, depth=0.2, height=0.2)
bpy.context.view_layer.objects.active = bpy.data.objects["B"]  # B is active, target A
r = run("add_modifier", type="ARRAY", target="A", count=3)
check("array add succeeds", r.get("success"), r.get("error"))
check("ARRAY landed on target A", any(m.type == 'ARRAY' for m in bpy.data.objects["A"].modifiers))
check("ARRAY did NOT land on active B", not any(m.type == 'ARRAY' for m in bpy.data.objects["B"].modifiers))
check("status_focus is the host A", r.get("status_focus") == "A", r.get("status_focus"))

print("== G89: SHRINKWRAP partner semantics preserved (target=partner, host=active) ==")
clean()
run("add_box", name="host", width=0.4, depth=0.4, height=0.4)
run("add_sphere", name="surf", radius=0.5)
bpy.context.view_layer.objects.active = bpy.data.objects["host"]
r = run("add_modifier", type="SHRINKWRAP", target="surf")
check("shrinkwrap add succeeds", r.get("success"), r.get("error"))
host = bpy.data.objects["host"]
sw = next((m for m in host.modifiers if m.type == 'SHRINKWRAP'), None)
check("SHRINKWRAP on active host", sw is not None)
check("SHRINKWRAP partner is surf", sw is not None and sw.target and sw.target.name == "surf")
check("partner surf has no modifier", not list(bpy.data.objects["surf"].modifiers))

print("== G89: missing target errors (non-partner) ==")
clean()
run("add_box", name="solo", width=0.2, depth=0.2, height=0.2)
bpy.context.view_layer.objects.active = None
r = run("add_modifier", type="ARRAY", target="nope")
check("unknown target errors", "error" in r and "not found" in r["error"], r)

# ───────────────────────── G90 — ARRAY count / offset settable ─────────────────────────
print("== G90: ARRAY add honors count + constant offset along axis ==")
clean()
run("add_box", name="link", width=0.1, depth=0.1, height=0.1)
r = run("add_modifier", type="ARRAY", target="link", count=5, offset=0.2, axis="X")
check("array add ok", r.get("success"), r.get("error"))
m = next(m for m in bpy.data.objects["link"].modifiers if m.type == 'ARRAY')
check("count == 5", m.count == 5, m.count)
check("use_constant_offset on", m.use_constant_offset is True)
check("constant_offset_displace.x == 0.2", abs(m.constant_offset_displace[0] - 0.2) < 1e-5,
      list(m.constant_offset_displace))

print("== G90: ARRAY modify honors offset (not skipped) ==")
r = run("modify_modifier", target="link", modifier_name=m.name, count=8, offset=0.35)
check("modify ok", r.get("success"), r.get("error"))
check("offset NOT in skipped", "offset" not in (r.get("skipped") or []), r.get("skipped"))
check("count updated to 8", m.count == 8, m.count)
check("constant offset updated to 0.35", abs(m.constant_offset_displace[0] - 0.35) < 1e-5,
      list(m.constant_offset_displace))

print("== G90: ARRAY relative offset (factor) along axis ==")
clean()
run("add_box", name="rl", width=0.1, depth=0.1, height=0.1)
r = run("add_modifier", type="ARRAY", target="rl", count=4, factor=1.5, axis="Y")
mr = next(m for m in bpy.data.objects["rl"].modifiers if m.type == 'ARRAY')
check("relative offset on", mr.use_relative_offset is True)
check("relative_offset_displace.y == 1.5", abs(mr.relative_offset_displace[1] - 1.5) < 1e-5,
      list(mr.relative_offset_displace))

# ───────────────────────── G84 — material transmission ─────────────────────────
print("== G84: material set transmission → BSDF + refraction flags ==")
clean()
run("add_box", name="glass", width=0.3, depth=0.3, height=0.3)
r = run("set_material", target="glass", transmission=1.0, ior=1.45, roughness=0.0)
check("set_material ok", r.get("success"), r.get("error"))
check("transmission in applied", any("transmission=1.0" in a for a in (r.get("applied") or [])),
      r.get("applied"))
bsdf, mat = bsdf_of(bpy.data.objects["glass"])
check("BSDF Transmission Weight == 1.0", abs(bsdf.inputs["Transmission Weight"].default_value - 1.0) < 1e-5,
      bsdf.inputs["Transmission Weight"].default_value)
check("mat.use_screen_refraction enabled", getattr(mat, "use_screen_refraction", False) is True)

# ───────────────────────── G86 — camera lens on existing camera ─────────────────────────
print("== G86: set_camera_lens retunes an existing camera ==")
clean()
run("add_camera", name="hero", x=2, y=-2, z=1, lens=50)
check("cam starts at 50mm", abs(bpy.data.objects["hero"].data.lens - 50) < 1e-4)
r = run("set_camera_lens", camera="hero", lens=85)
check("set lens ok", r.get("success"), r.get("error"))
check("lens now 85mm", abs(bpy.data.objects["hero"].data.lens - 85) < 1e-4,
      bpy.data.objects["hero"].data.lens)
# default (scene cam) path
r2 = run("set_camera_lens", lens=135)
check("scene-cam lens → 135", abs(bpy.data.objects["hero"].data.lens - 135) < 1e-4,
      bpy.data.objects["hero"].data.lens)
r3 = run("set_camera_lens", lens=24, camera="ghost")
check("unknown camera errors", "error" in r3, r3)

# ───────────────────────── G85 — extrude sel_bounds (DIAGNOSTIC) ─────────────────────────
print("== G85: post-extrude selection (inset a cap, extrude it) ==")
clean()
run("add_cylinder", name="cyl", radius=0.25, height=0.5)
cyl = bpy.data.objects["cyl"]
bpy.context.view_layer.objects.active = cyl
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(cyl.data)
bpy.ops.mesh.select_mode(type='FACE')
for f in bm.faces:
    f.select = False
# top cap = the face whose center z is the max
top = max(bm.faces, key=lambda f: f.calc_center_median().z)
top.select = True
bmesh.update_edit_mesh(cyl.data)
n_cap = len(top.verts)
print(f"  [info] cap face has {n_cap} verts")
# inset then extrude using the working-tree handlers
from extension import editmode  # noqa: E402
editmode.inset_faces({"thickness": 0.05})
st_inset = bb_status.get_blender_status({}).get("status", {}).get("edit", {})
print(f"  [info] after inset:   sel verts={st_inset.get('selected')} bounds.x={st_inset.get('selection_bounds',{}).get('x')}")
editmode.extrude({"down": 0.1})
st_ext = bb_status.get_blender_status({}).get("status", {}).get("edit", {})
sb = st_ext.get("selection_bounds", {})
print(f"  [info] after extrude: sel verts={st_ext.get('selected')} bounds.x={sb.get('x')}")
# An inset cap of radius (0.25-0.05)=0.20 → diameter ~0.40. The selection after extrude
# should describe ONLY that inner cap, NOT the full outer diameter ~0.50.
inner_face = bmesh.from_edit_mesh(cyl.data)
sel_faces = [f for f in inner_face.faces if f.select]
sel_verts = [v for v in inner_face.verts if v.select]
xr = sb.get("x")
span = (xr[1] - xr[0]) if isinstance(xr, (list, tuple)) and len(xr) == 2 else None
print(f"  [info] selected faces={len(sel_faces)} verts={len(sel_verts)} x-span={span}")
check("extrude leaves exactly 1 face selected", len(sel_faces) == 1, len(sel_faces))
check("extrude selection vert count == cap (not 2×)", len(sel_verts) == n_cap, len(sel_verts))
check("extrude sel x-span ≈ inner cap (~0.40, not outer 0.50)", span is not None and span < 0.45, span)
bpy.ops.object.mode_set(mode='OBJECT')

# ───────────────────────── G87 — move_verts → edit (REPRO ATTEMPT) ─────────────────────────
print("== G87: select-all → move_verts → taper_end across meshes (no-op repro) ==")
clean()
noops = []
for i in range(4):
    nm = f"col{i}"
    run("add_cylinder", name=nm, radius=0.2, height=1.0)
    run("select_all", target=nm)
    run("move_vertices", target=nm, z=0.05)
    rt = run("taper_end", target=nm, axis="Z", end="top", scale=0.5)
    no = bool(rt.get("no_op"))
    noops.append((nm, no, rt.get("success")))
    print(f"  [info] {nm}: success={rt.get('success')} no_op={no}")
check("no taper_end no-ops across 4 meshes", not any(n for _, n, _ in noops), noops)

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
else:
    print("ALL CHECKS PASSED")

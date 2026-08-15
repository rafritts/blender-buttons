"""SPEC-22 Phase 4 — headless real-geometry checks for the native-basis completion.

Exercises every new edit op through the extension dispatch (execute_command), on real
meshes, asserting actual geometry effects (counts / positions). Standalone: sets up its
own objects, records `failures`, sys.exit(1) on failure else prints ALL PASSED.

Usage: flatpak run org.blender.Blender --background --python /abs/path/tests/e2e_spec22_phase4.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bmesh  # noqa: E402
import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402

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
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def enter_edit(obj, mode='VERT'):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type=mode)


def bm(obj):
    return bmesh.from_edit_mesh(obj.data)


def new_grid(name, n=4):
    clean()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=n, y_subdivisions=n)
    o = bpy.context.active_object
    o.name = name
    return o


def new_cube(name):
    clean()
    bpy.ops.mesh.primitive_cube_add()
    o = bpy.context.active_object
    o.name = name
    return o


def new_sphere(name, r=1.0):
    clean()
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r)
    o = bpy.context.active_object
    o.name = name
    return o


# ── shrink_fatten: now wraps native transform.shrink_fatten (Offset Even available) ──
print("== shrink_fatten (native transform.shrink_fatten) ==")
o = new_sphere("sf", r=1.0)
enter_edit(o)
bpy.ops.mesh.select_all(action='SELECT')
r0 = max(v.co.length for v in bm(o).verts)
r = run("inflate_selection", amount=0.3, even=False)
r1 = max(v.co.length for v in bm(o).verts)
check("shrink_fatten success", r.get("success"), r)
check("shrink_fatten pushed out ~0.3", abs((r1 - r0) - 0.3) < 0.02, (r0, r1))
# Offset Even path drives without error
r = run("inflate_selection", amount=-0.1, even=True)
check("shrink_fatten even=True success", r.get("success"), r)

# ── duplicate (Shift+D) ──
print("== duplicate ==")
o = new_cube("dup")
enter_edit(o)
bpy.ops.mesh.select_all(action='SELECT')
r = run("duplicate_selection", up=1.0)
check("duplicate success", r.get("success"), r)
check("duplicate doubled verts", r.get("verts_after") == 2 * r.get("verts_before"), r)
# the copy is the selection and moved up by ~1
sel = [v for v in bm(o).verts if v.select]
check("copy selected (8 verts)", len(sel) == 8, len(sel))
# original cube top at z=1; the copy (all verts) moved up 1.0 → top at z=2.0
check("copy moved up ~1", abs(max(v.co.z for v in sel) - 2.0) < 0.05,
      max(v.co.z for v in bm(o).verts))

# ── rotate (R) ──
print("== rotate ==")
o = new_cube("rot")
enter_edit(o)
bpym = bm(o)
for v in bpym.verts:
    v.select = (v.co.z > 0)
bmesh.update_edit_mesh(o.data)
before = {v.index: v.co.copy() for v in bm(o).verts if v.select}
r = run("rotate_selection", angle=45, axis="Z")
after = {v.index: v.co.copy() for v in bm(o).verts if v.select}
moved = sum(1 for i in before if (before[i] - after[i]).length > 1e-4)
check("rotate success", r.get("success"), r)
check("rotate moved the top verts", moved == 4, moved)

# ── merge at CENTER / DISTANCE ──
print("== merge at ==")
o = new_cube("mrg")
enter_edit(o)
bpy.ops.mesh.select_all(action='SELECT')
r = run("merge_at", at="CENTER")
check("merge CENTER success", r.get("success"), r)
check("merge CENTER → 1 vert", r.get("verts_after") == 1, r)
# DISTANCE routes through the by-distance handler
o = new_cube("mrg2")
enter_edit(o)
bpy.ops.mesh.select_all(action='SELECT')
r = run("merge_by_distance", threshold=0.001)
check("merge DISTANCE success", r.get("success"), r)

# ── edge_face (F) ──
print("== edge_face ==")
o = new_grid("ef", n=4)
enter_edit(o)
bpy.ops.mesh.select_all(action='DESELECT')
g = bm(o)
g.verts.ensure_lookup_table()
# two adjacent boundary verts with no face between → new edge; pick a hole instead
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.delete(type='ONLY_FACE')  # keep the wire, remove faces
bpy.ops.mesh.select_all(action='DESELECT')
g = bm(o)
g.faces.ensure_lookup_table() if False else None
# select 4 verts forming one quad boundary
g.verts.ensure_lookup_table()
corner = [v for v in g.verts if abs(v.co.x + 1) < 1e-3 and abs(v.co.y + 1) < 1e-3][0]
ring = [corner]
# grab the 3 nearest verts to form a small loop
verts_sorted = sorted(g.verts, key=lambda v: (v.co - corner.co).length)
for v in verts_sorted[:4]:
    v.select = True
bmesh.update_edit_mesh(o.data)
f_before = len(bm(o).faces)
r = run("make_edge_face")
check("edge_face success", r.get("success"), r)
check("edge_face added an edge or face", (r.get("edges_added", 0) + r.get("faces_added", 0)) > 0, r)

# ── dissolve (Ctrl+X) vs delete ──
print("== dissolve ==")
o = new_grid("dis", n=4)
enter_edit(o)
g = bm(o)
g.verts.ensure_lookup_table()
for v in g.verts:
    v.select = (abs(v.co.x) < 0.01 and abs(v.co.y) < 0.01)
bmesh.update_edit_mesh(o.data)
vb = len(bm(o).verts)
fb = len(bm(o).faces)
r = run("dissolve", mode="VERT")
check("dissolve success", r.get("success"), r)
check("dissolve removed the vert", r.get("verts_after") == vb - 1, (vb, r))
# dissolve keeps the surface (merges faces) — face count drops but no hole
check("dissolve kept surface (fewer faces, still filled)", len(bm(o).faces) < fb, (fb, len(bm(o).faces)))

# ── hide / reveal (H / Alt+H) ──
print("== hide / reveal ==")
o = new_cube("hr")
enter_edit(o)
bpy.ops.mesh.select_all(action='DESELECT')
g = bm(o)
g.verts.ensure_lookup_table()
g.verts[0].select = True
bmesh.update_edit_mesh(o.data)
r = run("hide_geometry", unselected=False)
check("hide success", r.get("success"), r)
check("hide hid 1 vert", r.get("hidden_verts") == 1, r)
r = run("reveal_geometry")
check("reveal success", r.get("success"), r)
check("reveal unhid all", sum(1 for v in bm(o).verts if v.hide) == 0)

# ── rip (V) — bmesh equivalent ──
print("== rip ==")
o = new_grid("rip", n=4)
enter_edit(o, mode='EDGE')
bpy.ops.mesh.select_all(action='DESELECT')
g = bm(o)
g.edges.ensure_lookup_table()
sel = [e for e in g.edges if all(abs(v.co.x) < 0.01 for v in e.verts) and len(e.link_faces) == 2]
for e in sel:
    e.select = True
bmesh.update_edit_mesh(o.data)
vb = len(bm(o).verts)
r = run("rip_selection", right=0.1)
check("rip success", r.get("success"), r)
check("rip opened new verts", r.get("verts_after") > vb, (vb, r))

# ── split (Y) ──
print("== split ==")
o = new_grid("spl", n=4)
enter_edit(o, mode='FACE')
bpy.ops.mesh.select_all(action='DESELECT')
g = bm(o)
g.faces.ensure_lookup_table()
# an interior face (all its verts fully shared) so split duplicates its boundary
interior = min(g.faces, key=lambda f: f.calc_center_median().length)
interior.select = True
bmesh.update_edit_mesh(o.data)
vb = len(bm(o).verts)
r = run("split_selection")
check("split success", r.get("success"), r)
check("split duplicated boundary verts", r.get("verts_after") > vb, (vb, r))

# ── smooth (Vertex ▸ Smooth) ──
print("== smooth ==")
o = new_grid("smo", n=6)
enter_edit(o)
g = bm(o)
g.verts.ensure_lookup_table()
for v in g.verts:
    v.co.z += 0.3 * ((v.index % 3) - 1)
bmesh.update_edit_mesh(o.data)
bpy.ops.mesh.select_all(action='SELECT')
zb = [v.co.z for v in bm(o).verts]
var_b = max(zb) - min(zb)
r = run("smooth_vertices", factor=0.5, repeat=4)
za = [v.co.z for v in bm(o).verts]
var_a = max(za) - min(za)
check("smooth success", r.get("success"), r)
check("smooth reduced z-variance", var_a < var_b * 0.8, (var_b, var_a))

# ── bisect ──
print("== bisect ==")
o = new_cube("bis")
enter_edit(o)
bpy.ops.mesh.select_all(action='SELECT')
vb = len(bm(o).verts)
r = run("bisect", axis="Z", offset=0.0, use_fill=True)
check("bisect success", r.get("success"), r)
check("bisect added verts on the cut", r.get("verts_after") > vb, (vb, r))

# ── shear — bmesh equivalent ──
print("== shear ==")
o = new_cube("shr")
enter_edit(o)
bpy.ops.mesh.select_all(action='SELECT')
before = {v.index: v.co.copy() for v in bm(o).verts}
r = run("shear_selection", amount=0.5, axis="X", along="Z")
after = {v.index: v.co.copy() for v in bm(o).verts}
top = [i for i in before if before[i].z > 0]
bot = [i for i in before if before[i].z < 0]
dtop = sum((after[i].x - before[i].x) for i in top) / len(top)
dbot = sum((after[i].x - before[i].x) for i in bot) / len(bot)
check("shear success", r.get("success"), r)
check("shear slanted top +x, bottom -x", dtop > 0.2 and dbot < -0.2, (dtop, dbot))

# ── to_sphere ──
print("== to_sphere ==")
o = new_cube("sph")
enter_edit(o)
bpy.ops.mesh.select_all(action='SELECT')
r = run("to_sphere", factor=1.0)
lens = [v.co.length for v in bm(o).verts]
check("to_sphere success", r.get("success"), r)
check("to_sphere equalized radii", (max(lens) - min(lens)) < 1e-3, (min(lens), max(lens)))

# ── triangulate / tris_to_quads ──
print("== triangulate / tris_to_quads ==")
o = new_cube("tri")
enter_edit(o, mode='FACE')
bpy.ops.mesh.select_all(action='SELECT')
r = run("triangulate")
check("triangulate success", r.get("success"), r)
check("triangulate 6→12 faces", r.get("faces_after") == 12, r)
r = run("tris_to_quads")
check("tris_to_quads success", r.get("success"), r)
check("tris_to_quads back to 6 faces", r.get("faces_after") == 6, r)

# ── fill ──
print("== fill ==")
o = new_grid("fil", n=4)
enter_edit(o, mode='FACE')
g = bm(o)
g.faces.ensure_lookup_table()
g.faces[0].select = True
bmesh.update_edit_mesh(o.data)
bpy.ops.mesh.delete(type='ONLY_FACE')
bpy.ops.mesh.select_all(action='SELECT')
r = run("fill")
check("fill success", r.get("success"), r)
check("fill added faces", r.get("faces_added", 0) > 0, r)

# ── beautify ──
print("== beautify ==")
o = new_grid("bty", n=4)
enter_edit(o, mode='FACE')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.quads_convert_to_tris()
r = run("beautify")
check("beautify success", r.get("success"), r)

# ── connect (J) ──
print("== connect ==")
o = new_cube("con")
enter_edit(o)
bpy.ops.mesh.select_all(action='DESELECT')
g = bm(o)
g.faces.ensure_lookup_table()
vv = list(g.faces[0].verts)
vv[0].select = True
vv[2].select = True
bmesh.update_edit_mesh(o.data)
eb = len(bm(o).edges)
r = run("connect_verts")
check("connect success", r.get("success"), r)
check("connect cut a new edge", r.get("edges_added", 0) >= 1, r)

# ── slide — bmesh equivalent ──
print("== slide ==")
o = new_grid("sli", n=5)
enter_edit(o, mode='EDGE')
bpy.ops.mesh.select_all(action='DESELECT')
g = bm(o)
g.verts.ensure_lookup_table()
xs = sorted(set(round(v.co.x, 4) for v in g.verts))
col = xs[2]
for e in g.edges:
    if all(abs(v.co.x - col) < 1e-3 for v in e.verts):
        e.select = True
bmesh.update_edit_mesh(o.data)
sel_v = [v for v in bm(o).verts if v.select]
before = {v.index: v.co.copy() for v in sel_v}
r = run("slide", factor=0.6, mode="EDGE")
after = {v.index: v.co.copy() for v in bm(o).verts if v.index in before}
moved = sum(1 for i in before if (before[i] - after[i]).length > 1e-4)
check("slide success", r.get("success"), r)
check("slide moved the loop verts", moved > 0, moved)

# ── B8: move_modifier reorders without NameError (_BIND_TYPES restored) ──
print("== B8 move_modifier ==")
clean()
run("add_box", name="block", width=1, depth=1, height=1)
run("select_object", name="block")
run("add_modifier", type="SUBSURF", name="Subsurf")
run("add_modifier", type="BEVEL", name="Bevel")
run("add_modifier", type="SOLIDIFY", name="Solidify")
r = run("move_modifier", target="block", modifier="Solidify", index=0)
check("B8 move by index success", r.get("success") is True, str(r))
names = [m.name for m in bpy.data.objects["block"].modifiers]
check("B8 Solidify now on top", names == ["Solidify", "Subsurf", "Bevel"], names)
r = run("move_modifier", target="block", modifier="Solidify", after="Subsurf")
check("B8 move after= success", r.get("success") is True, str(r))
names = [m.name for m in bpy.data.objects["block"].modifiers]
check("B8 Solidify directly below Subsurf", names == ["Subsurf", "Solidify", "Bevel"], names)
r = run("move_modifier", target="block", modifier="Bevel", before="Subsurf")
check("B8 move before= success", r.get("success") is True, str(r))

# ── B9: randomize is native vertex_random (3D, no axis lock) ──
print("== B9 randomize (native vertex_random) ==")
o = new_grid("rnd", n=6)
enter_edit(o)
bpy.ops.mesh.select_all(action='SELECT')
before = [v.co.copy() for v in bm(o).verts]
r = run("jitter_vertices", amount=0.25, seed=7)
check("B9 randomize success", r.get("success") is True, str(r))
after = [v.co.copy() for v in bm(o).verts]
dx = sum(1 for a, b in zip(before, after) if abs(a.x - b.x) > 1e-8)
dy = sum(1 for a, b in zip(before, after) if abs(a.y - b.y) > 1e-8)
dz = sum(1 for a, b in zip(before, after) if abs(a.z - b.z) > 1e-8)
check("B9 displaced in X and Y, not Z-only", dx > 0 and dy > 0,
      f"dx={dx} dy={dy} dz={dz}")
# same seed reproduces
bpy.ops.mesh.select_all(action='SELECT')
for v, c in zip(bm(o).verts, before):
    v.co = c
bmesh.update_edit_mesh(o.data)
r = run("jitter_vertices", amount=0.25, seed=7)
again = [v.co.copy() for v in bm(o).verts]
check("B9 same seed reproduces",
      all((a - b).length < 1e-8 for a, b in zip(after, again)))

# ── B10: group MOVES into the new collection (native Move to Collection) ──
print("== B10 group unlinks previous collection ==")
clean()
run("add_box", name="Proto", width=0.1, depth=0.1, height=0.1)
proto = bpy.data.objects["Proto"]
prev = [c.name for c in proto.users_collection]
check("B10 proto starts in some collection", len(prev) >= 1, prev)
g = run("group", name="SprinkleProto", parts=["Proto"])
check("B10 group succeeds", g.get("success") is True, str(g.get("error")))
users = [c.name for c in proto.users_collection]
check("B10 proto is only in SprinkleProto", users == ["SprinkleProto"], users)
run("add_box", name="Other", width=0.1, depth=0.1, height=0.1)
other = bpy.data.objects["Other"]
r = run("add_to_group", name="SprinkleProto", parts=["Other"])
check("B10 add_to_group succeeds", r.get("success") is True, str(r.get("error")))
other_users = [c.name for c in other.users_collection]
check("B10 add_to_group unlinked Other from its previous collection",
      other_users == ["SprinkleProto"], other_users)

# ── grab snap_to=face_project ──
print("== grab snap_to=face_project ==")
clean()
# a target sphere to project onto
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 0))
target = bpy.context.active_object
target.name = "snap_target"
bpy.ops.object.mode_set(mode='OBJECT')
# a plane above it whose verts we drape down onto the sphere
bpy.ops.mesh.primitive_grid_add(x_subdivisions=3, y_subdivisions=3, size=1.0,
                                location=(0, 0, 2.0))
plane = bpy.context.active_object
plane.name = "drape"
enter_edit(plane)
bpy.ops.mesh.select_all(action='SELECT')
r = run("move_vertices", down=0.5, snap_to="face_project", snap_target="snap_target")
check("grab snap success", r.get("success"), r)
check("grab snapped verts onto surface", r.get("snapped_to_face", 0) > 0, r)
# every draped vert should now lie on the sphere surface (radius ~1 in world)
mw = plane.matrix_world
world = [mw @ v.co for v in bm(plane).verts]
on_sphere = sum(1 for w in world if abs(w.length - 1.0) < 0.05)
check("draped verts landed on the sphere", on_sphere == len(world), (on_sphere, len(world)))

# ── summary ──
print()
if failures:
    print(f"SPEC-22 P4: {len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("ALL PASSED")

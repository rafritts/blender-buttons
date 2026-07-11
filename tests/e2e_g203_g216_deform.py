"""E2E for the bead-of-icing gap batch + import interlock — runs the WORKING-TREE extension
headless (no socket), driving execute_command exactly like the live bridge.

Covers:
  G203 — file op=import stamps the clean baseline (next op doesn't trip the lock).
  G208 — sculpt displacement is METERS (scale-correct) and refuses before mutating >2×r.
  G211 — edit op=bend refuses BEFORE mutating when the axis is the object's long axis.
  G213 — a coarse footprint auto-densifies to detail= edge length before a stroke.
  G215 — a euclidean brush on a thin shell warns (two walls); connected= scopes one wall.
  G216 — edit op=scale proportional=True gathers a selection toward its centroid with falloff.

Usage: flatpak run org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_g203_g216_deform.py
"""
import os
import sys
import tempfile

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
    state.reset_history_state()


def make_grid(name, size=0.1, segs=6, z=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=segs, y_segments=segs, size=size / 2.0)
    for v in bm.verts:
        v.co.z += z
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def world_of(obj, idx):
    return obj.matrix_world @ obj.data.vertices[idx].co


# ───────────────────────── G203: import stamps the baseline ─────────────────────────
print("== G203: file op=import stamps the clean baseline ==")
clean()
make_grid("Seed")
# Establish a baseline with one real op, then export a mesh to import back.
run("move_vertices", target="Seed", x=0.0, y=0.0, z=0.0)  # logged → baseline set
blendpath = os.path.join(tempfile.gettempdir(), "bb_g203_import.blend")
bpy.ops.wm.save_as_mainfile(filepath=blendpath, copy=True)
res = run("import_mesh", path=blendpath, name="Seed")
check("import reports success", res.get("success"), str(res)[:200])
check("import logged an op_id (went through the mutating hook)", bool(res.get("op_id")), str(res)[:200])
imported = res.get("imported") or []
check("import returned object names", bool(imported), str(imported))
# The imported object must be in the freshly-stamped clean baseline, so the NEXT op
# doesn't see it as an external mutation.
in_baseline = imported and all(n in (state._clean_snapshot or {}) for n in imported)
check("imported objects are IN the clean baseline", in_baseline,
      f"baseline keys={sorted((state._clean_snapshot or {}).keys())}")
state.detect_external_mutation()
check("no lock latches after import (server's own mutation is first-party)",
      not state._world_locked)
nxt = run("move_vertices", target=imported[0] if imported else "Seed", z=0.0)
check("the next mutating op is NOT blocked by the lock", not nxt.get("world_locked"),
      str(nxt)[:160])


# ───────────────────────── G208: meters + refuse-before-mutate ─────────────────────────
print("== G208: sculpt displacement is scale-correct METERS + refuses >2×radius ==")
clean()
g = make_grid("Scaled", size=0.2, segs=10)
g.scale = (2.0, 2.0, 2.0)                       # a 2× object — the old bug doubled the move
bpy.context.view_layer.update()
# central vert (grid is 11×11 for segs=10); pick the vert nearest local origin
cidx = min(range(len(g.data.vertices)),
           key=lambda i: g.data.vertices[i].co.length)
before = world_of(g, cidx)
res = run("sculpt_inflate", target="Scaled", at=list(before), radius=0.06, amount=0.01)
check("inflate succeeded", res.get("success"), str(res)[:160])
after = world_of(g, cidx)
moved = (after - before).length
# meters-correct: the centre vert should move ~0.01 m in WORLD space (not 0.02).
check("world move ≈ amount (meters, scale-corrected)", 0.006 <= moved <= 0.014,
      f"moved={round(moved, 4)} m (expected ~0.01; old scale bug → ~0.02)")

# refuse before mutating: amount 0.5 on a 0.05 radius is 10× the radius.
clean()
g2 = make_grid("Refuse", size=0.2, segs=10)
snap = [v.co.copy() for v in g2.data.vertices]
res = run("sculpt_inflate", target="Refuse", at=[0, 0, 0], radius=0.05, amount=0.5)
check("over-2×-radius amount is REFUSED", bool(res.get("error")) and "refus" in res.get("error", "").lower(),
      str(res)[:200])
unchanged = all((v.co - snap[i]).length < 1e-6 for i, v in enumerate(g2.data.vertices))
check("refused stroke did NOT mutate the mesh", unchanged)


# ───────────────────────── G211: bend refuses the long-axis case ─────────────────────────
print("== G211: edit op=bend refuses BEFORE mutating on the long axis ==")
clean()
# an X-long bar (0.3 × 0.02 × 0.02)
me = bpy.data.meshes.new("Bar")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
for v in bm.verts:
    v.co.x *= 0.15
    v.co.y *= 0.01
    v.co.z *= 0.01
bm.to_mesh(me)
bm.free()
bar = bpy.data.objects.new("Bar", me)
bpy.context.collection.objects.link(bar)
bpy.context.view_layer.objects.active = bar
snap = [v.co.copy() for v in bar.data.vertices]
res = run("bend", targets="Bar", angle=45, axis="X")     # X is the long axis
check("bend around the long axis is REFUSED", bool(res.get("error")) and "refus" in res.get("error", "").lower(),
      str(res)[:200])
unchanged = all((v.co - snap[i]).length < 1e-6 for i, v in enumerate(bar.data.vertices))
check("refused bend did NOT mutate the bar", unchanged)
res = run("bend", targets="Bar", angle=45, axis="Y")     # perpendicular — should work
check("bend around a perpendicular axis succeeds", res.get("success"), str(res)[:200])


# ───────────────────────── G213: densify to detail= ─────────────────────────
print("== G213: a coarse footprint auto-densifies to detail= before a stroke ==")
clean()
# deliberately coarse: 2×2 grid over 0.2 m → 0.1 m edges, far coarser than a 6 mm brush
coarse = make_grid("Coarse", size=0.2, segs=2)
n_before = len(coarse.data.vertices)
res = run("sculpt_inflate", target="Coarse", at=[0, 0, 0], radius=0.03, amount=0.003)
check("stroke on coarse mesh succeeded", res.get("success"), str(res)[:160])
check("footprint was densified (subdivided_edges > 0)", res.get("subdivided_edges", 0) > 0,
      str(res.get("subdivided_edges")))
n_after = len(coarse.data.vertices)
check("vertex count grew (detail added real surface)", n_after > n_before,
      f"{n_before} → {n_after}")
# after densify no footprint edge should exceed ~detail (radius/4 = 7.5mm); allow slack
bm = bmesh.new(); bm.from_mesh(coarse.data)
mat = coarse.matrix_world
long_in_fp = [e for e in bm.edges
              if (((mat @ e.verts[0].co + mat @ e.verts[1].co) * 0.5)).length < 0.03
              and ((mat @ e.verts[0].co) - (mat @ e.verts[1].co)).length > 0.03]
check("no footprint edge longer than the radius remains", len(long_in_fp) == 0,
      f"{len(long_in_fp)} long edges left")
bm.free()


# ───────────────────────── G215: thin-shell two-wall warning + connected= ─────────────────────────
print("== G215: euclidean brush warns on a thin shell; connected= scopes one wall ==")
clean()
shell = make_grid("Shell", size=0.1, segs=10)
mod = shell.modifiers.new(name="Sol", type='SOLIDIFY')
mod.thickness = 0.002                            # 2 mm shell — thinner than the brush radius
bpy.context.view_layer.objects.active = shell
bpy.ops.object.modifier_apply(modifier="Sol")
top = max((world_of(shell, i) for i in range(len(shell.data.vertices))), key=lambda w: w.z)
# euclidean (default): radius 6mm > 2mm thickness → grabs both walls → warning
res_e = run("sculpt_inflate", target="Shell", at=[0, 0, top.z], radius=0.006, amount=0.001)
warn_e = (res_e.get("warning") or "")
check("euclidean stroke warns about two opposing walls", "two opposing" in warn_e or "back wall" in warn_e,
      f"warning={warn_e!r}")
n_euclid = res_e.get("verts_affected", 0)
# reset the shell (undo the inflate by rebuilding), then connected
clean()
shell = make_grid("Shell", size=0.1, segs=10)
mod = shell.modifiers.new(name="Sol", type='SOLIDIFY')
mod.thickness = 0.002
bpy.context.view_layer.objects.active = shell
bpy.ops.object.modifier_apply(modifier="Sol")
top = max((world_of(shell, i) for i in range(len(shell.data.vertices))), key=lambda w: w.z)
res_c = run("sculpt_inflate", target="Shell", at=[0, 0, top.z], radius=0.006, amount=0.001,
            connected=True)
warn_c = (res_c.get("warning") or "")
check("connected stroke does NOT warn about two walls", "two opposing" not in warn_c and "back wall" not in warn_c,
      f"warning={warn_c!r}")
n_conn = res_c.get("verts_affected", 0)
check("connected scope touched FEWER verts than euclidean (one wall, not both)",
      0 < n_conn < n_euclid, f"euclid={n_euclid} connected={n_conn}")


# ───────────────────────── G216: proportional_scale gathers with falloff ─────────────────────────
print("== G216: edit op=scale proportional=True gathers a selection toward its centroid ==")
clean()
patch = make_grid("Patch", size=0.2, segs=12)
# select a central cluster of verts (within 4cm of local origin)
sel = [i for i, v in enumerate(patch.data.vertices) if v.co.length < 0.04]
for i in sel:
    patch.data.vertices[i].select = True
# span of the selection before
xs = [patch.data.vertices[i].co.x for i in sel]
span_before = max(xs) - min(xs)
res = run("proportional_scale", factor=0.5, radius=0.05, falloff="SMOOTH")
check("proportional_scale succeeded", res.get("success"), str(res)[:200])
check("it reported dragging verts", res.get("affected", 0) > 0, str(res.get("affected")))
xs2 = [patch.data.vertices[i].co.x for i in sel]
span_after = max(xs2) - min(xs2)
check("selection GATHERED (span shrank toward centroid)", span_after < span_before * 0.95,
      f"span {round(span_before, 4)} → {round(span_after, 4)}")


print()
if failures:
    print(f"e2e_g203_g216_deform :: FAILED — {len(failures)}: {failures}")
    sys.exit(1)
print("e2e_g203_g216_deform :: PASSED — 0 failures")

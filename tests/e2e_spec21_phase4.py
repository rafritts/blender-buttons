"""E2E for SPEC-21 Phase 4 — coordinate starvation, headless.

Covers §6.2: bottom-level windows enumerate faces as BFS rings out from the
window centre (areas only, f<id>s); `look at=f<id>` opens the single-face vert
view — the only place vert coordinates appear, as Δs from the face centre in
world axes, with per-vert face-incidence ("shares 8 faces" = a pole) and edges
as lengths; `select op=list` reports Δ-from-centroid by default with world XYZ
demoted behind the world_xyz debug flag.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_spec21_phase4.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402
from extension import windows as bb_windows # noqa: E402

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
    bb_windows.reset()


def link(bm, name):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def ring_face_ids(lines):
    """All f<id>s named across the presented ring lines."""
    return [int(m) for ln in lines for m in re.findall(r"\bf(\d+)\b", ln)]


# ═════ A. bottom-level face enumeration: BFS rings ═══════════════════════════
print("== A. BFS ring enumeration on a bottom-level window ==")
clean()
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.2)
cube = link(bm, "Cube")

res = run("look_window", target="Cube")
check("root look succeeds", res.get("success"), str(res))
w = res.get("window", {})
check("cube window is bottom-level", w.get("bottom_level") is True, str(w))
rings = w.get("face_rings") or []
print(f"    rings: {rings}")
check("face_rings present on a bottom-level window", len(rings) > 0, str(w))
check("ring 0 is a single face", rings and rings[0].startswith("ring 0: f")
      and len(re.findall(r"\bf\d+\b", rings[0])) == 1, str(rings))
ids = ring_face_ids(rings)
check("all 6 faces enumerated exactly once",
      sorted(ids) == list(range(6)), str(ids))
check("uniform-area rings compress to '≈… each'",
      any("each" in ln for ln in rings), str(rings))
check("areas are formatted (cube face 0.04m² → 400.0cm²)",
      any("400.0cm²" in ln for ln in rings), str(rings))
check("no 'shell' prefix on a single-shell window",
      all("shell" not in ln for ln in rings), str(rings))

# BFS sanity on a 4×4-face grid: ring 0 = 1 centre face, counts grow outward
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=0.1)
grid = link(bm, "Grid")
res = run("look_window", target="Grid")
w = res.get("window", {})
rings = w.get("face_rings") or []
print(f"    grid rings: {rings}")
counts = [len(re.findall(r"\bf\d+\b", ln)) for ln in rings]
check("grid enumerates all 16 faces", sum(counts) == 16, str(counts))
check("grid ring 0 is one centre face", counts and counts[0] == 1, str(counts))
check("grid rings ordered ring 0..N",
      [ln.split(":")[0] for ln in rings]
      == [f"ring {i}" for i in range(len(rings))], str(rings))

# ═════ B. big windows do NOT enumerate ═══════════════════════════════════════
print("== B. no enumeration above the cap ==")
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=0.1)
sphere = link(bm, "Ball")
res = run("look_window", target="Ball")
w = res.get("window", {})
check("480-face window has no face_rings",
      "face_rings" not in w and not w.get("bottom_level"), str(w.keys()))

# ═════ C. multi-shell bottom windows: BFS restarts per shell ═════════════════
print("== C. multi-shell ring restart ==")
bm = bmesh.new()
res_g = bmesh.ops.create_grid(bm, x_segments=3, y_segments=3, size=0.03)
res_g = bmesh.ops.create_grid(bm, x_segments=3, y_segments=3, size=0.03)
for v in res_g["verts"]:
    v.co.x += 0.2
plates = link(bm, "Plates")
res = run("look_window", target="Plates")
w = res.get("window", {})
rings = w.get("face_rings") or []
print(f"    plate rings: {rings}")
check("both shells enumerated (2 × 9 faces)",
      sorted(ring_face_ids(rings)) == list(range(18)), str(rings))
check("shell prefixes label the restart",
      any(ln.startswith("shell 1 · ring 0:") for ln in rings)
      and any(ln.startswith("shell 2 · ring 0:") for ln in rings), str(rings))

# ═════ D. the single-face vert view ══════════════════════════════════════════
print("== D. look at=f<id> — the single-face vert view ==")
res = run("look_window", target="Cube")
w = res.get("window", {})
fid = ring_face_ids(w.get("face_rings") or [])[0]
res = run("look_window", at=f"f{fid}")
check("f-descent succeeds", res.get("success") and res.get("moved") == "down", str(res))
w = res.get("window", {})
fv = w.get("face_view") or {}
print(f"    face_view: {fv}")
check("face id echoes", fv.get("face") == f"f{fid}", str(fv))
check("window label carries the face", w.get("label", "").endswith(f"f{fid}"), str(w))
check("4 verts, each with id/at/shares",
      len(fv.get("verts", [])) == 4
      and all(v.get("id") and v.get("at", "").startswith("Δ(") and v.get("shares")
              for v in fv["verts"]), str(fv))
# local frame: origin = face centre → offsets are (±0.1, ±0.1, 0) in some axis order
ok_frame = True
for v in fv.get("verts", []):
    mags = sorted(round(abs(x), 6) for x in v.get("d", []))
    if mags != [0.0, 0.1, 0.1]:
        ok_frame = False
check("offsets are local (face centre origin): |d| = {0, 0.1, 0.1}",
      ok_frame, str(fv.get("verts")))
sums = [round(sum(v["d"][k] for v in fv["verts"]), 6) for k in range(3)]
check("offsets sum to zero (centroid origin)", sums == [0.0, 0.0, 0.0], str(sums))
check("cube corners share 3 faces",
      all(v["shares"] == 3 for v in fv.get("verts", [])), str(fv.get("verts")))
check("edges as lengths (0.2m → 20.0cm), loop-ordered, 4 of them",
      len(fv.get("edges", [])) == 4
      and all(e.endswith("20.0cm") for e in fv["edges"]), str(fv.get("edges")))
check("normal is a single world axis",
      fv.get("normal") in ("+X", "−X", "+Y", "−Y", "+Z", "−Z"), str(fv))
check("face area formatted", fv.get("area") == "400.0cm²", str(fv))
check("no landmarks/candidates/coverage noise in the face view",
      not w.get("landmarks") and not w.get("candidates")
      and "coverage" not in w, str(w))
check("stack shows the descent", len(w.get("stack", [])) == 2, str(w.get("stack")))

res = run("look_window", up=True)
check("look up pops back to the cube root",
      res.get("success") and res.get("window", {}).get("label") == "Cube", str(res))

# ═════ E. pole incidence: 'shares 8 faces' ═══════════════════════════════════
print("== E. pole face view announces incidence ==")
clean()
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=4, radius=0.05)
bm.verts.ensure_lookup_table()
bm.faces.ensure_lookup_table()
pole_v = max(bm.verts, key=lambda v: len(v.link_faces))
pole_deg = len(pole_v.link_faces)
pole_face = pole_v.link_faces[0].index
ball = link(bm, "Mini")
res = run("look_window", target="Mini")
check("mini sphere window opens (32 faces, bottom-level)",
      res.get("success") and res["window"].get("bottom_level"), str(res))
res = run("look_window", at=f"f{pole_face}")
fv = res.get("window", {}).get("face_view", {})
print(f"    pole face: {fv}")
check("pole vert announces itself: shares 8 faces",
      any(v["shares"] == pole_deg == 8 for v in fv.get("verts", [])), str(fv))
check("triangle face view has 3 verts / 3 edges",
      len(fv.get("verts", [])) == 3 and len(fv.get("edges", [])) == 3, str(fv))

# ═════ F. errors ═════════════════════════════════════════════════════════════
print("== F. legible errors ==")
res = run("look_window", at="f999")
check("unknown face id errors legibly",
      "not a face of window" in res.get("error", ""), str(res))
# f-descent respects window scope: a face outside a descended sub-window is
# not addressable there (re-open the root first — the stack is still on the
# single-face view from section E)
res = run("look_window", target="Mini")
res = run("look_window", at="top")
check("position descent works for the scope test", res.get("success"), str(res))
sub = res.get("window", {})
if res.get("success"):
    outside = [fi for fi in range(32)
               if fi not in ring_face_ids(sub.get("face_rings") or [])]
    if outside:
        res2 = run("look_window", at=f"f{outside[0]}")
        check("face outside the current window errors",
              "not a face of window" in res2.get("error", ""), str(res2))
    run("look_window", up=True)

# stale window: topology edit invalidates the face view path too
res = run("look_window", target="Mini")
me = ball.data
bm2 = bmesh.new()
bm2.from_mesh(me)
bm2.faces.ensure_lookup_table()
bmesh.ops.delete(bm2, geom=[bm2.faces[0]], context='FACES')
bm2.to_mesh(me)
bm2.free()
res = run("look_window", at=f"f{pole_face}")
check("stale window errors with recovery text",
      "stale" in res.get("error", "") and "look target=" in res.get("error", ""),
      str(res))

# ═════ G. select op=list — Δ by default, world XYZ behind debug ══════════════
print("== G. list starvation ==")
clean()
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.2)
cube = link(bm, "Cube")
cube.location.x = 1.0   # world ≠ local so the frames are distinguishable
bpy.context.view_layer.update()
res = run("select_all", action="SELECT", target="Cube")
check("select all works", res.get("success"), str(res))
res = run("list_components", max_verts=60)
check("default list succeeds, frame=centroid",
      res.get("success") and res.get("frame") == "centroid", str(res))
xs = sorted({v["co"][0] for v in res.get("verts", [])})
check("default coords are Δs (x = ±0.1, object offset gone)",
      xs == [-0.1, 0.1], str(xs))
sums = [round(sum(v["co"][k] for v in res["verts"]), 3) for k in range(3)]
check("Δs sum to zero", sums == [0.0, 0.0, 0.0], str(sums))
res = run("list_components", max_verts=60, world_xyz=True)
check("world_xyz=True restores world frame",
      res.get("success") and res.get("frame") == "world", str(res))
xs = sorted({v["co"][0] for v in res.get("verts", [])})
check("debug coords are world (x = 0.9 / 1.1)", xs == [0.9, 1.1], str(xs))
check("valence still reported",
      all(v.get("valence") == 3 for v in res.get("verts", [])), str(res))

print()
if failures:
    print(f"❌ {len(failures)} FAILURES:")
    for f in failures:
        print(f"   - {f}")
    sys.exit(1)
print("✅ all phase-4 checks pass")

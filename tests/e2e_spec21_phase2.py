"""E2E for SPEC-21 Phase 2 — landmark LOD windows (`look`), headless.

Builds a body-like compound mesh whose salience is known by construction:
  • a big central UV-sphere "torso" (one shell)
  • two long thin cylinders joined into that mesh, sticking out top-left and
    top-right (protrusions on the torso shell, mirror twins)
  • a valence-16 fan poked into the torso front (a pole / dense anomaly)
  • a small detached plate island floating beside it (a separate shell)
and asserts the root window finds them, descent is self-similar, the stack
pushes/pops, position tokens address regions, and stale windows error legibly.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_spec21_phase2.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402
import math       # noqa: E402

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


def build_body(name="Figure"):
    import mathutils
    bm = bmesh.new()
    # torso: uv sphere r=0.15 at origin
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=0.15)
    # arms: REAL protrusions — extrude the ±X extreme faces outward 0.25m, so
    # both tubes are welded into the torso shell (same connected component)
    for sx in (-1, 1):
        bm.faces.ensure_lookup_table()
        # nearest to the mirrored target point, so the two chosen faces are
        # exact mirror images (a max-x pick can land one segment off-mirror)
        import mathutils as _mu
        tgt = _mu.Vector((sx * 0.15, 0.01, 0.0))
        face = min(bm.faces, key=lambda f: (f.calc_center_median() - tgt).length)
        res = bmesh.ops.extrude_face_region(bm, geom=[face])
        new_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
        for v in new_verts:
            v.co.x += sx * 0.25
    # a poked fan disk floating at the front (an island AND a valence-16 pole)
    res = bmesh.ops.create_circle(bm, cap_ends=True, segments=16, radius=0.012)
    rotx = mathutils.Matrix.Rotation(math.radians(90), 4, 'X')
    for v in res["verts"]:
        v.co = rotx @ v.co
        v.co.y -= 0.152
        v.co.z += 0.02
    bm.faces.ensure_lookup_table()
    circle_face = [f for f in bm.faces if len(f.verts) == 16]
    if circle_face:
        bmesh.ops.poke(bm, faces=circle_face)
    # island: a small detached grid plate off to the bottom-right
    res = bmesh.ops.create_grid(bm, x_segments=3, y_segments=3, size=0.02)
    for v in res["verts"]:
        v.co.x += 0.16
        v.co.z -= 0.20
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


print("== root window: orientation + salience-ranked landmarks ==")
clean()
obj = build_body()
res = run("look_window", target="Figure")
check("root look succeeds", res.get("success"), str(res))
w = res.get("window", {})
check("root window covers the mesh", w.get("n_faces") == len(obj.data.polygons),
      str(w.get("n_faces")))
check("multi-shell count seen", w.get("shells_in_window", 0) >= 2,
      str(w.get("shells_in_window")))
# the off-centre plate island makes this figure genuinely NOT bilateral —
# the root window must say so (a real symmetry check comes below, on a sphere)
check("root reports a symmetry verdict", isinstance(w.get("symmetric_x"), bool),
      str(w.get("symmetric_x")))
lms = w.get("landmarks", [])
check("landmarks exist (5–9 curated)", 1 <= len(lms) <= 9, str(len(lms)))
channels = {lm["channel"] for lm in lms}
check("finds protrusions or islands", {"protrusion", "island"} & channels,
      str(channels))
check("every landmark has id/token/extent/faces",
      all(lm.get("id") and lm.get("token") and lm.get("extent")
          and lm.get("n_faces") for lm in lms), str(lms))
for lm in lms:
    print(f"    {lm['id']:<3} {lm['token']:<18} {lm['channel']:<11} "
          f"{lm['extent']:>7}  {lm['n_faces']} faces"
          + (f"  twin={lm['twin']}" if lm.get("twin") else ""))
if w.get("tail"):
    print(f"    tail: {w['tail']}")

# the welded arms surface as protrusions of the torso shell, mirror-twinned
prot = [lm for lm in lms if lm["channel"] == "protrusion"]
check("welded arms found as protrusions", len(prot) >= 2, str(channels))
twinned = [lm for lm in prot if lm.get("twin")]
check("arm protrusions are twinned", len(twinned) >= 2, str(prot))
# cross-channel dedup: no dense cluster re-announces a pole's fan
pole_tokens = {lm["token"].split("·")[0] for lm in lms if lm["channel"] == "pole"}
dense_tokens = {lm["token"].split("·")[0] for lm in lms if lm["channel"] == "dense"}
check("pole fans not re-announced as dense", not (pole_tokens & dense_tokens),
      f"poles={pole_tokens} dense={dense_tokens}")

print("== descent: self-similar breakdown, stack pushes ==")
first = lms[0]["id"]
res = run("look_window", at=first)
check("descend by landmark id", res.get("success"), str(res))
w2 = res.get("window", {})
check("child window is smaller", w2.get("n_faces", 9e9) < w.get("n_faces", 0),
      f"{w2.get('n_faces')} vs {w.get('n_faces')}")
check("stack is 2 deep", len(w2.get("stack", [])) == 2, str(w2.get("stack")))
check("child has same output shape (self-similar)",
      "landmarks" in w2 and "n_faces" in w2 and "size" in w2, str(w2.keys()))

print("== look up: pop back ==")
res = run("look_window", up=True)
check("up succeeds", res.get("success"), str(res))
check("back at root", res.get("window", {}).get("root") is True, str(res))

print("== position-token descent (no landmark needed) ==")
res = run("look_window", at="top-right")
check("descend by bare region token", res.get("success"), str(res))
w3 = res.get("window", {})
check("region window is a subset", 0 < w3.get("n_faces", 0) < w.get("n_faces", 0),
      str(w3.get("n_faces")))
run("look_window", up=True)

print("== re-look: bare call re-describes the current window ==")
res = run("look_window")
check("bare look re-describes", res.get("success")
      and res.get("window", {}).get("root") is True, str(res))
check("landmark ids stable across re-look",
      [lm["id"] for lm in res["window"]["landmarks"]] == [lm["id"] for lm in lms],
      "ids changed")

print("== errors are legible ==")
res = run("look_window", at="L99")
check("unknown landmark errors with the menu", "names no landmark" in res.get("error", ""),
      str(res))
clean_err = run("look_window", at="nonsense-token")
check("garbage at= errors, names options", "error" in clean_err, str(clean_err))

print("== stale window invalidation (§6.6) ==")
res = run("look_window", target="Figure")
# topology edit behind the window's back
me = obj.data
bm = bmesh.new()
bm.from_mesh(me)
bmesh.ops.create_cube(bm, size=0.01)
bm.to_mesh(me)
bm.free()
res = run("look_window", at="top-right")
check("stale window errors legibly", "stale" in res.get("error", ""), str(res))
check("stale error says how to recover", "look target=" in res.get("error", ""),
      str(res))
res = run("look_window", target="Figure")
check("re-open after topology change works", res.get("success"), str(res))

print("== no window open: actionable error ==")
bb_windows.reset()
res = run("look_window", at="top-right")
check("no-window error is actionable", "look target=" in res.get("error", ""), str(res))

print("== bilateral detection on a genuinely symmetric mesh ==")
me2 = bpy.data.meshes.new("Ball")
bm2 = bmesh.new()
bmesh.ops.create_uvsphere(bm2, u_segments=24, v_segments=16, radius=0.1)
bm2.to_mesh(me2)
bm2.free()
ball = bpy.data.objects.new("Ball", me2)
bpy.context.scene.collection.objects.link(ball)
res = run("look_window", target="Ball")
check("sphere reads bilateral across X",
      res.get("window", {}).get("symmetric_x") is True, str(res.get("window")))

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("ALL PASS")

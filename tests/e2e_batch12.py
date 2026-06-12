"""E2E for G1 — extrude_along_curve (sweep the edit-mode face selection along a
curve). Headless.

  G1 — the classic SWEEP. Extrude the current face selection along a curve in one
       call. The curve gives the SHAPE; it's re-rooted to the selection's centroid
       with its start tangent aligned to the selection's `out` normal (F1 frame).
       Frames carried by parallel transport (no candy-wrapping at bends). taper
       shrinks the cross-section per-step in its tangent plane. Guards: closed-band
       selection (no `out`) and self-intersection (bend radius < profile radius) are
       refused with numbers. Reports steps, path length (m), the F1 frame line.

Usage: flatpak run --filesystem=home org.blender.Blender --background \
         --python /abs/path/to/tests/e2e_batch12.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server   # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok    {label}")
    else:
        failures.append(label)
        print(f"  FAIL  {label}  {detail}")


def approx(a, b, tol=0.02):
    return a is not None and b is not None and abs(a - b) <= tol


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def top_face(name):
    """Select the top face of a box in edit mode."""
    run("select_object", name=name)
    run("set_mode", mode="EDIT")
    run("select_all", action="DESELECT")
    return run("select_by_axis", axis="Z", factor=0.9, comparison="GREATER")


def top_face_bounds():
    """Return (max_z, max_abs_x) over the currently-selected verts of the active obj."""
    import bmesh
    obj = bpy.context.active_object
    bm = bmesh.from_edit_mesh(obj.data)
    sel = [v for v in bm.verts if v.select]
    mat = obj.matrix_world
    ws = [mat @ v.co for v in sel]
    return max(w.z for w in ws), max(abs(w.x) for w in ws)


# ───────── G1: straight vertical sweep raises the cap by the path length ─────────
print("== G1: a straight curve sweeps the cap straight up by its length ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)   # top face at z=0.5
run("add_curve", name="path", points=[[0, 0, 0], [0, 0, 1.0]], type="POLY")
top_face("bx")
r = run("extrude_along_curve", curve="path", segments=4)
check("straight sweep succeeded", r.get("success"), repr(r))
check("4 steps placed", r.get("steps") == 4, repr(r))
check("path length ≈ 1.0 m", approx(r.get("path_length"), 1.0), repr(r))
check("frame names straight up", "up" in (r.get("frame") or ""), repr(r.get("frame")))
# the final cap is left selected — its centroid should sit at z ≈ 0.5 + 1.0
maxz, _ = top_face_bounds()
check("final cap reached z ≈ 1.5", approx(maxz, 1.5, tol=0.03), f"maxz={maxz}")
run("set_mode", mode="OBJECT")

# ───────── G1: taper shrinks the cross-section ─────────
print("== G1: taper=0.5 halves the cross-section at the tip ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
run("add_curve", name="path", points=[[0, 0, 0], [0, 0, 1.0]], type="POLY")
top_face("bx")
r = run("extrude_along_curve", curve="path", segments=4, taper=0.5)
check("tapered sweep succeeded", r.get("success"), repr(r))
maxz, maxx = top_face_bounds()
check("tip still reaches z ≈ 1.5", approx(maxz, 1.5, tol=0.03), f"maxz={maxz}")
# top face starts at |x| = 0.5; taper 0.5 → tip half-width ≈ 0.25
check("tip cross-section halved (|x| ≈ 0.25)", approx(maxx, 0.25, tol=0.04), f"maxx={maxx}")
run("set_mode", mode="OBJECT")

# ───────── G1: a gentle curved sweep succeeds and reports its length ─────────
print("== G1: a gentle smooth curve sweeps a thin profile without self-intersecting ==")
clean()
run("add_box", name="bx", width=0.2, depth=0.2, height=0.2)   # thin profile
run("add_curve", name="path",
    points=[[0, 0, 0], [0, 0, 1.0], [0.6, 0, 1.8]], type="BEZIER")
top_face("bx")
r = run("extrude_along_curve", curve="path", segments=12)
check("curved sweep succeeded", r.get("success"), repr(r))
check("12 steps placed", r.get("steps") == 12, repr(r))
check("path length reported (> 1.5 m)", (r.get("path_length") or 0) > 1.5, repr(r))
check("tightest bend radius reported", r.get("min_bend_radius") is not None, repr(r))
run("set_mode", mode="OBJECT")

# ───────── G1: self-intersection guard refuses a too-tight bend ─────────
print("== G1: a sharp bend under a fat profile is refused (self-intersection) ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)   # fat profile (r≈0.7)
run("add_curve", name="path",
    points=[[0, 0, 0], [0, 0, 0.5], [0.5, 0, 0.5]], type="POLY")  # 90° corner
top_face("bx")
r = run("extrude_along_curve", curve="path", segments=8)
check("self-intersecting sweep refused", not r.get("success"), repr(r))
check("error explains the bend/profile clash",
      "bend" in (r.get("error") or "") or "self-intersect" in (r.get("error") or ""),
      repr(r.get("error")))
run("set_mode", mode="OBJECT")

# ───────── G1: a closed surface has no 'out' → refused (F1 message) ─────────
print("== G1: a whole closed cylinder refuses the sweep (normals cancel) ==")
clean()
run("add_cylinder", name="cyl", radius=0.5, height=2.0, vertices=24)
run("add_curve", name="path", points=[[0, 0, 0], [0, 0, 1.0]], type="POLY")
run("select_object", name="cyl")
run("set_mode", mode="EDIT")
run("select_all", action="SELECT")   # every face — normals sum to ~0
r = run("extrude_along_curve", curve="path", segments=4)
check("closed band refused", not r.get("success"), repr(r))
check("refusal cites the cancelled normals", "normals cancel" in (r.get("error") or ""),
      repr(r.get("error")))
run("set_mode", mode="OBJECT")

# ───────── G1: no face selected → refused ─────────
print("== G1: nothing selected → refused with a face hint ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
run("add_curve", name="path", points=[[0, 0, 0], [0, 0, 1.0]], type="POLY")
run("select_object", name="bx")
run("set_mode", mode="EDIT")
run("select_all", action="DESELECT")
r = run("extrude_along_curve", curve="path", segments=4)
check("empty selection refused", not r.get("success"), repr(r))
check("hint mentions FACE", "FACE" in (r.get("error") or "") or "face" in (r.get("error") or ""),
      repr(r.get("error")))
run("set_mode", mode="OBJECT")

# ───────── G1: missing curve → clear error ─────────
print("== G1: a missing curve name errors clearly ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
top_face("bx")
r = run("extrude_along_curve", curve="ghost", segments=4)
check("missing curve refused", not r.get("success"), repr(r))
check("error names the missing curve", "ghost" in (r.get("error") or ""), repr(r.get("error")))
run("set_mode", mode="OBJECT")

# ───────── G1: passing a non-curve object → clear error ─────────
print("== G1: a mesh passed as the curve errors clearly ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
run("add_box", name="notacurve", width=0.5, depth=0.5, height=0.5)
top_face("bx")
r = run("extrude_along_curve", curve="notacurve", segments=4)
check("non-curve refused", not r.get("success"), repr(r))
check("error says it's not a curve", "not a curve" in (r.get("error") or ""),
      repr(r.get("error")))
run("set_mode", mode="OBJECT")

print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL BATCH-12 CHECKS PASSED")

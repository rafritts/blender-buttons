"""E2E for the F-batch gap fixes (F1, F2, F3). Headless.

  F1 — local-frame direction vocabulary on the vertex-moving verbs. extrude /
       move_vertices / proportional_move take METER-based direction words:
       out/inward (along the selection's area-weighted average normal),
       up/down/left/right/forward/back (world axes). Every result names the
       resolved 'out' direction in world-semantic words. Closed bands refuse
       'out'. Legacy x/y/z fraction params still work.
  F2 — closed-loop extrude termination: until_length (stop at a distance) and
       until_contact (raycast, stop at a named object's surface).
  F3 — sculpt_grab direction-word offset, scale_vertices in_plane, bevel width(m).

Usage: flatpak run --filesystem=home org.blender.Blender --background \
         --python /abs/path/to/tests/e2e_batch11.py
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


# ───────── F1: extrude(out=) follows the selection normal ─────────
print("== F1: extrude(out=) extrudes along the area-weighted average normal ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
top_face("bx")
r = run("extrude", out=0.2)
check("extrude(out=) succeeded", r.get("success"), repr(r))
tw = r.get("translation_world") or [None, None, None]
check("out resolved to +Z on the top face", approx(tw[2], 0.2) and approx(tw[0], 0.0) and approx(tw[1], 0.0), repr(tw))
check("frame names the direction (straight up)", "up" in (r.get("frame") or ""), repr(r.get("frame")))
run("set_mode", mode="OBJECT")

# extrude(out=) on a side face → world 'right', level
print("== F1: out names a horizontal direction on a side face ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
run("select_object", name="bx")
run("set_mode", mode="EDIT")
run("select_all", action="DESELECT")
run("select_by_axis", axis="X", factor=0.9, comparison="GREATER")
r = run("extrude", out=0.15)
tw = r.get("translation_world") or [None, None, None]
check("out resolved to +X on the +X face", approx(tw[0], 0.15), repr(tw))
check("frame says 'right'", "right" in (r.get("frame") or ""), repr(r.get("frame")))
run("set_mode", mode="OBJECT")

# composable: out + up in one call
print("== F1: out and a world word compose in one call ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
top_face("bx")
r = run("extrude", out=0.2, right=0.1)
tw = r.get("translation_world") or [None, None, None]
check("composed translation (up 0.2 + right 0.1)", approx(tw[2], 0.2) and approx(tw[0], 0.1), repr(tw))
run("set_mode", mode="OBJECT")

# world-only words report no 'out' frame
print("== F1: pure world words carry no out-frame ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
top_face("bx")
r = run("extrude", up=0.3)
tw = r.get("translation_world") or [None, None, None]
check("world word up=0.3 → +Z 0.3", approx(tw[2], 0.3), repr(tw))
check("no frame for pure world words", r.get("frame") is None, repr(r.get("frame")))
run("set_mode", mode="OBJECT")

# degeneracy guard: a closed side band cancels → refuse 'out'
print("== F1: a closed side band refuses 'out' (normals cancel) ==")
clean()
run("add_cylinder", name="cyl", radius=0.5, height=2.0, vertices=24)
run("select_object", name="cyl")
run("set_mode", mode="EDIT")
run("select_all", action="DESELECT")
run("select_between", axis="Z", lo=0.35, hi=0.65)
r = run("extrude", out=0.1)
check("closed band refuses out", not r.get("success"), repr(r))
check("refusal points at inflate_selection", "inflate_selection" in (r.get("error") or ""), repr(r.get("error")))
run("set_mode", mode="OBJECT")

# ───────── F1: move_vertices(out=) is a rigid translation ─────────
print("== F1: move_vertices(out=) rigidly translates along the normal ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
top_face("bx")
r = run("move_vertices", out=0.1)
check("move_vertices(out=) succeeded", r.get("success"), repr(r))
dw = r.get("delta_world") or [None, None, None]
check("rigid delta +Z 0.1", approx(dw[2], 0.1), repr(dw))
check("frame present", bool(r.get("frame")), repr(r))
check("moved the 4 top verts", r.get("verts_moved") == 4, repr(r))
run("set_mode", mode="OBJECT")

# legacy fraction path still works
print("== F1: legacy move_vertices(z=) fraction path is intact ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=2.0)
top_face("bx")
r = run("move_vertices", z=0.1)  # 0.1 * height(2.0) = 0.2 m
dw = r.get("delta_world") or [None, None, None]
check("legacy z=0.1 → 0.2 m world", approx(dw[2], 0.2), repr(dw))
run("set_mode", mode="OBJECT")

# ───────── F1: proportional_move(out=) ─────────
print("== F1: proportional_move(out=) drags along the normal ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
top_face("bx")
r = run("proportional_move", out=0.05, radius=0.3)
check("proportional_move(out=) succeeded", r.get("success"), repr(r))
dw = r.get("delta_world") or [None, None, None]
check("delta +Z 0.05", approx(dw[2], 0.05), repr(dw))
check("frame present", bool(r.get("frame")), repr(r))
run("set_mode", mode="OBJECT")

# ───────── F2: until_length ─────────
print("== F2: extrude(until_length=) stops at a fixed distance ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
top_face("bx")
r = run("extrude", until_length=0.4)  # direction defaults to out (=up here)
check("until_length succeeded", r.get("success"), repr(r))
check("distance ≈ 0.4 m", approx(r.get("distance_world"), 0.4), repr(r))
tw = r.get("translation_world") or [0, 0, 0]
check("translated up by 0.4", approx(tw[2], 0.4), repr(tw))
check("terminated_at names length", "length" in (r.get("terminated_at") or ""), repr(r))
run("set_mode", mode="OBJECT")

# ───────── F2: until_contact ─────────
print("== F2: extrude(until_contact=) stops at a named object's surface ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)   # top at z=0.5
run("add_plane", name="lid", width=3.0, depth=3.0)
run("nudge", targets=["lid"], up=1.5)                          # lid at z=1.5
top_face("bx")
r = run("extrude", up=1.0, until_contact="lid")
check("until_contact succeeded", r.get("success"), repr(r))
check("stopped ≈ 1.0 m below the lid", approx(r.get("distance_world"), 1.0, tol=0.03), repr(r))
check("terminated_at names the object", "lid" in (r.get("terminated_at") or ""), repr(r))
run("set_mode", mode="OBJECT")

print("== F2: until_contact on a missing object errors clearly ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
top_face("bx")
r = run("extrude", out=0.0, until_contact="ghost")
check("missing contact target errors", not r.get("success"), repr(r))
run("set_mode", mode="OBJECT")

# ───────── F3: bevel width in meters ─────────
print("== F3: bevel(width=) is an absolute offset in meters ==")
clean()
run("add_box", name="bx", width=2.0, depth=2.0, height=2.0)
run("select_object", name="bx")
run("set_mode", mode="EDIT")
run("select_all", action="SELECT")
r = run("bevel", width=0.1, segments=2)
check("bevel(width=) succeeded", r.get("success"), repr(r))
check("offset_world ≈ 0.1 m", approx(r.get("offset_world"), 0.1), repr(r))
run("set_mode", mode="OBJECT")

# ───────── F3: scale_vertices in_plane ─────────
print("== F3: scale_vertices(in_plane=) scales within the tangent plane ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=1.0)
top_face("bx")
r = run("scale_vertices", in_plane=2.0)
check("scale_vertices(in_plane=) succeeded", r.get("success"), repr(r))
check("scaled the 4 top verts", r.get("verts_scaled") == 4, repr(r))
check("frame names the in-plane orientation", "in-plane" in (r.get("frame") or ""), repr(r.get("frame")))
# verify the top face actually widened in XY (verts moved from ±0.5 to ±1.0)
import bmesh as _bmesh  # noqa: E402
run("select_object", name="bx")
run("set_mode", mode="EDIT")
run("select_by_axis", axis="Z", factor=0.9, comparison="GREATER")
_bm = _bmesh.from_edit_mesh(bpy.data.objects["bx"].data)
maxx = max(v.co.x for v in _bm.verts if v.select)
check("top face widened to x≈1.0", approx(maxx, 1.0, tol=0.05), f"maxx={maxx}")
run("set_mode", mode="OBJECT")

# ───────── F3: sculpt_grab direction words ─────────
print("== F3: sculpt_grab(out=) pushes the brushed region along its normal ==")
clean()
run("add_sphere", name="ball", radius=0.5, segments=32, rings=16)
r = run("sculpt_grab", target="ball", at=[0.0, 0.0, 0.5], radius=0.35, out=0.1,
        subdivide=True)
check("sculpt_grab(out=) succeeded", r.get("success"), repr(r))
ow = r.get("offset_world") or [None, None, None]
check("offset is mostly +Z at the pole", ow[2] is not None and ow[2] > 0.05, repr(ow))
check("frame present", bool(r.get("frame")), repr(r))

print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL BATCH-11 CHECKS PASSED")

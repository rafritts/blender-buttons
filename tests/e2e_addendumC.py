"""E2E for SPEC-05 Addendum C fixes #1, #2, #4 (engine side). Headless.

  #1 — select_object from a non-Object mode auto-switches to Object Mode and
       reports it via the `notes` channel (no more raw poll() failure).
  #2 — get_topology with an unknown method returns a self-correcting error that
       lists the valid method tokens.
  #4 — select_by_axis(extend=True) UNIONS onto the current selection instead of
       replacing it, so two calls can grab two regions before one delete.

Usage: flatpak run --filesystem=home org.blender.Blender --background \
         --python /path/to/blender-buttons/tests/e2e_addendumC.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


# ───────── #1: select_object auto-switches out of POSE ─────────
print("== #1: select_object from POSE auto-switches to OBJECT + notes ==")
clean()
run("add_box", name="cube", width=1, depth=1, height=1)
# an armature to enter pose mode on
arm = bpy.data.armatures.new("arm")
arm_obj = bpy.data.objects.new("rig", arm)
bpy.context.scene.collection.objects.link(arm_obj)
bpy.context.view_layer.objects.active = arm_obj
arm_obj.select_set(True)
bpy.ops.object.mode_set(mode='POSE')
check("in POSE mode before", bpy.context.mode == 'POSE', bpy.context.mode)

res = run("select_object", name="cube")
check("select_object succeeded from POSE", res.get("success") is True, repr(res))
check("now in OBJECT mode", bpy.context.mode == 'OBJECT', bpy.context.mode)
check("cube is active", bpy.context.active_object.name == "cube",
      repr(bpy.context.active_object))
check("notes report the auto-switch",
      any("OBJECT" in n for n in (res.get("notes") or [])), repr(res.get("notes")))

# from OBJECT mode there should be NO note (no switch needed)
res2 = run("select_object", name="rig")
check("no spurious note when already in OBJECT", not res2.get("notes"), repr(res2.get("notes")))

# ───────── #2: unknown topology method is self-correcting ─────────
print("== #2: get_topology unknown method lists valid tokens ==")
clean()
run("add_box", name="b", width=1, depth=1, height=1)
run("select_object", name="b")
res = run("get_topology", target="b", method=["openings"])  # 'openings' is NOT a token
err = res["topology"]["openings"]["error"]
check("error names the bad method", "openings" in err, err)
check("error lists 'boundaries' (the real token)", "boundaries" in err, err)
check("error lists 'sections'", "sections" in err, err)

# ───────── #4: select_by_axis extend unions two regions ─────────
print("== #4: select_by_axis(extend=True) unions onto the selection ==")
clean()
run("add_box", name="bar", width=4.0, depth=1.0, height=1.0)  # long along X
run("select_object", name="bar")
run("set_mode", mode="EDIT")
run("select_all", action="DESELECT")
r_right = run("select_by_axis", axis="X", factor=0.8, comparison="GREATER")  # right end
right_n = r_right["selected_count"]
check("right end selected some verts", right_n > 0, repr(right_n))
# WITHOUT extend: second call replaces → count == left-end only
r_repl = run("select_by_axis", axis="X", factor=0.2, comparison="LESS")
check("without extend, selection is replaced (not summed)",
      r_repl["selected_count"] == right_n, f"{r_repl['selected_count']} vs {right_n}")
# WITH extend: re-add the right end on top of the left
r_ext = run("select_by_axis", axis="X", factor=0.8, comparison="GREATER", extend=True)
check("with extend, both ends are selected (summed)",
      r_ext["selected_count"] == right_n * 2, f"{r_ext['selected_count']} vs {right_n*2}")
run("set_mode", mode="OBJECT")

print()
if failures:
    print(f"FAILURES ({len(failures)}): " + ", ".join(failures))
    sys.exit(1)
print("ALL ADDENDUM-C CHECKS PASSED")

"""G17 focused test: snap_loop registers a real undo step (the moved verts restore).

Usage: flatpak run --filesystem=home org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_g17.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import state  # noqa: E402

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
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    state.reset_history_state()


def vert_zs(name):
    o = bpy.data.objects[name]
    return [round((o.matrix_world @ v.co).z, 5) for v in o.data.vertices]


print("== G17: snap_loop undo round-trip ==")
clean()
# Two open tubes; B sits above A. Mint boundary handles, then snap A's top rim onto B.
run("add_cylinder", name="tubeA", radius=0.2, height=0.4, cap_fill="NOTHING")
run("add_cylinder", name="tubeB", radius=0.3, height=0.4, cap_fill="NOTHING")
run("move_to", targets="tubeB", to_z=1.5)
asm = run("feel_assembly", targets="tubeA,tubeB")
b_handles = [b["handle"] for o in asm["objects"] if o["name"] == "tubeB"
             for b in o.get("boundaries", [])]
check("tubeB has a boundary handle to target", len(b_handles) >= 1, str(asm))

before = sorted(vert_zs("tubeA"))
# Enter edit on tubeA, select a boundary loop (live selection), snap onto B's rim.
run("set_mode", mode="EDIT", target="tubeA")
run("select_boundary")  # selects open boundary verts of the active edit mesh
snap = run("snap_loop", handle=b_handles[0], fit_scale=True)
check("snap_loop succeeds", snap.get("success") is True, str(snap))
check("snap_loop returned to OBJECT mode", bpy.context.active_object.mode == "OBJECT",
      bpy.context.active_object.mode)
after = sorted(vert_zs("tubeA"))
check("snap_loop actually moved verts", before != after, "verts unchanged")

# The fix: undoing the snap restores the moved verts.
u = run("undo_steps", steps=1)
restored = sorted(vert_zs("tubeA"))
check("undo reports success", u.get("success") is True, str(u))
check("verts restored to pre-snap positions after undo", restored == before,
      f"max delta {max((abs(a-b) for a,b in zip(restored, before)), default=0)}")

print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("G17 UNDO ROUND-TRIP PASSED")

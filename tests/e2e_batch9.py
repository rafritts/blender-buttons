"""E2E for batch-9 gap fixes (X-series live regressions). Headless.

Covers the headless-reproducible parts:
  X1  — handle_client never serializes None on timeout (socket-level test).
  X3A — selectors flush vert selection up to edge/face domains (no stale higher sel).
  X4  — a VALID reconstruct bind shadows a position-only rest-shape edit; a DEAD one
        (vert-count mismatch) does not.
  X5  — modify_modifier drives factor / strength / show_viewport.
  X6  — eval-dirty bookkeeping (mark/flush) + eval_world_bbox stays correct.

X2 (frame_scene POSE) and the live depsgraph-wedge symptom of X6 need a real 3D
viewport / a real orphaned op and are verified by reasoning, not here.

Usage: flatpak run --filesystem=home org.blender.Blender --background \
         --python /abs/path/to/tests/e2e_batch9.py
"""
import os
import sys
import json
import socket
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state as bb_state     # noqa: E402

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


def bound_cloth():
    clean()
    run("add_sphere", name="cloth", radius=1.0, segments=24, rings=16)
    run("add_box", name="cage", width=2.6, depth=2.6, height=2.6)
    run("select_object", name="cloth")
    r = run("bind_mesh_deform", mesh="cloth", cage="cage")
    assert r.get("bound") is True, f"setup bind failed: {r}"
    return r


# ───────── X1: timeout never serializes None ─────────
print("== X1: handle_client returns an honest error on timeout, never null ==")
bb_state._eval_dirty = set()
# Drain any stale queue items first.
try:
    while True:
        bb_state._request_queue.get_nowait()
except Exception:
    pass

a, b = socket.socketpair()
cmd = json.dumps({"tool": "add_box", "params": {"name": "orphan_obj"}, "timeout": 1}) + "\n"
t = threading.Thread(target=bb_server.handle_client, args=(b,))
t.start()
a.sendall(cmd.encode())
# The queued on_main_thread is never drained (no main-loop timer here) → the wait
# times out exactly as a too-slow bind would live.
data = b""
while b"\n" not in data:
    chunk = a.recv(4096)
    if not chunk:
        break
    data += chunk
t.join(timeout=5)
a.close()
resp = json.loads(data.decode().strip()) if data.strip() else None
check("timeout response is a dict, NOT null", isinstance(resp, dict), repr(resp))
check("timeout response carries an error", isinstance(resp, dict) and "error" in resp, repr(resp))
check("error says the op was not cancelled", isinstance(resp, dict)
      and "NOT" in resp.get("error", "") and "get_history" in resp.get("error", ""), repr(resp))
check("touched object marked eval-dirty (X6 hand-off)", "orphan_obj" in bb_state._eval_dirty)
# Clean up the orphaned queue item so it can't run later.
try:
    while True:
        bb_state._request_queue.get_nowait()
except Exception:
    pass
bb_state._eval_dirty = set()


# ───────── X6: eval-dirty bookkeeping + eval bbox correctness ─────────
print("== X6: mark/flush eval-dirty, eval_world_bbox stays truthful ==")
from extension.common import eval_world_bbox  # noqa: E402
clean()
run("add_box", name="probe", width=1, depth=1, height=2)
bb_state.mark_eval_dirty("probe")
check("mark_eval_dirty records the object", "probe" in bb_state._eval_dirty)
bb_state.flush_eval_dirty()
check("flush clears the dirty set", len(bb_state._eval_dirty) == 0)
# The forced-fresh evaluated read returns sane bounds (a 2-tall box reads ~2.0).
ebb = eval_world_bbox(bpy.data.objects["probe"])
check("eval_world_bbox returns sane bounds after forced retag", abs((ebb[5] - ebb[2]) - 2.0) < 0.01, str(ebb))


# ───────── X3A: selection flush ─────────
print("== X3A: select_by_axis flushes to edge/face domains in EDGE mode ==")
clean()
run("add_box", name="grid", width=2, depth=2, height=2)
run("select_object", name="grid")
# Subdivide so there are interior loops to (de)select.
run("set_mode", mode="EDIT")
run("set_component_mode", mode="EDGE")
run("select_all", action="SELECT")  # everything selected: the trap state
me = bpy.data.objects["grid"].data
# Now select only the top-half verts by axis; previously all edges/faces stayed lit.
run("select_by_axis", axis="Z", factor=0.5, comparison="GREATER")
bm = bmesh.from_edit_mesh(me)
sel_v = sum(1 for v in bm.verts if v.select)
sel_e = sum(1 for e in bm.edges if e.select)
sel_f = sum(1 for f in bm.faces if f.select)
tot_e, tot_f = len(bm.edges), len(bm.faces)
check("some verts selected", sel_v > 0, f"{sel_v}")
check("NOT all edges still selected (flush worked)", sel_e < tot_e, f"{sel_e}/{tot_e}")
check("NOT all faces still selected (no whole-mesh extrude)", sel_f < tot_f, f"{sel_f}/{tot_f}")
# Every selected edge must have both verts selected (selection is authoritative).
bad_edges = [e for e in bm.edges if e.select and not all(v.select for v in e.verts)]
check("every selected edge is fully within the vert selection", len(bad_edges) == 0, f"{len(bad_edges)}")
run("set_mode", mode="OBJECT")


# ───────── X4: valid bind shadows a rest-shape edit; dead bind does not ─────────
def manual_position_edit(name):
    """A position-only edit via the manual path; returns the set_mode(OBJECT) result."""
    run("select_object", name=name)
    run("set_mode", mode="EDIT")
    run("select_all", action="SELECT")
    run("move_vertices", direction=[0, 0, 0.02])
    return run("set_mode", mode="OBJECT")


def manual_topology_edit(name):
    run("select_object", name=name)
    run("set_mode", mode="EDIT")
    run("select_by_axis", axis="Z", factor=0.5, comparison="GREATER")
    run("delete_geometry")
    return run("set_mode", mode="OBJECT")


print("== X4: VALID bind shadows a position-only edit ==")
bound_cloth()
r = manual_position_edit("cloth")
check("valid bind → bind_shadowed flag", r.get("bind_shadowed") is True, str(r))
check("shadow warning points at rebind_deform", "rebind_deform" in (r.get("bind_warning") or ""), str(r))
check("shadow warning is NOT the topology one", "VERTEX COUNT" not in (r.get("bind_warning") or "").upper())

print("== X4: a DEAD bind (vert-count mismatch) does NOT shadow ==")
r = manual_topology_edit("cloth")  # kills the bind (count changes)
check("topology edit → bind_invalidated", r.get("bind_invalidated") is True, str(r))
r = manual_position_edit("cloth")  # bind now dead → edit shows 1:1, must stay silent
check("dead bind → NO shadow warning (edit is real)", r.get("bind_shadowed") is None, str(r))
check("dead bind → NO invalidated warning (count unchanged)", r.get("bind_invalidated") is None, str(r))

print("== X4: rebind restores validity → shadow warns again ==")
r = run("rebind_deform", mesh="cloth")
check("rebind success", r.get("success") is True, str(r))
r = manual_position_edit("cloth")
check("revalidated bind → bind_shadowed again", r.get("bind_shadowed") is True, str(r))

print("== X4: an unbound mesh never shadows ==")
clean()
run("add_sphere", name="plain", radius=1.0, segments=16, rings=12)
r = manual_position_edit("plain")
check("unbound mesh → no shadow warning", r.get("bind_shadowed") is None, str(r))


# ───────── X5: modify_modifier factor / strength / show toggles ─────────
print("== X5: modify_modifier neutralize-a-modifier knobs ==")
clean()
run("add_sphere", name="cs", radius=1.0, segments=16, rings=12)
run("select_object", name="cs")
run("add_modifier", type="CORRECTIVE_SMOOTH", name="CS")
r = run("modify_modifier", target="cs", modifier_name="CS", factor=0.25)
csmod = bpy.data.objects["cs"].modifiers["CS"]
check("factor applied to CORRECTIVE_SMOOTH", abs(csmod.factor - 0.25) < 1e-4, str(r))
r = run("modify_modifier", target="cs", modifier_name="CS", show_viewport=False)
check("show_viewport toggled off", csmod.show_viewport is False, str(r))
check("modify reports the toggle applied", any("show_viewport" in a for a in r.get("applied", [])), str(r))
r = run("modify_modifier", target="cs", modifier_name="CS", show_viewport=True)
check("show_viewport toggled back on", csmod.show_viewport is True, str(r))

run("add_modifier", type="DISPLACE", name="Disp")
r = run("modify_modifier", target="cs", modifier_name="Disp", strength=0.7)
dispmod = bpy.data.objects["cs"].modifiers["Disp"]
check("strength applied to DISPLACE", abs(dispmod.strength - 0.7) < 1e-4, str(r))


print()
if failures:
    print(f"BATCH9 E2E: {len(failures)} FAILED → {failures}")
    sys.exit(1)
else:
    print("BATCH9 E2E: ALL TESTS PASSED")

"""E2E for the generic addon/operator bridge (extension/addons.py). Headless.

Exercises addon_list / addon_inspect / addon_run against BUILT-IN operators (factory
startup has no third-party addons, but the mechanism is identical), and checks the
read/mutate categorization.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_addon_driver.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402
from extension import addons                 # noqa: E402

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FAIL '} {label}" + ("" if cond else f"   {detail}"))
    if not cond:
        failures.append(label)


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    state.reset_history_state()


def make_cube(name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


# ── 0. registration + categorization ─────────────────────────────────────────
print("[0] registration & categorization")
for t in ("addon_list", "addon_inspect", "addon_run"):
    check(f"{t} registered in TOOLS", t in bb_server.TOOLS)
check("addon_list is read-only (NON_UNDOABLE)", "addon_list" in state.NON_UNDOABLE_TOOLS)
check("addon_inspect is read-only (NON_UNDOABLE)", "addon_inspect" in state.NON_UNDOABLE_TOOLS)
check("addon_list suppresses status", "addon_list" in state.NO_STATUS_TOOLS)
check("addon_run is a MUTATOR (not non-undoable)", "addon_run" not in state.NON_UNDOABLE_TOOLS)
check("addon_run is NOT lock-exempt", "addon_run" not in bb_server.LOCK_EXEMPT_TOOLS)

# ── 1. list ───────────────────────────────────────────────────────────────────
print("[1] addon_list")
r = addons.addon_list({})
check("list ok", r.get("success") and "addons" in r, str(r)[:120])
check("list filter is a substring match", addons.addon_list({"filter": "zzz-nomatch"})["count"] == 0)

# ── 2. inspect a namespace, then an operator ─────────────────────────────────
print("[2] addon_inspect")
r = addons.addon_inspect({"operator": "object"})
check("namespace lists operators", r.get("success") and any(
    o == "object.select_all" for o in r.get("operators", [])), str(r.get("count")))
r = addons.addon_inspect({"operator": "object.select_all"})
check("operator inspect ok", r.get("success"))
action = next((p for p in r.get("params", []) if p["name"] == "action"), None)
check("select_all exposes 'action' enum", action is not None and action["type"] == "ENUM")
check("enum lists SELECT/DESELECT", action and {"SELECT", "DESELECT"} <= set(action.get("values", [])),
      str(action))
check("bad operator → clean error", "error" in addons.addon_inspect({"operator": "nope.nothere"}))
check("empty operator → clean error", "error" in addons.addon_inspect({"operator": ""}))

# ── 3. run a real built-in operator ──────────────────────────────────────────
print("[3] addon_run")
clean()
a, b = make_cube("A"), make_cube("B")
for o in (a, b):
    o.select_set(True)
r = addons.addon_run({"operator": "object.select_all", "args": {"action": "DESELECT"}})
check("run FINISHED", r.get("success") and "FINISHED" in r.get("result", []), str(r))
check("operator actually deselected", not a.select_get() and not b.select_get())

# select via the driver
r = addons.addon_run({"operator": "object.select_all", "args": {"action": "SELECT"}})
check("re-select FINISHED", r.get("success"))
check("operator actually selected", a.select_get() and b.select_get())

# ── 4. error surfaces ────────────────────────────────────────────────────────
print("[4] error handling")
check("missing dot → clean error", "error" in addons.addon_run({"operator": "selectall"}))
check("unknown operator → clean error", "error" in addons.addon_run({"operator": "object.does_not_exist"}))
r = addons.addon_run({"operator": "object.select_all", "args": {"bogus_arg": 1}})
check("bad arg → clean TypeError-derived error", "error" in r and "inspect" in r["error"], str(r)[:160])
check("bad exec_context → clean error", "error" in addons.addon_run(
    {"operator": "object.select_all", "exec_context": "WUT"}))

# ── 5. end-to-end through the dispatch spine (status + op_id on a mutator) ────
print("[5] via execute_command dispatch")
clean(); make_cube("C")
out = bb_server.execute_command({"tool": "addon_run",
                                 "params": {"operator": "object.select_all", "args": {"action": "SELECT"}}})
check("dispatch returns success", out.get("success"), str(out)[:160])
check("mutator got an op_id", bool(out.get("op_id")))
check("mutator carries blender_status", "blender_status" in out)
# a read op should NOT carry a status block
out2 = bb_server.execute_command({"tool": "addon_list", "params": {}})
check("read op suppresses status", "blender_status" not in out2)

print()
if failures:
    print(f"e2e_addon_driver :: FAILED — {len(failures)} failure(s): {failures}")
    sys.exit(1)
print("e2e_addon_driver :: PASSED — 0 failure(s)")

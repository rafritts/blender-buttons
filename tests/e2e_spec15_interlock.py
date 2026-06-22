"""E2E for SPEC-15 — the external-mutation interlock (the dirty-world lock).

Runs the WORKING-TREE extension headless. The interlock is enforced at the socket
boundary (server.handle_client); the detection / lock-error / acknowledge logic it
calls lives in `state`, and the allowlist of tools that survive a lock is
`server.LOCK_EXEMPT_TOOLS`. This test exercises that logic directly (no socket).

Covers:
  1. A logged op sets a clean baseline; with no external change, detect does NOT latch.
  2. A direct (non-server) bpy mutation between calls IS detected — the lock latches
     and names what changed (object + kind).
  3. The allowlist: world-mutating tools are blocked; reads / selection / feel / render /
     acknowledge stay exempt.
  4. lock_error names the tool + the mutated object + how to clear it.
  5. detect is a no-op before any op (no baseline) and idempotent once locked.
  6. acknowledge clears the lock and re-baselines; a fresh detect stays clean; ack on an
     already-clean world is an honest no-op.

Usage: flatpak run org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_spec15_interlock.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import state  # noqa: E402

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
    state.reset_history_state()  # drop baseline + any latched lock for a clean start


# ───────────────── 5a. no baseline before any op ─────────────────
print("== SPEC-15: detect is a no-op before the first op ==")
clean()
state.detect_external_mutation()
check("no baseline: detect does not latch", not state._world_locked)
check("no baseline: scene hash is None", state._scene_hash is None)

# ───────────────── 1. logged op sets baseline; clean scene stays unlocked ─────────────────
print("== SPEC-15: a logged op sets the clean baseline ==")
r = run("add_box", name="Lockbox", width=1.0, depth=1.0, height=1.0)
check("add_box success", r.get("success"), r.get("error"))
check("baseline hash set after a logged op", state._scene_hash is not None)
state.detect_external_mutation()
check("clean scene: detect does not latch", not state._world_locked)

# ───────────────── 2. direct bpy mutation is detected ─────────────────
print("== SPEC-15: an external (direct-bpy) mutation latches the lock ==")
box = bpy.data.objects["Lockbox"]
box.location.x += 0.5  # the user nudging it in the Blender UI
state.detect_external_mutation()
check("external move: lock latched", state._world_locked)
info = state._lock_info or {}
moved = [c for c in info.get("changed", []) if c["object"] == "Lockbox"]
check("lock names the moved object", bool(moved), f"info={info}")
check("lock records a 'moved' change",
      bool(moved) and any("moved" in k for k in moved[0]["kinds"]),
      f"kinds={moved[0]['kinds'] if moved else None}")

# ───────────────── 5b. re-detect while locked: latched, but report refreshes ─────────────────
prev = state._lock_info
state.detect_external_mutation()
check("re-detect keeps the lock latched (only acknowledge clears it)", state._world_locked)
check("re-detect refreshes the report (recomputed) and still names the move",
      state._lock_info is not prev
      and any(c["object"] == "Lockbox" for c in (state._lock_info or {}).get("changed", [])),
      f"info={state._lock_info}")

# ───────────────── 3. the allowlist ─────────────────
print("== SPEC-15: the lock allowlist (blocked vs exempt) ==")
ex = bb_server.LOCK_EXEMPT_TOOLS
check("add_box is BLOCKED while locked", "add_box" not in ex)
check("extrude is BLOCKED while locked", "extrude" not in ex)
check("boolean is BLOCKED while locked", "boolean" not in ex)
check("read 'describe' is exempt", "describe" in ex)
check("read 'get_topology' is exempt", "get_topology" in ex)
check("selection 'select_by_axis' is exempt", "select_by_axis" in ex)
check("selection 'select_ring' is exempt", "select_ring" in ex)
check("feel 'verify_selection' is exempt", "verify_selection" in ex)
check("render 'render_to_file' is exempt", "render_to_file" in ex)
check("'acknowledge_mutation' is exempt", "acknowledge_mutation" in ex)

# ───────────────── 4. lock_error content ─────────────────
print("== SPEC-15: the block error is actionable ==")
err = state.lock_error("add_box")
check("lock_error flags world_locked", err.get("world_locked") is True)
msg = err.get("error", "")
check("lock_error names the blocked tool", "add_box" in msg)
check("lock_error names the mutated object", "Lockbox" in msg)
check("lock_error tells how to clear it", "acknowledge" in msg.lower())

# ───────────────── 6. acknowledge clears + re-baselines ─────────────────
print("== SPEC-15: acknowledge clears the lock and re-grounds ==")
ack = state.acknowledge_mutation()
check("acknowledge reports success", ack.get("success"))
check("acknowledge reports acknowledged=True", ack.get("acknowledged") is True)
check("lock cleared after ack", not state._world_locked)
check("lock_info cleared after ack", state._lock_info is None)
state.detect_external_mutation()
check("post-ack clean: no re-latch (baseline re-grounded to live)", not state._world_locked)

ack2 = state.acknowledge_mutation()
check("ack on an already-clean world: honest no-op (acknowledged=False)",
      ack2.get("success") and ack2.get("acknowledged") is False)

# ───────────────── 7. edit-mode change is visible (the in-session gap) ─────────────────
# An external edit made while the object is STILL in Edit Mode lives in a separate bmesh
# that doesn't flush to me.vertices until the session ends — so a base-mesh-only read
# would miss it. The signature must read the live bmesh in Edit Mode.
print("== SPEC-15: a change made while still in Edit Mode is detected ==")
clean()
run("add_box", name="EditBox", width=1.0, depth=1.0, height=1.0)  # baseline: 8 verts, OBJECT mode
state.detect_external_mutation()
check("edit-test: clean after add", not state._world_locked)

eb = bpy.data.objects["EditBox"]
bpy.context.view_layer.objects.active = eb
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(eb.data)
bm.verts.ensure_lookup_table()
base_vcount = len(eb.data.vertices)
bm.verts.new((2.0, 2.0, 2.0))            # add geometry — STAY in edit mode (no mode_set back)
bmesh.update_edit_mesh(eb.data)
sig = state._object_signature(eb)
check("edit-mode signature reads the LIVE bmesh vcount", sig.get("vcount") == len(bm.verts),
      f"sig.vcount={sig.get('vcount')} bmesh={len(bm.verts)} base={base_vcount}")
state.detect_external_mutation()
check("edit-mode topology change latches the lock", state._world_locked,
      f"info={state._lock_info}")
bpy.ops.object.mode_set(mode='OBJECT')

# ───────────────── 8. the report is CUMULATIVE, not frozen at the first trip ─────────────────
# The lock latches on the first divergence but RECOMPUTES the full diff every call, so it
# always reflects everything currently different from the baseline — including changes made
# AFTER the trip (e.g. an object deleted later must not still be reported as present).
print("== SPEC-15: the lock report is the full current diff, recomputed ==")
clean()
run("add_box", name="Alpha", width=1.0, depth=1.0, height=1.0)
run("add_box", name="Beta", width=1.0, depth=1.0, height=1.0)  # baseline: {Alpha, Beta}
state.detect_external_mutation()
check("cumulative: clean after the two adds", not state._world_locked)

bpy.data.objects["Alpha"].location.x += 0.5          # 1st external change → trips the lock
state.detect_external_mutation()
info1 = state._lock_info or {}
check("cumulative: lock trips on Alpha move",
      state._world_locked and any(c["object"] == "Alpha" for c in info1.get("changed", [])),
      f"info={info1}")
check("cumulative: 'since' names the baseline op (add_box), not a stale point",
      info1.get("since_label") == "add_box", f"since_label={info1.get('since_label')}")

bpy.data.objects.remove(bpy.data.objects["Beta"], do_unlink=True)  # 2nd change, AFTER the trip
state.detect_external_mutation()
info2 = state._lock_info or {}
moved_alpha = any(c["object"] == "Alpha" for c in info2.get("changed", []))
removed_beta = "Beta" in info2.get("removed", [])
check("cumulative: report now includes BOTH (Alpha moved + Beta removed)",
      moved_alpha and removed_beta, f"info={info2}")

# Frozen baseline: an exempt op that logs (selection) must NOT re-baseline while locked,
# or the diff above would collapse to empty.
run("select_all", action="SELECT", target="Alpha")
state.detect_external_mutation()
info3 = state._lock_info or {}
check("frozen baseline: diff survives an exempt logging op while locked",
      any(c["object"] == "Alpha" for c in info3.get("changed", []))
      and "Beta" in info3.get("removed", []), f"info={info3}")

# Acknowledge re-grounds and stamps an honest 'since' for any future trip.
state.acknowledge_mutation()
check("post-ack: lock cleared", not state._world_locked)
bpy.data.objects["Alpha"].location.x += 0.5
state.detect_external_mutation()
check("post-ack: a new trip says 'since your acknowledgement'",
      (state._lock_info or {}).get("since_label") == "your acknowledgement",
      f"since_label={(state._lock_info or {}).get('since_label')}")
state.acknowledge_mutation()

# ───────────────── summary ─────────────────
print()
if failures:
    print(f"SPEC-15: {len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("SPEC-15: all checks passed.")
sys.exit(0)

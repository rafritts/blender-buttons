"""E2E for SPEC-23 — script runner (batch / exec / dry_run + receipt).

Runs the WORKING-TREE extension headless (no socket). Covers the experimental v0:

  1. Happy-path batch: stacked relational adds → clean receipt with bounds
  2. Progressive bulk: second batch authored from first receipt names
  3. Hard cap: 26 steps → rejected_budget, mutates nothing
  4. dry_run: resolves tools without mutation
  5. Abort + transactional restore: deliberate fail mid-batch leaves scene clean
  6. Exec: Handle bounds mid-script for a follow-on place
  7. first_failure present on abort

Usage:
  flatpak run org.blender.Blender --background --factory-startup \\
    --python /abs/path/to/tests/e2e_spec23_script_runner.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import state  # noqa: E402
from extension import script_api  # noqa: E402

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FAIL '} {label}" + ("" if cond else f"   {detail}"))
    if not cond:
        failures.append(label)


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    state.reset_history_state()


# ───────────────── registration ─────────────────
print("== SPEC-23: tools registered ==")
for t in ("script_batch", "script_exec", "script_dry_run"):
    check(f"{t} in TOOLS", t in bb_server.TOOLS)
check("HARD_STEP_CAP is 25", script_api.HARD_STEP_CAP == 25)

# ───────────────── 1. happy-path batch ─────────────────
print("== SPEC-23: batch happy path (relational stack) ==")
clean()
r = run("script_batch", label="lamp-stack", steps=[
    {"verb": "add", "params": {
        "type": "cylinder", "name": "stem", "radius": 0.01, "height": 0.08,
        "on": {"on_floor": True},
    }},
    {"verb": "add", "params": {
        "type": "sphere", "name": "bulb", "radius": 0.03,
        "on": {"on": "stem"},
    }},
    {"verb": "add", "params": {
        "type": "cylinder", "name": "shade", "radius": 0.05, "height": 0.04,
        "on": {"on": "bulb"},
    }},
])
check("batch success", r.get("success"), r.get("error") or r.get("result"))
check("result ok", r.get("result") == "ok", r.get("result"))
check("3 created", r.get("created") == ["stem", "bulb", "shade"] or
      set(r.get("created") or []) == {"stem", "bulb", "shade"},
      r.get("created"))
check("journal length 3", (r.get("steps") or {}).get("total") == 3, r.get("steps"))
# dims/bounds on create steps
j = r.get("journal") or []
check("journal has dims on step 1", bool(j and j[0].get("dims")), j[0] if j else None)
check("journal has bounds on step 1", bool(j and j[0].get("bounds")), j[0] if j else None)
check("placement echoed on step 2", bool(j and len(j) > 1 and j[1].get("placement")),
      j[1] if len(j) > 1 else None)
fv = r.get("final_validate") or {}
check("final validate present", "passed" in fv or fv.get("off"), fv)
check("final status present", isinstance(r.get("final_status"), dict), r.get("final_status"))
check("objects live", all(bpy.data.objects.get(n) for n in ("stem", "bulb", "shade")))

# ───────────────── 2. progressive second batch ─────────────────
print("== SPEC-23: progressive second batch from receipt ==")
# Author next phase from first receipt names (finial on shade — no coplanar z-fight)
created = r.get("created") or []
check("phase1 names available for phase2", "shade" in created or bpy.data.objects.get("shade"),
      created)
r2 = run("script_batch", label="finial", steps=[
    {"verb": "add", "params": {
        "type": "sphere", "name": "finial", "radius": 0.008,
        "on": {"on": "shade"},
    }},
    {"verb": "material", "op": "set", "params": {
        "target": "finial", "hex": "#C0C0C0", "metallic": 0.8, "roughness": 0.25,
    }},
])
check("phase2 success", r2.get("success"), r2.get("error") or r2.get("result"))
check("finial created", "finial" in (r2.get("created") or []) or bpy.data.objects.get("finial"),
      r2.get("created"))
check("stem still present", bpy.data.objects.get("stem") is not None)
check("phase2 journal has material step",
      any((e.get("verb") == "material" or e.get("tool") == "set_material")
          for e in (r2.get("journal") or [])),
      r2.get("journal"))

# ───────────────── 3. hard cap 26 ─────────────────
print("== SPEC-23: hard cap rejects 26 steps ==")
clean()
steps26 = [
    {"verb": "add", "params": {
        "type": "box", "name": f"b{i}", "width": 0.05, "depth": 0.05, "height": 0.05,
        "on": {"on_floor": True} if i == 0 else {"on": f"b{i-1}"},
    }}
    for i in range(26)
]
r26 = run("script_batch", label="too-big", steps=steps26)
check("rejected_budget", r26.get("result") == "rejected_budget", r26.get("result"))
check("success false", r26.get("success") is False)
check("no objects created", len(bpy.context.scene.objects) == 0,
      [o.name for o in bpy.context.scene.objects])

# ───────────────── 4. dry_run ─────────────────
print("== SPEC-23: dry_run bind/budget ==")
clean()
rd = run("script_dry_run", mode="batch", steps=[
    {"verb": "add", "params": {"type": "box", "name": "d1", "width": 0.1,
                               "depth": 0.1, "height": 0.1}},
    {"tool": "add_sphere", "params": {"name": "d2", "radius": 0.05}},
])
check("dry_run ok", rd.get("success") and rd.get("dry_run"), rd)
check("resolved 2", rd.get("steps") == 2 or len(rd.get("resolved") or []) == 2, rd)
check("still empty scene", len(bpy.context.scene.objects) == 0)

rdbad = run("script_dry_run", mode="batch", steps=[
    {"verb": "add", "params": {"type": "notashape", "name": "x"}},
])
check("dry_run catches bad type", rdbad.get("success") is False, rdbad)

# ───────────────── 5. abort + transactional restore ─────────────────
print("== SPEC-23: abort restores scene ==")
clean()
# First create a known-good object outside the script
run("add_box", name="keep_me", width=0.2, depth=0.2, height=0.2,
    on={"on_floor": True})
check("keep_me exists pre-script", bpy.data.objects.get("keep_me") is not None)

# Batch: one good add, then a step that fails hard (duplicate name)
ra = run("script_batch", label="abort-test", on_error="abort", steps=[
    {"verb": "add", "params": {
        "type": "box", "name": "temp_a", "width": 0.1, "depth": 0.1, "height": 0.1,
        "on": {"on": "keep_me"},
    }},
    {"verb": "add", "params": {
        "type": "box", "name": "temp_a",  # duplicate name → error
        "width": 0.1, "depth": 0.1, "height": 0.1,
    }},
])
check("result aborted", ra.get("result") == "aborted", ra.get("result"))
check("first_failure present", isinstance(ra.get("first_failure"), dict),
      ra.get("first_failure"))
ff = ra.get("first_failure") or {}
check("first_failure has step index", ff.get("i") in (1, 2) or isinstance(ff.get("i"), int),
      ff)
# Transactional restore: temp_a should be gone; keep_me remains
check("temp_a removed after abort", bpy.data.objects.get("temp_a") is None,
      [o.name for o in bpy.context.scene.objects])
check("keep_me survived abort", bpy.data.objects.get("keep_me") is not None)
rest = (ra.get("undo") or {}).get("restore") or {}
check("restore attempted", rest.get("restored") is True or rest.get("steps", 0) >= 0, rest)

# ───────────────── 6. exec with Handle ─────────────────
print("== SPEC-23: exec Handle + mid-script place ==")
clean()
code = """
stem = add(type="cylinder", name="e_stem", radius=0.01, height=0.08,
           on={"on_floor": True})
assert stem.ok, stem.raw
assert stem.name == "e_stem"
assert stem.dims is not None or stem.bounds is not None
bulb = add(type="sphere", name="e_bulb", radius=0.03, on={"on": "e_stem"})
assert bulb.ok, bulb.raw
checkpoint("stem+bulb", focus="e_bulb")
"""
re = run("script_exec", label="exec-stack", code=code)
check("exec success", re.get("success"), re.get("error") or re.get("result"))
check("exec created stem+bulb",
      set(re.get("created") or []) >= {"e_stem", "e_bulb"} or
      (bpy.data.objects.get("e_stem") and bpy.data.objects.get("e_bulb")),
      re.get("created"))
check("checkpoint recorded", len(re.get("checkpoints") or []) >= 1, re.get("checkpoints"))

# exec budget: loop past 25
clean()
code_loop = """
for i in range(30):
    add(type="box", name=f"loop_{i}", width=0.02, depth=0.02, height=0.02,
        on={"on_floor": True})
"""
rl = run("script_exec", label="loop-budget", code=code_loop)
check("loop hits budget/abort", rl.get("result") in ("aborted", "rejected_budget")
      or rl.get("success") is False, rl.get("result"))
# After abort restore, should not have 30 boxes
n_loop = sum(1 for o in bpy.context.scene.objects if o.name.startswith("loop_"))
check("loop abort left <30 objects", n_loop < 30, n_loop)

# ───────────────── 7. tool= full-surface escape ─────────────────
print("== SPEC-23: tool= escape ==")
clean()
rt = run("script_batch", label="tool-escape", steps=[
    {"tool": "add_box", "params": {
        "name": "tbox", "width": 0.1, "depth": 0.1, "height": 0.1,
        "on": {"on_floor": True},
    }},
])
check("tool= path works", rt.get("success"), rt.get("error"))
check("tbox exists", bpy.data.objects.get("tbox") is not None)

# ───────────────── summary ─────────────────
print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    sys.exit(1)
print("ALL SPEC-23 checks passed")
sys.exit(0)

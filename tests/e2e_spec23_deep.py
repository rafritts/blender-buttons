"""Deeper SPEC-23 acceptance pass — criteria thin in e2e_spec23_script_runner.

Runs the WORKING-TREE extension headless (no socket).

  A. Exec uses Handle.dims for a follow-on place (AC #9)
  B. Transform + material thin-map (AC #10)
  C. Hard fail mid-run abort + transactional restore
  D. Nested script refuse
  E. on_error=continue keeps going
  F. Flat params form (verb + type at top level)
  G. Exact 25-step cap accepted
  H. first_failure shape complete
  I. dry_run budget reject for 26
  J. Exec path= from file
  K. feel mid-exec + checkpoint
  L. Progressive mini-donut two phases (AC #1–2)
  M. Code byte budget reject
  N. Unknown tool pre-mutate abort

Usage:
  flatpak run --filesystem=host org.blender.Blender --background --factory-startup \\
    --python /abs/path/to/tests/e2e_spec23_deep.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import state  # noqa: E402
from extension.common import world_bbox  # noqa: E402

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


# ── A ────────────────────────────────────────────────────────────────────────
print("== A: exec Handle dims drive later place ==")
clean()
code = """
base = add(type="box", name="base", width=0.2, depth=0.2, height=0.05,
           on={"on_floor": True})
assert base.ok and base.dims, (base.ok, base.dims)
h = base.dims[2]
col = add(type="cylinder", name="col", radius=0.02, height=h * 4,
          on={"on": "base"})
assert col.ok, col.raw
assert col.bounds is not None or col.dims is not None
checkpoint("measured", focus="col")
"""
ra = run("script_exec", label="handle-dims", code=code)
check("exec ok", ra.get("success"), ra.get("error") or ra.get("result"))
check("base+col created",
      set(ra.get("created") or []) >= {"base", "col"}
      or (bpy.data.objects.get("base") and bpy.data.objects.get("col")),
      ra.get("created"))
if bpy.data.objects.get("col") and bpy.data.objects.get("base"):
    bb, bc = world_bbox(bpy.data.objects["base"]), world_bbox(bpy.data.objects["col"])
    gap = abs(bc[2] - bb[5])
    check("col seated on base (z gap < 1mm)", gap < 0.001,
          f"gap={gap} base_zmax={bb[5]} col_zmin={bc[2]}")

# ── B ────────────────────────────────────────────────────────────────────────
print("== B: transform + material thin-map in batch ==")
clean()
rb = run("script_batch", label="xform-mat", steps=[
    {"verb": "add", "params": {
        "type": "box", "name": "tbox", "width": 0.1, "depth": 0.1, "height": 0.1,
        "on": {"on_floor": True},
    }},
    {"verb": "transform", "op": "nudge", "params": {"targets": "tbox", "up": 0.05}},
    {"verb": "material", "op": "set", "params": {
        "target": "tbox", "hex": "#336699", "roughness": 0.4,
    }},
    {"verb": "material", "op": "shade_smooth", "params": {"target": "tbox"}},
])
check("batch transform/material ok", rb.get("success"), rb.get("error") or rb.get("result"))
check("4 steps", (rb.get("steps") or {}).get("total") == 4, rb.get("steps"))
jtools = [e.get("tool") or e.get("verb_op") for e in (rb.get("journal") or [])]
check("nudge in journal", any("nudge" in str(t) for t in jtools), jtools)
if bpy.data.objects.get("tbox"):
    bb = world_bbox(bpy.data.objects["tbox"])
    check("tbox raised (zmin > 0.04)", bb[2] > 0.04, bb)

# ── C ────────────────────────────────────────────────────────────────────────
print("== C: hard fail mid-run abort restores ==")
clean()
run("add_box", name="keep", width=0.1, depth=0.1, height=0.1, on={"on_floor": True})
rc = run("script_batch", label="abort-missing", on_error="abort", steps=[
    {"verb": "add", "params": {
        "type": "sphere", "name": "temp_s", "radius": 0.03, "on": {"on": "keep"},
    }},
    {"verb": "transform", "op": "nudge", "params": {"targets": "does_not_exist", "up": 0.1}},
])
check("aborted", rc.get("result") == "aborted", rc.get("result"))
check("first_failure set", rc.get("first_failure") is not None, rc.get("first_failure"))
check("temp_s gone", bpy.data.objects.get("temp_s") is None, list(bpy.data.objects.keys()))
check("keep remains", bpy.data.objects.get("keep") is not None)

# ── D ────────────────────────────────────────────────────────────────────────
print("== D: nested script refuse ==")
clean()
rd = run("script_batch", label="nest", steps=[
    {"tool": "script_batch", "params": {
        "steps": [{"tool": "add_box", "params": {
            "name": "x", "width": 0.1, "depth": 0.1, "height": 0.1,
        }}],
    }},
])
check("nested refused", rd.get("success") is False, rd)
check("no x object", bpy.data.objects.get("x") is None)

# ── E ────────────────────────────────────────────────────────────────────────
print("== E: on_error=continue ==")
clean()
re = run("script_batch", label="continue", on_error="continue", steps=[
    {"verb": "add", "params": {
        "type": "box", "name": "ok1", "width": 0.05, "depth": 0.05, "height": 0.05,
        "on": {"on_floor": True},
    }},
    {"verb": "transform", "op": "nudge", "params": {"targets": "missing_obj", "up": 0.1}},
    {"verb": "add", "params": {
        "type": "box", "name": "ok2", "width": 0.05, "depth": 0.05, "height": 0.05,
        "on": {"on": "ok1"},
    }},
])
check("ok1 kept", bpy.data.objects.get("ok1") is not None, list(bpy.data.objects.keys()))
check("ok2 created after fail", bpy.data.objects.get("ok2") is not None, re.get("created"))
check("fail count >= 1", (re.get("steps") or {}).get("fail", 0) >= 1, re.get("steps"))
check("not pure ok",
      re.get("result") != "ok"
      or re.get("success") is False
      or (re.get("steps") or {}).get("fail", 0) >= 1,
      re.get("result"))

# ── F ────────────────────────────────────────────────────────────────────────
print("== F: flat params form ==")
clean()
rf = run("script_batch", label="flat", steps=[
    {"verb": "add", "type": "cylinder", "name": "flat_cyl", "radius": 0.02, "height": 0.1,
     "on": {"on_floor": True}},
])
check("flat form works", rf.get("success"), rf.get("error"))
check("flat_cyl exists", bpy.data.objects.get("flat_cyl") is not None)

# ── G ────────────────────────────────────────────────────────────────────────
print("== G: exact 25 steps accepted ==")
clean()
steps25 = [
    {"verb": "add", "params": {
        "type": "box", "name": f"c{i}", "width": 0.03, "depth": 0.03, "height": 0.03,
        "on": {"on_floor": True} if i == 0 else {"on": f"c{i-1}"},
    }}
    for i in range(25)
]
rg25 = run("script_batch", label="cap25", steps=steps25)
check("25 accepted", rg25.get("success"), rg25.get("error") or rg25.get("result"))
check("25 steps total", (rg25.get("steps") or {}).get("total") == 25, rg25.get("steps"))
check("c24 live", bpy.data.objects.get("c24") is not None)

# ── H ────────────────────────────────────────────────────────────────────────
print("== H: first_failure shape complete ==")
clean()
rh = run("script_batch", label="ff-shape", steps=[
    {"verb": "add", "params": {
        "type": "box", "name": "h1", "width": 0.1, "depth": 0.1, "height": 0.1,
    }},
    {"verb": "add", "params": {
        "type": "box", "name": "h1", "width": 0.1, "depth": 0.1, "height": 0.1,
    }},
])
ff = rh.get("first_failure") or {}
check("ff has i", isinstance(ff.get("i"), int), ff)
check("ff has error", bool(ff.get("error")), ff)
check("result aborted", rh.get("result") == "aborted", rh.get("result"))
check("receipt has journal", isinstance(rh.get("journal"), list))

# ── I ────────────────────────────────────────────────────────────────────────
print("== I: dry_run rejects 26 ==")
rd26 = run("script_dry_run", mode="batch", steps=[
    {"verb": "add", "params": {
        "type": "box", "name": f"d{i}", "width": 0.01, "depth": 0.01, "height": 0.01,
    }}
    for i in range(26)
])
check(
    "dry_run budget fail",
    rd26.get("success") is False
    or rd26.get("result") == "rejected_budget"
    or "budget" in str(rd26.get("error", "")).lower()
    or "cap" in str(rd26).lower(),
    rd26,
)

# ── J ────────────────────────────────────────────────────────────────────────
print("== J: exec path= from file ==")
clean()
with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
    f.write('add(type="sphere", name="from_file", radius=0.04, on={"on_floor": True})\n')
    path = f.name
rj = run("script_exec", label="from-path", path=path)
check("path exec ok", rj.get("success"), rj.get("error"))
check("from_file exists", bpy.data.objects.get("from_file") is not None)
os.unlink(path)

# ── K ────────────────────────────────────────────────────────────────────────
print("== K: feel mid-exec ==")
clean()
code_k = """
a = add(type="box", name="fa", width=0.1, depth=0.1, height=0.05,
        on={"on_floor": True})
b = add(type="box", name="fb", width=0.1, depth=0.1, height=0.05, on={"on": "fa"})
r = feel(op="resting", a="fb", b="fa")
assert r is not None
checkpoint("feel", focus="fb")
"""
rk = run("script_exec", label="feel-mid", code=code_k)
check("feel exec ok", rk.get("success"), rk.get("error") or rk.get("result"))
check("checkpoint present", len(rk.get("checkpoints") or []) >= 1, rk.get("checkpoints"))

# ── L ────────────────────────────────────────────────────────────────────────
print("== L: progressive mini-donut two phases ==")
clean()
r1 = run("script_batch", label="donut-body", steps=[
    {"verb": "add", "params": {
        "type": "torus", "name": "donut",
        "major_radius": 0.05, "minor_radius": 0.02,
        "on": {"on_floor": True},
    }},
    {"verb": "material", "op": "set", "params": {
        "target": "donut", "hex": "#C4784A", "roughness": 0.55,
    }},
])
check("phase1 donut", r1.get("success"), r1.get("error") or r1.get("result"))
name = (r1.get("created") or ["donut"])[0]
r2 = run("script_batch", label="donut-icing", steps=[
    {"verb": "add", "params": {
        "type": "torus", "name": "icing",
        "major_radius": 0.05, "minor_radius": 0.012,
        "on": {"on": name},
    }},
    {"verb": "material", "op": "set", "params": {
        "target": "icing", "hex": "#E8A0BF", "roughness": 0.35,
    }},
    {"verb": "feel", "op": "resting", "params": {"a": "icing", "b": name}},
])
check(
    "phase2 icing",
    r2.get("success") or r2.get("result") in ("ok", "completed_with_warnings"),
    r2.get("error") or r2.get("result"),
)
check("both live", bool(bpy.data.objects.get("donut") and bpy.data.objects.get("icing")))

# ── M ────────────────────────────────────────────────────────────────────────
print("== M: code byte budget reject ==")
huge = "x = 1\n" * (70 * 1024 // 6)
rn = run("script_exec", label="huge", code=huge)
check(
    "code size rejected",
    rn.get("result") == "rejected_budget" or rn.get("success") is False,
    rn.get("result"),
)

# ── N ────────────────────────────────────────────────────────────────────────
print("== N: unknown tool pre-mutate abort ==")
clean()
ro = run("script_batch", label="bad-tool", steps=[
    {"tool": "definitely_not_a_tool", "params": {"name": "z"}},
])
check("unknown tool aborted", ro.get("success") is False, ro)
check("scene empty", len(bpy.context.scene.objects) == 0,
      [o.name for o in bpy.context.scene.objects])

# ── summary ──────────────────────────────────────────────────────────────────
print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    sys.exit(1)
print("ALL DEEP SPEC-23 checks passed")
sys.exit(0)

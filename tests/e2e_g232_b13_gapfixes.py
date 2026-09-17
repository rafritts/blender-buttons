"""E2E for G232–G234 and B11–B13. Headless, working-tree extension via execute_command.

  G232 — applied UNION receipt flags unfused / shells>1 when operands never fused
  G233 — successful baked boolean consumes the cutter (live modifier still hides)
  G234 — feel silhouette occupancy is projected coverage, not an edge ring
  B11  — snap_to / snap_to_grid honor targets= (not the viewport-active)
  B12  — script batch/exec comma-list target= resolves like REPL _targets()
  B13  — script exec object(op=...) is the object verb, not builtins.object

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_g232_b13_gapfixes.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import state  # noqa: E402


def _load_fmt_silhouette():
    """Load the shipped `_fmt_silhouette` without importing FastMCP (not in Blender)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "server", "queries.py")
    src = open(path, encoding="utf-8").read()
    start = src.index("def _fmt_silhouette")
    end = src.index("\n@mcp.tool()", start)
    ns = {}
    exec(src[start:end], ns, ns)  # noqa: S102 — the shipped formatter, not a reimplementation
    return ns["_fmt_silhouette"]


_fmt_silhouette = _load_fmt_silhouette()

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


def sil_core(res):
    """Cage block from a get_silhouette execute_command result."""
    return res.get("cage") or res.get("evaluated") or res


def center_cell(grid):
    if not grid or not grid[0]:
        return None
    return grid[len(grid) // 2][len(grid[0]) // 2]


def interior_hash_count(grid, margin=2):
    """Count '#' cells inset from the border — a filled disc has many, a ring has ~0."""
    n = 0
    rows = len(grid)
    if rows <= 2 * margin:
        return sum(c == "#" for row in grid for c in row)
    cols = len(grid[0])
    for r in range(margin, rows - margin):
        row = grid[r]
        for c in range(margin, min(cols, len(row)) - margin):
            if row[c] == "#":
                n += 1
    return n


# ───────────────────────── G232: UNION unfused flag ─────────────────────────
print("== G232: applied UNION flags unfused when operands never fused ==")
clean()
run("add_box", name="host_apart", width=0.2, depth=0.2, height=0.2,
    on={"on_floor": True})
run("add_box", name="cut_apart", width=0.2, depth=0.2, height=0.2,
    on={"right_of": "host_apart", "gap": 2.8})
r_apart = run("boolean", target="host_apart", cutter="cut_apart", op="UNION", apply=True)
check("disjoint UNION reports success", r_apart.get("success"), str(r_apart)[:240])
check("disjoint UNION applied (non-empty bake)", r_apart.get("applied") is True,
      str(r_apart)[:240])
check("disjoint UNION has no empty_result (T8 unchanged)",
      not r_apart.get("empty_result"), str(r_apart)[:240])
unfused = r_apart.get("unfused")
shells = r_apart.get("shells")
flagged = bool(unfused) or (isinstance(shells, int) and shells > 1) or (
    not r_apart.get("success") and "unfused" in str(r_apart).lower()
)
check("disjoint UNION flags unfused / shells>1 (not a silent one-body success)",
      flagged, f"unfused={unfused!r} shells={shells!r} keys={list(r_apart)}")
if isinstance(shells, int):
    check("disjoint UNION shell count is >1", shells > 1, str(shells))

clean()
run("add_box", name="host_ov", width=0.2, depth=0.2, height=0.2,
    on={"on_floor": True})
run("add_box", name="cut_ov", width=0.2, depth=0.2, height=0.2,
    on={"right_of": "host_ov", "gap": -0.15})
r_ov = run("boolean", target="host_ov", cutter="cut_ov", op="UNION", apply=True)
check("overlapping UNION applied", r_ov.get("success") and r_ov.get("applied") is True,
      str(r_ov)[:240])
check("overlapping UNION has no unfused flag", not r_ov.get("unfused"),
      f"unfused={r_ov.get('unfused')!r} shells={r_ov.get('shells')!r}")
if r_ov.get("shells") is not None:
    check("overlapping UNION is one shell", r_ov.get("shells") == 1,
          str(r_ov.get("shells")))


# ───────────────────────── G233: consume cutter on bake ─────────────────────────
print("== G233: baked boolean consumes the cutter; live modifier keeps it ==")
clean()
run("add_box", name="g233_host", width=0.4, depth=0.4, height=0.4,
    on={"on_floor": True})
run("add_box", name="g233_cutter", width=0.1, depth=0.1, height=0.1,
    on={"centered_on": "g233_host"})
r_bake = run("boolean", target="g233_host", cutter="g233_cutter", op="DIFFERENCE",
             apply=True)
check("baked boolean applied", r_bake.get("success") and r_bake.get("applied") is True,
      str(r_bake)[:240])
check("baked default path consumes cutter (name gone from bpy.data)",
      "g233_cutter" not in bpy.data.objects,
      [o.name for o in bpy.data.objects])
re = run("add_box", name="g233_cutter", width=0.08, depth=0.08, height=0.08,
         on={"right_of": "g233_host", "gap": 0.1})
check("cutter name is free to reuse without .001",
      re.get("success") is True and bpy.data.objects.get("g233_cutter") is not None
      and bpy.data.objects["g233_cutter"].name == "g233_cutter",
      str(re)[:200])

clean()
run("add_box", name="g233_live_h", width=0.4, depth=0.4, height=0.4,
    on={"on_floor": True})
run("add_box", name="g233_live_c", width=0.1, depth=0.1, height=0.1,
    on={"centered_on": "g233_live_h"})
r_live = run("boolean", target="g233_live_h", cutter="g233_live_c", op="DIFFERENCE",
             apply=False)
check("live boolean keeps the cutter", "g233_live_c" in bpy.data.objects, str(r_live)[:200])
check("live boolean hides the cutter when hide_cutter defaults on",
      bpy.data.objects["g233_live_c"].hide_get() is True)

clean()
run("add_box", name="g233_keep_h", width=0.4, depth=0.4, height=0.4,
    on={"on_floor": True})
run("add_box", name="g233_keep_c", width=0.1, depth=0.1, height=0.1,
    on={"centered_on": "g233_keep_h"})
r_keep = run("boolean", target="g233_keep_h", cutter="g233_keep_c", op="DIFFERENCE",
             apply=True, hide_cutter=False)
check("explicit keep (hide_cutter=False) leaves the cutter after bake",
      "g233_keep_c" in bpy.data.objects, str(r_keep)[:200])
check("kept cutter is not hidden",
      bpy.data.objects["g233_keep_c"].hide_get() is False)


# ───────────────────────── G234: silhouette is coverage ─────────────────────────
print("== G234: silhouette # is projected coverage; holes stay empty ==")
clean()
run("add_box", name="slab", width=0.2, depth=0.2, height=0.04,
    on={"on_floor": True})
r_slab = run("get_silhouette", axis="Z", res=24, target="slab")
core_slab = sil_core(r_slab)
grid_slab = core_slab.get("grid") or []
check("slab silhouette succeeded", r_slab.get("success") and grid_slab,
      str(r_slab)[:200])
check("closed box along thin axis has interior # (not a hollow ring)",
      center_cell(grid_slab) == "#" and interior_hash_count(grid_slab) > 8,
      f"center={center_cell(grid_slab)!r} interior#={interior_hash_count(grid_slab)} "
      f"grid=\n" + "\n".join(grid_slab[:12]))
check("occupancy is coverage, not edge-hit",
      core_slab.get("occupancy") == "coverage",
      str(core_slab.get("occupancy")))

clean()
run("add_cylinder", name="puck", radius=0.08, height=0.03,
    on={"on_floor": True})
r_cyl = run("get_silhouette", axis="Z", res=24, target="puck")
core_cyl = sil_core(r_cyl)
grid_cyl = core_cyl.get("grid") or []
check("closed cylinder along thin axis has interior #",
      center_cell(grid_cyl) == "#" and interior_hash_count(grid_cyl) > 8,
      f"center={center_cell(grid_cyl)!r} interior#={interior_hash_count(grid_cyl)}")

clean()
run("add_torus", name="ring", major_radius=0.1, minor_radius=0.02)
r_tor = run("get_silhouette", axis="Z", res=28, target="ring")
core_tor = sil_core(r_tor)
grid_tor = core_tor.get("grid") or []
check("torus silhouette succeeded", r_tor.get("success") and grid_tor, str(r_tor)[:200])
check("torus hole is empty (center .)",
      center_cell(grid_tor) == ".",
      f"center={center_cell(grid_tor)!r} grid=\n" + "\n".join(grid_tor[:14]))
check("torus still has # cells (the annulus)",
      any("#" in row for row in grid_tor), grid_tor[:4])

clean()
run("add_box", name="plate", width=0.24, depth=0.24, height=0.08,
    on={"on_floor": True})
run("add_cylinder", name="drill", radius=0.05, height=0.2,
    on={"centered_on": "plate"})
run("boolean", target="plate", cutter="drill", op="DIFFERENCE", apply=True)
r_hole = run("get_silhouette", axis="Z", res=28, target="plate")
core_hole = sil_core(r_hole)
grid_hole = core_hole.get("grid") or []
check("differenced through-hole is empty at center",
      center_cell(grid_hole) == ".",
      f"center={center_cell(grid_hole)!r} grid=\n" + "\n".join(grid_hole[:14]))
check("differenced plate still has # around the hole",
      any("#" in row for row in grid_hole), grid_hole[:4])

fmt = _fmt_silhouette(core_slab)
head = "\n".join(fmt.split("\n")[:3]).lower()
check("formatter legend does not call an edge-hit 'filled'",
      "filled" not in head,
      fmt[:220])
check("formatter names occupancy as coverage/covered",
      "covered" in head,
      fmt[:220])


# ───────────────────────── B11: snap honors targets= ─────────────────────────
print("== B11: snap_to / snap_to_grid honor targets= ==")
clean()
run("add_box", name="SnapA", width=0.2, depth=0.2, height=0.2,
    on={"on_floor": True})
run("add_box", name="SnapB", width=0.2, depth=0.2, height=0.2,
    on={"right_of": "SnapA", "gap": 1.8})
a = bpy.data.objects["SnapA"]
b = bpy.data.objects["SnapB"]
bpy.context.view_layer.objects.active = a
loc_a = tuple(a.location)
loc_b = tuple(b.location)
r_snap = run("snap_to", targets="SnapB", target="SnapA", side="X_MAX")
check("snap_to succeeded", r_snap.get("success"), str(r_snap)[:240])
check("snap_to moved B (the named target), not viewport-active A",
      (tuple(b.location) != loc_b) and (tuple(a.location) == loc_a),
      f"A {loc_a}→{tuple(a.location)}  B {loc_b}→{tuple(b.location)}  res={str(r_snap)[:160]}")

clean()
run("add_box", name="GridA", width=0.1, depth=0.1, height=0.1,
    on={"on_floor": True})
run("add_box", name="GridB", width=0.1, depth=0.1, height=0.1,
    on={"right_of": "GridA", "gap": 1.0})
run("nudge", targets="GridA", right=0.13, back=0.13)
run("nudge", targets="GridB", right=0.27, back=0.19)
ga = bpy.data.objects["GridA"]
gb = bpy.data.objects["GridB"]
bpy.context.view_layer.objects.active = ga
ga_before = tuple(round(v, 5) for v in ga.location)
gb_before = tuple(round(v, 5) for v in gb.location)
r_grid = run("snap_to_grid", targets="GridB", size=0.1, axes="XYZ")
check("snap_to_grid succeeded", r_grid.get("success"), str(r_grid)[:240])
ga_after = tuple(round(v, 5) for v in ga.location)
gb_after = tuple(round(v, 5) for v in gb.location)
check("snap_to_grid moved B, not viewport-active A",
      ga_after == ga_before and gb_after != gb_before,
      f"A {ga_before}→{ga_after}  B {gb_before}→{gb_after}")


# ───────────────────────── B12: script comma-list target= ─────────────────────────
print("== B12: script comma-list target= resolves all three names ==")
clean()
r_batch = run("script_batch", label="b12-batch", steps=[
    {"verb": "add", "params": {
        "type": "box", "name": "N1", "width": 0.05, "depth": 0.05, "height": 0.05,
        "on": {"on_floor": True},
    }},
    {"verb": "add", "params": {
        "type": "box", "name": "N2", "width": 0.05, "depth": 0.05, "height": 0.05,
        "on": {"right_of": "N1", "gap": 0.1},
    }},
    {"verb": "add", "params": {
        "type": "box", "name": "N3", "width": 0.05, "depth": 0.05, "height": 0.05,
        "on": {"right_of": "N2", "gap": 0.1},
    }},
    {"verb": "material", "op": "set", "params": {
        "target": "N1,N2,N3", "hex": "#cc3333",
    }},
])
err_batch = str(r_batch.get("error") or "") + str(r_batch.get("first_failure") or "")
check("batch comma-list material did not 404 the joined name",
      "N1,N2,N3" not in err_batch and "not found" not in err_batch.lower(),
      err_batch[:240])
check("batch comma-list material succeeded",
      r_batch.get("success") and r_batch.get("result") == "ok",
      f"result={r_batch.get('result')} err={err_batch[:200]}")
mats = []
for n in ("N1", "N2", "N3"):
    o = bpy.data.objects.get(n)
    slot = (o.data.materials[0] if o and o.data and o.data.materials else None)
    mats.append(slot)
check("batch assigned a material on all three",
      all(m is not None for m in mats), [getattr(m, "name", None) for m in mats])

clean()
code_b12 = """
add(type="box", name="E1", width=0.05, depth=0.05, height=0.05, on={"on_floor": True})
add(type="box", name="E2", width=0.05, depth=0.05, height=0.05, on={"right_of": "E1", "gap": 0.1})
add(type="box", name="E3", width=0.05, depth=0.05, height=0.05, on={"right_of": "E2", "gap": 0.1})
h = material(op="set", target="E1,E2,E3", hex="#3366cc")
assert h.ok, h.raw
"""
r_exec = run("script_exec", label="b12-exec", code=code_b12)
err_exec = str(r_exec.get("error") or "") + str(r_exec.get("first_failure") or "")
check("exec comma-list material did not 404 the joined name",
      "E1,E2,E3" not in err_exec and "not found" not in err_exec.lower(),
      err_exec[:240])
check("exec comma-list material succeeded",
      r_exec.get("success") is True and r_exec.get("result") == "ok",
      f"result={r_exec.get('result')} err={err_exec[:200]}")
for n in ("E1", "E2", "E3"):
    o = bpy.data.objects.get(n)
    has = bool(o and o.data and o.data.materials and o.data.materials[0])
    check(f"exec material on {n}", has, n)


# ───────────────────────── B13: exec object() is the verb ─────────────────────────
print("== B13: script exec object(op=...) is the object verb ==")
clean()
code_b13 = """
c = add(type="camera", name="cam_src")
assert c.ok, c.raw
h = object(op="duplicate", name="cam_src", new_name="cam_copy")
assert h.ok, h.raw
"""
r_obj = run("script_exec", label="b13-object", code=code_b13)
err_obj = str(r_obj.get("error") or "") + str((r_obj.get("first_failure") or {}).get("error") or "")
tb = str((r_obj.get("first_failure") or {}).get("traceback") or "")
check("exec object() is not builtins.object TypeError",
      "takes no arguments" not in err_obj and "takes no arguments" not in tb
      and "TypeError: object()" not in err_obj,
      f"err={err_obj[:240]} tb={tb[:200]}")
check("exec object(op=duplicate) succeeded",
      r_obj.get("success") and bpy.data.objects.get("cam_copy") is not None,
      f"result={r_obj.get('result')} err={err_obj[:200]} "
      f"objs={[o.name for o in bpy.data.objects]}")


print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")
sys.exit(0)

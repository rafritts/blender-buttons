"""E2E for SPEC-21 Phase 1 — runs the WORKING-TREE extension headless.

  G220 — every mutating select narrates what got grabbed (count, patches, extent,
         position, island identity, open-rim flag) via `selection_report`.
  G219 — grow/shrink/flood report before → after; a Δ=0 carries `why_unchanged`
         (a saturated island reads as a correct no-op, never a malfunction).
  G221 — `pick_element`: one arbitrary element in a named scope, deterministic
         under a seed; pairs with grow to reproduce click-and-hold.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_spec21_phase1.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402

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
    state.reset_history_state()


def make_two_shell_mesh(name="TwoShell"):
    """A big 8×8 grid shell + a small detached 2×2 'fingernail' plate above it —
    the VRoid incident in miniature. Returns (obj, nail vert indices)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=8, y_segments=8, size=0.1)
    big_count = len(bm.verts)
    res = bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=0.01)
    for v in res["verts"]:
        v.co.z += 0.05
        v.co.x += 0.08
    bm.verts.ensure_lookup_table()
    nail = [v.index for v in bm.verts if v.index >= big_count]
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj, nail


# ───────────────── G220: narrated selects ─────────────────
print("== G220: every mutating select narrates the grabbed region ==")
clean()
obj, nail = make_two_shell_mesh()

res = run("select_by_axis", target=obj.name, axis="Z", factor=0.5, comparison="GREATER")
check("by_axis succeeds", res.get("success"), str(res))
check("by_axis returns a count", isinstance(res.get("selected_count"), int), str(res))
check("by_axis carries selection_report", bool(res.get("selection_report")), str(res.keys()))
rep = res.get("selection_report", "")
check("report names the vert count", str(res.get("selected_count")) in rep, rep)
check("report gives island identity (shell # of 2)", "of 2" in rep and "shell" in rep, rep)
print(f"    → {rep}")

res = run("select_all", target=obj.name, action="SELECT")
check("select_all reports a count", res.get("selected_count") == 90, str(res))
check("select_all narrates whole mesh", "whole mesh" in res.get("selection_report", ""),
      res.get("selection_report"))

res = run("select_all", target=obj.name, action="DESELECT")
check("deselect narrates EMPTY", "EMPTY" in res.get("selection_report", ""),
      res.get("selection_report"))

# ───────────────── G219: grow Δ-reporting + why ─────────────────
print("== G219: grow answers before → after, and says WHY on Δ=0 ==")
res = run("select_by_index", target=obj.name, indices=nail)
check("nail island selected", res.get("selected_count") == len(nail), str(res))
rep = res.get("selection_report", "")
check("narration flags the island as saturated", "exactly shell" in rep, rep)
print(f"    → {rep}")

res = run("grow_selection", target=obj.name, direction="GROW", steps=4)
check("grow succeeds", res.get("success"), str(res))
check("grow reports before/after", res.get("before") == len(nail)
      and res.get("after") == len(nail), str(res))
check("grow Δ=0 says why (saturated island)",
      "saturated" in res.get("why_unchanged", ""), res.get("why_unchanged"))
print(f"    → {res.get('why_unchanged')}")

res = run("grow_selection", target=obj.name, direction="SHRINK", steps=1)
check("shrink Δ=0 says why (no rim to peel)",
      "rim to peel" in res.get("why_unchanged", ""), res.get("why_unchanged"))

# a grow that CAN expand reports the delta and no why_unchanged
res = run("select_by_index", target=obj.name, indices=[0])
res = run("grow_selection", target=obj.name, direction="GROW", steps=1)
check("real grow reports Δ>0", res.get("after", 0) > res.get("before", 99),
      str((res.get("before"), res.get("after"))))
check("real grow carries no why_unchanged", "why_unchanged" not in res, str(res))

# flood from the nail island: Δ=0 with a reason
res = run("select_by_index", target=obj.name, indices=nail)
res = run("flood_to_crease", target=obj.name, angle=25.0)
check("flood on an island explains Δ=0",
      bool(res.get("why_unchanged")), str(res))
print(f"    → {res.get('why_unchanged')}")

# ───────────────── G221: pick — the yolo click ─────────────────
print("== G221: pick — one arbitrary element, deterministic under seed ==")
res = run("select_all", target=obj.name, action="DESELECT")
r1 = run("pick_element", target=obj.name, kind="FACE", seed=7)
check("pick face succeeds", r1.get("success"), str(r1))
check("pick reports candidate pool (whole mesh)", r1.get("candidates") == 68, str(r1))
check("pick reports area not coordinates", "area_mm2" in r1 and "co" not in r1, str(r1))
check("pick narrates the selection", bool(r1.get("selection_report")),
      str(r1.keys()))
r2 = run("pick_element", target=obj.name, kind="FACE", seed=7)
check("same seed → same face", r1.get("picked_index") == r2.get("picked_index"),
      f"{r1.get('picked_index')} vs {r2.get('picked_index')}")

# scope = a vertex group (the handle path)
vg = obj.vertex_groups.new(name="HANDLE_nailzone")
vg.add(nail, 1.0, 'REPLACE')
res = run("pick_element", target=obj.name, kind="FACE", within="nailzone", seed=0)
check("pick within a handle vgroup", res.get("success"), str(res))
check("pick scope is the group", "HANDLE_nailzone" in res.get("scope", ""), str(res))
me = obj.data
sel_faces = [p.index for p in me.polygons if p.select]
check("exactly one face selected", len(sel_faces) == 1, str(sel_faces))
face_verts = set(me.polygons[sel_faces[0]].vertices) if sel_faces else set()
check("picked face lies inside the scope", face_verts and face_verts <= set(nail),
      str(face_verts))

# pick → grow: the human click-and-hold, narrated
res = run("grow_selection", target=obj.name, direction="GROW", steps=8)
check("pick+grow saturates the island",
      res.get("after") == len(nail) or "saturated" in res.get("why_unchanged", ""),
      str(res))

# pick within current selection
res = run("select_by_index", target=obj.name, indices=nail)
res = run("pick_element", target=obj.name, kind="VERT", seed=3)
check("pick VERT from current selection", res.get("success")
      and "current selection" in res.get("scope", ""), str(res))
check("picked vert is in the prior selection",
      res.get("picked_index") in set(nail), str(res.get("picked_index")))

# error path: unknown group
res = run("pick_element", target=obj.name, kind="FACE", within="nope_xyz")
check("unknown scope errors with the group list", "no vertex group" in res.get("error", ""),
      str(res))

# ───────────────── single-shell mesh: identity clause stays silent ─────────────────
print("== narration is quiet about shells on a single-shell mesh ==")
clean()
me = bpy.data.meshes.new("Solo")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.1)
bm.to_mesh(me)
bm.free()
solo = bpy.data.objects.new("Solo", me)
bpy.context.scene.collection.objects.link(solo)
bpy.context.view_layer.objects.active = solo
solo.select_set(True)
res = run("select_by_axis", target="Solo", axis="Z", factor=0.5, comparison="GREATER")
rep = res.get("selection_report", "")
check("no shell clause on a 1-shell mesh", "shell" not in rep, rep)
check("still narrates patches/extent", "patch" in rep, rep)
print(f"    → {rep}")

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("ALL PASS")

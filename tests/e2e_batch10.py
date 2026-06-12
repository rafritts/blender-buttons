"""E2E for batch-10 gap fixes (Z1–Z3, Y1, Y2, X3B, X7). Headless.

  Z1  — assign_weight: scoped vertex-group weight on the edit-mode selection.
  Z2/X7 — loop_cut honors the selection (region-scoped) and reports region words,
          not a coordinate dump.
  Z3  — get_mesh_profile windowing (min/max) + max_rings even resampling.
  Y1  — a position edit on a keyed mesh lands on the ACTIVE shape key: the edit
        verb warns, the status block carries active_key, the warning takes
        precedence over bind_shadowed, and set_active_shape_key aims the edit.
  Y2/X3B — select_boundary grabs an open rim, which set_edge_crease can then aim at.

Usage: flatpak run --filesystem=home org.blender.Blender --background \
         --python /abs/path/to/tests/e2e_batch10.py
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


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


# ───────── Z1: assign_weight ─────────
print("== Z1: assign_weight scopes a vertex-group weight to the selection ==")
clean()
run("add_box", name="bx", width=1.0, depth=1.0, height=2.0)
run("select_object", name="bx")
run("set_mode", mode="EDIT")
r = run("select_by_axis", axis="Z", factor=0.5, comparison="GREATER")
sel = r["blender_status"]["edit"]["selected"]["verts"]
r = run("assign_weight", group="spine", weight=1.0, mode="REPLACE")
check("assign_weight succeeded", r.get("success"), repr(r))
check("group created", r.get("group_created") is True, repr(r))
check("assigned to exactly the selection", r.get("verts_assigned") == sel, f"{r.get('verts_assigned')} vs {sel}")
run("set_mode", mode="OBJECT")
obj = bpy.data.objects["bx"]
vg = obj.vertex_groups["spine"]
weighted = [v for v in obj.data.vertices if any(g.group == vg.index and g.weight > 0.9 for g in v.groups)]
check("weights actually landed on the mesh", len(weighted) == sel, f"{len(weighted)} vs {sel}")
unweighted = [v for v in obj.data.vertices if not any(g.group == vg.index for g in v.groups)]
check("unselected verts were NOT weighted", len(unweighted) == len(obj.data.vertices) - sel,
      f"{len(unweighted)}")
# ADD / SUBTRACT clamp
run("set_mode", mode="EDIT")
run("select_by_axis", axis="Z", factor=0.5, comparison="GREATER")
run("assign_weight", group="spine", weight=0.5, mode="ADD")  # 1.0 + 0.5 → clamp 1.0
run("set_mode", mode="OBJECT")
maxw = max(g.weight for v in obj.data.vertices for g in v.groups if g.group == vg.index)
check("ADD clamps to 1.0", abs(maxw - 1.0) < 1e-6, repr(maxw))
run("set_mode", mode="EDIT")
run("select_by_axis", axis="Z", factor=0.5, comparison="GREATER")
run("assign_weight", group="spine", weight=0.3, mode="SUBTRACT")
run("set_mode", mode="OBJECT")
minw = min(g.weight for v in obj.data.vertices for g in v.groups if g.group == vg.index)
check("SUBTRACT lowered the weight", abs(minw - 0.7) < 1e-6, repr(minw))


# ───────── Z2 / X7: loop_cut selection scope + region words ─────────
print("== Z2/X7: loop_cut is selection-scoped and reports region, not coords ==")


def segmented_stack(name):
    """A column pre-cut into 4 vertical segments (16 axis-running edges)."""
    run("add_box", name=name, width=1.0, depth=1.0, height=4.0)
    run("select_object", name=name)
    run("set_mode", mode="EDIT")
    run("select_all", action="DESELECT")
    run("loop_cut", axis="Z", cuts=3)


# Whole-mesh cut: nothing selected → cuts every vertical segment.
clean()
segmented_stack("s_whole")
run("select_all", action="DESELECT")
r_whole = run("loop_cut", axis="Z", cuts=1)
check("whole-mesh cut succeeded", r_whole.get("success"), repr(r_whole))
check("no coordinate dump in result", "loop_positions" not in r_whole, repr(list(r_whole.keys())))
check("reports region word", isinstance(r_whole.get("region"), str), repr(r_whole))
check("reports loop count", r_whole.get("loops", 0) >= 1, repr(r_whole))
check("whole-mesh cut is NOT scoped", r_whole.get("scoped_to_selection") is False, repr(r_whole))
whole_edges = r_whole["edges_subdivided"]
run("set_mode", mode="OBJECT")

# Scoped cut on an identical fresh mesh: top-half selection → fewer edges.
clean()
segmented_stack("s_scoped")
run("select_by_axis", axis="Z", factor=0.5, comparison="GREATER")
r_scoped = run("loop_cut", axis="Z", cuts=1)
check("scoped cut succeeded", r_scoped.get("success"), repr(r_scoped))
check("scoped flag set", r_scoped.get("scoped_to_selection") is True, repr(r_scoped))
check("scoped cut touched FEWER edges than whole mesh",
      r_scoped["edges_subdivided"] < whole_edges,
      f"{r_scoped['edges_subdivided']} vs {whole_edges}")
run("set_mode", mode="OBJECT")


# ───────── Z3: get_mesh_profile windowing + resample ─────────
print("== Z3: get_mesh_profile windows by min/max and caps rings by resampling ==")
clean()
run("add_box", name="col", width=1.0, depth=1.0, height=4.0)
run("select_object", name="col")
run("set_mode", mode="EDIT")
run("select_all", action="DESELECT")
run("loop_cut", axis="Z", cuts=30)   # ~32 rings
run("set_mode", mode="OBJECT")
full = run("get_mesh_profile", axis="Z")
total = full["rings_total"]
check("profile reports many rings", total >= 30, repr(total))
check("uncapped default fits (<=200)", full["rings"] == total, repr(full["rings"]))
capped = run("get_mesh_profile", axis="Z", max_rings=5)
check("max_rings caps the ring count", capped["rings"] <= 5, repr(capped["rings"]))
check("resample is reported", capped.get("resampled") is True, repr(capped))
check("first and last rings kept", capped["profile"][0]["Z"] == full["profile"][0]["Z"]
      and capped["profile"][-1]["Z"] == full["profile"][-1]["Z"], "extent not preserved")
# Window: only rings whose Z is within [-0.5, 0.5] (box spans z=0..4 by default origin? use bounds)
zmin = full["profile"][0]["Z"]
zmax = full["profile"][-1]["Z"]
mid_lo = zmin + 0.4 * (zmax - zmin)
mid_hi = zmin + 0.6 * (zmax - zmin)
win = run("get_mesh_profile", axis="Z", min=mid_lo, max=mid_hi)
check("windowed profile is a subset", win["rings"] < total, f"{win['rings']} vs {total}")
check("windowed flag set", win.get("windowed") is True, repr(win.get("window")))
check("windowed rings all inside the window",
      all(mid_lo - 1e-4 <= r["Z"] <= mid_hi + 1e-4 for r in win["profile"]), "out-of-window ring")


# ───────── Y1: shape-key shadowing ─────────
print("== Y1: a position edit on a keyed mesh lands on the active shape key ==")
clean()
run("add_box", name="head", width=1.0, depth=1.0, height=2.0)
obj = bpy.data.objects["head"]
obj.shape_key_add(name="Basis")
morph = obj.shape_key_add(name="smile")
morph.value = 0.0
# Make the non-basis key active (value 0) — the documented landmine.
obj.active_shape_key_index = 1
run("select_object", name="head")
run("set_mode", mode="EDIT")
run("select_by_axis", axis="Z", factor=0.5, comparison="GREATER")
r = run("move_vertices", x=0.0, y=0.0, z=0.2)
check("edit on non-basis key warns", bool(r.get("shape_key_warning")), repr(r.keys()))
check("warning flags it as shadowed (value 0)", r.get("shape_key_shadowed") is True, repr(r))
check("warning names the active key", "smile" in (r.get("shape_key_warning") or ""), repr(r.get("shape_key_warning")))
# status block carries active_key
ak = r["blender_status"]["edit"].get("active_key")
check("status block carries active_key", ak is not None and ak["name"] == "smile", repr(ak))
check("active_key marked non-basis", ak and ak.get("is_basis") is False, repr(ak))
# Aim at Basis with set_active_shape_key, then the same edit is NOT shadowed.
run("set_mode", mode="OBJECT")
r = run("set_active_shape_key", name="head", key="Basis")
check("set_active_shape_key → Basis", r.get("success") and r.get("is_basis") is True, repr(r))
run("set_mode", mode="EDIT")
run("select_by_axis", axis="Z", factor=0.5, comparison="GREATER")
r = run("move_vertices", x=0.0, y=0.0, z=0.2)
check("edit on Basis is NOT shadowed", not r.get("shape_key_warning"), repr(r.get("shape_key_warning")))
run("set_mode", mode="OBJECT")

# Precedence (Y1c): a keyed AND cage-bound mesh, position-only edit → the shape-key
# warning wins; bind_shadowed must NOT also fire (it would misdirect the diagnosis).
clean()
run("add_sphere", name="cloth", radius=1.0, segments=16, rings=12)
run("add_box", name="cage", width=2.6, depth=2.6, height=2.6)
run("select_object", name="cloth")
rb = run("bind_mesh_deform", mesh="cloth", cage="cage")
if rb.get("bound"):
    obj = bpy.data.objects["cloth"]
    obj.shape_key_add(name="Basis")
    k = obj.shape_key_add(name="corrective"); k.value = 0.0
    obj.active_shape_key_index = 1
    r = run("move_vertices", x=0.0, y=0.0, z=0.1, target="cloth")
    check("keyed+bound: shape-key warning fires", bool(r.get("shape_key_warning")), repr(r.keys()))
    check("keyed+bound: bind_shadowed SUPPRESSED (precedence)", not r.get("bind_shadowed"), repr(r))
else:
    print("  skip  bind_mesh_deform setup failed (live-only?) — precedence check skipped")


# ───────── X3B / Y2: select_boundary + crease the rim ─────────
print("== X3B/Y2: select_boundary grabs an open rim, set_edge_crease aims at it ==")
clean()
run("add_box", name="cup", width=2.0, depth=2.0, height=2.0)
run("select_object", name="cup")
run("set_mode", mode="EDIT")
run("select_by_axis", axis="Z", factor=0.9, comparison="GREATER")  # top face
run("delete_geometry", mode="ONLY_FACE")  # open the top → 4-edge rim
run("select_all", action="DESELECT")
r = run("select_boundary")
check("select_boundary found the rim", r.get("success") and r.get("boundary_edges") == 4, repr(r))
check("switched to EDGE component mode",
      r["blender_status"]["edit"]["component_mode"] == "EDGE", repr(r["blender_status"]["edit"]))
check("reports a region word", isinstance(r.get("region"), str), repr(r))
# Y2: the rim selection feeds set_edge_crease (the previously un-aimable crease).
r = run("set_edge_crease", weight=1.0)
check("set_edge_crease aimed at the rim", r.get("success") and r.get("edges_creased") == 4, repr(r))
run("set_mode", mode="OBJECT")
# Closed mesh → honest error.
clean()
run("add_sphere", name="ball", radius=1.0, segments=12, rings=8)
run("select_object", name="ball")
run("set_mode", mode="EDIT")
run("select_all", action="DESELECT")
r = run("select_boundary")
check("closed mesh → no-boundary error", not r.get("success") and "boundary" in r.get("error", ""), repr(r))
run("set_mode", mode="OBJECT")


print()
if failures:
    print(f"BATCH10 E2E: {len(failures)} FAILED: {failures}")
    sys.exit(1)
else:
    print("BATCH10 E2E: ALL TESTS PASSED")

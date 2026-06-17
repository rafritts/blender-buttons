"""E2E smoke test for the 2026-06-16 gap fixes (G11-G22) — runs inside headless Blender.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_gapfixes.py
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


# ───────────── G18: object mode EDIT→OBJECT on the active edit object ─────────
print("== G18: set_mode EDIT→OBJECT name=<self> ==")
clean()
run("add_box", name="g18", width=1.0, depth=1.0, height=1.0)
r = run("set_mode", mode="EDIT", target="g18")
check("entered EDIT", bpy.context.active_object.mode == "EDIT", str(r))
r = run("set_mode", mode="OBJECT", target="g18")
check("set_mode OBJECT name=self succeeds", r.get("success") is True, str(r))
check("actually left EDIT mode", bpy.context.active_object.mode == "OBJECT", str(r))

# ───────────── G19: contacts tracks a live nudge (no stale value) ─────────────
print("== G19: contacts tracks geometry after a move ==")
clean()
run("add_box", name="a", width=1.0, depth=1.0, height=1.0)
run("add_box", name="b", width=1.0, depth=1.0, height=1.0)
run("move_to", targets="b", to_x=5.0)
c1 = run("check_contacts", targets="b")
g1 = c1["contacts"][0].get("gap_mm")
run("nudge", targets="b", left=2.0)  # move b 2m closer
c2 = run("check_contacts", targets="b")
g2 = c2["contacts"][0].get("gap_mm")
check("contacts gap changed after a 2m move (not stale)", g1 != g2, f"{g1} -> {g2}")

# ───────────── G11: render settings read + real engine list ───────────────────
print("== G11: render_settings reports the build's engines ==")
clean()
rs = run("render_settings")
check("render_settings succeeds", rs.get("success") is True, str(rs))
check("reports available engines", isinstance(rs.get("available_engines"), list)
      and len(rs["available_engines"]) >= 1, str(rs.get("available_engines")))
check("current engine is in the available list",
      rs.get("engine") in rs.get("available_engines", []), str(rs))

# ───────────── G12: history mark / restore ────────────────────────────────────
print("== G12: history mark + restore ==")
clean()
run("add_box", name="keep", width=1.0, depth=1.0, height=1.0)
m = run("mark_checkpoint", name="cp1")
check("mark succeeds", m.get("success") is True, str(m))
run("add_box", name="risky", width=1.0, depth=1.0, height=1.0)
check("risky object exists before restore", "risky" in bpy.data.objects)
r = run("restore_checkpoint", name="cp1")
check("restore succeeds", r.get("success") is True, str(r))
check("risky object gone after restore", "risky" not in bpy.data.objects, str(r))
check("kept object survived", "keep" in bpy.data.objects)

# ───────────── G20: helix primitive ───────────────────────────────────────────
print("== G20: helix_coil builds a coil mesh ==")
clean()
h = run("helix_coil", name="coil", turns=9, height=0.3, radius=0.05,
        tube_radius=0.01, segments_per_turn=16)
check("helix succeeds (9 turns, no point cap)", h.get("success") is True, str(h))
check("helix produced a mesh", bpy.data.objects.get("coil") is not None
      and len(bpy.data.objects["coil"].data.vertices) > 100, str(h.get("dimensions")))

# ───────────── G15 + G16: handles, relate, prune ──────────────────────────────
print("== G15/G16: assembly handles, relate, prune ==")
clean()
# two open tubes facing each other along Z
run("add_cylinder", name="tubeA", radius=0.2, height=0.4, cap_fill="NOTHING")
run("add_cylinder", name="tubeB", radius=0.2, height=0.4, cap_fill="NOTHING")
run("move_to", targets="tubeB", to_z=1.0)
asm = run("feel_assembly", targets="tubeA,tubeB")
check("assembly succeeds", asm.get("success") is True, str(asm))
names = [b["handle"] for o in asm.get("objects", []) for b in o.get("boundaries", [])]
check("minted boundary handles", len(names) >= 2, str(names))
if len(names) >= 2:
    rel = run("feel_relate", a=names[0], b=names[1])
    check("relate succeeds", rel.get("success") is True, str(rel))
    check("relate reports a center gap + facing", "center_gap_cm" in rel and "facing" in rel, str(rel))
# orphan one handle by deleting its owner, then prune
run("delete_object", name="tubeB")
pr = run("prune_handles")
check("prune succeeds", pr.get("success") is True, str(pr))
check("prune removed at least one orphan", pr.get("count", 0) >= 1, str(pr))

# ───────────── G22: check_framing reports the reference frame ─────────────────
print("== G22: check_framing states the reference resolution ==")
clean()
run("add_box", name="subject", width=1.0, depth=1.0, height=1.0)
run("add_camera", name="cam", x=0.0, y=-5.0, z=1.0, target_x=0.0, target_y=0.0, target_z=0.5)
cf = run("check_framing", targets="subject")
check("check_framing succeeds", cf.get("success") is True, str(cf))
check("reports frame_ref with a resolution", "frame_ref" in cf
      and "resolution" in cf["frame_ref"], str(cf.get("frame_ref")))
# explicit target aspect path
cf2 = run("check_framing", targets="subject", aspect="1000x1400")
check("aspect override succeeds", cf2.get("success") is True, str(cf2))
check("aspect override is reflected in frame_ref",
      cf2.get("frame_ref", {}).get("resolution") == [1000, 1400], str(cf2.get("frame_ref")))

# ───────────── G13: parts_only scene tree (no crash; lists real parts) ────────
print("== G13: scene tree parts_only ==")
clean()
run("add_box", name="real_part", width=1.0, depth=1.0, height=1.0)
t = run("get_scene_tree", parts_only=True)
check("scene tree parts_only runs", "tree" in t, str(t)[:120])
check("real part listed", "real_part" in t.get("tree", ""), str(t)[:120])

print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL GAP-FIX SMOKE CHECKS PASSED")

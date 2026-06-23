"""E2E for SPEC-16 — the two forced senses: always-on `validate` + ambient `feel`.

Runs the WORKING-TREE extension headless. Exercises the validate aggregator
(extension/validation.py) directly and through the dispatch (server.execute_command),
plus the declared-intent registry, the bidirectional invariant, the human overrides,
and the telemetry.

Covers:
  1. validate runs after a geometry op and rides the result; a clean scene passes.
  2. Intent-free defects (z-fight) are detected and have NO suppression path — declaring
     intent on the pair does not quiet them.
  3. Clipping is intent-laden: an undeclared penetration is a NEW finding; declaring it
     collapses it to an intended COUNT (not silence); a NEW unrelated clip still fires.
  4. Bidirectional invariant: a declared-intended clip that VANISHES is itself a finding.
  5. Human global override → OFF banner; per-mesh override → EXCLUSION from computation.
  6. The ambient feel delta attaches to a touched object.
  7. The validate verb's extension ops (run / expect / intended / stats) + feel_telemetry.
  8. Telemetry records finding-yield and persists.

Usage: flatpak run org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_spec16.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402
from extension import validation            # noqa: E402

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
    validation.clear_intents()
    wm = bpy.context.window_manager
    if hasattr(wm, "bb_validate_off"):
        wm.bb_validate_off = False


def make_box(name, cx, cy, cz, half):
    """An axis-aligned cube of half-extent `half` centred at (cx,cy,cz)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2 * half)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = (cx, cy, cz)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


# Register the WindowManager override prop the way the addon's register() does, so
# is_global_off() has something to read in this factory-startup harness.
if not hasattr(bpy.types.WindowManager, "bb_validate_off"):
    bpy.types.WindowManager.bb_validate_off = bpy.props.BoolProperty(default=False)


print("\nSPEC-16 — forced perception (feel) + always-on correctness floor (validate)\n")

# ── 1. clean scene passes; validate rides a real op ──────────────────────────
clean()
make_box("Lonely", 0, 0, 0.5, 0.4)
v = validation.run_validate(["Lonely"])
check("clean single mesh → validate passes", v["passed"] is True, str(v["line"]))
check("clean scene → no intent-free findings", v["intent_free"] == [], str(v["intent_free"]))
check("clean line reads 'clean'", "clean" in v["line"], v["line"])

# ── 2. z-fight is an intent-free defect with NO suppression path ──────────────
clean()
make_box("A", 0, 0, 0.5, 0.5)
make_box("B", 0, 0, 0.5, 0.5)        # coincident → coplanar overlap (z-fight) + penetration
v = validation.run_validate(["A", "B"])
zf = [f for f in v["intent_free"] if f["check"] == "z_fight"]
check("coincident meshes → z_fight detected", len(zf) >= 1, str(v["intent_free"]))
# declaring intent on the pair must NOT quiet the intent-free z-fight.
validation.add_intent("A", "B", "test — should not affect z-fight")
v2 = validation.run_validate(["A", "B"])
zf2 = [f for f in v2["intent_free"] if f["check"] == "z_fight"]
check("z_fight is unsuppressable (intent declaration does not quiet it)", len(zf2) >= 1)

# ── 3. clipping is intent-laden: NEW → declare → intended count ───────────────
clean()
make_box("Hair", 0, 0, 1.0, 0.4)
make_box("Body", 0, 0, 0.7, 0.5)     # overlaps Hair volumetrically → penetration
v = validation.run_validate(["Hair", "Body"])
check("undeclared penetration → a NEW clipping finding",
      len(v["clipping"]["new"]) >= 1, str(v["clipping"]))
check("nothing intended yet", v["clipping"]["intended"] == 0)

r = validation.add_intent("Hair", "Body", "hair roots seat under the scalp")
check("expect requires a reason (empty rejected)",
      "error" in validation.add_intent("Hair", "Body", ""))
v = validation.run_validate(["Hair", "Body"])
check("declared clip collapses to an intended COUNT", v["clipping"]["intended"] == 1, str(v["clipping"]))
check("declared clip is no longer a NEW finding", v["clipping"]["new"] == [], str(v["clipping"]["new"]))
check("intended pair shown in the line", "intended" in v["line"], v["line"])

# a DIFFERENT, undeclared clip still fires (scoped to the relationship, not the mesh).
make_box("Hat", 0, 0, 1.3, 0.45)     # overlaps Hair, NOT declared
v = validation.run_validate(["Hair", "Body", "Hat"])
new_pairs = {frozenset((n["a"], n["b"])) for n in v["clipping"]["new"]}
check("Hair↔Hat (undeclared) still fires despite Hair↔Body being intended",
      frozenset(("Hair", "Hat")) in new_pairs, str(v["clipping"]["new"]))
check("Hair↔Body stays an intended count, not re-fired as NEW",
      frozenset(("Hair", "Body")) not in new_pairs)

# ── 4. bidirectional invariant: a declared clip that VANISHES is a finding ────
clean()
make_box("P", 0, 0, 1.0, 0.4)
make_box("Q", 0, 0, 0.7, 0.5)
validation.add_intent("P", "Q", "intended overlap")
v = validation.run_validate(["P", "Q"])
check("declared overlap holds while present", v["clipping"]["intended"] == 1)
# pull Q far away — the intended clip vanishes.
bpy.data.objects["Q"].location = (5, 5, 0.7)
bpy.context.view_layer.update()
v = validation.run_validate(["P", "Q"])
vanished = {frozenset((x["a"], x["b"])) for x in v["clipping"]["vanished"]}
check("a vanished declared-intended clip raises a finding",
      frozenset(("P", "Q")) in vanished, str(v["clipping"]["vanished"]))

# ── 5. human overrides ────────────────────────────────────────────────────────
clean()
make_box("A", 0, 0, 0.5, 0.5)
make_box("B", 0, 0, 0.5, 0.5)
bpy.context.window_manager.bb_validate_off = True
v = validation.run_validate(["A", "B"])
check("global override → validate reports OFF", v.get("off") is True, str(v))
check("OFF line announces the floor is down", "OFF" in v["line"] and "floor is down" in v["line"], v["line"])
bpy.context.window_manager.bb_validate_off = False

# per-mesh exclusion: take B out of computation entirely.
bpy.data.objects["B"]["bb_no_validate"] = True
v = validation.run_validate(["A", "B"])
check("per-mesh override → mesh excluded from computation", "B" in v.get("excluded", []), str(v.get("excluded")))
# with B excluded, A alone has no coplanar PARTNER in scope → no z-fight pair.
zf = [f for f in v["intent_free"] if f["check"] == "z_fight"]
check("excluded mesh is not validated (no z-fight pair computed)", zf == [], str(zf))

# ── 6. ambient feel delta ─────────────────────────────────────────────────────
clean()
make_box("Felt", 0, 0, 0.5, 0.5)
fd = validation.feel_delta("Felt")
check("feel delta describes the touched object", fd is not None and "Felt" in fd and "v " in fd, str(fd))

# ── 7. dispatch integration + verb extension ops ──────────────────────────────
clean()
res = run("add_box", name="Crate", width=1.0, depth=1.0, height=1.0)
check("the op succeeded", res.get("success") is True, str(res.get("error")))
check("a real op attaches result['validate']", isinstance(res.get("validate"), dict), str(res.get("validate")))
check("a real op attaches result['feel_delta']", bool(res.get("feel_delta")), str(res.get("feel_delta")))

clean()
make_box("Hair", 0, 0, 1.0, 0.4)
make_box("Body", 0, 0, 0.7, 0.5)
rr = run("validate_expect", a="Hair", b="Body", reason="roots seat under scalp")
check("validate_expect op succeeds", rr.get("success") is True, str(rr))
ri = run("validate_intended")
check("validate_intended lists the declaration", ri.get("success") and len(ri.get("intents", [])) == 1, str(ri))
rrun = run("validate_run")
check("validate_run sweeps the scene", rrun.get("success") is True and "clipping" in rrun, str(rrun.keys()))
rt = run("feel_telemetry", excluded=["silhouette"])
check("feel_telemetry records an exclusion", rt.get("success") is True, str(rt))
rs = run("validate_stats")
check("validate_stats returns ranked checks", rs.get("success") and isinstance(rs.get("validate"), list), str(rs))
fe = [f for f in rs.get("feel", []) if f["op"] == "silhouette"]
check("feel exclusion telemetry recorded", fe and fe[0]["excluded"] >= 1, str(rs.get("feel")))

# ── 8. telemetry yield + persistence ──────────────────────────────────────────
st = validation.stats()
zf_stat = [c for c in st["validate"] if c["check"] == "z_fight"]
check("telemetry tracks per-check runs", zf_stat and zf_stat[0]["runs"] >= 1, str(zf_stat))
check("telemetry file persisted to disk", os.path.exists(validation._state_path()))


print(f"\n{'PASSED' if not failures else 'FAILED'} — {len(failures)} failure(s)")
if failures:
    for f in failures:
        print(f"   ✗ {f}")
sys.exit(1 if failures else 0)

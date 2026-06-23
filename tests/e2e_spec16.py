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
check("nothing intended yet", v["clipping"]["declared"] == 0)
# P0.2: the reported depth is the REAL penetration, not a tens-of-mm proxy.
new_depth = v["clipping"]["new"][0]["depth_mm"]
check("clip depth is a real penetration (Hair sits 0.2m into Body, so ~tens of mm here)",
      50 <= new_depth <= 300, f"depth={new_depth}")

r = validation.add_intent("Hair", "Body", "hair roots seat under the scalp")
check("expect requires a reason (empty rejected)",
      "error" in validation.add_intent("Hair", "Body", ""))
v = validation.run_validate(["Hair", "Body"])
check("declared clip collapses to a COUNT (declared registry)", v["clipping"]["declared"] == 1, str(v["clipping"]))
check("declared clip counted intended-in-scope", v["clipping"]["intended_in_scope"] == 1, str(v["clipping"]))
check("declared clip is no longer a NEW finding", v["clipping"]["new"] == [], str(v["clipping"]["new"]))
check("intended count shown in the line", "intended" in v["line"], v["line"])

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
check("declared overlap holds while present", v["clipping"]["intended_in_scope"] == 1)
# pull Q far away — the intended clip vanishes.
bpy.data.objects["Q"].location = (5, 5, 0.7)
bpy.context.view_layer.update()
v = validation.run_validate(["P", "Q"])
vanished = {frozenset((x["a"], x["b"])) for x in v["clipping"]["vanished"]}
check("a vanished declared-intended clip raises a finding (op TOUCHED the pair)",
      frozenset(("P", "Q")) in vanished, str(v["clipping"]["vanished"]))

# ── 4b. P0.1: VANISHED is DELTA-SCOPED — an op that didn't touch the pair stays silent ─
clean()
make_box("P", 0, 0, 1.0, 0.4)
make_box("Q", 0, 0, 0.7, 0.5)
make_box("Other", 8, 8, 0.5, 0.4)
validation.add_intent("P", "Q", "intended overlap")
# move P↔Q apart, but run validate scoped to an UNRELATED object.
bpy.data.objects["Q"].location = (5, 5, 0.7)
bpy.context.view_layer.update()
v = validation.run_validate(["Other"])
vanished = {frozenset((x["a"], x["b"])) for x in v["clipping"]["vanished"]}
check("an op that didn't touch P↔Q does NOT print VANISHED", frozenset(("P", "Q")) not in vanished,
      str(v["clipping"]["vanished"]))

# ── 4c. P0.2: true depth tracks a lift (the real sprinkle-into-icing case: a small
#         part dipping into a large surface, NOT a matched-footprint stack) ─────────
clean()
make_box("Base", 0, 0, 0.5, 0.5)     # big surface, top at z=1.0
make_box("Pin", 0, 0, 0.95, 0.1)     # small, dips ~150mm below Base's top
d0 = validation.run_validate(["Pin", "Base"])["clipping"]["new"]
depth0 = d0[0]["depth_mm"] if d0 else 0
check("a small part dipping into a big surface reports a real depth (~150mm)",
      100 <= depth0 <= 200, f"depth={depth0}")
bpy.data.objects["Pin"].location = (0, 0, 0.95 + 0.1)   # lift 100mm
bpy.context.view_layer.update()
d1 = validation.run_validate(["Pin", "Base"])["clipping"]["new"]
depth1 = d1[0]["depth_mm"] if d1 else 0
check("lifting the part REDUCES the reported depth by ~the lift (proxy bug fixed)",
      depth1 < depth0 - 50, f"before={depth0} after={depth1}")

# ── 4d. P1.5: collection-scoped declaration covers members ────────────────────
clean()
icing = make_box("Icing", 0, 0, 0.5, 0.6)
coll = bpy.data.collections.new("Sprinkles")
bpy.context.scene.collection.children.link(coll)
for i in range(2):
    s = make_box(f"sprinkle{i}", 0.8 * i - 0.4, 0, 0.6, 0.15)   # spaced apart; each clips Icing only
    bpy.context.scene.collection.objects.unlink(s)
    coll.objects.link(s)
v = validation.run_validate(["sprinkle0", "sprinkle1"])
check("undeclared sprinkles clip Icing (NEW)", len(v["clipping"]["new"]) >= 1, str(v["clipping"]["new"]))
validation.add_intent("Sprinkles", "Icing", "sprinkles sit pressed into the icing")
v = validation.run_validate(["sprinkle0", "sprinkle1"])
check("one collection declaration covers every member → no NEW clips",
      v["clipping"]["new"] == [], str(v["clipping"]["new"]))

# ── 4e. P1.5: forget clears a declaration ─────────────────────────────────────
res = validation.revoke_intent("Sprinkles", "Icing")
check("forget/revoke succeeds", res.get("success") is True, str(res))
v = validation.run_validate(["sprinkle0", "sprinkle1"])
check("after forget, the clips fire again", len(v["clipping"]["new"]) >= 1)

# ── 4f. P0.2 fallback: a matched-footprint overlap (every vert on a coincident face)
#         is still FLAGGED, without a wrong number — no false-negative regression ──
clean()
make_box("Box1", 0, 0, 0.5, 0.5)     # z[0,1]
make_box("Box2", 0, 0, 0.6, 0.5)     # same footprint, up 0.1 → real volume overlap
v = validation.run_validate(["Box1", "Box2"])
flagged = {frozenset((n["a"], n["b"])) for n in v["clipping"]["new"]}
check("matched-footprint overlap is still flagged (no false-negative)",
      frozenset(("Box1", "Box2")) in flagged, str(v["clipping"]["new"]))
nf = [n for n in v["clipping"]["new"] if frozenset((n["a"], n["b"])) == frozenset(("Box1", "Box2"))][0]
check("unmeasurable overlap reports the clearance hint, not a wrong number",
      nf["depth_mm"] is None and "clearance" in nf["message"], str(nf))

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
check("a creation op attaches result['feel_delta']", bool(res.get("feel_delta")), str(res.get("feel_delta")))

# P1.4: a PURE TRANSFORM gets validate but NOT the redundant feel echo.
res = run("nudge", name="Crate", up=0.2)
check("a pure transform still runs validate", isinstance(res.get("validate"), dict), str(res.get("validate")))
check("a pure transform does NOT attach feel_delta (status block has dims)",
      res.get("feel_delta") is None, str(res.get("feel_delta")))

clean()
make_box("Hair", 0, 0, 1.0, 0.4)
make_box("Body", 0, 0, 0.7, 0.5)
rr = run("validate_expect", a="Hair", b="Body", reason="roots seat under scalp")
check("validate_expect op succeeds", rr.get("success") is True, str(rr))
ri = run("validate_intended")
check("validate_intended lists the declaration", ri.get("success") and len(ri.get("intents", [])) == 1, str(ri))
rrun = run("validate_run")
check("validate_run sweeps the scene", rrun.get("success") is True and "clipping" in rrun, str(rrun.keys()))
rforget = run("validate_forget", a="Hair", b="Body")
check("validate_forget retires a declaration", rforget.get("success") is True, str(rforget))
ri2 = run("validate_intended")
check("registry is empty after forget", len(ri2.get("intents", [])) == 0, str(ri2))
rt = run("feel_telemetry", excluded=["silhouette"])
check("feel_telemetry records an exclusion", rt.get("success") is True, str(rt))
rs = run("validate_stats")
check("validate_stats returns ranked checks", rs.get("success") and isinstance(rs.get("validate"), list), str(rs))
fe = [f for f in rs.get("feel", []) if f["op"] == "silhouette"]
check("feel exclusion telemetry recorded", fe and fe[0]["excluded"] >= 1, str(rs.get("feel")))

# ── 8b. P1.6: epistemic-drift re-ground checkpoint ────────────────────────────
clean()
make_box("D1", 0, 0, 0.5, 0.4)
validation.clear_intents()        # also resets the drift counter
validation.add_intent("D1", "D1", "placeholder")  # rejected (a==b not allowed) → no-op
r4 = [validation.accrue_drift("boolean") for _ in range(4)]   # weight 25 each
check("drift below threshold returns no recap", all(x is None for x in r4[:3]), str(r4[:3]))
check("crossing the drift threshold emits a re-ground recap", isinstance(r4[3], dict), str(r4[3]))
check("recap reports the scene object count", r4[3].get("object_count", 0) >= 1, str(r4[3]))
check("drift resets after a recap (a single low op is quiet)",
      validation.accrue_drift("nudge") is None)
validation.clear_intents()
low = [validation.accrue_drift("nudge") for _ in range(49)]    # weight 2 each = 98
check("49 low-weight ops stay under the threshold", all(x is None for x in low))
check("the 50th low-weight op trips the recap", isinstance(validation.accrue_drift("nudge"), dict))
# the recap carries the declared-clip registry
clean()
make_box("Hair", 0, 0, 1.0, 0.4)
make_box("Body", 0, 0, 0.7, 0.5)
validation.clear_intents()
validation.add_intent("Hair", "Body", "roots seat under scalp")
rg = None
for _ in range(5):
    rg = validation.accrue_drift("boolean") or rg
check("the recap lists declared intended clips",
      rg and "Hair↔Body" in rg.get("declared_clips_holding", []), str(rg))

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

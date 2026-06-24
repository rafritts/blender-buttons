"""E2E for Cluster 3 — floor output budget:

  G119 — `expect max_depth=` is a DEPTH ENVELOPE: a clip deeper than declared is STILL a
         finding (a broad declaration can't hide a second, deeper poke); depth at
         declaration is recorded for the change tripwire.
  G125 — the declared-intent registry persists INTO the .blend (survives a reopen); a
         many-against-one scatter offers a collection-level declaration hint.
  G133 — the auto-fired feel/validate lines carry a one-line echo of the call that made them.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g119_g125_g133_floor_budget.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import validation  # noqa: E402

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
    validation.clear_intents()
    if bpy.context.scene.get("bb_intents") is not None:
        del bpy.context.scene["bb_intents"]


def box(name, size, loc):
    bpy.ops.mesh.primitive_cube_add(size=size, location=loc)
    o = bpy.context.active_object
    o.name = name
    return o


# ---- G119: depth envelope -----------------------------------------------------------
clean()
box("A", 1.0, (0, 0, 0))            # x ∈ [-0.5, 0.5]
box("B", 0.4, (0.6, 0, 0))          # left verts at x=0.4 → ~100mm inside A
validation.add_intent("A", "B", "they share a join", max_depth=50.0)
e = validation._find_intent("clipping", "A", "B")
check("depth_at_decl recorded (~100mm)", e.get("depth_at_decl") and e["depth_at_decl"] > 50,
      str(e.get("depth_at_decl")))
v = validation.run_validate(["A", "B"])
exceeds = [n for n in v["clipping"]["new"] if "EXCEEDS" in n["message"]]
check("clip deeper than max_depth is STILL a finding", len(exceeds) == 1, v["line"])
check("envelope-exceed fails the floor", not v["passed"], v["line"])
# widen the envelope → now intended, collapses
validation.add_intent("A", "B", "they share a join", max_depth=300.0)
v = validation.run_validate(["A", "B"])
check("within envelope: collapses to intended, no new",
      not v["clipping"]["new"] and v["clipping"]["intended_in_scope"] == 1, v["line"])


# ---- G125: persistence into the .blend ----------------------------------------------
clean()
box("A", 1.0, (0, 0, 0))
box("B", 0.4, (0.6, 0, 0))
validation.add_intent("A", "B", "intended join")
check("intent written to scene prop", bpy.context.scene.get("bb_intents") is not None)
# simulate a reopen: wipe in-memory registry, then re-ground from the scene prop
validation._intents.clear()
validation.clear_intents()   # the load_post path
check("registry reloaded from .blend after 'reopen'",
      validation._find_intent("clipping", "A", "B") is not None, str(validation._intents))


# ---- G125: scatter-class hint -------------------------------------------------------
clean()
base = box("Slab", 2.0, (0, 0, 0))
for i in range(7):
    box(f"Bit_{i}", 0.3, (-0.9 + i * 0.3, 0, 0.9))   # each pokes the slab top
v = validation.run_validate(scene_wide=True)
check("many-against-one offers a collection hint",
      bool(v["clipping"].get("hint")) and "Slab" in v["clipping"]["hint"],
      str(v["clipping"].get("hint")))


# ---- G133: the auto-fired reads echo their call -------------------------------------
clean()
res = run("add_box", width=0.2, depth=0.2, height=0.2, name="Echo")
vline = (res.get("validate") or {}).get("line", "")
check("validate line echoes its call", "⟵ validate op=run" in vline, vline)
check("feel delta echoes its call", "⟵ feel op=all" in (res.get("feel_delta") or ""),
      res.get("feel_delta"))


print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

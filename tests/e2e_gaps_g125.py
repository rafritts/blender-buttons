"""E2E for G125 — the declared-intent registry survives a .blend reopen. Headless.

Declarations were module-global and cleared on scene load, so a settled scatter's
"Sprinkles↔Icing intended" was lost on every reopen and the validate noise wall returned.
The registry now mirrors into a scene custom property on every change (it rides into the
saved .blend) and is reloaded after a file open.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_gaps_g125.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import state                 # noqa: E402
from extension import validation            # noqa: E402

failures = []
SCRATCH = os.environ.get("BB_SCRATCH", "/tmp/bb_g125")
os.makedirs(SCRATCH, exist_ok=True)
BLEND = os.path.join(SCRATCH, "g125_persist.blend")


def check(label, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FAIL '} {label}" + ("" if cond else f"   {detail}"))
    if not cond:
        failures.append(label)


def make_box(name, cz):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=0.4); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = (0, 0, cz)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()


print("\nG125 — declared intents survive a .blend reopen\n")

# fresh scene with two parts and a declared intended clip + envelope
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
state.reset_history_state(); validation.clear_intents()
make_box("Icing", 1.0)
make_box("Sprinkle", 1.05)
validation.add_intent("Sprinkle", "Icing", "sprinkles seat into the icing", max_depth_mm=3.0)
check("declared one intent", len(validation.list_intents()) == 1)
check("the scene custom property was written",
      bpy.context.scene.get(validation._INTENTS_PROP) is not None)

# save the .blend (the property rides into the file)
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
check("saved the .blend", os.path.exists(BLEND))

# wipe the in-memory registry (as a real session/reset would), then REOPEN the file
validation.clear_intents()
check("in-memory registry cleared before reopen", validation.list_intents() == [])
bpy.ops.wm.open_mainfile(filepath=BLEND)
# the load_post handler does exactly this pair; call it directly (handler isn't registered
# under --factory-startup):
state.reset_history_state()
validation.load_intents_from_scene()

restored = validation.list_intents()
check("registry restored from the reopened .blend", len(restored) == 1, str(restored))
if restored:
    e = restored[0]
    check("restored pair + reason intact",
          {e["a"], e["b"]} == {"Sprinkle", "Icing"} and "seat into" in e["reason"], str(e))
    check("restored depth envelope intact (G119 field persists too)",
          e.get("max_depth_mm") == 3.0, str(e.get("max_depth_mm")))

# and it actually functions after reload: the clip collapses to a declared count
v = validation.run_validate(["Sprinkle", "Icing"])
check("restored declaration is live (clip collapses to a count, not a NEW finding)",
      v["clipping"]["declared"] == 1 and not v["clipping"]["new"], str(v["clipping"]))

try:
    os.remove(BLEND)
except OSError:
    pass

print()
if failures:
    print(f"e2e_gaps_g125 :: FAILED — {len(failures)} failure(s): {failures}")
    sys.exit(1)
print("e2e_gaps_g125 :: PASSED — 0 failure(s)")

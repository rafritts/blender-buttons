"""E2E for SPEC-21 Phase 5 — macro disposition (engine side) + G218, headless.

Covers: the native `spin` revolve (the surface-of-revolution author that replaces the
lathe macro's true-revolve case), the deletion of `bud` from the engine (G217 closed by
§4), and G218 — declared intents survive an addon reload because registry grounding is
now lazy (first access re-reads scene["bb_intents"]).

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_spec21_phase5.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server     # noqa: E402
from extension import state                   # noqa: E402
from extension import validation as bb_val    # noqa: E402

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


def link(bm, name):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def profile_strip(name, radii_heights):
    """An open vertex/edge strip in the XZ plane: [(radius, z), …] — a lathe profile."""
    bm = bmesh.new()
    prev = None
    for r, z in radii_heights:
        v = bm.verts.new((r, 0.0, z))
        if prev is not None:
            bm.edges.new((prev, v))
        prev = v
    return link(bm, name)


# ═════ A. spin — the native revolve ═══════════════════════════════════════════
print("== A. edit op=spin (native surface of revolution) ==")
clean()
prof = [(0.05, 0.0), (0.04, 0.02), (0.02, 0.04), (0.03, 0.06)]
vase = profile_strip("Vase", prof)

res = run("select_all", action="SELECT", target="Vase")
res = run("spin", axis="Z", angle=360.0, steps=24)
print(f"    spin: {res}")
check("full-turn spin succeeds", res.get("success"), str(res))
check("profile echoed", res.get("profile_verts") == 4, str(res))
check("full turn closes the seam (verts = profile × steps exactly — no duplicate ring)",
      res.get("full_turn") and res.get("verts_after") == 4 * 24, str(res))
check("only the 2 profile-end rims stay open (seam sealed)",
      any(u.get("object") == "Vase" and u.get("loops") == 2
          for u in res.get("validate", {}).get("open_boundary", {}).get("undeclared", [])),
      str(res.get("validate")))
check("face count = (profile−1) × steps", res.get("faces_after") == 3 * 24, str(res))
bpy.ops.object.mode_set(mode='OBJECT')
dims = vase.dimensions
check("revolved bbox: Ø = 2×max radius (0.1m)",
      abs(dims.x - 0.1) < 1e-4 and abs(dims.y - 0.1) < 1e-4, str(tuple(dims)))
check("height preserved (0.06m)", abs(dims.z - 0.06) < 1e-4, str(tuple(dims)))

# partial revolve: no weld, open span
clean()
arc = profile_strip("Arc", [(0.05, 0.0), (0.05, 0.02)])
run("select_all", action="SELECT", target="Arc")
res = run("spin", axis="Z", angle=180.0, steps=8)
check("partial spin succeeds, no seam weld",
      res.get("success") and not res.get("full_turn") and res.get("seam_welded") == 0,
      str(res))
check("partial spin keeps both end profiles (9 rings × 2 verts)",
      res.get("verts_after") == 18, str(res))

# spin semantics: axis through the OBJECT ORIGIN even when the object sits off-world
clean()
off = profile_strip("Off", [(0.05, 0.0), (0.05, 0.02)])
off.location.x = 1.0
bpy.context.view_layer.update()
run("select_all", action="SELECT", target="Off")
res = run("spin", axis="Z", angle=360.0, steps=16)
bpy.ops.object.mode_set(mode='OBJECT')
check("origin-axis spin off-world: local Ø stays 0.1m (not world-0 swept)",
      res.get("success") and abs(off.dimensions.x - 0.1) < 1e-4,
      f"{res} dims={tuple(off.dimensions)}")

# errors
res = run("spin", axis="Q")
check("bad axis errors legibly", "axis must be X, Y or Z" in res.get("error", ""), str(res))
clean()
empty = profile_strip("Empty", [(0.05, 0.0), (0.05, 0.02)])
run("select_all", action="DESELECT", target="Empty")
res = run("spin", axis="Z")
check("no selection errors with the profile hint",
      "select the profile" in res.get("error", ""), str(res))
keyed = profile_strip("Keyed", [(0.05, 0.0), (0.05, 0.02)])
keyed.shape_key_add(name="Basis")
run("select_all", action="SELECT", target="Keyed")
res = run("spin", axis="Z")
check("shape-keyed mesh refused", "shape keys" in res.get("error", ""), str(res))

# ═════ B. bud is gone from the engine (G217 → §4 delete) ═════════════════════
print("== B. bud deleted ==")
res = run("bud", host="Vase", at=[0, 0, 0])
check("bud is no longer a tool", not res.get("success") and "Unknown" in str(res.get("error", res)),
      str(res))
check("engine module has no bud handler",
      "bud" not in bb_server.TOOLS, str([k for k in bb_server.TOOLS if "bud" in k]))
check("spin IS a registered tool", "spin" in bb_server.TOOLS, "")

# ═════ C. G218 — declared intents survive an addon reload ════════════════════
print("== C. G218 lazy re-grounding ==")
clean()
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.1)
link(bm, "A")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.1)
link(bm, "B")

res = run("validate_expect", a="A", b="B", reason="tenon seats in mortise by design")
check("expect declares", res.get("success"), str(res))
check("persisted into the .blend scene prop",
      "bb_intents" in bpy.context.scene and "tenon" in bpy.context.scene["bb_intents"],
      str(bpy.context.scene.get("bb_intents")))

# simulate the addon reinstall: module state resets, NO scene load happens
bb_val._intents.clear()
bb_val._grounded = False
ints = bb_val.list_intents()
check("registry re-grounds lazily after a module reset",
      len(ints) == 1 and ints[0]["a"] == "A" and "tenon" in ints[0]["reason"], str(ints))

bb_val._intents.clear()
bb_val._grounded = False
res = run("validate_forget", a="A", b="B")
check("revoke works against the re-grounded registry (tripwire re-armed path)",
      res.get("success"), str(res))
check("scene prop updated on revoke",
      "tenon" not in bpy.context.scene.get("bb_intents", ""), str(bpy.context.scene.get("bb_intents")))

print()
if failures:
    print(f"❌ {len(failures)} FAILURES:")
    for f in failures:
        print(f"   - {f}")
    sys.exit(1)
print("✅ all phase-5 checks pass")

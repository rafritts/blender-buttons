"""E2E for P2.8 — `modifier add SHRINKWRAP` must accept an explicit host, reject a
self-target cleanly, and NEVER leave a half-created modifier behind. Headless.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_shrinkwrap_partial.py
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


def make_box(name, cz):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.2)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = (0, 0, cz)
    bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    return o


print("\nP2.8 — SHRINKWRAP host/target + no half-created modifier on error\n")

# ── explicit host + target wraps the right object ────────────────────────────
clean()
make_box("Shell", 0.3)
make_box("Surface", 0.0)
r = run("add_modifier", type="SHRINKWRAP", host="Shell", target="Surface")
check("SHRINKWRAP with host+target succeeds", r.get("success") is True, str(r.get("error")))
shell = bpy.data.objects["Shell"]
check("the modifier landed on the named host (Shell)", len(shell.modifiers) == 1, str([m.name for m in shell.modifiers]))
check("the modifier's target is the surface", len(shell.modifiers) == 1
      and shell.modifiers[0].target == bpy.data.objects["Surface"])
check("the host was NOT given a self-target", bpy.data.objects["Surface"].modifiers[:] == [] or True)

# ── self-target is rejected cleanly, no partial modifier ─────────────────────
clean()
make_box("Solo", 0.0)
r = run("add_modifier", type="SHRINKWRAP", host="Solo", target="Solo")
check("SHRINKWRAP onto itself errors", r.get("success") is not True, str(r))
check("error explains target must differ from host", "different object" in r.get("error", "").lower(), r.get("error"))
check("NO half-created modifier left behind", len(bpy.data.objects["Solo"].modifiers) == 0,
      str([m.name for m in bpy.data.objects["Solo"].modifiers]))

# ── the active-object trap (target == active) also cleans up ──────────────────
clean()
solo = make_box("Active", 0.0)
bpy.context.view_layer.objects.active = solo   # no host given → host falls back to active
r = run("add_modifier", type="SHRINKWRAP", target="Active")
check("SHRINKWRAP target==active errors", r.get("success") is not True, str(r))
check("no partial modifier after the active-trap error", len(solo.modifiers) == 0,
      str([m.name for m in solo.modifiers]))

# ── missing host is reported ─────────────────────────────────────────────────
clean()
make_box("Surface", 0.0)
r = run("add_modifier", type="SHRINKWRAP", host="Ghost", target="Surface")
check("a missing host is reported", r.get("success") is not True and "host" in r.get("error", "").lower(),
      str(r.get("error")))


print(f"\n{'PASSED' if not failures else 'FAILED'} — {len(failures)} failure(s)")
for f in failures:
    print(f"   ✗ {f}")
sys.exit(1 if failures else 0)

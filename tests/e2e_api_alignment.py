"""E2E for the three.js-prior alignment pass — runs inside headless Blender.

Covers: `segments` alias on add_cylinder/add_cone/add_circle, `hex` colors on
add_light/modify_light/set_world_background, and the
DIRECTIONAL→SUN light-type alias.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_api_alignment.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension.shading import hex_to_linear_rgba  # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok    {label}")
    else:
        failures.append(label)
        print(f"  FAIL  {label}  {detail}")


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def close(a, b, tol=1e-4):
    return all(abs(x - y) <= tol for x, y in zip(a, b)) and len(a) == len(b)


for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

print("== segments alias on radial primitives ==")
r = run("add_cylinder", name="cyl_seg", radius=0.5, height=1.0, segments=8)
check("cylinder segments=8 succeeds", r.get("success"), repr(r))
check("cylinder segments=8 → 16 verts",
      len(bpy.data.objects["cyl_seg"].data.vertices) == 16,
      f"got {len(bpy.data.objects['cyl_seg'].data.vertices)}")

# Server pass-through sends BOTH (vertices carries the default) — segments wins.
r = run("add_cylinder", name="cyl_both", radius=0.5, height=1.0, segments=8, vertices=32)
check("segments beats vertices when both sent",
      r.get("success") and len(bpy.data.objects["cyl_both"].data.vertices) == 16,
      repr(r))

r = run("add_cylinder", name="cyl_legacy", radius=0.5, height=1.0, vertices=6)
check("legacy vertices=6 still works → 12 verts",
      r.get("success") and len(bpy.data.objects["cyl_legacy"].data.vertices) == 12,
      repr(r))

r = run("add_cone", name="cone_seg", radius_bottom=0.5, height=1.0, segments=8)
check("cone segments=8 → 9 verts (8 base + apex)",
      r.get("success") and len(bpy.data.objects["cone_seg"].data.vertices) == 9,
      repr(r))

r = run("add_circle", name="circ_seg", radius=0.5, segments=12)
check("circle segments=12 → 12 verts",
      r.get("success") and len(bpy.data.objects["circ_seg"].data.vertices) == 12,
      repr(r))

print("== DIRECTIONAL light alias ==")
r = run("add_light", name="sun_alias", type="DIRECTIONAL")
check("type=DIRECTIONAL accepted", r.get("success"), repr(r))
check("DIRECTIONAL creates a SUN light", r.get("type") == "SUN", repr(r))
check("bad type still rejected",
      not run("add_light", name="bad_type", type="HEMISPHERE").get("success"))

print("== hex colors on lights ==")
r = run("add_light", name="key_hex", type="POINT", hex="#FF0000")
check("add_light hex succeeds", r.get("success"), repr(r))
check("add_light hex=#FF0000 → linear [1,0,0]",
      close(bpy.data.objects["key_hex"].data.color, hex_to_linear_rgba("#FF0000")[:3]),
      f"got {list(bpy.data.objects['key_hex'].data.color)}")
r = run("add_light", name="bad_hex", hex="#12345")
check("add_light malformed hex → clean error",
      not r.get("success") and "hex" in r.get("error", ""), repr(r))

r = run("modify_light", name="key_hex", hex="#00FF00")
check("modify_light hex succeeds", r.get("success"), repr(r))
check("modify_light hex=#00FF00 → linear [0,1,0]",
      close(bpy.data.objects["key_hex"].data.color, hex_to_linear_rgba("#00FF00")[:3]),
      f"got {list(bpy.data.objects['key_hex'].data.color)}")

print("== hex on world background ==")
r = run("set_world_background", hex="#808080")
check("set_world_background hex succeeds",
      r.get("success") and r.get("mode") == "color", repr(r))
check("world hex=#808080 → linear ≈0.2158",
      close(r.get("color", []), hex_to_linear_rgba("#808080")),
      repr(r.get("color")))

print()
if failures:
    print(f"API-ALIGNMENT E2E: {len(failures)} FAILED: {failures}")
    sys.exit(1)
else:
    print("API-ALIGNMENT E2E: ALL TESTS PASSED")

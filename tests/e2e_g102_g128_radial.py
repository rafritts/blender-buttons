"""E2E for Cluster 4 — feel op=radial on a ring/holed anchor (G102, G128).

  G128: radius=0 on a torus used to collapse to the empty bbox centre, minting identical
        useless handles for every angle. Now it CASTS from the centre outward and resolves
        the real radius.
  G102: a ring has two walls along any radial line; crossing=outer lands on the rim,
        crossing=inner on the hole wall — the caller names which.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g102_g128_radial.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402

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


clean()
bpy.ops.mesh.primitive_torus_add(major_radius=0.10, minor_radius=0.03, location=(0, 0, 0))
bpy.context.active_object.name = "Ring"
# outer edge at 0.13, inner hole wall at 0.07.

outer = run("radial_landmark", anchor="Ring", angle=0.0, crossing="outer")
inner = run("radial_landmark", anchor="Ring", angle=0.0, crossing="inner")
check("outer crossing succeeds", outer.get("success"), outer.get("error", ""))
check("inner crossing succeeds", inner.get("success"), inner.get("error", ""))
check("outer radius ≈ 0.13", outer.get("success") and abs(outer["radius"] - 0.13) < 0.01,
      str(outer.get("radius")))
check("inner radius ≈ 0.07", inner.get("success") and abs(inner["radius"] - 0.07) < 0.01,
      str(inner.get("radius")))
check("outer is farther out than inner", outer.get("radius", 0) > inner.get("radius", 99))
check("crossings_found == 2 (both walls seen)", outer.get("crossings_found") == 2,
      str(outer.get("crossings_found")))

# G128: radius=0 default (no crossing) must NOT return the bbox centre (r≈0)
deflt = run("radial_landmark", anchor="Ring", angle=0.0)
check("radius=0 default resolves a real radius, not the centre",
      deflt.get("success") and deflt.get("radius", 0) > 0.05, str(deflt.get("radius")))

# different angles give DIFFERENT points (G128's identical-handles bug)
p0 = run("radial_landmark", anchor="Ring", angle=0.0, crossing="outer")["point"]
p90 = run("radial_landmark", anchor="Ring", angle=90.0, crossing="outer")["point"]
check("different angles → different points", p0 != p90, f"{p0} vs {p90}")

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

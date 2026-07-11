"""E2E for the relational-placement primitives (no dead reckoning) — headless Blender.

  P1  on/under accept a LIST of anchors (span across / hang between supports)
  P2  at_corner gains top=True (rest on the target's top, not embed at its bottom)

Usage: flatpak run --filesystem=home org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_relational.py
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


def bounds(name):
    o = bpy.data.objects[name]
    xs = [(o.matrix_world @ v.co) for v in o.data.vertices]
    return (min(p.x for p in xs), min(p.y for p in xs), min(p.z for p in xs),
            max(p.x for p in xs), max(p.y for p in xs), max(p.z for p in xs))


# ───────────── P1: `on` accepts a list — a rail across two posts ─────────────
print("== P1: on=[a,b] spans the combined top, centered ==")
clean()
run("add_cylinder", name="post_a", radius=0.005, height=0.1, on={"at": [-0.05, 0, 0.05]})
run("add_cylinder", name="post_b", radius=0.005, height=0.1, on={"at": [0.05, 0, 0.05]})
r = run("add_cylinder", name="rail", radius=0.005, height=0.14, rotation_deg=[0, 90, 0],
        on={"on": ["post_a", "post_b"]})
check("rail on two posts succeeds", r.get("success") is True, str(r))
xmin, ymin, zmin, xmax, ymax, zmax = bounds("rail")
check("rail centered on the two posts (x≈0)", abs((xmin + xmax) / 2) < 1e-3, f"cx={(xmin+xmax)/2:.4f}")
check("rail rests ON the post tops (zmin≈0.10)", abs(zmin - 0.10) < 2e-3, f"zmin={zmin:.4f}")
# single-name `on` still works (backward compatible)
r2 = run("add_box", name="cap", width=0.02, depth=0.02, height=0.01, on={"on": "post_a"})
check("single-name on= still works", r2.get("success") is True, str(r2))

# ───────────── P1: `under` accepts a list — a ball between two rails ─────────
print("== P1: under=[a,b] hangs centered beneath the combined footprint ==")
clean()
run("add_cylinder", name="rail_f", radius=0.005, height=0.14, rotation_deg=[0, 90, 0], on={"at": [0, -0.03, 0.2]})
run("add_cylinder", name="rail_b", radius=0.005, height=0.14, rotation_deg=[0, 90, 0], on={"at": [0, 0.03, 0.2]})
r = run("add_sphere", name="ball", radius=0.01, on={"under": ["rail_f", "rail_b"], "gap": 0.02})
check("ball under two rails succeeds", r.get("success") is True, str(r))
xmin, ymin, zmin, xmax, ymax, zmax = bounds("ball")
check("ball centered between the rails (x≈0, y≈0)",
      abs((xmin + xmax) / 2) < 1e-3 and abs((ymin + ymax) / 2) < 1e-3,
      f"c=({(xmin+xmax)/2:.4f},{(ymin+ymax)/2:.4f})")
# rails' combined bottom is z=0.195; gap 0.02 → ball top at 0.175
check("ball hangs the gap below the rails (top≈0.175)", abs(zmax - 0.175) < 2e-3, f"top={zmax:.4f}")

# ───────────── P2: at_corner top=True rests on the target's top ──────────────
print("== P2: at_corner top=True (post stands ON the base, not through it) ==")
clean()
run("add_box", name="base2", width=0.2, depth=0.1, height=0.02, on={"at": [0, 0, 0.01]})  # top z=0.02
r = run("add_cylinder", name="post_top", radius=0.005, height=0.08,
        on={"at_corner": {"of": "base2", "corner": "front_left", "top": True}})
check("at_corner top=True succeeds", r.get("success") is True, str(r))
xmin, ymin, zmin, xmax, ymax, zmax = bounds("post_top")
check("post rests on the base top (zmin≈0.02)", abs(zmin - 0.02) < 1e-3, f"zmin={zmin:.4f}")
check("post sits at the front-left corner", xmin <= -0.09 and ymin <= -0.04, f"corner=({xmin:.3f},{ymin:.3f})")
# default (no top) still embeds at the base bottom
r2 = run("add_cylinder", name="post_embed", radius=0.005, height=0.08,
         on={"at_corner": {"of": "base2", "corner": "back_right"}})
_, _, ezmin, _, _, _ = bounds("post_embed")
check("at_corner without top still embeds at base bottom (zmin≈0)", abs(ezmin - 0.0) < 1e-3, f"zmin={ezmin:.4f}")

print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("RELATIONAL PASSED")

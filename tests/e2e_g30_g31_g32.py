"""E2E for the pencil-on-notebook dogfood gaps (G30/G31/G32) — headless Blender.

  G30  transform op=place — relational placement DSL for an EXISTING object
  G31  rest_on no-hit error is diagnostic (planar overlap + nudge), not a dead end
  G32  check_contacts surfaces ALL penetrations + a combined per-part read

Usage: flatpak run --filesystem=home org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_g30_g31_g32.py
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


# ───────────── G30: re-place an existing object relationally ─────────────
print("== G30: transform op=place seats an existing object left_of another ==")
clean()
run("add_box", name="base", width=0.1, depth=0.1, height=0.1, on={"at": [0, 0, 0.05]})
# cup starts far away, at an unrelated coordinate — place must MOVE it.
run("add_box", name="cup", width=0.04, depth=0.04, height=0.04, on={"at": [0.5, 0.3, 0.2]})
r = run("place", targets="cup", on={"left_of": "base", "gap": 0})
check("place succeeds", r.get("success") is True, str(r))
cxmin, cymin, czmin, cxmax, cymax, czmax = bounds("cup")
bxmin, bymin, bzmin, bxmax, bymax, bzmax = bounds("base")
check("cup right face flush to base left face (gap 0)", abs(cxmax - bxmin) < 1e-4,
      f"cup.xmax={cxmax:.4f} base.xmin={bxmin:.4f}")
check("cup Y/Z centered on base", abs((cymin + cymax) / 2 - (bymin + bymax) / 2) < 1e-4
      and abs((czmin + czmax) / 2 - (bzmin + bzmax) / 2) < 1e-4,
      f"cupYZc=({(cymin+cymax)/2:.4f},{(czmin+czmax)/2:.4f})")
# 'on' rests it on top of the base
r2 = run("place", targets="cup", on={"on": "base", "gap": 0})
_, _, c2zmin, _, _, _ = bounds("cup")
check("place on= rests it on base top (zmin≈0.10)", abs(c2zmin - 0.10) < 1e-4, f"zmin={c2zmin:.4f}")
# guard: missing spec
r3 = run("place", targets="cup")
check("place without on= errors", r3.get("success") is not True and "on" in r3.get("error", ""), str(r3))

# ───────────── G31: rest_on no-hit error is diagnostic ─────────────
print("== G31: rest_on with no surface below returns planar fit + nudge ==")
clean()
run("add_box", name="pad", width=0.04, depth=0.04, height=0.04, on={"at": [0, 0, 0.02]})  # x -0.02..0.02
run("add_box", name="block", width=0.02, depth=0.02, height=0.02, on={"at": [0.2, 0, 0.1]})  # +X, off the pad
r = run("rest_on", targets="block", target="pad", axis="Z")
check("rest_on off-target fails (no down-hit)", r.get("success") is not True, str(r))
err = r.get("error", "")
check("error reports planar separation", "apart" in err, err)
check("error names the X axis offset", "X" in err, err)
check("error suggests a nudge", "nudge" in err, err)
check("error reports nearest target point", "nearest target point" in err, err)
# sanity: a block ABOVE the pad still seats fine (no regression)
run("add_box", name="block2", width=0.02, depth=0.02, height=0.02, on={"at": [0, 0, 0.1]})
r2 = run("rest_on", targets="block2", target="pad", axis="Z")
check("rest_on above target still succeeds", r2.get("success") is True, str(r2))

# ───────────── G32: contacts surface ALL penetrations + combined read ─────────────
print("== G32: a part that touches one neighbour and penetrates another ==")
clean()
# link shares a face plane with anchor (touch) and a footprint with peg (penetration).
# Penetration is read where surfaces COINCIDE — matched footprints (sunk markers,
# chain links), which is what real interpenetration looks like.
run("add_box", name="link", width=0.06, depth=0.06, height=0.04, on={"at": [0, 0, 0.02]})    # x±0.03, z0..0.04
run("add_box", name="peg", width=0.06, depth=0.06, height=0.06, on={"at": [0, 0, 0.05]})     # same xy, z0.02..0.08 (sunk into link)
run("add_box", name="anchor", width=0.04, depth=0.06, height=0.04, on={"at": [0.05, 0, 0.02]})  # -X face on link's +X face (touch)
r = run("check_contacts", targets="link")
check("check_contacts succeeds", r.get("success") is True, str(r))
c = next((x for x in r.get("contacts", []) if x["object"] == "link"), None)
check("link relation is penetrating (priority over the touch)", c and c["relation"] == "penetrating", str(c))
check("link's penetrations list names peg", c and any(p["other"] == "peg" for p in c.get("penetrating", [])), str(c))
check("link summary shows BOTH the touch and the penetration",
      c and "anchor" in c.get("summary", "") and "peg" in c.get("summary", ""), str(c))

print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("G30_G31_G32 PASSED")

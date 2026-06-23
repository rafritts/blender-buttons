"""E2E for the validate-floor gap batch — G118, G124, G119. Headless.

G118: an inconsistent Euler characteristic (χ + boundary-loop count must be EVEN for an
      orientable manifold) is flagged as an unsuppressable intent-free defect. A Möbius
      band (χ=0, one boundary loop → χ+b=1, ODD) is the cleanest manifold trip; valid
      surfaces (closed cube, open cup, torus) must NOT fire.
G124: a penetration whose party is a non-watertight/open shell reports depth N/A (the
      signed inside/outside test is undefined there) instead of a fabricated magnitude.
G119: validate op=expect with a max_depth_mm ENVELOPE — a clip deeper than the blessed
      envelope still surfaces, so a broad pair declaration can't mask a deeper defect.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_gaps_batch_a.py
"""
import math
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


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    state.reset_history_state()
    validation.clear_intents()


def _link(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def make_box(name, cx, cy, cz, half):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2 * half)
    obj = _link(name, bm)
    obj.location = (cx, cy, cz)
    bpy.context.view_layer.update()
    return obj


def make_open_cube_shell(name, half):
    """A cube with one face removed → a watertight-looking box that is actually an OPEN
    shell (a single boundary loop of 4 edges)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2 * half)
    bm.faces.ensure_lookup_table()
    # drop the +Z face
    top = max(bm.faces, key=lambda f: f.calc_center_median().z)
    bmesh.ops.delete(bm, geom=[top], context='FACES_ONLY')
    return _link(name, bm)


def make_sphere(name):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.5)
    return _link(name, bm)


def make_torus(name):
    bm = bmesh.new()
    # a torus: χ=0, watertight (b=0) → χ+b even, must not fire.
    import mathutils
    seg, ring, R, r = 16, 8, 0.6, 0.2
    grid = []
    for i in range(seg):
        u = 2 * math.pi * i / seg
        row = []
        for j in range(ring):
            v = 2 * math.pi * j / ring
            x = (R + r * math.cos(v)) * math.cos(u)
            y = (R + r * math.cos(v)) * math.sin(u)
            z = r * math.sin(v)
            row.append(bm.verts.new((x, y, z)))
        grid.append(row)
    for i in range(seg):
        for j in range(ring):
            a = grid[i][j]
            b = grid[(i + 1) % seg][j]
            c = grid[(i + 1) % seg][(j + 1) % ring]
            d = grid[i][(j + 1) % ring]
            bm.faces.new((a, b, c, d))
    return _link(name, bm)


def make_open_cup(name):
    """A capless cylinder wall — open at BOTH ends: χ=0, b=2 → χ+b even, must not fire
    (an open shell is not by itself impossible)."""
    bm = bmesh.new()
    seg, h, r = 16, 1.0, 0.4
    bot, top = [], []
    for i in range(seg):
        u = 2 * math.pi * i / seg
        bot.append(bm.verts.new((r * math.cos(u), r * math.sin(u), 0.0)))
        top.append(bm.verts.new((r * math.cos(u), r * math.sin(u), h)))
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    return _link(name, bm)


def make_mobius(name, seg=24, R=1.0, w=0.35):
    """A triangulated Möbius band: a half-twist closes the strip with the two rows
    swapped, making it non-orientable. Every interior edge has 2 faces and the single
    boundary loop's edges have 1 — manifold (no ≥3-face junction) — yet χ + boundaries
    is ODD, the exact impossibility G118 must catch."""
    bm = bmesh.new()
    rows = []
    for i in range(seg):
        u = 2 * math.pi * i / seg
        col = []
        for s in (-1, 1):
            v = s * w
            x = (R + v * math.cos(u / 2)) * math.cos(u)
            y = (R + v * math.cos(u / 2)) * math.sin(u)
            z = v * math.sin(u / 2)
            col.append(bm.verts.new((x, y, z)))
        rows.append(col)
    for i in range(seg):
        a0, a1 = rows[i]
        if i < seg - 1:
            b0, b1 = rows[i + 1]
        else:
            b1, b0 = rows[0]          # the half-twist: swap the two rows at the seam
        # two triangles per quad (keeps every face valid even with the flip)
        bm.faces.new((a0, a1, b1))
        bm.faces.new((a0, b1, b0))
    return _link(name, bm)


print("\nvalidate-floor batch — G118 (Euler parity), G124 (open-shell depth), G119 (envelope)\n")

# ── G118: Euler parity ───────────────────────────────────────────────────────
print("[G118] inconsistent Euler characteristic = unsuppressable defect")
clean()
mob = make_mobius("Mobius")
v = validation.run_validate(["Mobius"])
eul = [f for f in v["intent_free"] if f["check"] == "euler_inconsistent"]
check("Möbius band → euler_inconsistent fires", len(eul) == 1, str(v["line"]))
check("the finding names the χ/boundary impossibility",
      eul and "must be even" in eul[0]["message"], str(eul))
# it has no suppression path (intent-free) — declaring intent must not quiet it.
validation.add_intent("Mobius", "Mobius", "test")
v2 = validation.run_validate(["Mobius"])
check("euler_inconsistent is unsuppressable",
      any(f["check"] == "euler_inconsistent" for f in v2["intent_free"]))

for builder, nm in ((make_sphere, "closed sphere"), (make_torus, "torus"),
                    (make_open_cup, "open cylinder (b=2)"),
                    (lambda n: make_open_cube_shell(n, 0.5), "open cube shell (b=1)")):
    clean()
    builder("Ctrl")
    v = validation.run_validate(["Ctrl"])
    fired = any(f["check"] == "euler_inconsistent" for f in v["intent_free"])
    check(f"valid surface does NOT false-fire: {nm}", not fired, str(v["line"]))

# ── G124: open-shell penetration reports N/A, not a fabricated depth ──────────
print("[G124] open shell → honest 'depth N/A', not a fabricated magnitude")
clean()
shell = make_open_cube_shell("Shell", 0.5)        # non-watertight (missing top face)
box = make_box("Poker", 0.5, 0.0, 0.0, 0.1)       # straddles the +X wall at x=0.5
check("_is_watertight: open shell → False", validation._is_watertight("Shell") is False)
check("_is_watertight: closed box → True", validation._is_watertight("Poker") is True)
v = validation.run_validate(["Shell", "Poker"])
clip_new = v["clipping"]["new"]
check("open-shell penetration is still surfaced (not dropped)", len(clip_new) >= 1, str(v["clipping"]))
if clip_new:
    f = clip_new[0]
    check("open-shell clip reports NO fabricated number (depth_mm None)", f["depth_mm"] is None, str(f))
    check("open-shell clip hints at the open shell + clearance",
          "open shell" in f["message"] and "clearance" in f["message"], f["message"])

# contrast: two watertight solids → a real numeric depth (no regression). A SMALLER box
# poking into a larger one (no coincident faces) gives a clean signed penetration, not a
# matched-footprint overlap. Lifted above the floor to avoid below_floor noise.
clean()
make_box("WA", 0, 0, 1.0, 0.5)
make_box("WB", 0.4, 0, 1.0, 0.2)                  # nested + poking out the +X side
v = validation.run_validate(["WA", "WB"])
wnew = v["clipping"]["new"]
check("watertight pair → a numeric depth (regression guard)",
      len(wnew) == 1 and isinstance(wnew[0]["depth_mm"], (int, float)) and wnew[0]["depth_mm"] > 0,
      str(v["clipping"]))

# ── G119: depth envelope on a declaration ────────────────────────────────────
print("[G119] declared envelope — a deeper clip than blessed still surfaces")
clean()
make_box("Coffee", 0, 0, 1.0, 0.5)
make_box("Mug", 0.4, 0, 1.0, 0.2)                 # deep clean penetration, like the gap
base = validation.run_validate(["Coffee", "Mug"])
deep = base["clipping"]["new"][0]["depth_mm"]
check("baseline deep clip measured", deep and deep > 50, f"depth={deep}")

# declare with a tight envelope: blessed only up to 2mm → the deep clip breaches it.
validation.add_intent("Coffee", "Mug", "coffee meets the inner wall at the rim", max_depth_mm=2.0)
v = validation.run_validate(["Coffee", "Mug"])
check("envelope breach surfaces in 'exceeded'", len(v["clipping"]["exceeded"]) == 1, str(v["clipping"]))
check("breach is NOT a plain NEW finding (it's the declared pair)",
      len(v["clipping"]["new"]) == 0, str(v["clipping"]["new"]))
check("envelope breach fails the floor (passed False)", v["passed"] is False)
check("line names the envelope breach", "ENVELOPE" in v["line"], v["line"])

# same declaration WITHOUT an envelope → collapses to a blessed count, no breach.
validation.clear_intents()
validation.add_intent("Coffee", "Mug", "coffee meets the inner wall", max_depth_mm=0)
v = validation.run_validate(["Coffee", "Mug"])
check("no-envelope declaration collapses to a count (no breach, no new)",
      not v["clipping"]["exceeded"] and not v["clipping"]["new"] and v["clipping"]["declared"] == 1,
      str(v["clipping"]))

print()
if failures:
    print(f"e2e_gaps_batch_a :: FAILED — {len(failures)} failure(s): {failures}")
    sys.exit(1)
print("e2e_gaps_batch_a :: PASSED — 0 failure(s)")

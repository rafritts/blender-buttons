"""E2E for the G96-G98 gap fixes — runs the WORKING-TREE extension headless.

  G96 — the flute engine (now the lobes preset of edit op=field, SPEC-21 §4) respects the live vertex selection (band-local fluting), and
        computes its rotation center from the selection, not the whole-mesh centroid.
  G97 — the clad engine (surface retired → guidance://techniques/shell, SPEC-21 §4): one-call surface-offset SHELL (clearance + wall) following a
        region (whole / selection / trunk).
  G98 — feel op=clearance: SIGNED nearest-surface read — shell outside vs stabbing
        through the surface it wraps.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_gaps_g96_g98.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402

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


def ring_radii(obj, axis_idx=2, decimals=4):
    """Mean in-plane radius per ring, measured in OBJECT mode (world space)."""
    me = obj.data
    mat = obj.matrix_world
    buckets = {}
    for v in me.vertices:
        w = mat @ v.co
        buckets.setdefault(round(w[axis_idx], decimals), []).append(w)
    out = {}
    other = [i for i in range(3) if i != axis_idx]
    for pos, ws in sorted(buckets.items()):
        cu = sum(w[other[0]] for w in ws) / len(ws)
        cv = sum(w[other[1]] for w in ws) / len(ws)
        r = sum(math.hypot(w[other[0]] - cu, w[other[1]] - cv) for w in ws) / len(ws)
        out[pos] = r
    return out


# ───────────────────────── G96 — flute respects selection ─────────────────────────
print("== G96: flute restricted to the live selection ==")
clean()
# A tall cylinder: 48 sides, several Z-rings. Flute only the TOP band; the bottom rings
# must stay byte-identical.
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.5, depth=2.0, location=(0, 0, 1.0))
cyl = bpy.context.active_object
cyl.name = "Col"
# loop-cut into Z-rings so there's a band structure to select within
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(cyl.data)
# subdivide the side edges to add Z-rings
side_edges = [e for e in bm.edges
              if abs((cyl.matrix_world @ e.verts[0].co).z - (cyl.matrix_world @ e.verts[1].co).z) > 0.1]
bmesh.ops.subdivide_edges(bm, edges=side_edges, cuts=6, use_grid_fill=False)
bmesh.update_edit_mesh(cyl.data)
bpy.ops.object.mode_set(mode='OBJECT')

before = ring_radii(cyl)
zs = sorted(before.keys())
zmid = 0.5 * (zs[0] + zs[-1])
# top band = rings clearly above the midline; bottom = clearly below.
top_band = [z for z in zs if z > zmid + 0.08]
bot_band = [z for z in zs if z < zmid - 0.08]
check("cylinder has rings above and below the midline", bool(top_band) and bool(bot_band),
      f"top={len(top_band)} bot={len(bot_band)}")

# Select the top band, then flute. select_between takes FRACTIONS (0..1) of the Z span;
# the band z>zmid+0.08 corresponds to lo just above 0.5.
lo_frac = (zmid + 0.08 - zs[0]) / (zs[-1] - zs[0])
r = run("select_between", axis="Z", lo=lo_frac, hi=1.0)
check("select_between top band ok", r.get("success"), r.get("error"))
r = run("flute", axis="Z", count=12, depth=0.05, profile="convex")
check("flute reports success", r.get("success"), r.get("error"))
check("flute scope == selection", r.get("scope") == "selection", f"scope={r.get('scope')}")

after = ring_radii(cyl)
# bottom rings must be untouched (radius unchanged); top rings must be perturbed.
bot_unchanged = all(abs(after[z] - before[z]) < 1e-6 for z in bot_band)
top_changed = any(abs(after[z] - before[z]) > 1e-4 for z in top_band)
check("bottom band radius UNCHANGED (flute did not reach it)", bot_unchanged)
check("top band radius CHANGED (flute reached it)", top_changed)

# whole-mesh fallback still works when nothing is selected.
clean()
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.5, depth=1.0)
c2 = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.object.mode_set(mode='OBJECT')
r = run("flute", axis="Z", count=8, depth=0.03, profile="convex")
check("flute with no selection falls back to whole_mesh",
      r.get("success") and r.get("scope") == "whole_mesh", f"scope={r.get('scope')}")


# ───────────────────────── G97 — clad: offset shell ─────────────────────────
print("== G97: clad creates a surface-offset shell ==")
clean()
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(0, 0, 0))
body = bpy.context.active_object
body.name = "Body"

CLEAR = 0.02   # 20mm standoff
WALL = 0.01    # 10mm wall
r = run("clad_surface", target="Body", region="whole", clearance=CLEAR, thickness=WALL,
        new_name="Shell")
check("clad reports success", r.get("success"), r.get("error"))
shell = bpy.data.objects.get("Shell")
check("Shell object created", shell is not None)
check("Shell != Body", shell is not None and shell.name != "Body")
check("Shell carries a SOLIDIFY modifier",
      shell is not None and any(m.type == 'SOLIDIFY' for m in shell.modifiers))
# Body itself must be untouched (still a sphere of radius ~0.5).
body_r = max((body.matrix_world @ v.co).length for v in body.data.vertices)
check("Body geometry untouched", abs(body_r - 0.5) < 1e-4, f"body_r={body_r}")

# clad region='selection' — clad only a Z-band of a fresh sphere.
clean()
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, segments=32, ring_count=16)
b2 = bpy.context.active_object
b2.name = "Body2"
# equator band of a unit-ish sphere (z in [-0.5,0.5]): fractions 0.35..0.65
r = run("select_between", axis="Z", lo=0.35, hi=0.65)
check("band select ok", r.get("success"), r.get("error"))
r = run("clad_surface", target="Body2", region="selection", clearance=0.02, thickness=0.01,
        new_name="Band")
check("clad region=selection ok", r.get("success"), r.get("error"))
band = bpy.data.objects.get("Band")
check("Band shell created", band is not None)
if band:
    # the band shell is only a sub-region, so far fewer verts than a full sphere copy
    check("Band is a sub-region (fewer verts than whole body)",
          len(band.data.vertices) < len(b2.data.vertices),
          f"band={len(band.data.vertices)} body={len(b2.data.vertices)}")
    bz = [(band.matrix_world @ v.co).z for v in band.data.vertices]
    check("Band confined to the selected Z-band",
          min(bz) > -0.35 and max(bz) < 0.35, f"z range {min(bz):.3f}..{max(bz):.3f}")


# ───────────────────────── G98 — feel op=clearance (signed) ─────────────────────────
print("== G98: signed clearance read ==")
clean()
# A shell that correctly ENVELOPS a body: inner sphere r=0.5, outer shell sphere r=0.6.
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(0, 0, 0))
inner = bpy.context.active_object
inner.name = "Inner"
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.6, location=(0, 0, 0))
outer = bpy.context.active_object
outer.name = "Outer"

r = run("check_clearance", shell="Outer", surface="Inner", threshold=2.0)
check("clearance reports success", r.get("success"), r.get("error"))
check("enveloping shell: 100% outside the surface",
      abs(r.get("fraction_outside", 0) - 1.0) < 1e-6, f"frac={r.get('fraction_outside')}")
check("enveloping shell: no penetrations", r.get("penetrations") == 0,
      f"pen={r.get('penetrations')}")
check("enveloping shell: min clearance ~100mm",
      r.get("min_clearance_mm") is not None and abs(r["min_clearance_mm"] - 100.0) < 10.0,
      f"min={r.get('min_clearance_mm')}")
check("enveloping shell: clears>=2mm verdict PASS", r.get("clears") is True)

# Now a shell that STABS THROUGH: shift the outer shell sideways so part dips inside.
outer.location = (0.4, 0, 0)
bpy.context.view_layer.update()
r = run("check_clearance", shell="Outer", surface="Inner", threshold=2.0)
check("stabbing shell: success", r.get("success"), r.get("error"))
check("stabbing shell: some verts INSIDE the surface", r.get("penetrations", 0) > 0,
      f"pen={r.get('penetrations')}")
check("stabbing shell: fraction_outside < 1.0",
      r.get("fraction_outside", 1.0) < 1.0, f"frac={r.get('fraction_outside')}")
check("stabbing shell: clears verdict FAIL", r.get("clears") is False)
# the two cases must give DIFFERENT verdicts — the whole point of G98 vs bbox overlap.


# ───────────────────────── summary ─────────────────────────
print()
if failures:
    print(f"FAILED ({len(failures)}): " + ", ".join(failures))
    sys.exit(1)
print("ALL G96-G98 CHECKS PASSED")

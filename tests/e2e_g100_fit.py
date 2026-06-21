"""E2E for SPEC-14 / G100 — geometry fit (feel op=fit).

Runs the WORKING-TREE extension headless. Covers the spec's acceptance criteria:

  1. Primitive round-trips — add a known cylinder/sphere/cone/plane → model=auto recovers
     the type + params within tolerance, residual ≈ mesh discretisation (sub-mm).
  2. Auto picks the SIMPLER model on a tie (cylinder over swept_tube; sphere over ellipsoid).
  3. swept_tube with an injected gap — the deleted band is reported as a `gap` at the right
     s-interval (the direct G100 continuity/void read), centerline + R(s) returned.
  4. Honesty — a forced wrong model (sphere onto a tall cylinder) returns a HIGH residual and
     a verdict that explicitly declines ("no clean parametric form").
  5. Half-coverage — half a cylinder fits with low residual but coverage ≈ 50% (the
     half-cylinder trap, surfaced).
  6. ellipsoid + torus round-trips (forced model).
  7. as_handle / as_curve minting — fitted axis handle + centerline Bézier created.
  8. per_component — two joined shells fit independently, not averaged across the gap.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g100_fit.py
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


def add_z_rings(obj, cuts):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    side = [e for e in bm.edges
            if abs((obj.matrix_world @ e.verts[0].co).z - (obj.matrix_world @ e.verts[1].co).z) > 0.05]
    bmesh.ops.subdivide_edges(bm, edges=side, cuts=cuts, use_grid_fill=False)
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')


# ───────────────── 1 + 2. Primitive round-trips + simpler-model tie-break ─────────────────
print("== G100-1/2: primitive round-trips + auto simpler-model tie-break ==")

clean()
bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.5, depth=2.0, location=(0, 0, 1.0))
add_z_rings(bpy.context.active_object, 8)  # intermediate rings: a 2-ring tube also lies on a sphere
r = run("fit", model="auto")
check("cylinder: success", r.get("success"), r.get("error"))
check("cylinder: auto picks 'cylinder' (simpler than swept_tube)", r.get("model") == "cylinder",
      f"model={r.get('model')}")
check("cylinder: radius ~0.5m", abs(r.get("params", {}).get("radius", 0) - 0.5) < 0.005,
      f"r={r.get('params',{}).get('radius')}")
check("cylinder: length ~2.0m", abs(r.get("params", {}).get("length", 0) - 2.0) < 0.02,
      f"len={r.get('params',{}).get('length')}")
check("cylinder: residual sub-mm (verts on the ideal circle)", r.get("residual_mm", 99) < 1.0,
      f"res={r.get('residual_mm')}mm")
check("cylinder: clean-fit verdict", "clean fit" in r.get("verdict", ""), r.get("verdict"))

clean()
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32, radius=0.5)
r = run("fit", model="auto")
check("sphere: auto picks 'sphere' (simpler than ellipsoid/swept_tube)", r.get("model") == "sphere",
      f"model={r.get('model')}")
check("sphere: radius ~0.5m", abs(r.get("params", {}).get("radius", 0) - 0.5) < 0.005,
      f"r={r.get('params',{}).get('radius')}")
check("sphere: residual sub-mm", r.get("residual_mm", 99) < 1.0, f"res={r.get('residual_mm')}mm")

clean()
bpy.ops.mesh.primitive_cone_add(vertices=64, radius1=0.5, radius2=0.0, depth=2.0, location=(0, 0, 1.0))
add_z_rings(bpy.context.active_object, 8)  # intermediate rings so it isn't sphere-degenerate
r = run("fit", model="auto")
check("cone: auto picks 'cone'", r.get("model") == "cone", f"model={r.get('model')}")
check("cone: half-angle ~14° (atan(0.5/2))",
      abs(r.get("params", {}).get("half_angle_deg", 0) - math.degrees(math.atan(0.5 / 2.0))) < 1.5,
      f"ha={r.get('params',{}).get('half_angle_deg')}")
check("cone: residual sub-mm", r.get("residual_mm", 99) < 1.0, f"res={r.get('residual_mm')}mm")

clean()
bpy.ops.mesh.primitive_grid_add(x_subdivisions=12, y_subdivisions=12, size=2.0)
r = run("fit", model="auto")
check("plane: auto picks 'plane'", r.get("model") == "plane", f"model={r.get('model')}")
check("plane: residual sub-mm", r.get("residual_mm", 99) < 1.0, f"res={r.get('residual_mm')}mm")


# ───────────────── 3. swept_tube with an injected gap ─────────────────
print("== G100-3: swept_tube reports an injected gap (continuity byproduct) ==")
clean()
bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.4, depth=2.0, location=(0, 0, 1.0))
tube = bpy.context.active_object
add_z_rings(tube, 19)  # ~20 Z rings over z∈[0,2]
# delete a middle band z∈[0.7,1.3] → a void in the sweep
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(tube.data)
bpy.ops.mesh.select_all(action='DESELECT')
for v in bm.verts:
    if 0.7 < (tube.matrix_world @ v.co).z < 1.3:
        v.select = True
bm.select_flush_mode()
bmesh.update_edit_mesh(tube.data)
bpy.ops.mesh.delete(type='VERT')
bpy.ops.object.mode_set(mode='OBJECT')

r = run("fit", model="swept_tube", axis="Z", bands=24)
check("swept_tube: success", r.get("success"), r.get("error"))
check("swept_tube: has a centerline", bool(r.get("centerline")), "no centerline")
check("swept_tube: R(s) profile returned", bool(r.get("radius_profile")), "no R(s)")
gaps = r.get("gaps", [])
check("swept_tube: a gap detected", len(gaps) >= 1, f"gaps={gaps}")
# the void z∈[0.7,1.3] over z∈[0,2] → s∈[0.35,0.65]
hit = any(g[0] < 0.65 and g[1] > 0.35 for g in gaps)
check("swept_tube: gap at the correct s-interval (~0.35..0.65)", hit, f"gaps={gaps}")


# ───────────────── 4. Honesty — forced wrong model ─────────────────
print("== G100-4: forced wrong model declines honestly ==")
clean()
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.5, depth=2.0, location=(0, 0, 1.0))
add_z_rings(bpy.context.active_object, 8)  # rings break the degenerate 2-ring-tube-is-a-sphere case
r = run("fit", model="sphere")
check("forced sphere: success (returns a fit)", r.get("success"), r.get("error"))
check("forced sphere: HIGH residual (>>tol)", r.get("residual_mm", 0) > r.get("tol_mm", 3),
      f"res={r.get('residual_mm')}mm tol={r.get('tol_mm')}mm")
check("forced sphere: verdict declines (no clean parametric form)",
      "no clean parametric form" in r.get("verdict", ""), r.get("verdict"))


# ───────────────── 5. Half-coverage (the half-cylinder trap) ─────────────────
print("== G100-5: half a cylinder → low residual but ~50% coverage ==")
clean()
bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.5, depth=2.0, location=(0, 0, 1.0))
half = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(half.data)
bpy.ops.mesh.select_all(action='DESELECT')
for v in bm.verts:
    if (half.matrix_world @ v.co).y > 0.001:   # keep only one half (y<=0) → delete y>0
        v.select = True
bm.select_flush_mode()
bmesh.update_edit_mesh(half.data)
bpy.ops.mesh.delete(type='VERT')
bpy.ops.object.mode_set(mode='OBJECT')

r = run("fit", model="cylinder")
check("half-cylinder: success", r.get("success"), r.get("error"))
check("half-cylinder: residual still low (fits the data present)", r.get("residual_mm", 99) < 1.0,
      f"res={r.get('residual_mm')}mm")
check("half-cylinder: coverage ~50% (surfaced, not hidden)", r.get("coverage", 1.0) < 0.62,
      f"coverage={r.get('coverage')}")


# ───────────────── 6. ellipsoid + torus round-trips ─────────────────
print("== G100-6: ellipsoid + torus round-trips ==")
clean()
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32, radius=0.5)
ell = bpy.context.active_object
ell.scale = (1.0, 0.7, 0.5)        # world semi-axes 0.5, 0.35, 0.25 (baked via matrix_world)
bpy.context.view_layer.update()
r = run("fit", model="ellipsoid")
check("ellipsoid: success", r.get("success"), r.get("error"))
semi = sorted(r.get("params", {}).get("semi_axes", []), reverse=True)
check("ellipsoid: semi-axes ~[0.5,0.35,0.25]",
      len(semi) == 3 and abs(semi[0] - 0.5) < 0.01 and abs(semi[1] - 0.35) < 0.01
      and abs(semi[2] - 0.25) < 0.01, f"semi={semi}")

clean()
bpy.ops.mesh.primitive_torus_add(major_radius=0.5, minor_radius=0.15,
                                 major_segments=48, minor_segments=24)
r = run("fit", model="torus")
check("torus: success", r.get("success"), r.get("error"))
check("torus: major ~0.5m", abs(r.get("params", {}).get("major_radius", 0) - 0.5) < 0.01,
      f"R={r.get('params',{}).get('major_radius')}")
check("torus: minor ~0.15m", abs(r.get("params", {}).get("minor_radius", 0) - 0.15) < 0.01,
      f"r={r.get('params',{}).get('minor_radius')}")


# ───────────────── 7. as_handle / as_curve minting ─────────────────
print("== G100-7: as_handle + as_curve minting ==")
clean()
bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.3, depth=2.0, location=(0, 0, 1.0))
tube = bpy.context.active_object
add_z_rings(tube, 11)
r = run("fit", model="swept_tube", axis="Z", as_handle="arm_axis", as_curve="arm_spine")
check("mint: success", r.get("success"), r.get("error"))
check("mint: as_curve created the Bézier 'arm_spine'",
      r.get("curve") == "arm_spine" and bpy.data.objects.get("arm_spine") is not None,
      f"curve={r.get('curve')}")
check("mint: 'arm_spine' is a CURVE object",
      bpy.data.objects.get("arm_spine") is not None
      and bpy.data.objects["arm_spine"].type == 'CURVE')
check("mint: as_handle created a handle object",
      bool(r.get("handle")) and bpy.data.objects.get(r.get("handle")) is not None,
      f"handle={r.get('handle')}")


# ───────────────── 8. per_component ─────────────────
print("== G100-8: per_component fits each shell independently ==")
clean()
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.5, depth=2.0, location=(0, 0, 1.0))
a = bpy.context.active_object
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.25, depth=2.0, location=(2.0, 0, 1.0))
b = bpy.context.active_object
bpy.context.view_layer.objects.active = a
b.select_set(True); a.select_set(True)
bpy.ops.object.join()
r = run("fit", model="cylinder", per_component=True)
check("per_component: success", r.get("success"), r.get("error"))
check("per_component: 2 components", r.get("n_components") == 2, f"n={r.get('n_components')}")
comps = r.get("components", [])
radii = sorted(c.get("params", {}).get("radius", 0) for c in comps)
check("per_component: distinct radii recovered (~0.25 and ~0.5), not averaged",
      len(radii) == 2 and abs(radii[0] - 0.25) < 0.01 and abs(radii[1] - 0.5) < 0.01,
      f"radii={radii}")


# ───────────────── summary ─────────────────
print()
if failures:
    print(f"FAILED ({len(failures)}): " + ", ".join(failures))
    sys.exit(1)
print("ALL G100 FIT CHECKS PASSED")

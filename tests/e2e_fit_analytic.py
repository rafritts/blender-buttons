"""E2E for SPEC-19 Phase 1 — analytic patch fitting (feel op=fit model=quadric).

Runs the WORKING-TREE extension headless. Covers Phase 1's acceptance criteria:

  A. READ — a region of quads built as an EXACT height-field quadric z=αx²+βy² is recovered
     by model=quadric: coefficients a≈α, b≈β, c≈0, residual ≈ 0, captured ≈ 100%, and the
     shape verdict names it (saddle / dome). By symmetry the centred patch's PCA frame is the
     world axes, so recovery is exact, not approximate.
  B. ROUND-TRIP — `edit op=field` a KNOWN quadric expr onto a flat grid, then fit it back and
     recover the same surface (the §4 loop). Then apply the FITTED expr back through the real
     field sandbox and confirm it parses + is a no-op on its own surface (verts already satisfy
     it) — the emitted expr is genuinely executable, not decorative.
  C. REFUSE, DON'T CORRUPT (§1.5) — a folded region (a full sphere) is NOT a height field;
     model=quadric returns a HIGH residual (>> tol), never a quiet plausible fiction.
  D. The Phase-2 menu refuses cleanly with a teach error (model=bspline → not-built-yet).

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_fit_analytic.py
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


def make_grid(xext, yext, subdiv=16):
    """A flat rectangular grid centred at the origin, transform baked (matrix_world identity)."""
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=subdiv, y_subdivisions=subdiv, size=2.0)
    obj = bpy.context.active_object
    obj.scale = (xext / 2.0, yext / 2.0, 1.0)         # size=2 → [-1,1] → [-xext/2, xext/2]
    bpy.ops.object.transform_apply(scale=True, location=False, rotation=False)
    return obj


def displace_quadric(obj, alpha, beta):
    """Set each vert's Z to α·x² + β·y² exactly (an analytic height-field patch)."""
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    for v in bm.verts:
        x, y = v.co.x, v.co.y
        v.co.z = alpha * x * x + beta * y * y
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')


# ───────────────── A. READ — recover an exact quadric ─────────────────
print("== SPEC19-A: model=quadric recovers an exact height-field patch ==")
clean()
ALPHA, BETA = 0.40, -0.25                 # x² up, y² down → a saddle
g = make_grid(1.2, 0.8, subdiv=16)        # X-extent > Y-extent → PCA u-axis = X
displace_quadric(g, ALPHA, BETA)
r = run("fit", model="quadric")
check("A: success", r.get("success"), r.get("error"))
check("A: model == quadric", r.get("model") == "quadric", f"model={r.get('model')}")
p = r.get("params", {})
check("A: a ≈ α (0.40)", abs(p.get("a", 0) - ALPHA) < 0.01, f"a={p.get('a')}")
check("A: b ≈ β (-0.25)", abs(p.get("b", 0) - BETA) < 0.01, f"b={p.get('b')}")
check("A: c ≈ 0 (no twist)", abs(p.get("c", 1)) < 0.01, f"c={p.get('c')}")
check("A: residual ≈ 0 (verts exactly on the quadric)", r.get("residual_mm", 99) < 0.05,
      f"res={r.get('residual_mm')}mm")
check("A: captured ≈ 100%", r.get("captured", 0) > 0.999, f"captured={r.get('captured')}")
check("A: k_max > 0 and k_min < 0 (saddle)",
      p.get("k_max", 0) > 0.2 and p.get("k_min", 0) < -0.2, f"k=({p.get('k_max')},{p.get('k_min')})")
check("A: shape verdict says 'saddle'", "saddle" in p.get("shape", ""), f"shape={p.get('shape')}")
check("A: emits a legible h(u,v) formula", r.get("formula", "").startswith("h(u,v)"),
      f"formula={r.get('formula')}")
check("A: emits an executable expr + axis:v channel",
      bool(r.get("expr")) and r.get("apply_channel") == "axis:v",
      f"expr={r.get('expr')} ch={r.get('apply_channel')}")


# ───────────────── B. ROUND-TRIP — field a known expr, fit it back ─────────────────
print("== SPEC19-B: field a known quadric → fit recovers it → emitted expr re-applies clean ==")
clean()
g = make_grid(1.2, 0.8, subdiv=16)        # flat; field will shape it
# author z = -0.50·x² - 0.30·y² (a dome). In the grid's AUTO frame L=X(field z), U=Y(field x).
bpy.context.view_layer.objects.active = g
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.object.mode_set(mode='OBJECT')
rf = run("field", axis="auto", channel="axis:v", field_mode="add",
         expr="-0.50*z*z - 0.30*x*x")
check("B: field applied", rf.get("success"), rf.get("error"))
r = run("fit", model="quadric")
check("B: fit recovers the field-authored surface (residual ≈ 0)", r.get("residual_mm", 99) < 0.05,
      f"res={r.get('residual_mm')}mm")
check("B: captured ≈ 100%", r.get("captured", 0) > 0.999, f"captured={r.get('captured')}")
pb = r.get("params", {})
check("B: both curvatures negative → dome", pb.get("k_max", 1) < 0 and pb.get("k_min", 1) < 0,
      f"k=({pb.get('k_max')},{pb.get('k_min')})")
check("B: shape verdict says 'dome'", "dome" in pb.get("shape", ""), f"shape={pb.get('shape')}")

# now apply the FITTED expr back through the real field sandbox — must parse and be a no-op
emitted = r.get("expr")
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.object.mode_set(mode='OBJECT')
rr = run("field", axis="auto", channel="axis:v", field_mode="add", expr=emitted)
check("B: emitted expr parses + runs in the field sandbox", rr.get("success"), rr.get("error"))
# re-applying (quadric)−y to its own surface should displace by ≈0 (verts already satisfy it);
# the residual displacement is just 6-sig-fig coefficient rounding — assert it's negligible in
# MAGNITUDE (microns), the honest claim, not vert-count against the field's 1nm move threshold.
frng = rr.get("f_range", [9, 9])
check("B: emitted expr is a near-perfect no-op (|displacement| < 0.05mm)",
      max(abs(frng[0]), abs(frng[1])) < 5e-5, f"f_range={frng} m")
r2 = run("fit", model="quadric")
check("B: re-fit after re-apply still ≈ 0 residual (round-trip closed)",
      r2.get("residual_mm", 99) < 0.05, f"res={r2.get('residual_mm')}mm")


# ───────────────── C. REFUSE — a fold is not a height field ─────────────────
print("== SPEC19-C: a folded region (full sphere) returns a HIGH residual, no fiction ==")
clean()
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=24, radius=0.5)
r = run("fit", model="quadric")
check("C: success (returns a fit, doesn't crash)", r.get("success"), r.get("error"))
check("C: HIGH residual (>> tol) — region isn't height-field-like",
      r.get("residual_mm", 0) > r.get("tol_mm", 3), f"res={r.get('residual_mm')}mm tol={r.get('tol_mm')}mm")
check("C: captured is poor (the formula explains little)", r.get("captured", 1.0) < 0.85,
      f"captured={r.get('captured')}")


# ───────────────── D. Phase-2 menu refuses cleanly ─────────────────
print("== SPEC19-D: the Phase-2 bases teach-error instead of silently failing ==")
clean()
g = make_grid(1.0, 1.0, subdiv=8)
r = run("fit", model="bspline")
check("D: model=bspline refuses with a Phase-2 teach error",
      (not r.get("success")) and "Phase 2" in (r.get("error", "")), f"r={r}")


# ───────────── E. INSTANTIATE — mint the fit as a patch, re-fit recovers it ─────────────
print("== SPEC19-E: as_surface mints a mesh patch; re-fitting it recovers the formula ==")
clean()
ALPHA, BETA = 0.6, -0.7                   # saddle, both |k| > the 0.5/m flat threshold
g = make_grid(1.0, 0.7, subdiv=16)
displace_quadric(g, ALPHA, BETA)
# NB: this drives the extension directly (bypassing the server facade that maps
# surface_res→resolution), so pass the extension's own `resolution=` arg here.
r = run("fit", model="quadric", as_surface="Patch", resolution="20x14")
check("E: fit success", r.get("success"), r.get("error"))
check("E: minted a surface object 'Patch'", r.get("surface") == "Patch", f"surface={r.get('surface')}")
check("E: surface_res honored (20x14)", r.get("surface_res") == [20, 14], f"res={r.get('surface_res')}")
patch = bpy.data.objects.get("Patch")
check("E: Patch exists with 20×14 verts",
      patch is not None and len(patch.data.vertices) == 20 * 14,
      f"verts={len(patch.data.vertices) if patch else None}")
# re-fit the minted patch (object mode → whole mesh) — the §5 verification
bpy.context.view_layer.objects.active = patch
r2 = run("fit", model="quadric", target="Patch")
check("E: re-fit of the minted patch ≈ 0 residual (mesh IS the formula)",
      r2.get("residual_mm", 99) < 0.05, f"res={r2.get('residual_mm')}mm")
check("E: re-fit captured ≈ 100%", r2.get("captured", 0) > 0.999, f"captured={r2.get('captured')}")
p2 = r2.get("params", {})
check("E: re-fit shape verdict still 'saddle'", "saddle" in p2.get("shape", ""), f"shape={p2.get('shape')}")
# coefficient magnitudes survive (normal eigenvector sign is arbitrary → compare |·|)
check("E: |a| ≈ |α| and |b| ≈ |β| (coefficients survived the round-trip)",
      abs(abs(p2.get("a", 0)) - abs(ALPHA)) < 0.02 and abs(abs(p2.get("b", 0)) - abs(BETA)) < 0.02,
      f"a={p2.get('a')} b={p2.get('b')}")
# resolution SUGGESTED when surface_res is unset (curvier patch → a real grid, not the floor)
clean()
g = make_grid(1.0, 1.0, subdiv=12)
displace_quadric(g, 0.6, 0.6)
r3 = run("fit", model="quadric", as_surface="Patch2")
sr = r3.get("surface_res") or [0, 0]
check("E: default resolution suggested when surface_res unset",
      r3.get("surface") == "Patch2" and min(sr) >= 4, f"res={sr}")


# ─────── F. PROGRESSIVE — quadric gross form + a localized bump on the residual ───────
print("== SPEC19-F: progressive layering recovers a quadric base + a Gaussian bump ==")
clean()
CX, CY, AMP, W = 0.18, 0.10, 0.09, 0.16
g = make_grid(1.2, 1.0, subdiv=24)
bpy.context.view_layer.objects.active = g
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(g.data)
for vv in bm.verts:                          # z = gentle dome + ONE off-centre bump
    x, yv = vv.co.x, vv.co.y
    vv.co.z = (-0.08 * x * x - 0.08 * yv * yv
               + AMP * math.exp(-((x - CX) ** 2 + (yv - CY) ** 2) / (W * W)))
bmesh.update_edit_mesh(g.data)
bpy.ops.object.mode_set(mode='OBJECT')

# tol is the single residual target: a loose default leaves the base "clean" and adds no
# bumps; ask for sub-mm fidelity (tol=1.0) and progressive layers until it gets there.
rb = run("fit", model="quadric")                                            # base: bump left behind
rp = run("fit", model="quadric", progressive=True, basis_terms=3, tol=1.0)  # layered: explains it
check("F: progressive success", rp.get("success"), rp.get("error"))
pf = rp.get("params", {})
base_res = rb.get("residual_mm", 0)
prog_res = rp.get("residual_mm", 99)
check("F: at least one bump placed", pf.get("n_bumps", 0) >= 1, f"n_bumps={pf.get('n_bumps')}")
check("F: progressive residual substantially < base (the bump got explained)",
      prog_res < 0.4 * base_res, f"prog={prog_res} base={base_res}")
check("F: progressive residual now small (<4mm, a 90mm bump ~96% explained)",
      prog_res < 4.0, f"res={prog_res}mm")
bumps = pf.get("bumps", [])
near = any(abs(abs(b.get("cu", 9)) - CX) < 0.12 and abs(abs(b.get("cv", 9)) - CY) < 0.12
           and 0.04 < abs(b.get("amp", 0)) < 0.16 for b in bumps)
check("F: a bump lands near the authored centre with ~right amplitude", near, f"bumps={bumps}")

# the layered expr round-trips through the field sandbox
emitted = rp.get("expr")
clean()
g2 = make_grid(1.2, 1.0, subdiv=24)
bpy.context.view_layer.objects.active = g2
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.object.mode_set(mode='OBJECT')
rr = run("field", axis="auto", channel="axis:v", field_mode="add", expr=emitted)
check("F: layered expr parses + runs in the field sandbox", rr.get("success"), rr.get("error"))
r2 = run("fit", model="quadric", progressive=True, basis_terms=3, tol=1.0)
check("F: re-fit of the applied layered field reproduces the small residual (round-trip closed)",
      r2.get("residual_mm", 99) < 3.0, f"res={r2.get('residual_mm')}mm")

# rbf model is the standalone layered fit (base + bumps), same machinery, on the active mesh
rrbf = run("fit", model="rbf", basis_terms=3, tol=1.0)
check("G: model=rbf returns a layered height field with bumps",
      rrbf.get("success") and rrbf.get("model") == "rbf" and rrbf.get("params", {}).get("n_bumps", 0) >= 1,
      f"r={rrbf.get('model')} n={rrbf.get('params', {}).get('n_bumps')}")


# ───────────────── summary ─────────────────
print()
if failures:
    print(f"FAILED ({len(failures)}): " + ", ".join(failures))
    sys.exit(1)
print("ALL SPEC-19 ANALYTIC-FIT CHECKS PASSED")

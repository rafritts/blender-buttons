"""E2E for SPEC-19 Phase 1 — analytic patch fitting (feel op=fit model=quadric).

Runs the WORKING-TREE extension headless. Covers Phase 1's acceptance criteria:

  A. READ — a region of quads built as an EXACT height-field quadric z=αx²+βy² is recovered
     by model=quadric: coefficients a≈α, b≈β, c≈0, residual ≈ 0, captured ≈ 100%, and the
     shape verdict names it (saddle / dome). By symmetry the centred patch's PCA frame is the
     world axes, so recovery is exact, not approximate.
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


def make_superellipsoid(name, A, B, C, e1, e2, n=20):
    """A point-cloud mesh sampling a known superellipsoid surface (fit reads verts)."""
    def sg(a, e):
        return math.copysign(abs(math.sin(a)) ** e, math.sin(a))

    def cg(a, e):
        return math.copysign(abs(math.cos(a)) ** e, math.cos(a))
    verts = []
    for i in range(n):
        et = -math.pi / 2 + (i + 1) * (math.pi / (n + 1))
        for j in range(2 * n):
            om = -math.pi + j * (2 * math.pi / (2 * n))
            verts.append((A * cg(et, e1) * cg(om, e2),
                          B * cg(et, e1) * sg(om, e2), C * sg(et, e1)))
    verts += [(0.0, 0.0, -C), (0.0, 0.0, C)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], [])
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    return obj


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


# ───────────────── D. unbuilt menu refuses cleanly ─────────────────
print("== SPEC19-D: a not-yet-built basis teach-errors instead of silently failing ==")
clean()
g = make_grid(1.0, 1.0, subdiv=8)
r = run("fit", model="thin_plate")
check("D: model=thin_plate refuses with a Phase-2 teach error",
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

# rbf model is the standalone layered fit (base + bumps), same machinery, on the active mesh
rrbf = run("fit", model="rbf", basis_terms=3, tol=1.0)
check("G: model=rbf returns a layered height field with bumps",
      rrbf.get("success") and rrbf.get("model") == "rbf" and rrbf.get("params", {}).get("n_bumps", 0) >= 1,
      f"r={rrbf.get('model')} n={rrbf.get('params', {}).get('n_bumps')}")


# ─────── H. BSPLINE — control-grid fit, refinement, mint+re-fit ───────
print("== SPEC19-H: bspline control-grid surface — refines with more control points ==")
clean()
g = make_grid(1.2, 1.0, subdiv=24)
bpy.context.view_layer.objects.active = g
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(g.data)
for vv in bm.verts:                              # a smooth ripple: low control counts under-fit
    x, yv = vv.co.x, vv.co.y
    vv.co.z = 0.05 * math.sin(4 * x) + 0.04 * math.cos(5 * yv)
bmesh.update_edit_mesh(g.data)
bpy.ops.object.mode_set(mode='OBJECT')

rh = run("fit", model="bspline", basis_terms=6, as_surface="BPatch", resolution="24x20")
check("H: bspline success", rh.get("success"), rh.get("error"))
check("H: reports a 6×6 control grid", rh.get("params", {}).get("control_grid") == "6×6",
      f"grid={rh.get('params', {}).get('control_grid')}")
check("H: 6×6 residual small (<2mm)", rh.get("residual_mm", 99) < 2.0, f"res={rh.get('residual_mm')}mm")
check("H: minted patch 'BPatch'", rh.get("surface") == "BPatch", f"surface={rh.get('surface')}")
bpy.context.view_layer.objects.active = g
rc = run("fit", model="bspline", basis_terms=4)
rf = run("fit", model="bspline", basis_terms=8)
check("H: more control points → lower residual (4 > 6 > 8)",
      rc.get("residual_mm", 0) > rh.get("residual_mm", 9) > rf.get("residual_mm", 9),
      f"4={rc.get('residual_mm')} 6={rh.get('residual_mm')} 8={rf.get('residual_mm')}")
# re-fit the minted patch — the mesh faithfully IS the B-spline surface
patch = bpy.data.objects.get("BPatch")
bpy.context.view_layer.objects.active = patch
r2 = run("fit", model="bspline", basis_terms=6, target="BPatch")
check("H: re-fit of the minted patch ≈ 0 residual (mesh is the surface)",
      r2.get("residual_mm", 99) < 0.5, f"res={r2.get('residual_mm')}mm")


# ─────── I. SUPERQUADRIC — recover a closed mass, mint a blob, re-fit ───────
print("== SPEC19-I: superquadric recovers a closed mass + mints/re-fits a blob ==")
clean()
A0, B0, C0, E1, E2 = 0.55, 0.40, 0.30, 0.30, 0.30        # a rounded box (boxy both ways)
make_superellipsoid("SQ", A0, B0, C0, E1, E2)
r = run("fit", model="superquadric", as_surface="Blob", resolution="20x20")
check("I: success", r.get("success"), r.get("error"))
pp = r.get("params", {})
got = sorted([pp.get("size_xy", [0, 0])[0], pp.get("size_xy", [0, 0])[1], pp.get("size_z", 0)])
exp = sorted([A0, B0, C0])
check("I: radii recovered (axis-permutation-robust, sorted)",
      all(abs(g - e) < 0.03 for g, e in zip(got, exp)), f"got={got} exp={exp}")
check("I: boxiness exponents recovered (both < 0.6 → boxy)",
      pp.get("e1_profile", 9) < 0.6 and pp.get("e2_section", 9) < 0.6,
      f"e1={pp.get('e1_profile')} e2={pp.get('e2_section')}")
check("I: shape verdict names a box", "box" in pp.get("shape", ""), f"shape={pp.get('shape')}")
check("I: residual small (closed mass fits)", r.get("residual_mm", 99) < 5.0,
      f"res={r.get('residual_mm')}mm")
check("I: minted blob 'Blob'", r.get("surface") == "Blob" and r.get("surface_verts", 0) > 50,
      f"surface={r.get('surface')} verts={r.get('surface_verts')}")
# re-fit the minted blob — the parametric mesh IS the superquadric
blob = bpy.data.objects.get("Blob")
bpy.context.view_layer.objects.active = blob
r2 = run("fit", model="superquadric", target="Blob")
check("I: re-fit of the minted blob low residual", r2.get("residual_mm", 99) < 8.0,
      f"res={r2.get('residual_mm')}mm")
got2 = sorted([r2.get("params", {}).get("size_xy", [0, 0])[0],
               r2.get("params", {}).get("size_xy", [0, 0])[1], r2.get("params", {}).get("size_z", 0)])
check("I: re-fit radii ≈ original (round-trip closed)",
      all(abs(g - e) < 0.05 for g, e in zip(got2, exp)), f"got2={got2} exp={exp}")

# a sphere reads as round (e≈1) — the exponent knob actually moves
clean()
make_superellipsoid("SP", 0.5, 0.5, 0.5, 1.0, 1.0)
rs = run("fit", model="superquadric")
check("J: a sphere reads as round (e1,e2 ≈ 1, shape=ellipsoid)",
      abs(rs.get("params", {}).get("e1_profile", 0) - 1.0) < 0.2
      and "ellipsoid" in rs.get("params", {}).get("shape", ""),
      f"e1={rs.get('params', {}).get('e1_profile')} shape={rs.get('params', {}).get('shape')}")


# ─────── K. CURVE-NET — as_net mints iso-curves; nodes coincide, Gordon agrees ───────
print("== SPEC19-K: as_net mints an iso-curve net; nodes coincide + Gordon agrees ==")


def dome_bump(obj):
    """z = dome + an off-centre Gaussian bump — NON-separable, so the bilinear Gordon
    reconstruction is approximate (a separable quadric would reconstruct exactly at any
    density, hiding the convergence)."""
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    for v in bm.verts:
        x, y = v.co.x, v.co.y
        v.co.z = (-0.4 * x * x - 0.25 * y * y
                  + 0.12 * math.exp(-((x - 0.2) ** 2 + y ** 2) / 0.06))
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')


clean(); g = make_grid(1.2, 1.0, subdiv=22); dome_bump(g)
r = run("fit", model="quadric", progressive=True, basis_terms=2, tol=1.0,
        as_net="Net", resolution="6x6")
check("K: success", r.get("success"), r.get("error"))
check("K: minted a net 'Net'", r.get("net") == "Net", f"net={r.get('net')}")
check("K: 12 iso-curves (6 u-family + 6 v-family)", r.get("net_curves") == 12,
      f"curves={r.get('net_curves')}")
nc = bpy.data.collections.get("Net")
check("K: net collection holds the curve objects", nc is not None and len(nc.objects) == 12,
      f"objs={len(nc.objects) if nc else None}")
check("K: node gap ≈ 0 (the net CLOSES — families agree at crossings)",
      r.get("node_gap_mm", 9) < 1e-3, f"gap={r.get('node_gap_mm')}mm")
check("K: Gordon-vs-direct agreement small at 6×6 (<3.5mm over a bumpy patch)",
      r.get("gordon_rms_mm", 99) < 3.5, f"rms={r.get('gordon_rms_mm')}mm")
# denser net → tighter Gordon agreement (the two faces converge)
clean(); g = make_grid(1.2, 1.0, subdiv=22); dome_bump(g)
ra = run("fit", model="quadric", progressive=True, basis_terms=2, tol=1.0,
         as_net="NetA", resolution="3x3")
clean(); g = make_grid(1.2, 1.0, subdiv=22); dome_bump(g)
rb_ = run("fit", model="quadric", progressive=True, basis_terms=2, tol=1.0,
          as_net="NetB", resolution="9x9")
check("K: denser net → tighter Gordon agreement (faces converge)",
      rb_.get("gordon_rms_mm", 9) < ra.get("gordon_rms_mm", 0),
      f"3x3={ra.get('gordon_rms_mm')} 9x9={rb_.get('gordon_rms_mm')}")
# a bspline patch also yields a net (height-field face)
clean(); g = make_grid(1.0, 1.0, subdiv=18); displace_quadric(g, 0.3, -0.3)
rbn = run("fit", model="bspline", basis_terms=5, as_net="BNet", resolution="4x4")
check("K: bspline fit also mints a net", rbn.get("net") == "BNet" and rbn.get("net_curves") == 8,
      f"net={rbn.get('net')} curves={rbn.get('net_curves')}")


# ───────────────── summary ─────────────────
print()
if failures:
    print(f"FAILED ({len(failures)}): " + ", ".join(failures))
    sys.exit(1)
print("ALL SPEC-19 ANALYTIC-FIT CHECKS PASSED")

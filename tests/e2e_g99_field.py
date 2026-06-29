"""E2E for SPEC-13 / G99 — the field deformer (buttons-deform-macro op=field).

Runs the WORKING-TREE extension headless. Covers the spec's acceptance criteria:

  1. De-facet taper on a SUB-SHELL of a multi-shell mesh — selection-scoped, the other
     shell byte-identical; a smoothstep radial taper is smooth (monotone radii, no step).
  2. Per-component strand wave — channel=axis + (s/L) envelope: each strand's ROOT (s≈0)
     is unmoved, displacement grows to the tip; per_component resets s per strand.
  3. expr + clamp — a custom radial expression bounded by clamp_min/clamp_max.
  4. Sandbox rejection — an expr naming a forbidden builtin is refused (no mutation).
  5. Determinism — an absolute (mode=set) field re-run with identical args is a byte-
     identical no-op (the no-op detector fires).

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_g99_field.py
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


def ring_radii(obj, axis_idx=2, decimals=4, zmin=None, zmax=None, xmax=None):
    """Mean in-plane radius per Z-ring, world space (object mode). xmax filters verts to a
    single shell so a multi-shell mesh isn't lumped into one bogus ring centroid."""
    me = obj.data
    mat = obj.matrix_world
    buckets = {}
    other = [i for i in range(3) if i != axis_idx]
    for v in me.vertices:
        w = mat @ v.co
        z = w[axis_idx]
        if zmin is not None and z < zmin:
            continue
        if zmax is not None and z > zmax:
            continue
        if xmax is not None and w[0] > xmax:
            continue
        buckets.setdefault(round(z, decimals), []).append(w)
    out = {}
    for pos, ws in sorted(buckets.items()):
        cu = sum(w[other[0]] for w in ws) / len(ws)
        cv = sum(w[other[1]] for w in ws) / len(ws)
        r = sum(math.hypot(w[other[0]] - cu, w[other[1]] - cv) for w in ws) / len(ws)
        out[pos] = r
    return out


def vert_sig(obj):
    return [tuple(round(c, 6) for c in v.co) for v in obj.data.vertices]


# ───────────────── 1. De-facet taper on a sub-shell ─────────────────
print("== G99-1: smoothstep radial taper, selection-scoped to ONE shell ==")
clean()
# Two separate cylinders joined into ONE multi-shell mesh.
bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.5, depth=2.0, location=(0, 0, 1.0))
a = bpy.context.active_object
a.name = "Twin"
bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.5, depth=2.0, location=(2.0, 0, 1.0))
b = bpy.context.active_object
# add Z-rings to both so the taper has resolution
for obj in (a, b):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    side = [e for e in bm.edges
            if abs((obj.matrix_world @ e.verts[0].co).z - (obj.matrix_world @ e.verts[1].co).z) > 0.1]
    bmesh.ops.subdivide_edges(bm, edges=side, cuts=10, use_grid_fill=False)
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')
# join b into a → one mesh, two shells
bpy.context.view_layer.objects.active = a
b.select_set(True)
a.select_set(True)
bpy.ops.object.join()
twin = bpy.context.active_object

before = vert_sig(twin)
# select ONLY the first shell (x < 1.0), then taper it
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(twin.data)
bpy.ops.mesh.select_all(action='DESELECT')
for v in bm.verts:
    if (twin.matrix_world @ v.co).x < 1.0:
        v.select = True
bm.select_flush_mode()
bmesh.update_edit_mesh(twin.data)
bpy.ops.object.mode_set(mode='OBJECT')

r = run("field", axis="Z", channel="radial", field_mode="multiply",
        preset="smoothstep", preset_a=1.0, preset_b=0.5)
check("field reports success", r.get("success"), r.get("error"))
check("scope == selection", r.get("scope") == "selection", f"scope={r.get('scope')}")

after = vert_sig(twin)
# second shell (x > 1.0) must be byte-identical
n_far_unchanged = all(
    (abs(p[0] - q[0]) < 1e-7 and abs(p[1] - q[1]) < 1e-7 and abs(p[2] - q[2]) < 1e-7)
    for p, q in zip(before, after) if p[0] > 1.0)
check("second shell byte-identical (selection-scoped)", n_far_unchanged)

# Measure ONLY the tapered (first) shell, x<1.0, so the far shell can't pollute the
# ring centroid. smoothstep a=1.0→b=0.5 on a 0.5m cylinder ⇒ bottom r≈0.5, top r≈0.25.
tap = ring_radii(twin, xmax=1.0)
zs = sorted(tap.keys())
bottom_r, top_r = tap[zs[0]], tap[zs[-1]]
check("tapered bottom ~full radius (a=1.0 → 0.5m)", abs(bottom_r - 0.5) < 0.02,
      f"bottom radius={bottom_r:.4f}")
check("tapered top ~half radius (smoothstep b=0.5 → 0.25m)", abs(top_r - 0.25) < 0.02,
      f"top radius={top_r:.4f}")
check("radius monotonically decreasing bottom→top",
      all(tap[zs[i + 1]] <= tap[zs[i]] + 1e-6 for i in range(len(zs) - 1)))
# smoothness: no concave junction STEP between consecutive rings (the de-facet criterion).
diffs = [abs(tap[zs[i + 1]] - tap[zs[i]]) for i in range(len(zs) - 1)]
check("no large per-ring radius STEP (smooth, not stacked cylinders)",
      max(diffs) < 0.05, f"max consecutive Δradius={max(diffs):.4f}")


# ───────────────── 2. Per-component strand wave ─────────────────
print("== G99-2: per_component strand wave, root pinned (s/L envelope) ==")
clean()
# Three separate vertical strands (thin tubes) in ONE mesh.
strands = []
for i in range(3):
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.02, depth=1.0,
                                        location=(i * 0.2, 0, 0.5))
    s = bpy.context.active_object
    bpy.context.view_layer.objects.active = s
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(s.data)
    side = [e for e in bm.edges
            if abs((s.matrix_world @ e.verts[0].co).z - (s.matrix_world @ e.verts[1].co).z) > 0.05]
    bmesh.ops.subdivide_edges(bm, edges=side, cuts=12, use_grid_fill=False)
    bmesh.update_edit_mesh(s.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    strands.append(s)
bpy.context.view_layer.objects.active = strands[0]
for s in strands:
    s.select_set(True)
bpy.ops.object.join()
field_obj = bpy.context.active_object

# record per-vert (z, x) before
mat = field_obj.matrix_world
before = [(mat @ v.co).copy() for v in field_obj.data.vertices]

# select all, wave each strand laterally in X by an (s/L) envelope.
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.object.mode_set(mode='OBJECT')
r = run("field", axis="Z", channel="axis:X", per_component=True,
        expr="0.05 * (s/L) * sin(6.2831*(s/L))")
check("strand-wave reports success", r.get("success"), r.get("error"))
check("3 components detected", r.get("components") == 3, f"components={r.get('components')}")

after = [(mat @ v.co) for v in field_obj.data.vertices]
# root verts (lowest z of each strand, s≈0) must be unmoved in X; some tip verts must move.
zmin = min(w.z for w in before)
zmax = max(w.z for w in before)
root_dx = [abs(after[i].x - before[i].x) for i, w in enumerate(before) if w.z < zmin + 0.02]
tip_dx = [abs(after[i].x - before[i].x) for i, w in enumerate(before) if w.z > zmax - 0.02]
check("strand ROOTS unmoved (s≈0 envelope pins them)", max(root_dx) < 1e-4,
      f"max root Δx={max(root_dx):.5f}")
check("strand interior/tips displaced", max(tip_dx) >= 0 and max(after[i].x - before[i].x
      for i in range(len(before))) > 0.001,
      f"max Δx overall={max(abs(after[i].x-before[i].x) for i in range(len(before))):.5f}")


# ───────────────── 3. expr + clamp ─────────────────
print("== G99-3: custom expr radial bulge, bounded by clamp ==")
clean()
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.5, depth=2.0)
cyl = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(cyl.data)
side = [e for e in bm.edges
        if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.1]
bmesh.ops.subdivide_edges(bm, edges=side, cuts=16, use_grid_fill=False)
bmesh.update_edit_mesh(cyl.data)
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.object.mode_set(mode='OBJECT')
# barrel: r' = (1 + 0.4*sin(pi*t)) * r, but CLAMP the multiplier to <= 1.2.
r = run("field", axis="Z", channel="radial", field_mode="multiply",
        expr="1 + 0.4*sin(pi*t)", clamp_max=1.2, clamp_min=1.0)
check("expr field success", r.get("success"), r.get("error"))
fr = r.get("f_range", [None, None])
check("F clamped to [1.0, 1.2]", fr[0] is not None and fr[0] >= 1.0 - 1e-6 and fr[1] <= 1.2 + 1e-6,
      f"f_range={fr}")
# the mid radius is bulged but bounded to 1.2× (≤0.6m), not the unclamped ~0.7m.
rr = ring_radii(cyl)
zs = sorted(rr.keys())
mid_r = rr[zs[len(zs) // 2]]
check("mid radius bulged but capped at 1.2× (≈0.6m, not 0.7m)",
      0.55 < mid_r < 0.605, f"mid radius={mid_r:.4f}")


# ───────────────── 4. Sandbox rejection ─────────────────
print("== G99-4: forbidden expr is refused (no mutation) ==")
clean()
bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.5, depth=1.0)
c = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.object.mode_set(mode='OBJECT')
before = vert_sig(c)
for bad in ('__import__("os").system("echo hi")',
            'open("/etc/passwd")',
            't.__class__'):
    r = run("field", axis="Z", channel="radial", field_mode="multiply", expr=bad)
    check(f"rejected: {bad[:24]}", not r.get("success") and bool(r.get("error")),
          f"got {r}")
after = vert_sig(c)
check("mesh UNCHANGED after rejected exprs",
      all(p == q for p, q in zip(before, after)))


# ───────────────── 5. Determinism / no-op detection ─────────────────
print("== G99-5: absolute (set) field re-run is a byte-identical no-op ==")
clean()
bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.5, depth=2.0)
cyl = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(cyl.data)
side = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.1]
bmesh.ops.subdivide_edges(bm, edges=side, cuts=8, use_grid_fill=False)
bmesh.update_edit_mesh(cyl.data)
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.object.mode_set(mode='OBJECT')
# absolute radius set to 0.3 — idempotent: running twice is a no-op.
r1 = run("field", axis="Z", channel="radial", field_mode="set", expr="0.3")
check("first set-field success", r1.get("success"), r1.get("error"))
sig1 = vert_sig(cyl)
r2 = run("field", axis="Z", channel="radial", field_mode="set", expr="0.3")
sig2 = vert_sig(cyl)
check("re-run byte-identical (deterministic + idempotent set)",
      sig1 == sig2)
check("no-op detector fired on the identical re-run",
      bool(r2.get("no_op_warning")), f"no_op_warning={r2.get('no_op_warning')}")


# ───────────────── 6. Smoke: remaining channels + preset families ─────────────────
print("== G99-6: smoke every channel + preset family ==")


def fresh_cyl(sides=32, cuts=10):
    clean()
    bpy.ops.mesh.primitive_cylinder_add(vertices=sides, radius=0.5, depth=2.0)
    o = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bm_ = bmesh.from_edit_mesh(o.data)
    side = [e for e in bm_.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.1]
    bmesh.ops.subdivide_edges(bm_, edges=side, cuts=cuts, use_grid_fill=False)
    bmesh.update_edit_mesh(o.data)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    return o


cases = [
    ("channel=normal preset=bell", dict(channel="normal", preset="bell",
                                        amp=0.1, center=0.5, bell_width=0.2)),
    ("channel=twist preset=taper", dict(channel="twist", preset="taper",
                                        preset_a=0.0, preset_b=1.2)),
    ("channel=axis:Z preset=sine", dict(channel="axis:Z", preset="sine",
                                        amp=0.05, freq=3.0)),
    ("channel=radial preset=lobes (flute)", dict(channel="radial", field_mode="add",
                                                 preset="lobes", freq=12, amp=-0.01)),
    ("channel=radial preset=power", dict(channel="radial", field_mode="multiply",
                                         preset="power", preset_a=1.0, preset_b=0.3, k=2.0)),
    ("channel=radial points=curve", dict(channel="radial", field_mode="multiply",
                                         points=[[0.0, 1.0], [0.5, 0.4], [1.0, 0.9]],
                                         interp="cubic")),
    ("channel=vector frame=local", dict(channel="vector", frame="local",
                                        expr_x="0.03*sin(tau*t)", expr_z="0.0")),
    ("axis=auto radial taper", dict(axis="auto", channel="radial", field_mode="multiply",
                                    preset="taper", preset_a=1.0, preset_b=0.6)),
]
for label, kw in cases:
    fresh_cyl()
    r = run("field", **kw)
    check(label, r.get("success") and r.get("verts_moved", 0) > 0,
          f"{r.get('error') or r}")


# ───────────────── summary ─────────────────
print()
if failures:
    print(f"FAILED ({len(failures)}): " + ", ".join(failures))
    sys.exit(1)
print("ALL G99 FIELD CHECKS PASSED")

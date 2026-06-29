"""E2E — G186 (scale_verts pivot=INDIVIDUAL / Individual Origins) +
G187 (render op=engine — set the active engine as state, no render). Headless.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_g186_g187.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402

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
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    state.reset_history_state()


def two_disjoint_quads():
    """One mesh, TWO unconnected unit quads in the XY plane: A centred at x=0, B at x=10.
    Shared centroid is x=5; each quad's own centroid is x=0 / x=10. Scaling X about the
    shared pivot would drag both toward x=5; about Individual Origins each stays put."""
    me = bpy.data.meshes.new("Quads")
    bm = bmesh.new()
    for cx in (0.0, 10.0):
        vs = [bm.verts.new((cx - 0.5, -0.5, 0.0)),
              bm.verts.new((cx + 0.5, -0.5, 0.0)),
              bm.verts.new((cx + 0.5, 0.5, 0.0)),
              bm.verts.new((cx - 0.5, 0.5, 0.0))]
        bm.faces.new(vs)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("Quads", me)
    bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    return o


def quad_stats(obj):
    """(centroid_x, width_x) for each quad, split by sign of x. Read in OBJECT mode."""
    xs = [v.co.x for v in obj.data.vertices]
    a = [x for x in xs if x < 5.0]
    b = [x for x in xs if x >= 5.0]
    return ((sum(a) / len(a), max(a) - min(a)),
            (sum(b) / len(b), max(b) - min(b)))


# ─────────────────────────────────────────────────────────────────────────────
# G186 — pivot=INDIVIDUAL scales each connected island about its OWN centroid.
# ─────────────────────────────────────────────────────────────────────────────
print("\nG186 — scale_verts pivot=INDIVIDUAL (Individual Origins)\n")

clean()
obj = two_disjoint_quads()
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
r = run("scale_vertices", x=0.5, pivot="INDIVIDUAL")
bpy.ops.object.mode_set(mode='OBJECT')

check("INDIVIDUAL scale succeeds", r.get("success") is True, str(r.get("error")))
check("two disjoint quads → 2 islands", r.get("islands") == 2, str(r.get("islands")))
(ca, wa), (cb, wb) = quad_stats(obj)
check("quad A stays centred at its OWN centre x≈0 (did NOT drift toward shared x=5)",
      abs(ca - 0.0) < 1e-4, f"centroid_x={ca}")
check("quad B stays centred at its OWN centre x≈10",
      abs(cb - 10.0) < 1e-4, f"centroid_x={cb}")
check("quad A width halved (1.0→0.5)", abs(wa - 0.5) < 1e-4, f"width={wa}")
check("quad B width halved (1.0→0.5)", abs(wb - 0.5) < 1e-4, f"width={wb}")

# Contrast: the SHARED-centre pivot DOES drag both quads toward x=5 — confirms the
# distinction is real, not a no-op that happens to leave them put.
clean()
obj = two_disjoint_quads()
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
run("scale_vertices", x=0.5, pivot="SELECTION")
bpy.ops.object.mode_set(mode='OBJECT')
(ca2, _), (cb2, _) = quad_stats(obj)
check("SELECTION pivot DOES drag quad A toward shared centre (x≈2.5, not 0)",
      abs(ca2 - 2.5) < 1e-4, f"centroid_x={ca2}")
check("SELECTION pivot DOES drag quad B toward shared centre (x≈7.5, not 10)",
      abs(cb2 - 7.5) < 1e-4, f"centroid_x={cb2}")


# ─────────────────────────────────────────────────────────────────────────────
# G187 — set the active render engine as STATE, no frame rendered.
# ─────────────────────────────────────────────────────────────────────────────
print("\nG187 — render op=engine sets scene.render.engine without rendering\n")

clean()
avail = run("render_settings").get("available_engines", [])
check("render_settings reports available engines", bool(avail), str(avail))

# Missing name → a teaching error that names the requirement + the available list.
r = run("set_render_engine")
check("empty name errors (requirement named)", "error" in r, str(r))

# Invalid id → the build's real available list, not a crash.
r = run("set_render_engine", name="NOPE_ENGINE")
check("invalid engine returns error with the available list",
      "error" in r and "available" in r["error"], str(r.get("error")))

# Pick a real target engine that ISN'T the current one, so we prove a switch happened.
current = bpy.context.scene.render.engine
target = next((e for e in avail if e != current), None)
if target:
    r = run("set_render_engine", name=target)
    check(f"switch to {target} succeeds", r.get("success") is True, str(r.get("error")))
    check("scene.render.engine actually changed", bpy.context.scene.render.engine == target,
          bpy.context.scene.render.engine)
    check("result echoes previous engine", r.get("previous") == current, str(r.get("previous")))
    check("no file rendered (no filepath in result)", "filepath" not in r, str(r))

    # Re-setting the same engine is a clean no-op, not an error.
    r = run("set_render_engine", name=target)
    check("re-setting same engine reports unchanged", r.get("unchanged") is True, str(r))
else:
    check("build exposes a second engine to switch to", False,
          f"only {avail} available — cannot prove a switch")


print(f"\n{'PASSED' if not failures else 'FAILED'} — {len(failures)} failure(s)")
for f in failures:
    print(f"   ✗ {f}")
sys.exit(1 if failures else 0)

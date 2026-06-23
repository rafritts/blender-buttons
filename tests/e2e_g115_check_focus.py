"""E2E for G115 — `view op=check_focus` validates depth of field deterministically.
Headless.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_g115_check_focus.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402
import mathutils  # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402
from extension import introspect            # noqa: E402

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


def make_box(name, cx, cy, cz, half):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2 * half)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = (cx, cy, cz)
    bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    return o


def setup_cam(focus_dist, fstop):
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam_data.sensor_width = 36.0
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = fstop
    cam_data.dof.focus_distance = focus_dist
    cam = bpy.data.objects.new("Cam", cam_data)
    # place camera 0.5 m back along -Y looking +Y (forward = +Y)
    cam.location = (0, -0.5, 0)
    cam.rotation_euler = (mathutils.Vector((1.5707963, 0, 0)))  # look down +Y
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    bpy.context.view_layer.update()
    return cam


print("\nG115 — check_focus validates depth of field\n")

# ── macro-scale tabletop at f/4: a deep subject is BLURRED ───────────────────
clean()
# subject centered at origin, 0.09 m deep along Y (the camera axis) — like a donut.
make_box("Donut", 0, 0, 0, 0.045)
setup_cam(focus_dist=0.5, fstop=4.0)   # focus on the subject center, shallow DOF
r = introspect.check_focus({"targets": "Donut"})
check("check_focus succeeds", r.get("success") is True, str(r))
check("DOF slab at f/4 macro is shallow (< subject depth ~90mm)",
      r["dof_slab_mm"] is not None and r["dof_slab_mm"] < 90, f"slab={r['dof_slab_mm']}")
dt = r["targets"][0]
check("the deep subject reads BLURRED at f/4", dt["in_focus"] is False, str(dt))
check("blur is reported as a partial in-focus pct", 0 <= dt["in_focus_pct"] < 100, str(dt))

# ── stopping down to f/22 widens the slab → sharp ────────────────────────────
r2 = introspect.check_focus({"targets": "Donut", "aperture": 22.0})
check("f/22 widens the DOF slab vs f/4", r2["dof_slab_mm"] is None or r2["dof_slab_mm"] > r["dof_slab_mm"],
      f"f4={r['dof_slab_mm']} f22={r2['dof_slab_mm']}")

# ── the aperture resolver finds an f-stop that keeps the subject sharp ────────
r3 = introspect.check_focus({"targets": "Donut", "resolve_for": "Donut"})
ra = r3.get("resolved_aperture")
check("resolver returns an aperture (or None)", "resolved_aperture" in r3, str(r3))
if ra is not None:
    r4 = introspect.check_focus({"targets": "Donut", "aperture": ra})
    check("at the resolved aperture the subject is SHARP", r4["targets"][0]["in_focus"] is True,
          f"resolved f/{ra} → {r4['targets'][0]}")

# ── a thin subject at the focal plane is SHARP even wide open ─────────────────
clean()
make_box("Chip", 0, 0, 0, 0.001)       # 2 mm deep
setup_cam(focus_dist=0.5, fstop=2.0)
r5 = introspect.check_focus({"targets": "Chip"})
check("a paper-thin subject at focus is SHARP at f/2", r5["targets"][0]["in_focus"] is True, str(r5["targets"][0]))

# ── DOF off → reported, and everything is sharp ──────────────────────────────
clean()
make_box("Big", 0, 0, 0, 0.2)
cam = setup_cam(focus_dist=0.5, fstop=2.0)
cam.data.dof.use_dof = False
r6 = introspect.check_focus({"targets": "Big"})
check("check_focus reports DOF disabled", r6["use_dof"] is False, str(r6.get("use_dof")))

# ── end-to-end through the dispatch ──────────────────────────────────────────
clean()
make_box("Donut", 0, 0, 0, 0.045)
setup_cam(focus_dist=0.5, fstop=4.0)
disp = bb_server.execute_command({"tool": "check_focus", "params": {"targets": "Donut"}})
check("check_focus runs through the dispatch", disp.get("success") is True, str(disp.get("error")))


print(f"\n{'PASSED' if not failures else 'FAILED'} — {len(failures)} failure(s)")
for f in failures:
    print(f"   ✗ {f}")
sys.exit(1 if failures else 0)

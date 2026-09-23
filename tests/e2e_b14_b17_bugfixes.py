"""E2E for B14–B17. Headless, working-tree extension via execute_command.

  B14 — modifier modify writes Subsurf levels as an int
  B15 — focus_object is a distance snapshot; rig recomputes it; status says when stale
  B16 — select_ring then grab moves the ring, including after a FACE/EDGE select-all
  B17 — rest_on seats the evaluated shell; a Subsurf cage below z=0 is not below_floor

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_b14_b17_bugfixes.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bmesh  # noqa: E402
import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import validation  # noqa: E402
from extension.common import eval_world_bbox, world_bbox  # noqa: E402


def _load_status_formatter():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "server", "_core.py")
    src = open(path, encoding="utf-8").read()
    start = src.index("def _status")
    end = src.index("\ndef fmt_provenance")
    ns = {}
    exec(src[start:end], ns, ns)  # noqa: S102 — the shipped formatter
    return ns["_status"]


_status = _load_status_formatter()

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FAIL '} {label}" + ("" if cond else f"   {detail}"))
    if not cond:
        failures.append(label)


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    validation._intents.clear()


def below_names(result):
    v = result.get("validate") or {}
    return [f.get("object") for f in v.get("intent_free") or [] if f.get("check") == "below_floor"]


# ───────────────────────── B14 ─────────────────────────
print("== B14: Subsurf levels is an int ==")
clean()
bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0, 0, 0.2))
bpy.context.active_object.name = "Box"
r = run("add_modifier", type="SUBSURF", target="Box", name="Subsurf",
        levels=2.0, render_levels=2.0)
check("add accepts float levels", r.get("success") is True, str(r.get("error")))
mod = bpy.data.objects["Box"].modifiers["Subsurf"]
check("add stored viewport levels as int 2", mod.levels == 2 and isinstance(mod.levels, int),
      f"levels={mod.levels!r}")
r = run("modify_modifier", target="Box", modifier_name="Subsurf", levels=1.0, render_levels=3.0)
check("modify float levels succeeds", r.get("success") is True, str(r.get("error")))
check("modify stored levels 1 and render_levels 3",
      mod.levels == 1 and mod.render_levels == 3, f"{mod.levels!r} {mod.render_levels!r}")


# ───────────────────────── B15 ─────────────────────────
print("== B15: focus snapshot, rig recomputes, status names a stale plane ==")
clean()
bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0, 0, 0.1))
bpy.context.active_object.name = "Donut"
run("add_camera", name="Cam", x=0, y=-0.5, z=0.1, target="Donut")
cam = bpy.data.objects["Cam"]
r = run("set_camera_dof", focus_object="Donut", aperture=2.8, camera="Cam")
check("dof snapshot succeeds", r.get("success") is True, str(r.get("error")))
check("receipt names the target, not a live focus_object binding",
      r.get("focus_target") == "Donut" and "focus_object" not in r and r.get("tracking") is False,
      str({k: r.get(k) for k in ("focus_target", "focus_object", "tracking", "note")}))
check("note says not tracking", "not tracking" in (r.get("note") or ""), r.get("note"))
check("Blender focus_object stays clear", cam.data.dof.focus_object is None)
d0 = cam.data.dof.focus_distance
cam.location.y = -1.2
bpy.context.view_layer.update()
st = run("get_blender_status")
dof = (st.get("status") or {}).get("dof") or {}
check("status marks the plane stale after the camera moves",
      dof.get("stale") is True and dof.get("focus_target") == "Donut", str(dof))
block = _status({"blender_status": st.get("status")})
check("status block says STALE", "STALE" in block, block)
r = run("rig_around", name="Cam", subject="Donut", azimuth=0, elevation=0, distance=0.8)
check("rig recomputes the snapshot", "not tracking" in (r.get("focus_note") or ""),
      r.get("focus_note"))
check("rig changed the stored distance", abs(cam.data.dof.focus_distance - d0) > 0.05,
      f"{d0} -> {cam.data.dof.focus_distance}")
check("Blender focus_object still clear after rig", cam.data.dof.focus_object is None)
st = run("get_blender_status")
dof = (st.get("status") or {}).get("dof") or {}
check("status is fresh after rig", dof.get("stale") is not True and dof.get("focus_target") == "Donut",
      str(dof))
block = _status({"blender_status": st.get("status")})
check("fresh block names the snapshot", "not tracking" in block and "Donut" in block, block)
r = run("set_camera_dof", focus_distance=0.3, camera="Cam")
check("explicit distance clears the named target",
      r.get("success") is True and r.get("focus_target") is None and "bb_focus_target" not in cam.keys(),
      str(r.get("focus_target")))


# ───────────────────────── B16 ─────────────────────────
print("== B16: select_ring survives the edit round-trip ==")


def ring_then_grab(mode):
    clean()
    bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.02, vertices=16, location=(0, 0, 0.02))
    obj = bpy.context.active_object
    obj.name = "Plate"
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = mode
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    sel = run("select_ring", index=0, axis="Z", target="Plate")
    z0 = world_bbox(obj)
    grab = run("move_vertices", up=0.005, target="Plate")
    z1 = world_bbox(obj)
    return sel, grab, z0, z1


for label, mode in (("FACE", (False, False, True)), ("EDGE", (False, True, False))):
    sel, grab, z0, z1 = ring_then_grab(mode)
    ring_n = sel.get("verts_in_ring")
    check(f"{label} select_ring reports the live count",
          sel.get("success") and sel.get("verts_selected") == ring_n and ring_n == 16,
          str({k: sel.get(k) for k in ("success", "verts_in_ring", "verts_selected", "error")}))
    check(f"{label} grab moves the ring, not the mesh",
          grab.get("verts_moved") == ring_n, f"moved={grab.get('verts_moved')} ring={ring_n}")
    check(f"{label} top stays put", abs(z1[5] - z0[5]) < 1e-4,
          f"zmax {z0[5]:.4f} -> {z1[5]:.4f}")
    check(f"{label} bottom ring rose ~5mm", abs((z1[2] - z0[2]) - 0.005) < 1e-4,
          f"zmin {z0[2]:.4f} -> {z1[2]:.4f}")


# ───────────────────────── B17 ─────────────────────────
print("== B17: evaluated shell seats; cage hang is not below_floor ==")
clean()
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, -0.5))
bpy.context.active_object.name = "Table"
bpy.context.active_object.scale = (0.5, 0.5, 1.0)
bpy.ops.object.transform_apply(scale=True)
me = bpy.data.meshes.new("Plate")
bm = bmesh.new()
pts = [(0.02, 0.0), (0.045, 0.001), (0.07, 0.004), (0.09, 0.012)]
verts = [bm.verts.new((x, 0.0, z)) for x, z in pts]
for a, b in zip(verts, verts[1:]):
    bm.edges.new((a, b))
for v in bm.verts:
    v.select = True
bm.to_mesh(me)
bm.free()
plate = bpy.data.objects.new("Plate", me)
bpy.context.scene.collection.objects.link(plate)
bpy.context.view_layer.objects.active = plate
plate.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
spin = run("spin", axis="Z", steps=32, target="Plate")
check("plate spin succeeds", spin.get("success") is True, str(spin.get("error")))
bpy.ops.object.mode_set(mode="OBJECT")
run("add_modifier", type="SOLIDIFY", target="Plate", name="Solidify", thickness=0.002, offset=1)
run("add_modifier", type="SUBSURF", target="Plate", name="Subsurf", levels=2, render_levels=2)
plate.location.z = 0.01
bpy.context.view_layer.update()
r = run("rest_on", targets="Plate", target="Table", offset=0)
check("rest_on succeeds", r.get("success") is True, str(r.get("error")))
ez = eval_world_bbox(plate)
cz = world_bbox(plate)
check("evaluated foot is on the table (zmin ≈ 0)", abs(ez[2]) < 1.5e-4, f"eval zmin={ez[2]:.5f}")
check("floor does not call the seated plate below_floor",
      "Plate" not in below_names(r), str(below_names(r)))
if cz[2] < -1e-4:
    hang = (r.get("rested") or [{}])[0].get("cage_hang_mm")
    check("cage hang is reported, not treated as a failed seat",
          hang is not None and hang > 0.1, f"cage zmin={cz[2]:.5f} hang={hang}")
else:
    check("cage is not below the table either", cz[2] >= -1e-4, f"cage zmin={cz[2]:.5f}")

print("== B17: a shell below z=0 still trips the floor ==")
clean()
bpy.ops.mesh.primitive_plane_add(size=0.2, location=(0, 0, 0.001))
bpy.context.active_object.name = "Sheet"
run("add_modifier", type="SOLIDIFY", target="Sheet", name="Solidify", thickness=0.004, offset=-1)
bpy.context.view_layer.update()
sheet = bpy.data.objects["Sheet"]
ez = eval_world_bbox(sheet)
check("evaluated shell dips below z=0", ez[2] < -1e-4, f"eval zmin={ez[2]:.5f}")
v = validation.run_validate(["Sheet"])
hit = any(f.get("check") == "below_floor" and f.get("object") == "Sheet"
          for f in v.get("intent_free") or [])
check("floor reports the evaluated shell", hit, v.get("line"))

print("== B17: a modifier-free body still uses its cage ==")
clean()
bpy.ops.mesh.primitive_cube_add(size=0.1, location=(0, 0, 0))
bpy.context.active_object.name = "Dip"
v = validation.run_validate(["Dip"])
hit = any(f.get("check") == "below_floor" and f.get("object") == "Dip"
          for f in v.get("intent_free") or [])
check("cage below z=0 is still below_floor", hit, v.get("line"))


print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASSED")

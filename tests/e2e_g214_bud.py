"""E2E for G214 — the `bud` primitive: grow a CLOSED teardrop mass fused to a host,
preserving the host's identity (name, materials, modifier stack). Runs the WORKING-TREE
extension headless via execute_command.

Contrast with graft (which makes a NEW object and DROPS the host's materials + modifiers).

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_g214_bud.py
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
    state.reset_history_state()


def make_icosphere(name, r=0.05):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=r, location=(0, 0, 0))
    o = bpy.context.active_object
    o.name = name
    return o


def open_edges(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    n = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    bm.free()
    return n


def components(obj):
    """Count connected vertex islands via a bmesh flood."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    seen = set()
    comps = 0
    for v in bm.verts:
        if v.index in seen:
            continue
        comps += 1
        stack = [v]
        seen.add(v.index)
        while stack:
            w = stack.pop()
            for e in w.link_edges:
                o = e.other_vert(w)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
    bm.free()
    return comps


# ───────────────────────── bud on a SOLID host: clean fused mass + identity kept ─────────────────────────
print("== G214: bud on a closed host — clean weld, identity preserved ==")
clean()
host = make_icosphere("Blob", r=0.05)
# give it identity to protect: a material and a live modifier
mat = bpy.data.materials.new("Icing")
host.data.materials.append(mat)
mod = host.modifiers.new(name="Bevel", type='BEVEL')
mod.width = 0.001
mat_before = len(host.data.materials)
mod_before = len(host.modifiers)
verts_before = len(host.data.vertices)
zmin_before = min((host.matrix_world @ v.co).z for v in host.data.vertices)

# anchor at the BOTTOM pole so the drip hangs cleanly downward, past the host
bottom = min((host.matrix_world @ v.co for v in host.data.vertices), key=lambda w: w.z)
res = run("bud", host="Blob", at=list(bottom), diameter=0.02, hang=0.03, neck=0.008)
check("bud succeeded", res.get("success"), str(res)[:220])
check("host KEPT its name", "Blob" in bpy.data.objects, str(list(bpy.data.objects.keys())))
host = bpy.data.objects.get("Blob")
check("materials preserved (flag)", res.get("materials_preserved"), str(res))
check("modifiers preserved (flag)", res.get("modifiers_preserved"), str(res))
check("material slot survived on the mesh", len(host.data.materials) == mat_before,
      f"{mat_before} → {len(host.data.materials)}")
check("the live Bevel modifier survived", any(m.name == "Bevel" for m in host.modifiers),
      str([m.name for m in host.modifiers]))
check("mesh grew (the bead was added)", len(host.data.vertices) > verts_before,
      f"{verts_before} → {len(host.data.vertices)}")
check("fused result is a SINGLE connected mass (not two overlapping shells)",
      components(host) == 1, f"components={components(host)}")
check("fused result stays watertight (no open boundary edges)", open_edges(host) == 0,
      f"open_edges={open_edges(host)}")
zmin_after = min((host.matrix_world @ v.co).z for v in host.data.vertices)
check("the bead HANGS below the host (bbox floor dropped)", zmin_after < zmin_before - 0.01,
      f"zmin {round(zmin_before, 4)} → {round(zmin_after, 4)}")
# validate should have run (bud is in VALIDATE_AFTER) and find no defects on the clean weld
val = (res.get("validate") or {}).get("line", "")
check("the always-on validate floor ran after bud", bool(val), str(res.get("validate")))


# ───────────────────────── bud on an OPEN host: identity kept + honest note ─────────────────────────
print("== G214: bud on an OPEN shell — identity kept, honest open-host note ==")
clean()
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.05, segments=24, ring_count=16, location=(0, 0, 0))
dome = bpy.context.active_object
dome.name = "Shell"
dome.data.materials.append(bpy.data.materials.new("Glaze"))
mat_before = len(dome.data.materials)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.object.mode_set(mode='OBJECT')
for v in dome.data.vertices:
    if v.co.z < -0.002:
        v.select = True
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.delete(type='VERT')
bpy.ops.object.mode_set(mode='OBJECT')
verts_before = len(dome.data.vertices)

# anchor on the rim (a boundary vert), drip downward
rim = min((dome.matrix_world @ v.co for v in dome.data.vertices
           if abs((dome.matrix_world @ v.co).z) < 0.006), key=lambda w: -w.x, default=None)
res = run("bud", host="Shell", at=list(rim), diameter=0.012, hang=0.02, neck=0.005, solver="FLOAT")
check("bud on open shell returns a result (success or honest error)",
      res.get("success") or res.get("error"), str(res)[:200])
if res.get("success"):
    check("open-host identity kept (name)", "Shell" in bpy.data.objects)
    check("open-host material preserved",
          len(bpy.data.objects["Shell"].data.materials) == mat_before, str(res))
    check("mesh grew (bead present)", len(bpy.data.objects["Shell"].data.vertices) > verts_before,
          f"{verts_before} → {len(bpy.data.objects['Shell'].data.vertices)}")
    check("open host is honestly flagged in the notes",
          any("open" in n.lower() for n in res.get("notes", [])), str(res.get("notes")))


print()
if failures:
    print(f"e2e_g214_bud :: FAILED — {len(failures)}: {failures}")
    sys.exit(1)
print("e2e_g214_bud :: PASSED — 0 failures")

"""E2E for SPEC-18 Phase 1 — uv op=unwrap + material space=uv. Headless.

Exercises the extension handlers directly (bypassing the socket), against a fresh
factory-startup scene, so it never touches a live design session.

Covers:
  • uv_unwrap creates a UV layer for each no-seam method (smart/cube/cylinder/sphere)
  • multi-target unwrap (each mesh gets its own UVs)
  • mode hygiene (G157): the scene is left in OBJECT mode
  • registration / categorization (mutating, not a read, not lock-exempt)
  • material space=uv refuses legibly when the mesh has no UV layer
  • material space=uv wires TexCoord.UV + Image projection='FLAT'
  • material space=box (default) still wires TexCoord.Object + projection='BOX'

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_uv_unwrap.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402
from extension import uv as bb_uv           # noqa: E402
from extension import textures              # noqa: E402

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


def make_cylinder(name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=1.0, radius2=1.0, depth=2.0)
    bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def make_cube(name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def tiny_png(path):
    """A real 4x4 PNG on disk — image_node loads from a file path."""
    img = bpy.data.images.new("uv_test_tex", 4, 4)
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    return path


# ── 0. registration + categorization ─────────────────────────────────────────
print("[0] registration & categorization")
check("uv_unwrap registered in TOOLS", "uv_unwrap" in bb_server.TOOLS)
check("uv_unwrap is a MUTATOR (not non-undoable)", "uv_unwrap" not in state.NON_UNDOABLE_TOOLS)
check("uv_unwrap is NOT lock-exempt", "uv_unwrap" not in bb_server.LOCK_EXEMPT_TOOLS)
check("uv_unwrap NOT in NOOP_CHECK (UV isn't geometry)", "uv_unwrap" not in bb_server.NOOP_CHECK_TOOLS)

# ── 1. unwrap each no-seam method ────────────────────────────────────────────
print("[1] unwrap methods")
for method in ("smart", "cube", "cylinder", "sphere"):
    clean()
    obj = make_cylinder(f"Cyl_{method}")
    r = bb_uv.uv_unwrap({"target": obj.name, "method": method})
    ok = r.get("success") and r.get("count") == 1
    check(f"{method}: unwrap ok", ok, str(r)[:160])
    if ok:
        check(f"{method}: mesh has a UV layer", len(obj.data.uv_layers) >= 1)
        # a non-degenerate unwrap writes non-zero UV spread (not all coords identical)
        uvs = [tuple(round(c, 4) for c in d.uv) for d in obj.data.uv_layers.active.data]
        check(f"{method}: UVs are non-degenerate", len(set(uvs)) > 1, f"distinct={len(set(uvs))}")
        check(f"{method}: left in OBJECT mode (G157)", bpy.context.mode == 'OBJECT')

# ── 2. multi-target unwrap (each mesh its own UVs) ───────────────────────────
print("[2] multi-target unwrap")
clean()
a, b = make_cylinder("MugA"), make_cube("PlateB")
r = bb_uv.uv_unwrap({"target": ["MugA", "PlateB"], "method": "smart"})
check("multi: both unwrapped", r.get("success") and r.get("count") == 2, str(r)[:160])
check("multi: MugA has UVs", len(a.data.uv_layers) >= 1)
check("multi: PlateB has UVs", len(b.data.uv_layers) >= 1)

# ── 3. unknown method refused ────────────────────────────────────────────────
print("[3] bad method")
clean()
make_cube("X")
r = bb_uv.uv_unwrap({"target": "X", "method": "angle"})
check("angle (Phase 2) refused with guidance", not r.get("success") and "Phase 2" in r.get("error", ""),
      str(r)[:160])

# ── 4. material space=uv refusal (no UV layer) ───────────────────────────────
print("[4] material space=uv refusal")
clean()
make_cube("NoUV")
path = tiny_png(os.path.join("/tmp", "uv_e2e_tex.png"))
r = textures.set_textured_material({"target": "NoUV", "maps": {"diffuse": path}, "space": "uv"})
check("space=uv with no UV layer refuses", not r.get("success") and "no UV layer" in r.get("error", ""),
      str(r)[:160])
check("refusal points at uv op=unwrap", "uv op=unwrap" in r.get("error", ""), str(r)[:160])

# ── 5. material space=uv success → TexCoord.UV + projection FLAT ──────────────
print("[5] material space=uv node graph")
clean()
obj = make_cylinder("Wrapped")
bb_uv.uv_unwrap({"target": "Wrapped", "method": "cylinder"})
r = textures.set_textured_material({"target": "Wrapped", "maps": {"diffuse": path}, "space": "uv"})
check("space=uv applies", r.get("success"), str(r)[:160])
check("result records space=uv", r.get("space") == "uv")
if r.get("success"):
    mat = bpy.data.materials.get(r["material"])
    nt = mat.node_tree
    img_nodes = [n for n in nt.nodes if n.type == 'TEX_IMAGE']
    check("image node projection=FLAT", img_nodes and all(n.projection == 'FLAT' for n in img_nodes))
    texco = next((n for n in nt.nodes if n.type == 'TEX_COORD'), None)
    mapping = next((n for n in nt.nodes if n.type == 'MAPPING'), None)
    # the UV output of TexCoord must feed the Mapping vector
    uv_feeds_mapping = False
    if texco and mapping:
        for link in nt.links:
            if (link.from_node == texco and link.from_socket.name == 'UV'
                    and link.to_node == mapping):
                uv_feeds_mapping = True
    check("TexCoord.UV feeds Mapping", uv_feeds_mapping)

# ── 6. material space=box (default) → TexCoord.Object + projection BOX ────────
print("[6] material space=box default unchanged")
clean()
obj = make_cube("Boxed")
r = textures.set_textured_material({"target": "Boxed", "maps": {"diffuse": path}})
check("default (no space) applies", r.get("success"), str(r)[:160])
check("result records space=box", r.get("space") == "box")
if r.get("success"):
    mat = bpy.data.materials.get(r["material"])
    nt = mat.node_tree
    img_nodes = [n for n in nt.nodes if n.type == 'TEX_IMAGE']
    check("image node projection=BOX", img_nodes and all(n.projection == 'BOX' for n in img_nodes))
    texco = next((n for n in nt.nodes if n.type == 'TEX_COORD'), None)
    mapping = next((n for n in nt.nodes if n.type == 'MAPPING'), None)
    obj_feeds_mapping = any(
        (link.from_node == texco and link.from_socket.name == 'Object' and link.to_node == mapping)
        for link in nt.links) if (texco and mapping) else False
    check("TexCoord.Object feeds Mapping", obj_feeds_mapping)

# ── summary ──────────────────────────────────────────────────────────────────
print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL PASS")

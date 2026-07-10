"""E2E for the generic PBR-folder importer's node wiring (extension side). Headless.

Exercises extension/textures.py::set_textured_material with the FULL map set
(diffuse/roughness/metal/normal/ao/height + opt-in displacement, and the gloss path)
against the real on-disk Poliigon library, asserting the Principled node graph.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
       --python /abs/path/to/tests/e2e_pbr_material.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import textures   # noqa: E402
from extension import state      # noqa: E402

failures = []
# Point BB_PBR_ASSET_DIR at a PBR map folder (e.g. a Poliigon 4K export) to run the
# node-wiring assertions; unset, every block below prints SKIP with this message.
ASSET = os.environ.get("BB_PBR_ASSET_DIR", "")


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


def make_cube(name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def maps_from_dir(d):
    """Tiny inline classifier (the server's classifier is the authoritative one;
    here we just need the real paths keyed by role)."""
    kw = {"BaseColor": "diffuse", "Roughness": "roughness", "Metallic": "metal",
          "Normal": "normal", "AmbientOcclusion": "ao", "Displacement": "height"}
    out = {}
    for f in os.listdir(d):
        for token, role in kw.items():
            if token in f:
                out[role] = os.path.join(d, f)
    return out


def linked_to(nt, node_type, bsdf_input):
    """True if some node of node_type feeds bsdf's named input (directly or via 1 hop)."""
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    inp = bsdf.inputs[bsdf_input]
    if not inp.links:
        return False
    src = inp.links[0].from_node
    if src.bl_idname == node_type:
        return True
    # one hop back (e.g. NormalMap, Mix, Invert in between)
    for i in src.inputs:
        for lk in i.links:
            if lk.from_node.bl_idname == node_type:
                return True
    return False


# ── 1. Full Poliigon set + displacement ──────────────────────────────────────
print("[1] full Poliigon map set with displacement")
if not os.path.isdir(ASSET):
    print(f"  SKIP — set BB_PBR_ASSET_DIR to a PBR map folder (got {ASSET!r})")
else:
    clean()
    cube = make_cube("Stone")
    maps = maps_from_dir(ASSET)
    check("classified all 6 maps", len(maps) == 6, f"got {sorted(maps)}")
    res = textures.set_textured_material({
        "target": "Stone", "maps": maps, "scale": 1.0, "displacement": 0.1,
        "asset_id": "Poliigon_StoneQuartzite_8060",
    })
    check("build succeeded", res.get("success"), res.get("error", ""))
    check("assigned to Stone", res.get("assigned_to") == ["Stone"], str(res.get("assigned_to")))
    mat = cube.data.materials[0] if cube.data.materials else None
    check("material on slot 0", mat is not None)
    if mat:
        nt = mat.node_tree
        tex_imgs = [n for n in nt.nodes if n.bl_idname == 'ShaderNodeTexImage']
        check("6 image-texture nodes", len(tex_imgs) == 6, f"got {len(tex_imgs)}")
        check("base color driven by a node", linked_to(nt, 'ShaderNodeMix', 'Base Color')
              or linked_to(nt, 'ShaderNodeTexImage', 'Base Color'))
        check("AO multiply present (Mix MULTIPLY)",
              any(n.bl_idname == 'ShaderNodeMix' and n.blend_type == 'MULTIPLY' for n in nt.nodes))
        check("roughness wired", linked_to(nt, 'ShaderNodeTexImage', 'Roughness'))
        check("metallic wired", linked_to(nt, 'ShaderNodeTexImage', 'Metallic'))
        check("normal via NormalMap node", linked_to(nt, 'ShaderNodeNormalMap', 'Normal'))
        disp = [n for n in nt.nodes if n.bl_idname == 'ShaderNodeDisplacement']
        check("displacement node present", len(disp) == 1)
        if disp:
            out = next(n for n in nt.nodes if n.bl_idname == 'ShaderNodeOutputMaterial')
            check("displacement → output", bool(out.inputs['Displacement'].links)
                  and out.inputs['Displacement'].links[0].from_node == disp[0])
            check("displacement scale = 0.1", abs(disp[0].inputs['Scale'].default_value - 0.1) < 1e-6)
        check("maps_wired lists ao+displacement",
              "ao" in res["maps_wired"] and any("displacement" in w for w in res["maps_wired"]),
              str(res["maps_wired"]))

# ── 2. displacement=0 omits the displacement node (Poliigon default) ──────────
print("[2] displacement=0 → no displacement node")
if os.path.isdir(ASSET):
    clean()
    make_cube("Stone2")
    res = textures.set_textured_material({
        "target": "Stone2", "maps": maps_from_dir(ASSET), "displacement": 0.0,
    })
    mat = bpy.data.objects["Stone2"].data.materials[0]
    disp = [n for n in mat.node_tree.nodes if n.bl_idname == 'ShaderNodeDisplacement']
    check("no displacement node at strength 0", len(disp) == 0)

# ── 3. gloss path → Invert node into Roughness ───────────────────────────────
print("[3] gloss map inverts into roughness")
if os.path.isdir(ASSET):
    clean()
    make_cube("Glossy")
    m = maps_from_dir(ASSET)
    res = textures.set_textured_material({
        "target": "Glossy",
        "maps": {"diffuse": m["diffuse"], "gloss": m["roughness"]},  # reuse a gray map as gloss
    })
    mat = bpy.data.objects["Glossy"].data.materials[0]
    nt = mat.node_tree
    check("invert node present", any(n.bl_idname == 'ShaderNodeInvert' for n in nt.nodes))
    check("roughness fed via invert", linked_to(nt, 'ShaderNodeInvert', 'Roughness'))
    check("gloss→roughness in wired", any("gloss" in w for w in res["maps_wired"]), str(res["maps_wired"]))

# ── 4. existing Poly Haven paths still work: tint multiply + base_color override ──
print("[4] tint + base_color override (Poly Haven path regression)")
if os.path.isdir(ASSET):
    m = maps_from_dir(ASSET)
    clean(); make_cube("Tinted")
    textures.set_textured_material({"target": "Tinted",
                                    "maps": {"diffuse": m["diffuse"]}, "tint": [0.5, 0.4, 0.35]})
    nt = bpy.data.objects["Tinted"].data.materials[0].node_tree
    check("tint adds a MULTIPLY mix into base color",
          any(n.bl_idname == 'ShaderNodeMix' and n.blend_type == 'MULTIPLY' for n in nt.nodes)
          and linked_to(nt, 'ShaderNodeMix', 'Base Color'))

    clean(); cube = make_cube("Golden")
    textures.set_textured_material({"target": "Golden",
                                    "maps": {"diffuse": m["diffuse"], "roughness": m["roughness"]},
                                    "base_color": [1.0, 0.8, 0.2], "metallic": 1.0})
    nt = bpy.data.objects["Golden"].data.materials[0].node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    check("base_color override sets scalar (no diffuse node link)", not bsdf.inputs['Base Color'].links
          and abs(bsdf.inputs['Base Color'].default_value[0] - 1.0) < 1e-6)
    check("metallic override sets scalar", not bsdf.inputs['Metallic'].links
          and abs(bsdf.inputs['Metallic'].default_value - 1.0) < 1e-6)
    check("roughness map still wired under override", linked_to(nt, 'ShaderNodeTexImage', 'Roughness'))

print()
if failures:
    print(f"e2e_pbr_material :: FAILED — {len(failures)} failure(s): {failures}")
    sys.exit(1)
print("e2e_pbr_material :: PASSED — 0 failure(s)")

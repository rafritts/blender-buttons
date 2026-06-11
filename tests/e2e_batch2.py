"""E2E for batch-2 gap fixes (U5, T3) — material introspection. Headless.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_batch2.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok    {label}")
    else:
        failures.append(label)
        print(f"  FAIL  {label}  {detail}")


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)


def make_principled(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat, nt, bsdf


def box_with(name, mat):
    run("add_box", name=name, width=1.0, depth=1.0, height=1.0)
    o = bpy.data.objects[name]
    o.data.materials.clear()
    o.data.materials.append(mat)
    return o


# ───────────── literal Principled values still report verbatim ──────────────
print("== literal Principled values unchanged ==")
clean()
mat, nt, bsdf = make_principled("plastic")
bsdf.inputs['Base Color'].default_value = (0.1, 0.2, 0.8, 1.0)
bsdf.inputs['Roughness'].default_value = 0.3
box_with("b_plastic", mat)
d = run("describe", name="b_plastic")
m = d["materials"][0]
check("literal base_color reported", m.get("base_color")[:3] == [0.1, 0.2, 0.8], str(m))
check("literal roughness reported", m.get("roughness") == 0.3, str(m))
check("no false nodegraph flag", "base_color_driven" not in m, str(m))
check("describe shows color", "color=[0.1, 0.2, 0.8]" in d["description"], d["description"])

# ───────────────── U5: node-graph-driven base color is flagged ───────────────
print("== U5: node-graph base color reported as unreliable, no false glow ==")
clean()
mat, nt, bsdf = make_principled("skin")
rgb = nt.nodes.new('ShaderNodeRGB')
nt.links.new(rgb.outputs['Color'], bsdf.inputs['Base Color'])
# Principled default: Emission Strength 1.0, Emission Color black → renders no glow.
box_with("b_skin", mat)
d = run("describe", name="b_skin")
m = d["materials"][0]
check("base_color_driven flagged nodegraph", m.get("base_color_driven") == "nodegraph", str(m))
check("no misleading base_color value", "base_color" not in m, str(m))
check("no false emission glow off the black default", "emission_strength" not in m, str(m))
check("describe says summary unreliable",
      "nodegraph-driven (summary unreliable)" in d["description"], d["description"])
check("describe does NOT claim a glow", "glow=" not in d["description"], d["description"])

# ───────────── U5: a node-driven roughness/metallic socket is flagged ────────
print("== U5: node-driven roughness/metallic flagged, not defaulted ==")
clean()
mat, nt, bsdf = make_principled("scan")
rgh = nt.nodes.new('ShaderNodeTexImage')
nt.links.new(rgh.outputs['Color'], bsdf.inputs['Roughness'])
box_with("b_scan", mat)
d = run("describe", name="b_scan")
m = d["materials"][0]
check("roughness_driven flagged", m.get("roughness_driven") == "nodegraph", str(m))
check("no misleading literal roughness", "roughness" not in m, str(m))
check("describe shows rough=nodegraph", "rough=nodegraph" in d["description"], d["description"])

# ───────────────────── T3: tint read back from the live mix ──────────────────
print("== T3: tint surfaced from the live MULTIPLY node ==")
clean()
mat, nt, bsdf = make_principled("rope_mat")
diffuse = nt.nodes.new('ShaderNodeTexImage')
mix = nt.nodes.new('ShaderNodeMix')
mix.data_type = 'RGBA'
mix.blend_type = 'MULTIPLY'
mix.inputs['Factor'].default_value = 1.0
nt.links.new(diffuse.outputs['Color'], mix.inputs['A'])
mix.inputs['B'].default_value = (0.45, 0.33, 0.2, 1.0)
nt.links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
mat["bb_texture"] = json.dumps({"asset_id": "cotton_jersey", "resolution": "1k",
                                "scale": 1.0, "tint": [0.45, 0.33, 0.2]})
box_with("b_rope", mat)
d = run("describe", name="b_rope")
m = d["materials"][0]
check("base_color_tint read from live node",
      m.get("base_color_tint")[:3] == [0.45, 0.33, 0.2], str(m))
check("not falsely flagged as opaque nodegraph", "base_color_driven" not in m, str(m))
check("describe shows texture with tint",
      "texture(cotton_jersey@1k tint=[0.45, 0.33, 0.2])" in d["description"], d["description"])

# A later hand-edit of the tint node is reflected (honest instrument, not a stored echo).
mix.inputs['B'].default_value = (0.9, 0.1, 0.1, 1.0)
d2 = run("describe", name="b_rope")
check("live tint edit reflected (reads socket, not stored dict)",
      d2["materials"][0].get("base_color_tint")[:3] == [0.9, 0.1, 0.1],
      str(d2["materials"][0]))

print()
if failures:
    print(f"BATCH2 E2E: {len(failures)} FAILED: {failures}")
    sys.exit(1)
else:
    print("BATCH2 E2E: ALL TESTS PASSED")

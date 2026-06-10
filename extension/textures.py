"""Textured PBR materials wired from LOCAL image paths (no network here).

The server (server/polyhaven.py) downloads + caches Poly Haven maps and passes
their local file paths in; this module only wires the Principled BSDF node graph.
Box projection means no UV unwrap is needed or attempted.
"""

import json

import bpy

from .common import resolve_targets


def set_textured_material(params):
    """Wire a Principled BSDF from local PBR map paths. Internal — the
    set_textured_material MCP tool resolves the Poly Haven asset to paths first.

    target:     object OR group name.
    maps:       {"diffuse": path, "normal": path, "roughness": path, "metal": path}
                (any subset; diffuse expected). Paths are local files the server
                already cached.
    scale:      texture tiling scale (Mapping node), default 1.0.
    base_color: optional [r,g,b(,a)] — REPLACES the diffuse map (no diffuse node
                is created): the scan contributes roughness/normal/metal surface
                detail while the color is yours (e.g. gold trim from a gray scan).
    tint:       optional [r,g,b(,a)] — MULTIPLIES the diffuse map (keeps the
                grain/color variation, shifts it darker/warmer). Ignored when
                base_color is given.
    metallic:   optional 0..1 — sets the Metallic input directly, overriding the
                metal map if one was supplied.
    roughness:  optional 0..1 — sets the Roughness input directly, overriding
                the roughness map (1.0 = fully matte, no sheen).
    asset_id /  recorded on mat['bb_texture'] for describe() readback.
    resolution:
    """
    target = params.get("target")
    if not target:
        return {"error": "'target' (object or group name) is required"}
    maps = params.get("maps") or {}
    if not maps:
        return {"error": "no texture maps supplied"}
    scale = float(params.get("scale", 1.0))
    resolution = params.get("resolution", "1k")
    asset_id = params.get("asset_id", "")
    base_color = params.get("base_color")
    metallic = params.get("metallic")
    tint = params.get("tint")
    roughness = params.get("roughness")

    objs, err = resolve_targets(target)
    if err:
        return {"error": err}
    meshes = [o for o in objs if o.type == 'MESH']
    if not meshes:
        return {"error": f"'{target}' contains no mesh objects"}

    mat_name = params.get("material_name") or f"{target}_tex"
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (600, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (300, 0)
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

    # Box projection driven by object coordinates — no UV unwrap needed.
    texco = nt.nodes.new('ShaderNodeTexCoord'); texco.location = (-700, 0)
    mapping = nt.nodes.new('ShaderNodeMapping'); mapping.location = (-500, 0)
    mapping.inputs['Scale'].default_value = (scale, scale, scale)
    nt.links.new(texco.outputs['Object'], mapping.inputs['Vector'])

    def image_node(path, colorspace, y):
        n = nt.nodes.new('ShaderNodeTexImage'); n.location = (-250, y)
        img = bpy.data.images.load(path, check_existing=True)
        n.image = img
        img.colorspace_settings.name = colorspace
        n.projection = 'BOX'
        n.projection_blend = 0.2
        nt.links.new(mapping.outputs['Vector'], n.inputs['Vector'])
        return n

    wired = []
    if base_color is not None:
        c = list(base_color) + [1.0] if len(base_color) == 3 else list(base_color)
        bsdf.inputs['Base Color'].default_value = tuple(float(x) for x in c[:4])
        wired.append("base_color override")
    elif maps.get("diffuse"):
        d = image_node(maps["diffuse"], 'sRGB', 250)
        if tint is not None:
            t = list(tint) + [1.0] if len(tint) == 3 else list(tint)
            mix = nt.nodes.new('ShaderNodeMix'); mix.location = (60, 250)
            mix.data_type = 'RGBA'
            mix.blend_type = 'MULTIPLY'
            mix.inputs['Factor'].default_value = 1.0
            nt.links.new(d.outputs['Color'], mix.inputs['A'])
            mix.inputs['B'].default_value = tuple(float(x) for x in t[:4])
            nt.links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
            wired.append("diffuse*tint")
        else:
            nt.links.new(d.outputs['Color'], bsdf.inputs['Base Color'])
            wired.append("diffuse")
    if roughness is not None:
        bsdf.inputs['Roughness'].default_value = float(roughness)
        wired.append(f"roughness={float(roughness)}")
    elif maps.get("roughness"):
        r = image_node(maps["roughness"], 'Non-Color', 0)
        nt.links.new(r.outputs['Color'], bsdf.inputs['Roughness'])
        wired.append("roughness")
    if metallic is not None:
        bsdf.inputs['Metallic'].default_value = float(metallic)
        wired.append(f"metallic={float(metallic)}")
    elif maps.get("metal"):
        m = image_node(maps["metal"], 'Non-Color', 500)
        nt.links.new(m.outputs['Color'], bsdf.inputs['Metallic'])
        wired.append("metal")
    if maps.get("normal"):
        n = image_node(maps["normal"], 'Non-Color', -250)
        nm = nt.nodes.new('ShaderNodeNormalMap'); nm.location = (0, -250)
        nt.links.new(n.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
        wired.append("normal")

    store = {"asset_id": asset_id, "resolution": resolution, "scale": scale}
    if base_color is not None:
        store["base_color"] = [float(x) for x in base_color]
    if metallic is not None:
        store["metallic"] = float(metallic)
    if tint is not None:
        store["tint"] = [float(x) for x in tint]
    if roughness is not None:
        store["roughness"] = float(roughness)
    mat["bb_texture"] = json.dumps(store)

    for o in meshes:
        if o.data.materials:
            o.data.materials[0] = mat
        else:
            o.data.materials.append(mat)

    return {
        "success": True,
        "target": target,
        "material": mat.name,
        "assigned_to": [o.name for o in meshes],
        "maps_wired": wired,
    }


TOOLS = {
    "set_textured_material": set_textured_material,
}

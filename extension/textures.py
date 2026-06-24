"""Textured PBR materials wired from LOCAL image paths (no network here).

The server (server/polyhaven.py) downloads + caches Poly Haven maps and passes
their local file paths in; this module only wires the Principled BSDF node graph.
Box projection means no UV unwrap is needed or attempted.
"""

import json

import bpy

from .common import resolve_targets, has_material_slots


def set_textured_material(params):
    """Wire a Principled BSDF from local PBR map paths. Internal — the
    set_textured_material MCP tool resolves the Poly Haven asset to paths first.

    target:     object OR group name.
    maps:       {role: path} — any subset of: diffuse, roughness, gloss (inverted
                into roughness), metal, normal, height (→ bump displacement),
                ao (multiplied into base color), emission, alpha. Paths are local
                files the server already resolved. (Poly Haven passes the first four;
                the PBR-folder importer can pass the rest.)
    displacement: optional >0 — wire the height map through a Displacement node at
                this strength (BUMP method). 0/omitted = no displacement (matches a
                normal-map-only setup).
    scale:      texture tiling scale (Mapping node), default 1.0. Unitless.
    physical_size: G141 — real-world metres one texture tile should cover. When given,
                the Mapping scale is DERIVED per-axis from the object's world scale
                (world_scale / physical_size), so the grain reads at a true physical size
                regardless of the part's dimensions, and `scale` is ignored.
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
    # G141: physical_size (meters per texture tile) makes the box-projection scale a
    # DERIVED real-world quantity instead of a unitless guess — see the mapping block.
    physical_size = float(params.get("physical_size", 0.0) or 0.0)
    resolution = params.get("resolution", "1k")
    asset_id = params.get("asset_id", "")
    base_color = params.get("base_color")
    metallic = params.get("metallic")
    tint = params.get("tint")
    roughness = params.get("roughness")

    objs, err = resolve_targets(target)
    if err:
        return {"error": err}
    meshes = [o for o in objs if has_material_slots(o)]
    if not meshes:
        return {"error": f"'{target}' contains nothing that can hold a material"}
    from .common import linked_guard_any
    blocked = linked_guard_any(meshes)
    if blocked:
        return {"error": blocked}

    # G138: target may arrive as a list (multi-object shade with one material) —
    # derive a clean string label for the default material name.
    tgt_label = target if isinstance(target, str) else (target[0] if target else "material")
    mat_name = params.get("material_name") or f"{tgt_label}_tex"
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
    # G141: 'Object' coordinates are the mesh's LOCAL coords, so a texture feature's WORLD
    # size = its local size × the object's world scale. To make one tile span exactly
    # `physical_size` METRES in world space, the Mapping scale per axis is therefore
    # world_scale / physical_size — a value DERIVED from the part's measured transform,
    # not a unitless guess. Falls back to the raw `scale` when physical_size isn't given.
    if physical_size > 0.0:
        ws = meshes[0].matrix_world.to_scale()
        map_scale = tuple(abs(c) / physical_size for c in ws)
    else:
        map_scale = (scale, scale, scale)
    mapping.inputs['Scale'].default_value = map_scale
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

    def mix_multiply(a_socket, b_value_or_socket, y):
        mx = nt.nodes.new('ShaderNodeMix'); mx.location = (90, y)
        mx.data_type = 'RGBA'
        mx.blend_type = 'MULTIPLY'
        mx.inputs['Factor'].default_value = 1.0
        nt.links.new(a_socket, mx.inputs['A'])
        if isinstance(b_value_or_socket, bpy.types.NodeSocket):
            nt.links.new(b_value_or_socket, mx.inputs['B'])
        else:
            mx.inputs['B'].default_value = b_value_or_socket
        return mx.outputs['Result']

    wired = []
    # --- Base color: diffuse map (optional tint, optional AO multiply) or scalar override ---
    color_socket = None
    if base_color is not None:
        c = list(base_color) + [1.0] if len(base_color) == 3 else list(base_color)
        bsdf.inputs['Base Color'].default_value = tuple(float(x) for x in c[:4])
        wired.append("base_color override")
    elif maps.get("diffuse"):
        d = image_node(maps["diffuse"], 'sRGB', 250)
        color_socket = d.outputs['Color']
        wired.append("diffuse")
        if tint is not None:
            t = list(tint) + [1.0] if len(tint) == 3 else list(tint)
            color_socket = mix_multiply(color_socket, tuple(float(x) for x in t[:4]), 300)
            wired.append("tint")
    # AO darkens the base color (only meaningful when a color map feeds it).
    if maps.get("ao") and color_socket is not None:
        ao = image_node(maps["ao"], 'Non-Color', 150)
        color_socket = mix_multiply(color_socket, ao.outputs['Color'], 250)
        wired.append("ao")
    if color_socket is not None:
        nt.links.new(color_socket, bsdf.inputs['Base Color'])

    # --- Roughness: map, or gloss inverted, or scalar override ---
    if roughness is not None:
        bsdf.inputs['Roughness'].default_value = float(roughness)
        wired.append(f"roughness={float(roughness)}")
    elif maps.get("roughness"):
        r = image_node(maps["roughness"], 'Non-Color', 0)
        nt.links.new(r.outputs['Color'], bsdf.inputs['Roughness'])
        wired.append("roughness")
    elif maps.get("gloss"):
        g = image_node(maps["gloss"], 'Non-Color', 0)
        inv = nt.nodes.new('ShaderNodeInvert'); inv.location = (60, 0)
        nt.links.new(g.outputs['Color'], inv.inputs['Color'])
        nt.links.new(inv.outputs['Color'], bsdf.inputs['Roughness'])
        wired.append("gloss→roughness")

    # --- Metallic ---
    if metallic is not None:
        bsdf.inputs['Metallic'].default_value = float(metallic)
        wired.append(f"metallic={float(metallic)}")
    elif maps.get("metal"):
        m = image_node(maps["metal"], 'Non-Color', 500)
        nt.links.new(m.outputs['Color'], bsdf.inputs['Metallic'])
        wired.append("metal")

    # --- Normal ---
    if maps.get("normal"):
        n = image_node(maps["normal"], 'Non-Color', -250)
        nm = nt.nodes.new('ShaderNodeNormalMap'); nm.location = (0, -250)
        nt.links.new(n.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
        wired.append("normal")

    # --- Emission ---
    if maps.get("emission"):
        e = image_node(maps["emission"], 'sRGB', -500)
        ecol = 'Emission Color' if 'Emission Color' in bsdf.inputs else 'Emission'
        nt.links.new(e.outputs['Color'], bsdf.inputs[ecol])
        if 'Emission Strength' in bsdf.inputs:
            bsdf.inputs['Emission Strength'].default_value = 1.0
        wired.append("emission")

    # --- Alpha / opacity (G126: OPT-IN) ---
    # An alpha channel in a SURFACE scan is almost never whole-material transparency — it's
    # a crema/decal/cutout mask. Auto-wiring it into the BSDF Alpha made an opaque coffee
    # render 100% invisible. Only wire it when explicitly asked (use_alpha=True); otherwise
    # report it was detected-but-skipped so the agent can opt in if it really wants a cutout.
    alpha_skipped = False
    if maps.get("alpha"):
        if bool(params.get("use_alpha")):
            a = image_node(maps["alpha"], 'Non-Color', -750)
            nt.links.new(a.outputs['Color'], bsdf.inputs['Alpha'])
            try:
                mat.blend_method = 'CLIP'
            except Exception:
                pass
            wired.append("alpha")
        else:
            alpha_skipped = True

    # --- Displacement (height → Displacement node → Output), opt-in via `displacement` ---
    disp_amt = params.get("displacement")
    if maps.get("height") and disp_amt is not None and float(disp_amt) > 0:
        h = image_node(maps["height"], 'Non-Color', -1000)
        disp = nt.nodes.new('ShaderNodeDisplacement'); disp.location = (350, -400)
        disp.inputs['Scale'].default_value = float(disp_amt)
        nt.links.new(h.outputs['Color'], disp.inputs['Height'])
        nt.links.new(disp.outputs['Displacement'], out.inputs['Displacement'])
        try:
            mat.displacement_method = 'BUMP'
        except Exception:
            pass
        wired.append(f"displacement={float(disp_amt)}")

    store = {"asset_id": asset_id, "resolution": resolution, "scale": scale}
    if physical_size > 0.0:
        store["physical_size"] = physical_size
        store["scale"] = [round(c, 5) for c in map_scale]
    if base_color is not None:
        store["base_color"] = [float(x) for x in base_color]
    if metallic is not None:
        store["metallic"] = float(metallic)
    if tint is not None:
        store["tint"] = [float(x) for x in tint]
    if roughness is not None:
        store["roughness"] = float(roughness)
    if params.get("displacement"):
        store["displacement"] = float(params.get("displacement"))
    mat["bb_texture"] = json.dumps(store)

    slot_idx = int(params.get("slot")) if params.get("slot") is not None else 0
    for o in meshes:
        mats = o.data.materials
        if slot_idx < len(mats):
            mats[slot_idx] = mat
        elif slot_idx == len(mats):
            mats.append(mat)
        else:
            return {"error": f"'{o.name}' has {len(mats)} slot(s); slot {slot_idx} is "
                             f"out of range (can only append at index {len(mats)})"}

    out = {
        "success": True,
        "target": target,
        "material": mat.name,
        "slot": slot_idx,
        "assigned_to": [o.name for o in meshes],
        "maps_wired": wired,
    }
    if physical_size > 0.0:
        out["physical_size"] = physical_size
        out["map_scale"] = [round(c, 5) for c in map_scale]
    if alpha_skipped:
        out["alpha_skipped"] = True
        out.setdefault("notes", []).append(
            "an alpha map was detected but NOT wired (it would make the surface transparent — "
            "usually wrong for an opaque material). Pass use_alpha=True if you want it as a "
            "cutout/mask.")
    return out


TOOLS = {
    "set_textured_material": set_textured_material,
}

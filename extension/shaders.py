"""Stylized shaders: set_toon_material (cel/anime), add_outline/remove_outline.

These build ONE fixed node graph each — agents never touch raw nodes. All
parameters are stored as JSON on the material/object custom properties so
describe()/material_summary() can read them back verbatim instead of parsing
the graph.

EEVEE ONLY: the toon shader uses a Shader-to-RGB node, which only works in
Eevee. Cycles renders of these materials will look wrong.

Colors are scene-linear floats 0..1 — the same convention as set_material
(see gaps.md E6: Blender treats material floats as scene-linear).
"""

import json

import bpy

from .common import activate, resolve_targets


def _rgba(c, alpha=1.0):
    """Normalize a color to a 4-tuple of floats, or None."""
    if c is None:
        return None
    c = list(c)
    if len(c) == 3:
        c = c + [alpha]
    return tuple(float(x) for x in c[:4])


def _toon_default_shadow(base):
    """Anime shadows are cool, not black: scale the base ~0.55 and bias it
    slightly toward blue."""
    r, g, b, _a = base
    f = 0.55
    return (min(r * f * 0.92, 1.0), min(g * f * 0.97, 1.0), min(b * f * 1.12, 1.0), 1.0)


def _lerp_rgb(a, b, t):
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t,
            1.0)


def _build_toon_graph(mat, base, shadow, bands, softness, rim, rim_width,
                      grad_top, grad_bottom, rep_obj):
    """Wire the fixed toon node graph (see module docstring). Rebuilt from
    scratch each call so reuse-by-name stays idempotent."""
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (1000, 0)
    emit = nt.nodes.new('ShaderNodeEmission'); emit.location = (760, 0)
    emit.inputs['Strength'].default_value = 1.0
    nt.links.new(emit.outputs['Emission'], out.inputs['Surface'])

    # Lighting term: a white Diffuse BSDF -> Shader-to-RGB gives the raw N·L
    # shading as a color, which the ColorRamp quantizes into hard cel bands.
    diffuse = nt.nodes.new('ShaderNodeBsdfDiffuse'); diffuse.location = (-700, 240)
    diffuse.inputs['Color'].default_value = (1, 1, 1, 1)
    to_rgb = nt.nodes.new('ShaderNodeShaderToRGB'); to_rgb.location = (-480, 240)
    nt.links.new(diffuse.outputs['BSDF'], to_rgb.inputs['Shader'])

    ramp = nt.nodes.new('ShaderNodeValToRGB'); ramp.location = (-260, 240)
    nt.links.new(to_rgb.outputs['Color'], ramp.inputs['Factor'])
    cr = ramp.color_ramp
    cr.interpolation = 'CONSTANT'
    while len(cr.elements) > 1:
        cr.elements.remove(cr.elements[-1])
    cr.elements[0].position = 0.0
    cr.elements[0].color = shadow if bands > 1 else (1, 1, 1, 1)
    for i in range(1, bands):
        base_pos = i / bands
        # shadow_softness widens the darkest band (true gradient terminators
        # would need LINEAR interpolation, which breaks hard cel banding).
        pos = min(base_pos + softness * (1.0 - base_pos), 0.999)
        e = cr.elements.new(pos)
        e.position = pos
        e.color = _lerp_rgb(shadow, (1, 1, 1, 1), i / (bands - 1))

    # Base-color path: a flat color, or a vertical object-space gradient.
    base_out = None
    if grad_top is not None and grad_bottom is not None:
        texco = nt.nodes.new('ShaderNodeTexCoord'); texco.location = (-700, -220)
        sep = nt.nodes.new('ShaderNodeSeparateXYZ'); sep.location = (-480, -220)
        nt.links.new(texco.outputs['Object'], sep.inputs['Vector'])
        mr = nt.nodes.new('ShaderNodeMapRange'); mr.location = (-260, -220)
        nt.links.new(sep.outputs['Z'], mr.inputs[0])  # Value (float variant)
        zs = [v[2] for v in rep_obj.bound_box]
        mr.inputs[1].default_value = min(zs)   # From Min
        mr.inputs[2].default_value = max(zs)   # From Max
        mr.inputs[3].default_value = 0.0       # To Min
        mr.inputs[4].default_value = 1.0       # To Max
        grad = nt.nodes.new('ShaderNodeValToRGB'); grad.location = (-40, -220)
        grad.color_ramp.interpolation = 'LINEAR'
        grad.color_ramp.elements[0].position = 0.0
        grad.color_ramp.elements[0].color = grad_bottom
        grad.color_ramp.elements[1].position = 1.0
        grad.color_ramp.elements[1].color = grad_top
        nt.links.new(mr.outputs['Result'], grad.inputs['Factor'])
        base_out = grad.outputs['Color']

    mix = nt.nodes.new('ShaderNodeMixRGB'); mix.location = (220, 120)
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    nt.links.new(ramp.outputs['Color'], mix.inputs['Color1'])
    if base_out is not None:
        nt.links.new(base_out, mix.inputs['Color2'])
    else:
        mix.inputs['Color2'].default_value = base
    color_out = mix.outputs['Color']

    # Optional rim light added on top via a facing-weight cutoff.
    if rim is not None:
        lw = nt.nodes.new('ShaderNodeLayerWeight'); lw.location = (220, -120)
        rimramp = nt.nodes.new('ShaderNodeValToRGB'); rimramp.location = (400, -120)
        rc = rimramp.color_ramp
        rc.interpolation = 'CONSTANT'
        rc.elements[0].position = 0.0
        rc.elements[0].color = (0, 0, 0, 1)
        rc.elements[1].position = max(0.0, min(0.999, 1.0 - rim_width))
        rc.elements[1].color = rim
        nt.links.new(lw.outputs['Facing'], rimramp.inputs['Factor'])
        addn = nt.nodes.new('ShaderNodeMixRGB'); addn.location = (580, 0)
        addn.blend_type = 'ADD'
        addn.inputs['Factor'].default_value = 1.0
        nt.links.new(mix.outputs['Color'], addn.inputs['Color1'])
        nt.links.new(rimramp.outputs['Color'], addn.inputs['Color2'])
        color_out = addn.outputs['Color']

    nt.links.new(color_out, emit.inputs['Color'])


def set_toon_material(params):
    """Apply an anime/cel-shaded material as a fixed, parameterized node graph.

    EEVEE ONLY — uses a Shader-to-RGB node; Cycles renders will look wrong.
    Colors are scene-linear floats 0..1 (same convention as set_material).

    target:          object OR group name (group expands to every mesh inside).
    base_color:      [r,g,b(,a)] flat surface color. Required unless BOTH
                     gradient_top and gradient_bottom are given.
    shadow_color:    color of the darkest band. Default: base scaled ~0.55 and
                     biased cool (anime shadows are cool, not black).
    bands:           number of hard shading steps (>=1). 2-3 reads cleanest.
    shadow_softness: 0..1, widens the darkest band. (A true soft terminator needs
                     LINEAR interpolation, which would break the hard cel look,
                     so this nudges the band boundary instead.)
    rim_color:       optional rim/fresnel light color added at grazing edges.
    rim_width:       0..1 fraction of the silhouette the rim covers. Default 0.2.
    gradient_top /   optional vertical object-space color gradient that REPLACES
    gradient_bottom: the flat base color (e.g. lighter hair at the tips).
    material_name:   defaults to "<target>_toon"; reused/updated in place if present.
    """
    target = params.get("target")
    if not target:
        return {"error": "'target' (object or group name) is required"}
    objs, err = resolve_targets(target)
    if err:
        return {"error": err}
    meshes = [o for o in objs if o.type == 'MESH']
    if not meshes:
        return {"error": f"'{target}' contains no mesh objects"}

    base = _rgba(params.get("base_color"))
    grad_top = _rgba(params.get("gradient_top"))
    grad_bottom = _rgba(params.get("gradient_bottom"))
    if base is None and not (grad_top is not None and grad_bottom is not None):
        return {"error": "base_color is required (or supply both gradient_top and gradient_bottom)"}

    bands = int(params.get("bands", 2))
    if bands < 1:
        return {"error": "bands must be >= 1"}
    softness = float(params.get("shadow_softness", 0.05))
    shadow = _rgba(params.get("shadow_color")) or _toon_default_shadow(base or grad_bottom)
    rim = _rgba(params.get("rim_color"))
    rim_width = float(params.get("rim_width", 0.2))

    mat_name = params.get("material_name") or f"{target}_toon"
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    _build_toon_graph(mat, base, shadow, bands, softness, rim, rim_width,
                      grad_top, grad_bottom, meshes[0])

    stored = {
        "base_color": list(base) if base else None,
        "shadow_color": list(shadow),
        "bands": bands,
        "shadow_softness": softness,
        "rim_color": list(rim) if rim else None,
        "rim_width": rim_width,
        "gradient_top": list(grad_top) if grad_top else None,
        "gradient_bottom": list(grad_bottom) if grad_bottom else None,
        "graph_version": 1,
    }
    mat["bb_toon"] = json.dumps(stored)

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
        "bands": bands,
        "note": "Shader-to-RGB is Eevee-only; Cycles renders of this material look wrong.",
    }


TOOLS = {
    "set_toon_material": set_toon_material,
}

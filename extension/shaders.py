"""Stylized shader helpers: toon node-graph and inverted-hull outline builders.

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

from .common import activate, resolve_targets, has_material_slots


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


def _emission_material(name, color):
    """A flat, backface-culled emission material — the outline shell color."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    emit = nt.nodes.new('ShaderNodeEmission')
    emit.inputs['Color'].default_value = color
    emit.inputs['Strength'].default_value = 1.0
    nt.links.new(emit.outputs['Emission'], out.inputs['Surface'])
    # Cull front faces so only the flipped-normal back hull (the outline) shows.
    mat.use_backface_culling = True
    return mat


def _strip_outline(obj):
    """Remove the bb_outline modifier + the material slot it appended. Returns True
    if an outline was present."""
    state = obj.get("bb_outline")
    if state is None:
        return False
    mod = obj.modifiers.get("bb_outline")
    if mod is not None:
        obj.modifiers.remove(mod)
    try:
        data = json.loads(state)
        mat_name = data.get("material")
    except (ValueError, TypeError):
        mat_name = None
    if mat_name is not None and obj.data is not None:
        idx = next((i for i, m in enumerate(obj.data.materials)
                    if m is not None and m.name == mat_name), None)
        if idx is not None:
            activate(obj)
            obj.active_material_index = idx
            bpy.ops.object.material_slot_remove()
    del obj["bb_outline"]
    return True


TOOLS = {
}

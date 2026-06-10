"""Shading and materials: shade_smooth, shade_flat, set_material.

Materials use a Principled BSDF — the standard Blender shader that covers
~80% of real materials (color + metallic + roughness + IOR + emission + alpha).
For full shader-graph control, drop into Blender's node editor by hand.
"""

import math

import bpy

from .common import activate, resolve_targets


def _set_auto_smooth_angle(mesh, angle_deg):
    """Blender 4.1+ replaced mesh.use_auto_smooth/auto_smooth_angle with a modifier."""
    if hasattr(mesh, "use_auto_smooth"):
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = math.radians(angle_deg)


def shade_smooth(params):
    """Toggle smooth shading on per-face normals — the donut-tutorial right-click step.
    targets: object name / group / list / None (active). auto_smooth_angle in degrees
    (faces with edges sharper than this stay faceted)."""
    targets = params.get("targets")
    angle_deg = params.get("auto_smooth_angle", 30.0)
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    processed = []
    for o in objs:
        if o.type != 'MESH':
            continue
        activate(o)
        bpy.ops.object.shade_smooth()
        _set_auto_smooth_angle(o.data, angle_deg)
        processed.append(o.name)
    return {"success": True, "smoothed": processed, "auto_smooth_angle": angle_deg}


def shade_flat(params):
    """Restore faceted shading."""
    targets = params.get("targets")
    objs, err = resolve_targets(targets)
    if err:
        return {"error": err}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    processed = []
    for o in objs:
        if o.type != 'MESH':
            continue
        activate(o)
        bpy.ops.object.shade_flat()
        if hasattr(o.data, "use_auto_smooth"):
            o.data.use_auto_smooth = False
        processed.append(o.name)
    return {"success": True, "flattened": processed}


def _ensure_principled(mat):
    """Return the Principled BSDF node in mat's tree, creating one if missing."""
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if out is None:
            out = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return bsdf


def _set_input(node, key, value):
    """Set a node input by name if it exists. Blender renames inputs across
    versions (e.g. 'Emission' → 'Emission Color' in 4.x); silently skip misses."""
    if key in node.inputs:
        node.inputs[key].default_value = value
        return True
    return False


def _srgb_to_linear(c):
    """Standard sRGB transfer function, per channel (0..1 in, 0..1 out)."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_linear_rgba(hex_str):
    """Parse a "#RRGGBB" / "#RRGGBBAA" hex color (sRGB, as picked from any
    reference/screenshot) into scene-linear [r, g, b, a].

    Blender stores Base Color in scene-linear space, so a raw 8-bit hex value
    fed in as floats reads far too pale. Convert through the sRGB curve first.
    Raises ValueError on a malformed string."""
    s = hex_str.strip().lstrip("#")
    if len(s) not in (6, 8):
        raise ValueError(f"hex must be '#RRGGBB' or '#RRGGBBAA', got '{hex_str}'")
    try:
        ints = [int(s[i:i + 2], 16) for i in range(0, len(s), 2)]
    except ValueError:
        raise ValueError(f"hex contains non-hex digits: '{hex_str}'")
    r, g, b = (_srgb_to_linear(v / 255.0) for v in ints[:3])
    a = ints[3] / 255.0 if len(ints) == 4 else 1.0  # alpha is linear (no curve)
    return [round(r, 6), round(g, 6), round(b, 6), round(a, 6)]


def set_material(params):
    """Create or update a Principled BSDF material and assign it to an object.

    target:        object name (required). Material is assigned to slot 0.
    material_name: name for the material (created if missing, reused if present).
                   If omitted, defaults to "<target>_mat".
    base_color:    [r, g, b] or [r, g, b, a], floats 0..1.
    metallic:      0..1.
    roughness:     0..1.
    ior:           index of refraction (default 1.45 — glass ≈ 1.5, water ≈ 1.33).
    alpha:         0..1 (also enables BLEND transparency on the material).
    emission_color: [r, g, b] glow color.
    emission_strength: glow intensity (watts/m²-ish).
    """
    from .common import resolve_targets
    target = params.get("target")
    if not target:
        return {"error": "'target' (object or group name) is required"}
    objs, err = resolve_targets(target)
    if err:
        return {"error": err}
    meshes = [o for o in objs if o.type == 'MESH']
    if not meshes:
        return {"error": f"'{target}' contains no mesh objects"}

    mat_name = params.get("material_name") or f"{target}_mat"
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    bsdf = _ensure_principled(mat)

    applied = []

    # hex (sRGB) takes precedence over base_color floats and is converted to
    # scene-linear so the rendered color matches the reference it was picked from.
    hex_str = params.get("hex")
    bc = params.get("base_color")
    if hex_str:
        try:
            bc = hex_to_linear_rgba(hex_str)
        except ValueError as e:
            return {"error": str(e)}
    if bc is not None:
        if len(bc) == 3:
            bc = list(bc) + [1.0]
        if _set_input(bsdf, "Base Color", tuple(bc)):
            applied.append(f"hex={hex_str}→{bc}" if hex_str else f"base_color={bc}")

    for key, label in (("metallic", "Metallic"),
                       ("roughness", "Roughness"),
                       ("ior", "IOR")):
        v = params.get(key)
        if v is not None and _set_input(bsdf, label, float(v)):
            applied.append(f"{key}={v}")

    alpha = params.get("alpha")
    if alpha is not None:
        if _set_input(bsdf, "Alpha", float(alpha)):
            applied.append(f"alpha={alpha}")
        if alpha < 1.0:
            mat.blend_method = 'BLEND'

    ec = params.get("emission_color")
    if ec is not None:
        if len(ec) == 3:
            ec = list(ec) + [1.0]
        # Blender renamed "Emission" → "Emission Color" around 4.0
        if _set_input(bsdf, "Emission Color", tuple(ec)) or _set_input(bsdf, "Emission", tuple(ec)):
            applied.append(f"emission_color={ec}")

    es = params.get("emission_strength")
    if es is not None and _set_input(bsdf, "Emission Strength", float(es)):
        applied.append(f"emission_strength={es}")

    for obj in meshes:
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

    return {
        "success": True,
        "target": target,
        "assigned_to": [o.name for o in meshes],
        "material": mat.name,
        "applied": applied,
    }


TOOLS = {
    "shade_smooth": shade_smooth,
    "shade_flat":   shade_flat,
    "set_material": set_material,
}

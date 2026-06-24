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

    Addressing the material (gaps.md T1):
    target:        object/group name. Material is assigned to slot 0 by default.
    material:      address an EXISTING material datablock by name, with NO target —
                   restyle a shared material everywhere it's used in one call
                   (e.g. material="iron_mat" recolors every object using it).
    slot:          with a target, operate on this material SLOT index instead of 0.
                   Without material_name, edits the material already in that slot
                   in place (restyle a multi-slot mesh's secondary material);
                   with material_name, assigns the new material to that slot.
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
    from .common import resolve_targets, has_material_slots, linked_guard_any
    target = params.get("target")
    material = params.get("material")
    slot = params.get("slot")

    meshes = []
    if material and not target:
        # Address an existing material datablock directly — no object needed.
        mat = bpy.data.materials.get(material)
        if mat is None:
            return {"error": f"material '{material}' not found"}
    else:
        if not target:
            return {"error": "provide 'target' (object/group) or 'material' "
                             "(existing material name to edit in place)"}
        objs, err = resolve_targets(target)
        if err:
            return {"error": err}
        meshes = [o for o in objs if has_material_slots(o)]
        if not meshes:
            return {"error": f"'{target}' contains nothing that can hold a material"}
        blocked = linked_guard_any(meshes)
        if blocked:
            return {"error": blocked}
        if slot is not None and params.get("material_name") is None and not material:
            # Slot targeting with no new material → edit the material ALREADY in that
            # slot, in place (restyle the wheel's iron rim sitting in slot 1).
            slot_idx = int(slot)
            o0 = meshes[0]
            mats = o0.data.materials
            if slot_idx < 0 or slot_idx >= len(mats) or mats[slot_idx] is None:
                return {"error": f"'{o0.name}' has no material in slot {slot_idx}"}
            mat = mats[slot_idx]
            meshes = []  # editing the slot's material in place; no reassignment
        else:
            # target may be a list (G27 multi-object recolor); derive a string label
            # for the default material name rather than stringifying the list.
            tgt_label = target if isinstance(target, str) else (target[0] if target else "material")
            mat_name = params.get("material_name") or material or f"{tgt_label}_mat"
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

    # G84: transmission makes a refractive SOLID (glass, gem, lens, water) — light bends
    # through it and pairs with `ior` — rather than alpha's flat, non-refracting see-
    # through surface. Modern Principled folds transmission roughness into the main
    # Roughness input, so there's no separate transmission-roughness dial.
    transmission = params.get("transmission")
    if transmission is not None:
        # Blender renamed "Transmission" → "Transmission Weight" around 4.0
        if (_set_input(bsdf, "Transmission Weight", float(transmission))
                or _set_input(bsdf, "Transmission", float(transmission))):
            applied.append(f"transmission={transmission}")
        # Enable refraction on the material so it actually bends light in EEVEE — the
        # analog of alpha's blend_method='BLEND'. (Screen-space/raytraced refraction
        # still needs raytracing enabled on the engine to be visible in the render.)
        if transmission > 0.0:
            if hasattr(mat, "use_screen_refraction"):
                mat.use_screen_refraction = True
            if hasattr(mat, "use_raytrace_refraction"):
                mat.use_raytrace_refraction = True

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

    # G113: a scattered instance shares ONE mesh datablock, so writing a material slot on it
    # writes the SHARED mesh — and every other instance silently gets the same colour (last
    # colour wins). Make an object single-user FIRST when its mesh is shared with an object
    # OUTSIDE this assignment set, so a per-subset colour sticks (same principle as the G114
    # join fix). Assigning to ALL users (e.g. target=whole group) writes the shared mesh
    # once — no needless copies.
    mesh_set = set(meshes)
    made_single_user = []
    for obj in meshes:
        me = obj.data
        if me is not None and me.users > 1:
            shared_outside = any(u.data is me and u not in mesh_set
                                 for u in bpy.data.objects)
            if shared_outside:
                obj.data = me.copy()
                made_single_user.append(obj.name)

    slot_idx = int(slot) if slot is not None else 0
    for obj in meshes:
        mats = obj.data.materials
        if slot_idx < len(mats):
            mats[slot_idx] = mat
        elif slot_idx == len(mats):
            mats.append(mat)
        else:
            return {"error": f"'{obj.name}' has {len(mats)} slot(s); slot {slot_idx} is "
                             f"out of range (can only append at index {len(mats)})"}

    # G126: reusing an existing (e.g. PBR-textured) material by name only patches the
    # Principled SCALAR inputs — but a TEXTURE NODE wired into Alpha/Metallic/Roughness/Base
    # Color OVERRIDES the scalar (default_value is ignored when the input is linked). So the
    # 'fix' (alpha=1 to un-hide an invisibly-transparent material) silently does nothing.
    # Detect the inputs the agent set that are still node-driven and say so.
    _attempted = []
    if bc is not None:
        _attempted.append("Base Color")
    for key, label in (("metallic", "Metallic"), ("roughness", "Roughness"),
                       ("ior", "IOR"), ("alpha", "Alpha")):
        if params.get(key) is not None:
            _attempted.append(label)
    shadowed = [lab for lab in _attempted
                if bsdf.inputs.get(lab) is not None and bsdf.inputs[lab].is_linked]

    out = {
        "success": True,
        "target": target,
        "assigned_to": [o.name for o in meshes],
        "material": mat.name,
        "slot": slot_idx if slot is not None else None,
        "edited_in_place": not meshes,
        "applied": applied,
    }
    if shadowed:
        out["shadowed_inputs"] = shadowed
        out.setdefault("notes", []).append(
            f"the value(s) you set for {', '.join(shadowed)} are OVERRIDDEN by a texture node "
            f"still wired into '{mat.name}' — the scalar is ignored while the node is "
            f"connected. To actually replace them, pass a NEW material_name (mints a fresh "
            f"Principled with no texture graph).")
    if made_single_user:
        out["made_single_user"] = made_single_user
        out.setdefault("notes", []).append(
            f"{len(made_single_user)} instance(s) made single-user so this material sticks "
            f"per-object (their mesh was shared with objects outside the target) — they no "
            f"longer share geometry with the rest of the scatter.")
    return out


TOOLS = {
    "shade_smooth": shade_smooth,
    "shade_flat":   shade_flat,
    "set_material": set_material,
}

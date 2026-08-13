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

    # G113: a scattered instance shares ONE mesh datablock, so writing the mesh's material
    # slot recolors EVERY instance (last colour wins). When an object's mesh is shared with
    # objects OUTSIDE this assignment set, override the material on a per-object OBJECT-LINKED
    # slot — the colour sticks to THIS instance with NO geometry duplication (the mesh stays
    # shared, which is the whole point of a 100-instance scatter). When every user of the
    # mesh is already in the target set (recolouring the whole group), write the shared data
    # slot once instead — no needless per-object overrides.
    mesh_set = set(meshes)
    slot_idx = int(slot) if slot is not None else 0
    object_linked = []
    for obj in meshes:
        me = obj.data
        shared_outside = me is not None and me.users > 1 and any(
            u.data is me and u not in mesh_set for u in bpy.data.objects)
        if shared_outside:
            # Grow the (shared) data slot list so slot_idx exists for every instance, then
            # override the material for THIS object via the OBJECT link — the shared data
            # slot itself is left untouched, so the other instances keep their colour.
            while len(me.materials) <= slot_idx:
                me.materials.append(None)
            obj.material_slots[slot_idx].link = 'OBJECT'
            obj.material_slots[slot_idx].material = mat
            object_linked.append(obj.name)
        else:
            mats = me.materials
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
    if object_linked:
        out["object_linked"] = object_linked
        out.setdefault("notes", []).append(
            f"{len(object_linked)} instance(s) share a mesh with objects outside the target, "
            f"so this material was assigned via an OBJECT-linked slot — it's per-instance (the "
            f"others keep theirs) with the mesh still shared, so a scatter gets colour variety "
            f"without un-sharing geometry.")
    return out


def assign_material(params):
    """Assign a material to the LIVE edit-mode FACE SELECTION — the per-region paint
    primitive (G146). `set_material` colours a whole object/slot; this writes
    face.material_index on JUST the selected faces, so a plate gets a brown rim band,
    a bottle a label patch, a wall a wainscot — without separating geometry.

    Run a `select` op to choose the faces first; this reads that live selection (the
    dispatch re-enters edit mode and restores the selection from the mesh, exactly
    like `select op=by_material`).

    material:   assign an EXISTING material datablock by name.
    OR a colour: base_color / hex (+ optional metallic, roughness, material_name) mints
                 a fresh material and assigns that. material_name defaults to
                 '<obj>_face_mat'. A slot for the material is reused if present, else
                 appended — existing slots and their faces are untouched.
    """
    import bmesh
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "active object is not a mesh"}
    if obj.mode != 'EDIT':
        return {"error": "Must be in edit mode — run a `select` op first to choose the faces"}

    material = params.get("material")
    if material:
        mat = bpy.data.materials.get(material)
        if mat is None:
            return {"error": f"material '{material}' not found"}
    elif (params.get("material_name") or params.get("hex")
          or any(params.get(k) is not None for k in ("base_color", "metallic", "roughness"))):
        mat_name = params.get("material_name") or f"{obj.name}_face_mat"
        mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
        bsdf = _ensure_principled(mat)
        bc = params.get("base_color")
        hex_str = params.get("hex")
        if hex_str:
            try:
                bc = hex_to_linear_rgba(hex_str)
            except ValueError as e:
                return {"error": str(e)}
        if bc is not None:
            if len(bc) == 3:
                bc = list(bc) + [1.0]
            _set_input(bsdf, "Base Color", tuple(bc))
        for key, lab in (("metallic", "Metallic"), ("roughness", "Roughness")):
            v = params.get(key)
            if v is not None:
                _set_input(bsdf, lab, float(v))
    else:
        return {"error": "give material=<existing name>, or a colour "
                         "(base_color / hex [+ metallic/roughness/material_name]) to "
                         "paint the selected faces"}

    bm = bmesh.from_edit_mesh(obj.data)
    sel = [f for f in bm.faces if f.select]
    if not sel:
        return {"error": "no faces selected — choose the region with a `select` op first "
                         "(a vertex/edge-only selection assigns nothing)"}

    me = obj.data
    slot_idx = next((i for i, m in enumerate(me.materials) if m is mat), None)
    minted_slot = slot_idx is None
    if minted_slot:
        me.materials.append(mat)
        slot_idx = len(me.materials) - 1

    for f in sel:
        f.material_index = slot_idx
    bmesh.update_edit_mesh(me)

    return {"success": True, "target": obj.name, "material": mat.name,
            "slot": slot_idx, "slot_minted": minted_slot,
            "faces_assigned": len(sel), "slot_count": len(me.materials)}


def _resolve_slot_object(params):
    """Resolve the single object to operate on for slot ops — `target` if given,
    else the active object. Returns (obj, error_string). Guards linked data and
    requires the object to actually hold material slots."""
    from .common import has_material_slots, linked_guard
    target = params.get("target")
    if target:
        objs, err = resolve_targets(target)
        if err:
            return None, err
        meshes = [o for o in objs if has_material_slots(o)]
        if not meshes:
            return None, f"'{target}' contains nothing that can hold a material"
        obj = meshes[0]
    else:
        obj = bpy.context.active_object
        if obj is None:
            return None, "no active object — pass target=<object>"
        if not has_material_slots(obj):
            return None, f"'{obj.name}' can't hold materials"
    blocked = linked_guard(obj)
    if blocked:
        return None, blocked
    return obj, None


def remove_material_slot(params):
    """Remove a single material slot from an object (Material Properties ▸ −).

    Reassign faces off the slot FIRST (`material op=assign`) — Blender re-homes any
    faces still on a removed slot to slot 0 and shifts every higher index down by one.

    target: object name (default: active object).
    slot:   slot index to remove (required).
    """
    obj, err = _resolve_slot_object(params)
    if err:
        return {"error": err}
    slot = params.get("slot")
    if slot is None:
        return {"error": "slot is required (the slot index to remove)"}
    slot_idx = int(slot)
    mats = obj.data.materials
    n = len(mats)
    if slot_idx < 0 or slot_idx >= n:
        return {"error": f"'{obj.name}' has {n} slot(s); slot {slot_idx} is out of range"}
    removed_name = mats[slot_idx].name if mats[slot_idx] is not None else None
    activate(obj)
    obj.active_material_index = slot_idx
    bpy.ops.object.material_slot_remove()
    return {"success": True, "target": obj.name, "removed_slot": slot_idx,
            "removed_material": removed_name,
            "slot_count": len(obj.data.materials),
            "slots": [m.name if m else None for m in obj.data.materials]}


def remove_unused_material_slots(params):
    """Remove every material slot with NO faces assigned to it (Material Properties
    ▸ ⌄ ▸ 'Remove Unused Slots') — trim a consolidated mesh to its real slot count.

    target: object name (default: active object).
    """
    obj, err = _resolve_slot_object(params)
    if err:
        return {"error": err}
    before = [m.name if m else None for m in obj.data.materials]
    activate(obj)
    try:
        bpy.ops.object.material_slot_remove_unused()
    except (AttributeError, RuntimeError):
        # Fallback for Blender builds without the operator: drop slots that no
        # face references, removing from the highest index down so the active-
        # index removal doesn't shift slots we still need to visit.
        me = obj.data
        used = {p.material_index for p in me.polygons}
        for idx in range(len(me.materials) - 1, -1, -1):
            if idx not in used:
                obj.active_material_index = idx
                bpy.ops.object.material_slot_remove()
    after = [m.name if m else None for m in obj.data.materials]
    removed = [n for n in before if n not in after]
    return {"success": True, "target": obj.name,
            "removed_count": len(before) - len(after),
            "removed_materials": removed,
            "slot_count": len(after), "slots": after}


def _resolve_image(spec):
    """A packed image name or a filesystem path. Packs on load so the bind
    survives .blend save (G230)."""
    import os
    spec = (spec or "").strip()
    if not spec:
        return None, "image= is required — a filesystem path or a packed image name"
    img = bpy.data.images.get(spec)
    if img is not None:
        _try_pack(img)
        return img, None
    path = os.path.abspath(os.path.expanduser(spec))
    if not os.path.isfile(path):
        packed = [i.name for i in bpy.data.images]
        hint = f" Packed images: {packed}." if packed else ""
        return None, (f"image '{spec}' not found as a packed image or file.{hint}")
    img = bpy.data.images.load(path, check_existing=True)
    if not _try_pack(img):
        return None, f"loaded '{path}' but pack failed — the image is not in the .blend"
    return img, None


def _try_pack(img):
    """Embed file-backed images. Generated images already live in the .blend."""
    if img.packed_file or getattr(img, "source", None) == 'GENERATED':
        return True
    try:
        img.pack()
    except Exception:
        return bool(img.packed_file)
    return bool(img.packed_file) or getattr(img, "source", None) == 'GENERATED'


def _image_in_blend(img):
    return bool(img.packed_file) or getattr(img, "source", None) == 'GENERATED'


def _wire_image(nt, bsdf, img, space, bind):
    """One Image Texture → Principled Base Color and/or Emission Color.
    Thin bind, not the retired PBR graph."""
    tex = None
    for n in nt.nodes:
        if n.type == 'TEX_IMAGE' and n.image == img:
            tex = n
            break
    if tex is None:
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = img
        tex.label = "bb_image"
        tex.location = (bsdf.location.x - 360, bsdf.location.y)
    else:
        tex.image = img
    tex.projection = 'BOX' if space == 'box' else 'FLAT'
    for link in list(tex.inputs['Vector'].links):
        nt.links.remove(link)
    coord = next((n for n in nt.nodes if n.type == 'TEX_COORD'), None)
    if coord is None:
        coord = nt.nodes.new('ShaderNodeTexCoord')
        coord.location = (tex.location.x - 280, tex.location.y)
    if space == 'box':
        mapping = next((n for n in nt.nodes
                        if n.type == 'MAPPING' and n.label == 'bb_box'), None)
        if mapping is None:
            mapping = nt.nodes.new('ShaderNodeMapping')
            mapping.label = 'bb_box'
            mapping.location = (tex.location.x - 160, tex.location.y)
        for link in list(mapping.inputs['Vector'].links):
            nt.links.remove(link)
        nt.links.new(coord.outputs['Object'], mapping.inputs['Vector'])
        nt.links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
    else:
        nt.links.new(coord.outputs['UV'], tex.inputs['Vector'])

    color_out = tex.outputs['Color']
    if bind in ('base', 'both') and 'Base Color' in bsdf.inputs:
        for link in list(bsdf.inputs['Base Color'].links):
            nt.links.remove(link)
        nt.links.new(color_out, bsdf.inputs['Base Color'])
    for em_name in ('Emission Color', 'Emission'):
        if bind in ('emission', 'both') and em_name in bsdf.inputs:
            for link in list(bsdf.inputs[em_name].links):
                nt.links.remove(link)
            nt.links.new(color_out, bsdf.inputs[em_name])
            break
    return tex


def bind_image(params):
    """G230 — bind a packed image to a mesh's Principled (base and/or emission).
    space=uv needs an existing UV layer (pair with `uv op=unwrap`); space=box
    uses object projection. Not the retired textured/pbr node-graph sugar."""
    from .common import resolve_targets, has_material_slots, linked_guard_any
    target = params.get("target")
    if not target:
        return {"error": "bind_image needs target=<mesh>"}
    img, err = _resolve_image(params.get("image"))
    if err:
        return {"error": err}
    bind = (params.get("bind") or "base").strip().lower()
    if bind not in ("base", "emission", "both"):
        return {"error": f"bind={bind!r} unknown — use base | emission | both"}
    space = (params.get("space") or "box").strip().lower()
    if space not in ("uv", "box"):
        return {"error": f"space={space!r} unknown — use uv | box"}

    objs, err = resolve_targets(target)
    if err:
        return {"error": err}
    meshes = [o for o in objs if has_material_slots(o)]
    if not meshes:
        return {"error": f"'{target}' contains nothing that can hold a material"}
    blocked = linked_guard_any(meshes)
    if blocked:
        return {"error": blocked}

    if space == 'uv':
        missing = [o.name for o in meshes
                   if o.type == 'MESH' and o.data and not o.data.uv_layers]
        if missing:
            return {"error": (
                f"{', '.join(missing)} ha{'s' if len(missing) == 1 else 've'} no UV "
                f"map — `uv op=unwrap` first, or pass space=box")}

    tgt_label = target if isinstance(target, str) else (target[0] if target else "material")
    mat_name = params.get("material_name") or params.get("material") or f"{tgt_label}_mat"
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    bsdf = _ensure_principled(mat)
    _wire_image(mat.node_tree, bsdf, img, space, bind)

    es = params.get("emission_strength")
    applied = [f"image={img.name}", f"bind={bind}", f"space={space}"]
    if bind in ('emission', 'both'):
        if es is None:
            es = 1.0
        if _set_input(bsdf, "Emission Strength", float(es)):
            applied.append(f"emission_strength={es}")
    elif es is not None and _set_input(bsdf, "Emission Strength", float(es)):
        applied.append(f"emission_strength={es}")

    slot_idx = int(params["slot"]) if params.get("slot") is not None else 0
    assigned = []
    for obj in meshes:
        me = obj.data
        if me is None:
            continue
        while len(me.materials) <= slot_idx:
            me.materials.append(None)
        me.materials[slot_idx] = mat
        assigned.append(obj.name)

    return {
        "success": True,
        "target": target,
        "assigned_to": assigned,
        "material": mat.name,
        "image": img.name,
        "packed": _image_in_blend(img),
        "bind": bind,
        "space": space,
        "applied": applied,
        "status_focus": assigned[0] if assigned else None,
    }


TOOLS = {
    "shade_smooth":    shade_smooth,
    "shade_flat":      shade_flat,
    "set_material":    set_material,
    "assign_material": assign_material,
    "bind_image":      bind_image,
    "remove_material_slot":         remove_material_slot,
    "remove_unused_material_slots": remove_unused_material_slots,
}

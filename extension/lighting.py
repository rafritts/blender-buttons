"""Lighting + world + camera DoF.

add_light:           drop a POINT/SUN/SPOT/AREA light at world coordinates,
                     optionally aimed at a target object.
set_world_background: solid color + strength, OR an HDRI image file.
set_camera_dof:      enable depth of field on the scene camera (focus + aperture).
"""

import os

import bpy
import mathutils


_LIGHT_TYPES = {"POINT", "SUN", "SPOT", "AREA"}


def add_light(params):
    """Create a new light object.

    name:     required, unique.
    type:     POINT | SUN | SPOT | AREA (default POINT). DIRECTIONAL is accepted
              as an alias for SUN.
    x, y, z:  world position (default 0,0,5).
    energy:   light strength. Default 1000 for POINT/SPOT/AREA, 5 for SUN.
              POINT/SPOT/AREA energy is in watts; SUN is irradiance-like.
    color:    [r, g, b] floats 0..1 (scene-linear). Default warm white [1, 0.95, 0.9].
    hex:      "#RRGGBB" sRGB color, converted to scene-linear. Overrides color.
    size:     soft-shadow radius (POINT), or AREA quad side, or SPOT radius. Default 0.25.
    target:   optional object name. If given, the light is aimed at that object's center.
    spot_angle: FULL cone (apex) angle in degrees for SPOT lights. Default 45.
    """
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    if bpy.data.objects.get(name) is not None:
        return {"error": f"Object '{name}' already exists"}

    light_type = (params.get("type") or "POINT").upper()
    if light_type == "DIRECTIONAL":
        light_type = "SUN"
    if light_type not in _LIGHT_TYPES:
        return {"error": f"Invalid light type '{light_type}'. Use one of {sorted(_LIGHT_TYPES)}"}

    x = params.get("x", 0.0)
    y = params.get("y", 0.0)
    z = params.get("z", 5.0)
    color = params.get("color") or [1.0, 0.95, 0.9]
    hex_str = params.get("hex")
    if hex_str:
        from .shading import hex_to_linear_rgba
        try:
            color = hex_to_linear_rgba(hex_str)[:3]
        except ValueError as e:
            return {"error": str(e)}
    if len(color) != 3:
        return {"error": "'color' must be a 3-element RGB list"}
    size = params.get("size", 0.25)
    default_energy = 5.0 if light_type == "SUN" else 1000.0
    energy = params.get("energy", default_energy)

    light_data = bpy.data.lights.new(name=name, type=light_type)
    light_data.energy = float(energy)
    light_data.color = tuple(color)
    if hasattr(light_data, "shadow_soft_size"):
        light_data.shadow_soft_size = float(size)
    if light_type == "AREA":
        light_data.size = float(size)
    if light_type == "SPOT" and hasattr(light_data, "spot_size"):
        spot_deg = params.get("spot_angle", 45.0)
        import math
        light_data.spot_size = math.radians(spot_deg)

    obj = bpy.data.objects.new(name=name, object_data=light_data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (x, y, z)

    target = params.get("target")
    if target:
        tgt = bpy.data.objects.get(target)
        if tgt is None:
            bpy.data.objects.remove(obj, do_unlink=True)
            return {"error": f"target '{target}' not found"}
        # Aim the light's -Z axis at the target center.
        from .common import world_center
        tx, ty, tz = world_center(tgt)
        direction = mathutils.Vector((tx, ty, tz)) - mathutils.Vector((x, y, z))
        obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    bpy.context.view_layer.update()
    return {
        "success": True,
        "object_name": obj.name,
        "type": light_type,
        "energy": light_data.energy,
        "color": list(color),
        "location": [round(x, 4), round(y, 4), round(z, 4)],
    }


def aim_at(params):
    """G79 — re-aim an existing object's -Z axis at a named subject's centre. General:
    cameras (no aim path before), spotlights, area lights, or any object you want to
    'look at' something — by name, never a typed point."""
    name = params.get("name")
    obj = bpy.data.objects.get(name) if name else bpy.context.active_object
    if obj is None:
        return {"error": f"object '{name or '(active)'}' not found"}
    subject = params.get("subject") or params.get("target")
    tgt = bpy.data.objects.get(subject) if subject else None
    if tgt is None:
        return {"error": f"subject '{subject}' not found — aim needs a named object to look at"}
    from .common import world_center
    c = mathutils.Vector(world_center(tgt))
    direction = c - obj.matrix_world.translation
    if direction.length < 1e-9:
        return {"error": f"'{obj.name}' sits at the subject's centre — move it out first"}
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.view_layer.update()
    return {"success": True, "aimed": [obj.name], "subject": tgt.name}


def rig_around(params):
    """G79 — position an object on a sphere around a subject (azimuth / elevation /
    distance) and aim it inward. The relational light/camera rig: a key/fill/rim light or
    a hero camera at an angle + radius around the subject, no typed coordinates — the
    spherical analogue of array_radial. azimuth 0 = front (−Y), 90 = +X (right side);
    elevation = degrees above the horizon; distance = subject-centre → object.

    G149 — subject may be SEVERAL objects (comma list or group name): the rig orbits and
    aims at their UNION bbox centre. fit=True then auto-derives the distance so the whole
    group fills the frame — for a camera, from its real field of view; for a light, from
    the subject's extent. So a multi-part vignette (donut + plate + mug) frames in one
    call instead of hand-tuning distance until check_framing stops clipping."""
    import math
    name = params.get("name")
    obj = bpy.data.objects.get(name) if name else bpy.context.active_object
    if obj is None:
        return {"error": f"object '{name or '(active)'}' not found"}
    subject = params.get("subject") or params.get("target")
    if not subject:
        return {"error": "rig needs a named subject to orbit"}

    from .common import resolve_targets, world_bbox
    # Expand a comma list / group name into the set of subject objects to frame.
    tokens = subject.split(",") if isinstance(subject, str) else subject
    subj_objs, seen = [], set()
    for tok in tokens:
        objs, _ = resolve_targets(tok.strip() if isinstance(tok, str) else tok,
                                  include_non_mesh=True)
        for s in (objs or []):
            if s is not obj and s.name not in seen:   # never orbit the rig around itself
                seen.add(s.name)
                subj_objs.append(s)
    if not subj_objs:
        return {"error": f"subject '{subject}' not found — rig needs a named subject "
                         "(or group/comma-list) to orbit"}

    # Union world bbox of every subject → aim centre + extent.
    mins = [float("inf")] * 3
    maxs = [float("-inf")] * 3
    for s in subj_objs:
        b = world_bbox(s)
        for i in range(3):
            mins[i] = min(mins[i], b[i])
            maxs[i] = max(maxs[i], b[i + 3])
    c = mathutils.Vector(((mins[0] + maxs[0]) * 0.5,
                          (mins[1] + maxs[1]) * 0.5,
                          (mins[2] + maxs[2]) * 0.5))
    diag = math.sqrt(sum((maxs[i] - mins[i]) ** 2 for i in range(3)))
    radius = max(diag * 0.5, 1e-4)

    az = math.radians(float(params.get("azimuth", 45.0)))
    el = math.radians(float(params.get("elevation", 25.0)))
    dist = float(params.get("distance", 8.0))
    fit = bool(params.get("fit", False))
    fit_note = None
    if fit:
        if obj.type == 'CAMERA':
            # Distance that fits a sphere of `radius` inside BOTH frame dimensions, given
            # the camera's true horizontal/vertical FOV, plus a margin off the edges.
            ax = getattr(obj.data, "angle_x", None) or obj.data.angle
            ay = getattr(obj.data, "angle_y", None) or obj.data.angle
            dist = max(radius / math.tan(ax / 2.0), radius / math.tan(ay / 2.0)) * 1.15
            fit_note = (f"distance {round(dist, 3)}m auto-fit to frame {len(subj_objs)} "
                        f"subject(s) (bbox diag {round(diag, 3)}m)")
        else:
            dist = max(dist, radius * 3.0)
            fit_note = f"distance {round(dist, 3)}m from subject extent"

    dir_to_obj = mathutils.Vector((math.cos(el) * math.sin(az),
                                   -math.cos(el) * math.cos(az),
                                   math.sin(el)))
    pos = c + dist * dir_to_obj
    obj.location = pos
    direction = c - pos
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.view_layer.update()
    subj_label = subj_objs[0].name if len(subj_objs) == 1 else \
        f"{len(subj_objs)} subjects ({', '.join(s.name for s in subj_objs)})"
    out = {"success": True, "rigged": [obj.name], "subject": subj_label,
           "azimuth": round(math.degrees(az), 1), "elevation": round(math.degrees(el), 1),
           "distance": round(dist, 4), "location": [round(v, 4) for v in pos]}
    if fit_note:
        out["fit"] = fit_note
    return out


def set_world_background(params):
    """Set the scene's world environment.

    color:    [r, g, b] solid background color (0..1 scene-linear floats). Optional.
    hex:      "#RRGGBB" sRGB solid color, converted to scene-linear (overrides color).
    strength: background light intensity. Default 1.0.
    hdri:     path to an HDRI/EXR image. If provided, overrides `color`.
              The image is loaded as an Environment Texture and connected
              to the World Background.
    """
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree

    bg = next((n for n in nt.nodes if n.type == 'BACKGROUND'), None)
    if bg is None:
        bg = nt.nodes.new('ShaderNodeBackground')
    out = next((n for n in nt.nodes if n.type == 'OUTPUT_WORLD'), None)
    if out is None:
        out = nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])

    strength = params.get("strength")
    if strength is not None:
        bg.inputs['Strength'].default_value = float(strength)

    # Clear any existing environment texture link first.
    for link in list(nt.links):
        if link.to_node is bg and link.to_socket.name == 'Color':
            nt.links.remove(link)

    hdri = params.get("hdri")
    color = params.get("color")
    hex_str = params.get("hex")
    if hex_str:
        from .shading import hex_to_linear_rgba
        try:
            color = hex_to_linear_rgba(hex_str)
        except ValueError as e:
            return {"error": str(e)}
    if hdri:
        path = os.path.expanduser(hdri)
        if not os.path.isfile(path):
            return {"error": f"HDRI file not found: {path}"}
        env = next((n for n in nt.nodes if n.type == 'TEX_ENVIRONMENT'), None)
        if env is None:
            env = nt.nodes.new('ShaderNodeTexEnvironment')
        env.image = bpy.data.images.load(path, check_existing=True)
        nt.links.new(env.outputs['Color'], bg.inputs['Color'])
        return {
            "success": True,
            "mode": "hdri",
            "hdri": path,
            "strength": bg.inputs['Strength'].default_value,
        }

    if color is not None:
        if len(color) == 3:
            color = list(color) + [1.0]
        bg.inputs['Color'].default_value = tuple(color)
        return {
            "success": True,
            "mode": "color",
            "color": list(color),
            "strength": bg.inputs['Strength'].default_value,
        }

    return {
        "success": True,
        "mode": "unchanged",
        "strength": bg.inputs['Strength'].default_value,
    }


def set_camera_dof(params):
    """Enable depth of field on the scene camera.

    camera:         camera object name. If omitted, uses the scene camera.
    focus_distance: meters from camera to focal plane. Ignored if focus_object is set.
    focus_object:   object name to focus on. Focuses on the object's EVALUATED
                    (posed/deformed) geometry center at call time — not Blender's
                    focus-object tracking, which follows the rest origin and so
                    misses a boulder riding a cocked arm by ~1m (gaps.md T2).
    aperture:       f-stop value. Lower = shallower DoF (more blur).
                    Typical: 1.4 (very shallow), 2.8 (portrait), 8 (everything in focus).
    """
    name = params.get("camera")
    if name:
        cam = bpy.data.objects.get(name)
        if cam is None or cam.type != 'CAMERA':
            return {"error": f"Camera '{name}' not found"}
    else:
        cam = bpy.context.scene.camera or next(
            (o for o in bpy.data.objects if o.type == 'CAMERA'), None)
        if cam is None:
            return {"error": "No camera in scene"}

    dof = cam.data.dof
    dof.use_dof = True

    focus_object_name = params.get("focus_object")
    focus_target = None
    if focus_object_name:
        import mathutils
        from .common import eval_world_center
        tgt = bpy.data.objects.get(focus_object_name)
        if tgt is None:
            return {"error": f"focus_object '{focus_object_name}' not found"}
        # Project the evaluated-geometry center onto the camera's view axis to get
        # the focal-plane distance (focus_distance is measured along the lens axis,
        # not euclidean to the point). Setting a computed distance — not
        # dof.focus_object — focuses on the POSED geometry, not the rest origin.
        center = mathutils.Vector(eval_world_center(tgt))
        cam_mat = cam.matrix_world
        forward = (cam_mat.to_3x3() @ mathutils.Vector((0.0, 0.0, -1.0))).normalized()
        dof.focus_object = None
        dof.focus_distance = float((center - cam_mat.translation).dot(forward))
        focus_target = tgt.name
    else:
        dof.focus_object = None
        fd = params.get("focus_distance")
        if fd is not None:
            dof.focus_distance = float(fd)

    aperture = params.get("aperture")
    if aperture is not None:
        # aperture_fstop is the Cycles/Eevee shared property.
        dof.aperture_fstop = float(aperture)

    return {
        "success": True,
        "camera": cam.name,
        "use_dof": True,
        "focus_object": focus_target,
        "focus_distance": round(dof.focus_distance, 4),
        "aperture_fstop": round(dof.aperture_fstop, 4),
    }


def modify_light(params):
    """Tweak an existing light's energy/color/size/position without rebuilding it.

    name:     required — light object name.
    energy:   optional new energy (watts for POINT/SPOT/AREA, irradiance for SUN).
    color:    optional [r, g, b] (scene-linear).
    hex:      optional "#RRGGBB" sRGB color, converted to scene-linear (overrides color).
    size:     optional soft-shadow radius / AREA quad side / SPOT radius.
    spot_angle: SPOT only — FULL cone (apex) angle in degrees.
    x, y, z:  optional new world position. Each axis independent — omitted axes stay.
    target:   optional object name to aim at (re-aims the light's -Z axis at target center).
    """
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != 'LIGHT':
        return {"error": f"Light '{name}' not found"}
    light_data = obj.data

    applied = []

    energy = params.get("energy")
    if energy is not None:
        light_data.energy = float(energy)
        applied.append(f"energy={energy}")

    color = params.get("color")
    hex_str = params.get("hex")
    if hex_str:
        from .shading import hex_to_linear_rgba
        try:
            color = hex_to_linear_rgba(hex_str)[:3]
        except ValueError as e:
            return {"error": str(e)}
    if color is not None:
        if len(color) != 3:
            return {"error": "'color' must be a 3-element RGB list"}
        light_data.color = tuple(color)
        applied.append(f"hex={hex_str}→{list(color)}" if hex_str else f"color={list(color)}")

    size = params.get("size")
    if size is not None:
        if hasattr(light_data, "shadow_soft_size"):
            light_data.shadow_soft_size = float(size)
        if light_data.type == 'AREA':
            light_data.size = float(size)
        applied.append(f"size={size}")

    spot_angle = params.get("spot_angle")
    if spot_angle is not None and light_data.type == 'SPOT' and hasattr(light_data, "spot_size"):
        import math as _math
        light_data.spot_size = _math.radians(float(spot_angle))
        applied.append(f"spot_angle={spot_angle}")

    moved = False
    cur = list(obj.location)
    for i, key in enumerate(("x", "y", "z")):
        if key in params:
            cur[i] = float(params[key])
            moved = True
    if moved:
        obj.location = tuple(cur)
        applied.append(f"location={cur}")

    target = params.get("target")
    if target:
        tgt = bpy.data.objects.get(target)
        if tgt is None:
            return {"error": f"target '{target}' not found"}
        from .common import world_center
        tx, ty, tz = world_center(tgt)
        direction = mathutils.Vector((tx, ty, tz)) - mathutils.Vector(obj.location)
        obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        applied.append(f"aimed→{target}")

    bpy.context.view_layer.update()
    return {
        "success": True,
        "light": obj.name,
        "type": light_data.type,
        "energy": light_data.energy,
        "color": list(light_data.color),
        "applied": applied,
    }


def set_color_management(params):
    """Set the scene's view transform / look / exposure / gamma.

    Blender 4.x defaults to the AgX view transform, which lifts and desaturates
    midtones — great for filmic PBR, but it mutes flat toon/NPR colors and any
    emission-driven glow. Switch to 'Standard' for cel-shaded work.

    view_transform: 'Standard' | 'AgX' | 'Filmic' | 'Raw' | ... (any installed).
    look:           contrast look, e.g. 'None', 'AgX - Punchy', 'Medium Contrast'.
    exposure:       stops of exposure (float, default 0).
    gamma:          display gamma (float, default 1.0).
    """
    scene = bpy.context.scene
    vs = scene.view_settings
    applied = []

    vt = params.get("view_transform")
    if vt is not None:
        try:
            vs.view_transform = vt
        except TypeError:
            return {"error": f"view_transform '{vt}' not available. "
                             "Common: Standard, AgX, Filmic, Raw."}
        applied.append(f"view_transform={vt}")

    look = params.get("look")
    if look is not None:
        try:
            vs.look = look
        except TypeError:
            return {"error": f"look '{look}' not available for the current view transform."}
        applied.append(f"look={look}")

    exposure = params.get("exposure")
    if exposure is not None:
        vs.exposure = float(exposure)
        applied.append(f"exposure={exposure}")

    gamma = params.get("gamma")
    if gamma is not None:
        vs.gamma = float(gamma)
        applied.append(f"gamma={gamma}")

    return {
        "success": True,
        "applied": applied,
        "view_transform": vs.view_transform,
        "look": vs.look,
        "exposure": round(vs.exposure, 4),
        "gamma": round(vs.gamma, 4),
    }


def set_render_quality(params):
    """Toggle Eevee render-quality features that are off by default in Blender 4.x.

    raytracing: enable screen-space ray tracing — required for crisp metal
                reflections and sharp specular highlights. Without it metallic=1
                only reflects the low-res world probe and reads as plastic.
    ao:         ambient occlusion (contact shadows in crevices).
    shadows:    soft/jittered shadows.
    samples:    viewport+render sample count (higher = less noise, slower).

    Only the Eevee properties that exist in this Blender build are touched;
    others are reported as skipped. (Cycles ignores these — it ray-traces always.)
    """
    scene = bpy.context.scene
    eevee = getattr(scene, "eevee", None)
    if eevee is None:
        return {"error": "scene.eevee not available (is the render engine Eevee?)"}
    applied = []
    skipped = []

    def _toggle(attr, val, label):
        if hasattr(eevee, attr):
            setattr(eevee, attr, bool(val))
            applied.append(f"{label}={bool(val)}")
        else:
            skipped.append(label)

    rt = params.get("raytracing")
    if rt is not None:
        _toggle("use_raytracing", rt, "raytracing")
    ao = params.get("ao")
    if ao is not None:
        # Eevee Next dropped use_gtao for use_ambient_occlusion-less raytraced AO;
        # set whichever exists.
        if hasattr(eevee, "use_gtao"):
            eevee.use_gtao = bool(ao)
            applied.append(f"ao={bool(ao)}")
        else:
            skipped.append("ao")
    shadows = params.get("shadows")
    if shadows is not None:
        _toggle("use_shadows", shadows, "shadows")
    samples = params.get("samples")
    if samples is not None:
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = int(samples)
        if hasattr(eevee, "taa_samples"):
            eevee.taa_samples = int(samples)
        applied.append(f"samples={int(samples)}")

    return {
        "success": True,
        "engine": scene.render.engine,
        "applied": applied,
        "skipped": skipped,
    }


def _enable_cycles_gpu(backend):
    """Enable a Cycles GPU backend in the addon preferences and tick its devices.

    Returns (ok, chosen_backend, enabled_device_names, error). Mirrors what the
    Preferences > System > Cycles Render Devices panel does: pick a compute backend,
    then enable the GPU device(s) of that type (and untick the CPU, for pure-GPU).
    """
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        return False, "", [], "Cycles addon not enabled in this Blender build."
    prefs = addon.preferences

    # compute_device_type is a DYNAMIC enum (items come from a runtime hardware
    # callback), so its members can't be read reliably via bl_rna.enum_items —
    # that comes back empty. Instead, try to SELECT each candidate backend and
    # catch the TypeError an unsupported value raises, then confirm it has a device.
    candidates = [backend.upper()] if backend else ["OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"]
    tried = []
    for bk in candidates:
        try:
            prefs.compute_device_type = bk
        except TypeError:
            tried.append(f"{bk}:unsupported")
            continue
        # Populate prefs.devices for the selected backend (API name varies by version).
        for refresh in ("refresh_devices", "get_devices"):
            fn = getattr(prefs, refresh, None)
            if fn is not None:
                try:
                    fn()
                    break
                except Exception:
                    pass
        gpu = [d for d in prefs.devices if d.type == bk]
        if gpu:
            enabled = []
            for d in prefs.devices:
                if d.type == bk:
                    d.use = True
                    enabled.append(d.name)
                elif d.type == 'CPU':
                    d.use = False  # pure-GPU; the user can re-tick CPU for hybrid
            return True, bk, enabled, ""
        tried.append(f"{bk}:no-device")

    label = f"backend '{backend}'" if backend else "any GPU backend"
    return False, "", [], (f"could not enable {label} (tried: {', '.join(tried)}) — "
                          "check GPU drivers / Preferences > System > Cycles Render Devices.")


def set_cycles_quality(params):
    """Cycles-specific render controls — the Cycles counterpart to set_render_quality
    (which only touches Eevee). All settings persist on the scene.

    device:   'GPU' | 'CPU'. 'GPU' also enables the card in Cycles addon prefs, so a
              .blend saved as CPU starts using the GPU.
    backend:  GPU backend when device='GPU': OPTIX | CUDA | HIP | ONEAPI | METAL.
              Empty = auto-pick the best backend that has a device.
    denoise:  True/False — denoise the final image (the main grain fix).
    denoiser: 'OPTIX' | 'OPENIMAGEDENOISE'. Empty = leave as-is.
    adaptive_threshold: noise floor for adaptive sampling (e.g. 0.01); enables it.
    samples:  max render sample count.
    """
    scene = bpy.context.scene
    cycles = getattr(scene, "cycles", None)
    if cycles is None:
        return {"error": "scene.cycles not available — switch the engine to CYCLES first "
                         "(e.g. render_to_file(..., engine='CYCLES'))."}

    applied = []
    skipped = []

    device = params.get("device")
    if device is not None:
        dev = str(device).upper()
        if dev not in {"GPU", "CPU"}:
            return {"error": "device must be 'GPU' or 'CPU'"}
        if dev == "GPU":
            ok, chosen, gpu_devices, err = _enable_cycles_gpu(params.get("backend") or "")
            if not ok:
                return {"error": err}
            cycles.device = 'GPU'
            applied.append(f"device=GPU({chosen}: {', '.join(gpu_devices) or 'none'})")
        else:
            cycles.device = 'CPU'
            applied.append("device=CPU")

    denoise = params.get("denoise")
    if denoise is not None:
        cycles.use_denoising = bool(denoise)
        applied.append(f"denoise={bool(denoise)}")

    denoiser = params.get("denoiser")
    if denoiser:
        d = str(denoiser).upper()
        try:
            cycles.denoiser = d
            applied.append(f"denoiser={d}")
        except TypeError:
            skipped.append(f"denoiser={d} (not available in this build)")

    thr = params.get("adaptive_threshold")
    if thr is not None:
        cycles.use_adaptive_sampling = True
        cycles.adaptive_threshold = float(thr)
        applied.append(f"adaptive_threshold={float(thr)}")

    samples = params.get("samples")
    if samples is not None:
        cycles.samples = int(samples)
        applied.append(f"samples={int(samples)}")

    return {
        "success": True,
        "engine": scene.render.engine,
        "device": cycles.device,
        "denoise": cycles.use_denoising,
        "denoiser": cycles.denoiser,
        "samples": cycles.samples,
        "applied": applied,
        "skipped": skipped,
    }


TOOLS = {
    "add_light":            add_light,
    "modify_light":         modify_light,
    "aim_at":               aim_at,
    "rig_around":           rig_around,
    "set_world_background": set_world_background,
    "set_camera_dof":       set_camera_dof,
    "set_color_management": set_color_management,
    "set_render_quality":   set_render_quality,
    "set_cycles_quality":   set_cycles_quality,
}

"""Viewport tools: angle, framing, orbit, camera positioning."""

import math

import bpy
import mathutils


def find_view3d_context():
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return window, screen, area, region
    return None, None, None, None


def set_viewport_angle(params):
    angle = params.get("angle", "FRONT").upper()
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        if angle == "CAMERA":
            bpy.ops.view3d.view_camera()
        else:
            bpy.ops.view3d.view_axis(type=angle)

    return {"success": True, "angle": angle}


def frame_scene(params):
    """Fit objects in the viewport. By default ignores lights/cameras so they don't
    blow out the framing.

    targets: optional comma-separated names or single name. If given, fit only those.
    include_lights: include LIGHT/CAMERA objects in the fit. Default False.
    """
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    targets = params.get("targets") or ""
    include_lights = bool(params.get("include_lights", False))

    if targets or not include_lights:
        if isinstance(targets, list):
            names = [str(s).strip() for s in targets if s]
        else:
            names = [s.strip() for s in str(targets).split(",") if s.strip()]

        if names:
            from .common import resolve_targets
            objs, err = resolve_targets(names if len(names) > 1 else names[0])
            if err:
                return {"error": err}
        else:
            objs = [o for o in bpy.context.scene.objects
                    if include_lights or o.type not in {'LIGHT', 'CAMERA'}]

        if not objs:
            return {"error": "No objects to frame"}

        active = bpy.context.view_layer.objects.active
        # select_all's poll fails in any non-OBJECT mode — EDIT and also POSE, which
        # production rigs open in (gaps.md X2). Drop to OBJECT for the framing, then
        # restore the user's mode so framing isn't a silent mode-switch side effect.
        prev_mode = active.mode if active is not None else None
        if prev_mode is not None and prev_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        saved_active = bpy.context.view_layer.objects.active
        saved_selected = list(bpy.context.selected_objects)

        bpy.ops.object.select_all(action='DESELECT')
        for o in objs:
            try:
                o.select_set(True)
            except Exception:
                pass
        bpy.context.view_layer.objects.active = objs[0]

        with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
            bpy.ops.view3d.view_selected(use_all_regions=False)

        bpy.ops.object.select_all(action='DESELECT')
        for o in saved_selected:
            try:
                o.select_set(True)
            except Exception:
                pass
        if saved_active:
            bpy.context.view_layer.objects.active = saved_active
        if prev_mode not in (None, 'OBJECT') and saved_active:
            try:
                bpy.ops.object.mode_set(mode=prev_mode)
            except Exception:
                pass

        return {"success": True, "framed": [o.name for o in objs],
                "include_lights": include_lights}

    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        bpy.ops.view3d.view_all(center=False)
    return {"success": True}


def zoom_to_selected(params):
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}
    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        bpy.ops.view3d.view_selected()
    return {"success": True}


def _scene_view_bounds():
    """Union world bbox of visible mesh objects (selection if any are selected,
    else the whole scene). Returns (center, diagonal) or None when nothing fits."""
    from .common import world_bbox
    objs = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not objs:
        objs = [o for o in bpy.context.scene.objects
                if o.type == 'MESH' and o.visible_get()]
    if not objs:
        return None
    xs0, ys0, zs0, xs1, ys1, zs1 = [], [], [], [], [], []
    for o in objs:
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
        xs0.append(xmin); ys0.append(ymin); zs0.append(zmin)
        xs1.append(xmax); ys1.append(ymax); zs1.append(zmax)
    lo = (min(xs0), min(ys0), min(zs0))
    hi = (max(xs1), max(ys1), max(zs1))
    center = tuple((a + b) / 2.0 for a, b in zip(lo, hi))
    diag = math.sqrt(sum((b - a) ** 2 for a, b in zip(lo, hi)))
    return center, diag


def orbit_viewport(params):
    azimuth  = params.get("azimuth",  45.0)
    elevation = params.get("elevation", 25.0)
    distance  = params.get("distance",  8.0)
    tx = params.get("target_x", 0.0)
    ty = params.get("target_y", 0.0)
    tz = params.get("target_z", 1.0)

    # G79: orbit around a NAMED object's centre, not just a fixed point.
    target_obj = params.get("target")
    if target_obj:
        o = bpy.data.objects.get(target_obj)
        if o is None:
            return {"error": f"orbit target '{target_obj}' not found"}
        from .common import world_center
        tx, ty, tz = world_center(o)

    # auto_frame: derive target + distance from the scene/selection bounds so the
    # subject fills the frame at the current orbit angle — no eyeballing distance.
    auto_framed = None
    if params.get("auto_frame"):
        bounds = _scene_view_bounds()
        if bounds is None:
            return {"error": "auto_frame: no visible mesh objects to frame"}
        center, diag = bounds
        tx, ty, tz = center
        distance = max(diag * 1.5, 0.5)  # 1.5× diagonal frames with a little margin
        auto_framed = {"target": [round(c, 4) for c in center],
                       "distance": round(distance, 4)}

    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    r3d = next((s.region_3d for s in area.spaces if s.type == 'VIEW_3D'), None)
    if r3d is None:
        return {"error": "Could not access view"}

    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        bpy.ops.view3d.view_axis(type='FRONT')

    r3d.view_perspective = 'PERSP'
    r3d.view_location = mathutils.Vector((tx, ty, tz))
    r3d.view_distance = distance

    q_az = mathutils.Quaternion((0.0, 0.0, 1.0), math.radians(azimuth))
    r3d.view_rotation = q_az @ r3d.view_rotation
    q_el = mathutils.Quaternion((1.0, 0.0, 0.0), math.radians(-elevation))
    r3d.view_rotation = r3d.view_rotation @ q_el

    out = {"success": True}
    if auto_framed is not None:
        out["auto_framed"] = auto_framed
    return out


def set_active_camera(params):
    """G35: make an existing camera the active scene camera, so a freshly-added hero
    camera can become the render camera (and the target of the camera-write ops) without
    deleting every other camera. The missing 'set active camera' primitive."""
    name = params.get("camera") or params.get("name")
    if not name:
        return {"error": "'camera' is required"}
    cam = bpy.data.objects.get(name)
    if cam is None or cam.type != 'CAMERA':
        return {"error": f"Camera '{name}' not found"}
    bpy.context.scene.camera = cam
    bpy.context.view_layer.update()
    return {"success": True, "camera": cam.name, "active": True}


def add_camera(params):
    """Create a new camera and set it as the active scene camera.

    name:     required, unique.
    x, y, z:  world position (default 7, -7, 5).
    target:   optional object name to aim at. If omitted, uses target_x/y/z.
    target_x, target_y, target_z: world point to aim at (default 0, 0, 0).
    lens:     focal length in mm (default 50).
    """
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    if bpy.data.objects.get(name) is not None:
        return {"error": f"Object '{name}' already exists"}

    x = params.get("x", 7.0)
    y = params.get("y", -7.0)
    z = params.get("z", 5.0)
    lens = float(params.get("lens", 50.0))

    target = params.get("target")
    if target:
        tgt = bpy.data.objects.get(target)
        if tgt is None:
            return {"error": f"target '{target}' not found"}
        from .common import world_center
        tx, ty, tz = world_center(tgt)
    else:
        tx = params.get("target_x", 0.0)
        ty = params.get("target_y", 0.0)
        tz = params.get("target_z", 0.0)

    cam_data = bpy.data.cameras.new(name=name)
    cam_data.lens = lens
    obj = bpy.data.objects.new(name=name, object_data=cam_data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (x, y, z)

    direction = mathutils.Vector((tx, ty, tz)) - mathutils.Vector((x, y, z))
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    bpy.context.scene.camera = obj
    bpy.context.view_layer.update()

    return {
        "success": True,
        "camera": obj.name,
        "location": [round(x, 4), round(y, 4), round(z, 4)],
        "target": [round(tx, 4), round(ty, 4), round(tz, 4)],
        "lens": lens,
        "active": True,
    }


_SHADING_TYPES = {"WIREFRAME", "SOLID", "MATERIAL", "RENDERED"}


def set_viewport_shading(params):
    """Switch the 3D viewport's shading mode.

    mode: WIREFRAME | SOLID | MATERIAL | RENDERED
          - SOLID: matcap/default flat shading (no materials visible)
          - MATERIAL: previews materials with built-in studio lighting (cheap, fast)
          - RENDERED: full Eevee/Cycles preview using your scene lights + world
          - WIREFRAME: edges only

    Sets the user's live viewport shading (and what render_to_file captures if it
    uses the viewport). Without MATERIAL/RENDERED, the user sees whatever mode is
    currently set (usually SOLID), which hides every material decision.
    """
    mode = params.get("mode", "MATERIAL").upper()
    if mode not in _SHADING_TYPES:
        return {"error": f"Invalid mode '{mode}'. Use one of {sorted(_SHADING_TYPES)}"}
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}
    space = next((s for s in area.spaces if s.type == 'VIEW_3D'), None)
    if space is None:
        return {"error": "No VIEW_3D space found"}
    space.shading.type = mode
    return {"success": True, "mode": mode}


_OVERLAY_FLAGS = {
    "relationship_lines": "show_relationship_lines",
    "floor":              "show_floor",
    "cursor":             "show_cursor",
    "wireframes":         "show_wireframes",
    "text_info":          "show_text",
    "overlays":           "show_overlays",   # master toggle
}


def set_viewport_overlays(params):
    """Toggle the USER's live 3D-viewport overlays — clean up what the PERSON sees
    (gaps.md T5). On a rigged, scattered scene the
    dashed relationship lines and grid clutter make a textured model read as gray
    blockout to whoever's watching.

    Pass any of: relationship_lines, floor, cursor, wireframes, text_info, axes,
    overlays (master) — each a bool. To hide an armature's bones from the user, use
    set_object_visibility on the armature (the Armature modifier keeps deforming)."""
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found (headless?)"}
    space = next((s for s in area.spaces if s.type == 'VIEW_3D'), None)
    if space is None:
        return {"error": "No VIEW_3D space found"}
    ov = space.overlay

    changed = {}
    for key, attr in _OVERLAY_FLAGS.items():
        if params.get(key) is not None and hasattr(ov, attr):
            setattr(ov, attr, bool(params[key]))
            changed[key] = bool(params[key])
    if params.get("axes") is not None:
        val = bool(params["axes"])
        ov.show_axis_x = val
        ov.show_axis_y = val
        changed["axes"] = val

    if not changed:
        opts = ", ".join(list(_OVERLAY_FLAGS) + ["axes"])
        return {"error": f"no overlay flags given. Options (bool each): {opts}"}
    return {"success": True, "changed": changed}


TOOLS = {
    "set_viewport_angle":      set_viewport_angle,
    "set_viewport_shading":    set_viewport_shading,
    "set_viewport_overlays":   set_viewport_overlays,
    "frame_scene":             frame_scene,
    "zoom_to_selected":        zoom_to_selected,
    "orbit_viewport":          orbit_viewport,
    "set_active_camera":       set_active_camera,
    "add_camera":              add_camera,
}

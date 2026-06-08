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
    type:     POINT | SUN | SPOT | AREA (default POINT).
    x, y, z:  world position (default 0,0,5).
    energy:   light strength. Default 1000 for POINT/SPOT/AREA, 5 for SUN.
              POINT/SPOT/AREA energy is in watts; SUN is irradiance-like.
    color:    [r, g, b] floats 0..1. Default warm white [1, 0.95, 0.9].
    size:     soft-shadow radius (POINT), or AREA quad side, or SPOT radius. Default 0.25.
    target:   optional object name. If given, the light is aimed at that object's center.
    """
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    if bpy.data.objects.get(name) is not None:
        return {"error": f"Object '{name}' already exists"}

    light_type = (params.get("type") or "POINT").upper()
    if light_type not in _LIGHT_TYPES:
        return {"error": f"Invalid light type '{light_type}'. Use one of {sorted(_LIGHT_TYPES)}"}

    x = params.get("x", 0.0)
    y = params.get("y", 0.0)
    z = params.get("z", 5.0)
    color = params.get("color") or [1.0, 0.95, 0.9]
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


def set_world_background(params):
    """Set the scene's world environment.

    color:    [r, g, b] solid background color (0..1 floats). Optional.
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
    focus_object:   object name to focus on (camera auto-tracks its distance).
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
    if focus_object_name:
        tgt = bpy.data.objects.get(focus_object_name)
        if tgt is None:
            return {"error": f"focus_object '{focus_object_name}' not found"}
        dof.focus_object = tgt
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
        "focus_object": dof.focus_object.name if dof.focus_object else None,
        "focus_distance": round(dof.focus_distance, 4),
        "aperture_fstop": round(dof.aperture_fstop, 4),
    }


TOOLS = {
    "add_light":            add_light,
    "set_world_background": set_world_background,
    "set_camera_dof":       set_camera_dof,
}

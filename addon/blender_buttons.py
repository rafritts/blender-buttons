bl_info = {
    "name": "Blender Buttons",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "description": "MCP bridge — lets an LLM drive Blender like a human would",
    "category": "System",
}

import bpy
import mathutils
import socket
import threading
import json
import base64
import os
import tempfile
import queue
import math

PORT = 8765
_request_queue = queue.Queue()
_server_thread = None
_running = False


def find_view3d_context():
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return window, screen, area, region
    return None, None, None, None


# --- Tools (all run on main thread) ---

def get_scene_tree():
    def fmt_collection(col, depth=0):
        pad = "│   " * depth
        lines = [f"{pad}├── {col.name}/"]
        for obj in col.objects:
            active = " ● active" if obj == bpy.context.active_object else ""
            sel = " ◆" if obj.select_get() else ""
            lines.append(f"{pad}│   ├── {obj.name} [{obj.type}]{active}{sel}")
        for child in col.children:
            lines += fmt_collection(child, depth + 1)
        return lines

    lines = ["Scene Collection"]
    for col in bpy.context.scene.collection.children:
        lines += fmt_collection(col)
    for obj in bpy.context.scene.collection.objects:
        active = " ● active" if obj == bpy.context.active_object else ""
        sel = " ◆" if obj.select_get() else ""
        lines.append(f"├── {obj.name} [{obj.type}]{active}{sel}")
    return {"tree": "\n".join(lines)}


def get_viewport_screenshot(params):
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    scene = bpy.context.scene
    old_path = scene.render.filepath
    old_format = scene.render.image_settings.file_format

    tmp = os.path.join(tempfile.gettempdir(), "bb_viewport.png")
    scene.render.filepath = tmp
    scene.render.image_settings.file_format = 'PNG'

    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        bpy.ops.render.opengl(write_still=True)

    scene.render.filepath = old_path
    scene.render.image_settings.file_format = old_format

    with open(tmp, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    return {"image": data, "format": "png"}


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


def add_primitive(params):
    ptype = params.get("type", "CUBE").upper()
    location = params.get("location", [0, 0, 0])

    bpy.ops.object.select_all(action='DESELECT')

    ops = {
        "CUBE": bpy.ops.mesh.primitive_cube_add,
        "SPHERE": bpy.ops.mesh.primitive_uv_sphere_add,
        "CYLINDER": bpy.ops.mesh.primitive_cylinder_add,
        "PLANE": bpy.ops.mesh.primitive_plane_add,
        "CONE": bpy.ops.mesh.primitive_cone_add,
    }

    if ptype not in ops:
        return {"error": f"Unknown primitive: {ptype}. Valid: {list(ops.keys())}"}

    ops[ptype](location=location)
    obj = bpy.context.active_object
    return {"success": True, "object_name": obj.name if obj else None}


def select_object(params):
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}

    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"error": f"Object '{name}' not found"}

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return {"success": True, "selected": name}


def scale_object(params):
    x = params.get("x", 1.0)
    y = params.get("y", 1.0)
    z = params.get("z", 1.0)
    bpy.ops.transform.resize(value=(x, y, z))
    return {"success": True}


def move_object(params):
    x = params.get("x", 0.0)
    y = params.get("y", 0.0)
    z = params.get("z", 0.0)
    bpy.ops.transform.translate(value=(x, y, z))
    return {"success": True}


def rotate_object(params):
    angle = params.get("angle", 0.0)
    axis = params.get("axis", "Z").upper()
    bpy.ops.transform.rotate(value=math.radians(angle), orient_axis=axis)
    return {"success": True}


def set_mode(params):
    mode = params.get("mode", "OBJECT").upper()
    bpy.ops.object.mode_set(mode=mode)
    return {"success": True, "mode": mode}


def delete_object(params):
    name = params.get("name")
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"error": f"Object '{name}' not found"}
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    active = bpy.context.active_object
    if active is None:
        return {"error": "No active object to delete"}
    deleted = active.name
    bpy.ops.object.delete()
    return {"success": True, "deleted": deleted}


def frame_scene(params):
    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}
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


def orbit_viewport(params):
    azimuth = params.get("azimuth", 45.0)    # 0=front, positive=right, negative=left
    elevation = params.get("elevation", 25.0) # 0=horizontal, positive=from above
    distance = params.get("distance", 8.0)
    tx = params.get("target_x", 0.0)
    ty = params.get("target_y", 0.0)
    tz = params.get("target_z", 1.0)

    window, screen, area, region = find_view3d_context()
    if area is None:
        return {"error": "No 3D viewport found"}

    r3d = None
    for space in area.spaces:
        if space.type == 'VIEW_3D':
            r3d = space.region_3d
            break
    if r3d is None:
        return {"error": "Could not access view"}

    # Start from a known base orientation (FRONT) then apply orbit
    with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
        bpy.ops.view3d.view_axis(type='FRONT')

    r3d.view_perspective = 'PERSP'
    r3d.view_location = mathutils.Vector((tx, ty, tz))
    r3d.view_distance = distance

    # Azimuth: spin around world Z
    q_az = mathutils.Quaternion((0.0, 0.0, 1.0), math.radians(azimuth))
    r3d.view_rotation = q_az @ r3d.view_rotation

    # Elevation: tilt around the view's local right axis
    q_el = mathutils.Quaternion((1.0, 0.0, 0.0), math.radians(-elevation))
    r3d.view_rotation = r3d.view_rotation @ q_el

    return {"success": True}


def set_camera_position(params):
    x = params.get("x", 5.0)
    y = params.get("y", -5.0)
    z = params.get("z", 5.0)
    tx = params.get("target_x", 0.0)
    ty = params.get("target_y", 0.0)
    tz = params.get("target_z", 0.0)

    cam = next((o for o in bpy.data.objects if o.type == 'CAMERA'), None)
    if cam is None:
        return {"error": "No camera in scene"}

    cam.location = (x, y, z)
    direction = mathutils.Vector((tx, ty, tz)) - mathutils.Vector((x, y, z))
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    return {"success": True, "camera": cam.name}


# --- Dispatch ---

TOOLS = {
    "get_scene_tree": lambda p: get_scene_tree(),
    "get_viewport_screenshot": get_viewport_screenshot,
    "set_viewport_angle": set_viewport_angle,
    "add_primitive": add_primitive,
    "select_object": select_object,
    "scale_object": scale_object,
    "move_object": move_object,
    "rotate_object": rotate_object,
    "set_mode": set_mode,
    "delete_object": delete_object,
    "frame_scene": frame_scene,
    "zoom_to_selected": zoom_to_selected,
    "set_camera_position": set_camera_position,
    "orbit_viewport": orbit_viewport,
}


def execute_command(command):
    tool = command.get("tool")
    params = command.get("params", {})
    fn = TOOLS.get(tool)
    if fn is None:
        return {"error": f"Unknown tool: {tool}. Available: {list(TOOLS.keys())}"}
    try:
        return fn(params)
    except Exception as e:
        return {"error": str(e)}


# --- Socket server ---

def handle_client(conn):
    try:
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break

        command = json.loads(data.decode().strip())
        result_event = threading.Event()
        result_box = [None]

        def on_main_thread():
            result_box[0] = execute_command(command)
            result_event.set()
            return None

        _request_queue.put(on_main_thread)
        result_event.wait(timeout=30)

        conn.sendall((json.dumps(result_box[0]) + "\n").encode())
    except Exception as e:
        try:
            conn.sendall((json.dumps({"error": str(e)}) + "\n").encode())
        except Exception:
            pass
    finally:
        conn.close()


def server_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("localhost", PORT))
    sock.listen(5)
    sock.settimeout(1.0)
    while _running:
        try:
            conn, _ = sock.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
        except socket.timeout:
            continue
    sock.close()


def process_queue():
    while not _request_queue.empty():
        try:
            fn = _request_queue.get_nowait()
            fn()
        except queue.Empty:
            break
    return 0.05


# --- UI ---

class BB_OT_StartServer(bpy.types.Operator):
    bl_idname = "bb.start_server"
    bl_label = "Start Server"

    def execute(self, context):
        global _server_thread, _running
        if _running:
            self.report({'INFO'}, "Already running")
            return {'FINISHED'}
        _running = True
        _server_thread = threading.Thread(target=server_loop, daemon=True)
        _server_thread.start()
        bpy.app.timers.register(process_queue, persistent=True)
        self.report({'INFO'}, f"Blender Buttons listening on port {PORT}")
        return {'FINISHED'}


class BB_OT_StopServer(bpy.types.Operator):
    bl_idname = "bb.stop_server"
    bl_label = "Stop Server"

    def execute(self, context):
        global _running
        _running = False
        if bpy.app.timers.is_registered(process_queue):
            bpy.app.timers.unregister(process_queue)
        self.report({'INFO'}, "Server stopped")
        return {'FINISHED'}


class BB_PT_Panel(bpy.types.Panel):
    bl_label = "Blender Buttons"
    bl_idname = "BB_PT_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        layout.operator("bb.start_server", icon='PLAY')
        layout.operator("bb.stop_server", icon='PAUSE')
        layout.label(text=f"Status: {'Running' if _running else 'Stopped'}")
        layout.label(text=f"Port: {PORT}")


classes = [BB_OT_StartServer, BB_OT_StopServer, BB_PT_Panel]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    global _running
    _running = False
    if bpy.app.timers.is_registered(process_queue):
        bpy.app.timers.unregister(process_queue)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

import socket
import json
import base64
from mcp.server.fastmcp import FastMCP, Image

ADDON_HOST = "localhost"
ADDON_PORT = 8765

mcp = FastMCP("blender-buttons")


def call_blender(tool: str, params: dict = {}) -> dict:
    payload = json.dumps({"tool": tool, "params": params}) + "\n"
    with socket.create_connection((ADDON_HOST, ADDON_PORT), timeout=30) as sock:
        sock.sendall(payload.encode())
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
    return json.loads(data.decode().strip())


# --- Tools ---

@mcp.tool()
def get_scene_tree() -> str:
    """List all objects in the Blender scene as a tree. Call this first to know what exists."""
    result = call_blender("get_scene_tree")
    return result.get("tree", result.get("error", "unknown error"))


@mcp.tool()
def get_viewport_screenshot() -> Image:
    """Capture the current 3D viewport. Call this to see what Blender looks like right now."""
    result = call_blender("get_viewport_screenshot")
    if "error" in result:
        raise RuntimeError(result["error"])
    return Image(data=base64.b64decode(result["image"]), format="png")


@mcp.tool()
def set_viewport_angle(angle: str) -> str:
    """
    Set the viewport to a standard angle.
    angle: FRONT | BACK | LEFT | RIGHT | TOP | BOTTOM | CAMERA
    """
    result = call_blender("set_viewport_angle", {"angle": angle})
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def add_primitive(type: str, x: float = 0, y: float = 0, z: float = 0) -> str:
    """
    Add a mesh primitive to the scene.
    type: CUBE | SPHERE | CYLINDER | PLANE | CONE
    x, y, z: location in world space
    """
    result = call_blender("add_primitive", {"type": type, "location": [x, y, z]})
    if result.get("success"):
        return f"Added {type} as '{result['object_name']}'"
    return result.get("error", "failed")


@mcp.tool()
def select_object(name: str) -> str:
    """Select an object by name and make it active. Use get_scene_tree first to find names."""
    result = call_blender("select_object", {"name": name})
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def scale_object(x: float = 1.0, y: float = 1.0, z: float = 1.0) -> str:
    """
    Scale the active object. Values are multipliers (0.5 = half size, 2.0 = double).
    Use per-axis scaling to change proportions (e.g. x=1, y=1, z=3 makes it tall).
    """
    result = call_blender("scale_object", {"x": x, "y": y, "z": z})
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def move_object(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> str:
    """Move the active object by a relative offset in world units."""
    result = call_blender("move_object", {"x": x, "y": y, "z": z})
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def rotate_object(angle: float, axis: str = "Z") -> str:
    """
    Rotate the active object.
    angle: degrees
    axis: X | Y | Z
    """
    result = call_blender("rotate_object", {"angle": angle, "axis": axis})
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def set_mode(mode: str) -> str:
    """
    Switch the active object's interaction mode.
    mode: OBJECT | EDIT | SCULPT
    """
    result = call_blender("set_mode", {"mode": mode})
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def delete_object(name: str) -> str:
    """Delete an object by name. Use get_scene_tree to find object names."""
    result = call_blender("delete_object", {"name": name})
    if result.get("success"):
        return f"Deleted '{result['deleted']}'"
    return result.get("error", "failed")


@mcp.tool()
def frame_scene() -> str:
    """Fit all objects in the viewport. Call this when the view is cropped or objects are out of frame."""
    result = call_blender("frame_scene")
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def zoom_to_selected() -> str:
    """
    Zoom the viewport to tightly frame the currently selected object.
    Use select_object first, then call this to zoom in for detail work.
    """
    result = call_blender("zoom_to_selected")
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def orbit_viewport(azimuth: float = 45.0, elevation: float = 25.0, distance: float = 8.0,
                   target_x: float = 0.0, target_y: float = 0.0, target_z: float = 1.0) -> str:
    """
    Position the viewport perspective camera using orbit controls. Captures with get_viewport_screenshot — no camera border, no crop.
    azimuth: horizontal angle in degrees (0=front, +right, -left)
    elevation: vertical angle in degrees (0=horizontal, positive=from above)
    distance: distance from target
    target_x/y/z: point to orbit around (default chair center)
    """
    result = call_blender("orbit_viewport", {
        "azimuth": azimuth, "elevation": elevation, "distance": distance,
        "target_x": target_x, "target_y": target_y, "target_z": target_z,
    })
    return "ok" if result.get("success") else result.get("error", "failed")


@mcp.tool()
def set_camera_position(x: float, y: float, z: float, target_x: float = 0.0, target_y: float = 0.0, target_z: float = 0.0) -> str:
    """
    Move the camera to a position and aim it at a target point.
    Then call set_viewport_angle(CAMERA) to see the composed shot.
    target_x/y/z default to the scene origin (0, 0, 0).
    """
    result = call_blender("set_camera_position", {
        "x": x, "y": y, "z": z,
        "target_x": target_x, "target_y": target_y, "target_z": target_z,
    })
    return "ok" if result.get("success") else result.get("error", "failed")


if __name__ == "__main__":
    mcp.run()

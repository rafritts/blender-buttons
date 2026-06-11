import socket
import json
from mcp.server.fastmcp import FastMCP

ADDON_HOST = "localhost"
ADDON_PORT = 8765

mcp = FastMCP("blender-buttons")


def call_blender(tool: str, params: dict = None, label: str = "", timeout: float = 30) -> dict:
    payload = json.dumps({"tool": tool, "params": params or {}, "label": label,
                          "timeout": timeout}) + "\n"
    try:
        with socket.create_connection((ADDON_HOST, ADDON_PORT), timeout=timeout) as sock:
            sock.settimeout(timeout)  # cap each recv too, so long renders aren't cut at 30s
            sock.sendall(payload.encode())
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        return {"error": (
            f"Cannot reach Blender extension on {ADDON_HOST}:{ADDON_PORT} ({type(e).__name__}). "
            "Open Blender, enable the 'Blender Buttons' extension, and click 'Start Server' "
            "in the Scene properties panel."
        )}
    return json.loads(data.decode().strip())


def _status(result: dict) -> str:
    """Format the blender_status block that every tool response now carries."""
    s = result.get("blender_status")
    if not s:
        return ""
    wb = s.get("world_bounds") or {}
    lines = [
        "",
        "── blender status ──────────────────────────────",
        f"  mode:        {s['mode']}",
        f"  active:      {s['active_object']} ({s['active_type']})",
        f"  selected:    {s['selected_objects']}",
        f"  dims:        {s.get('dimensions')}     (world bbox, rotation-aware)",
        f"  bounds:      x={wb.get('x')}  y={wb.get('y')}  z={wb.get('z')}",
        f"  rot_deg:     {s.get('rotation_deg')}",
        f"  last_action: {s.get('last_action')}",
    ]
    r = s.get("render")
    if r:
        rt = f"  raytracing={r['raytracing']}" if "raytracing" in r else ""
        lines.append(
            f"  render:      {r['engine']}  view={r['view_transform']} "
            f"look={r['look']} exp={r['exposure']} gamma={r['gamma']}{rt}"
        )
    if s.get("viewport"):
        lines.append(f"  viewport:    {s['viewport']}  (user's live shading mode)")
    if "edit" in s:
        e = s["edit"]
        lines += [
            f"  ── edit ──",
            f"  component:   {e['component_mode']}",
            f"  selected:    {e['selected']}  /  total: {e['total']}",
            f"  sel_z:       {e.get('selection_z_range', '—')}",
        ]
    lines.append("────────────────────────────────────────────────")
    return "\n".join(lines)


def _add_result(ptype: str, result: dict) -> str:
    if result.get("success"):
        dims = result.get("dimensions")
        bounds = result.get("world_bounds", {})
        bounds_str = (f" at x={bounds.get('x')} y={bounds.get('y')} z={bounds.get('z')}"
                      if bounds else "")
        return f"Added {ptype} as '{result['object_name']}' dims={dims}{bounds_str} [{result.get('op_id','')}]"
    return result.get("error", "failed")


def _targets(targets: str):
    """Parse a `targets` string used by multi-object tools.

    "" → None (caller should treat as "active object")
    "name" → "name"
    "a,b,c" → ["a", "b", "c"]
    """
    if not targets:
        return None
    parts = [s.strip() for s in targets.split(",")]
    return parts[0] if len(parts) == 1 else parts

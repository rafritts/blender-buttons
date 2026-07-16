# Session Notes

## What We're Building

An MCP server called **blender-buttons** that exposes Blender operations so an LLM can drive Blender the way a human would — looking at viewport screenshots and issuing named operations, never reasoning over raw geometry.

## Current State

### What's Built
- `addon/blender_buttons.py` — Blender add-on. Opens a TCP socket on port 8765, listens for JSON commands, executes them via `bpy` on Blender's main thread (via a queue + timer), returns results. Has a Start/Stop button panel in Properties → Scene.
- `server/main.py` — FastMCP server. Exposes 9 tools that proxy to the add-on over the socket.
- `pyproject.toml` — uv project, depends on `mcp[cli]`.
- `.mcp.json` at the repo root — points Claude Code at the server.
- `~/.claude/settings.json` (symlinked from `~/dotfiles/.claude/settings.json`) — has `enabledMcpjsonServers: ["blender-buttons"]`.

### Tools Exposed
1. `get_scene_tree` — lists scene collection as a readable tree
2. `get_viewport_screenshot` — captures the 3D viewport as an image (via `render.opengl`)
3. `set_viewport_angle` — sets view angle: FRONT | BACK | LEFT | RIGHT | TOP | BOTTOM | CAMERA
4. `add_primitive` — adds CUBE | SPHERE | CYLINDER | PLANE | CONE at a location
5. `select_object` — selects an object by name
6. `scale_object` — scales active object per axis
7. `move_object` — moves active object by offset
8. `rotate_object` — rotates active object by degrees around an axis
9. `set_mode` — switches OBJECT | EDIT | SCULPT mode

### Architecture
```
LLM (Claude)
  ↓ MCP tool calls
server/main.py  (FastMCP, stdio)
  ↓ JSON over TCP socket (localhost:8765)
addon/blender_buttons.py  (runs inside Blender)
  ↓ bpy
Blender 5.2.0 LTS
```

## MCP Configuration

`.mcp.json` must use **absolute paths** — Claude Code does not respect the `cwd` field, so relative paths fail. The correct config is:

```json
{
  "mcpServers": {
    "blender-buttons": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["/absolute/path/to/server/main.py"]
    }
  }
}
```

Claude Code uses MCP protocol version `2025-11-25`. The FastMCP server (mcp 1.27.2) negotiates this correctly.

After moving the repo, update the absolute paths in `.mcp.json` to match the new location.

## Setup Steps

1. Install the add-on in Blender: Edit → Preferences → Add-ons → Install → pick `addon/blender_buttons.py` → enable it
2. In Blender: Properties → Scene → Blender Buttons → Start Server
3. Open a Claude Code session in this repo root (picks up `.mcp.json`)
4. Verify: call `get_scene_tree`, then `get_viewport_screenshot`

## Known Issues / Things to Watch

- `render.opengl` for screenshots requires a 3D viewport to be open and active — won't work if Blender is minimized or only showing non-3D areas
- Transform operators (scale, move, rotate) need an active selected object — always call `select_object` first
- The add-on's `process_queue` timer runs every 50ms — introduces slight latency on each operation
- Context overrides (`temp_override`) require Blender 4.0+; we're on 5.2 LTS so this is fine

## User Context

Backend systems engineer, 13 years experience, strong agentic systems background. Not a 3D artist. Passionate about gaming. Wants quality assets, not AI slop. Blender is installed as a Flatpak (`org.blender.Blender`). Settings live in `~/dotfiles/` and are symlinked into `~/.claude/`.

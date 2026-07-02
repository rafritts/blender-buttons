# UE5-buttons — handoff notes (2026-07-01, Linux session)

Porting the buttons principle to UE5: sidestep the human-optimized interactive UI and
project the domain into agent-space (names, relations, dimensions, legible perception).
Partnership split: human owns taste + experiential playtesting ("does it feel right");
agent owns precision + mechanical verification ("does it provably work"). Agent never
uses the human as a smoke-tester; human never needs engine knowledge.

## Proven tonight (UE 5.8.0, Linux, RTX 4090)

Full perceive/mutate loop from a terminal into a live editor, **zero custom code**:

```
terminal → HTTP :30010 → Remote Control plugin → editor Python → scene graph
```

- Listed all level actors of the ThirdPerson template.
- Moved an actor (`SM_Cube` +300 Z) and read back its location.

### The probe commands

```bash
# API alive? (GET, not PUT)
curl -s http://localhost:30010/remote/info

# Execute editor Python (the everything-bridge)
curl -s -X PUT http://localhost:30010/remote/object/call \
  -H "Content-Type: application/json" -d '{
  "objectPath": "/Script/PythonScriptPlugin.Default__PythonScriptLibrary",
  "functionName": "ExecutePythonCommandEx",
  "parameters": {
    "PythonCommand": "import unreal; sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem); print(sorted(a.get_actor_label() for a in sub.get_all_level_actors()))",
    "PythonCommandExecutionMode": "ExecuteStatement"}}'
```

`ExecutePythonCommandEx` returns `LogOutput` (stdout lines) + `ReturnValue` in the HTTP
response — a complete REPL. Subsystem access: `unreal.get_editor_subsystem(unreal.EditorActorSubsystem)`.

## Setup keys (replicate on Windows)

1. **Plugins — enable by editing the `.uproject` directly** (no Plugins window needed);
   add to the `"Plugins"` array:
   `{"Name": "PythonScriptPlugin", "Enabled": true}, {"Name": "RemoteControl", "Enabled": true}`
2. **`Config/DefaultRemoteControl.ini`** (new file in the project; 5.8 has a layered
   security model — names verified against 5.8 plugin source, both required for the
   Python bridge; editor restart required to pick up changes):

   ```ini
   [/Script/RemoteControlCommon.RemoteControlSettings]
   bEnableRemotePythonExecution=True
   bAllowAnyRemoteFunctionCall=True
   ```
3. Ports: HTTP **30010** (binds 127.0.0.1), WebSocket **30020** (binds **0.0.0.0** —
   LAN-exposed; fine for dev, lock down for real use). A real server should replace
   `bAllowAnyRemoteFunctionCall=True` with a narrow `CustomAllowedRemoteFunctionCalls` list.

## Topology (revised 2026-07-01): Claude on the Mac mini, UE on the Windows box

Claude Code's home is the Mac mini (`restless@100.76.210.101`, Apple Silicon,
`~/workspace/blender-buttons`); UE runs on the Windows gaming rig. Connection is
cross-machine over Tailscale — NOT loopback — so RC HTTP's 127.0.0.1 bind on the
Windows side is definitely unreachable as-is. Fixes, in order of preference:
1. Find/set the RC web-server bind-address setting (`RemoteControlSettings`, same ini).
2. Windows port proxy: `netsh interface portproxy add v4tov4 listenport=30010
   connectaddress=127.0.0.1 connectport=30010` (+ firewall rule; scope to Tailscale IP).
3. SSH tunnel from Mac → Windows (needs OpenSSH server on Windows).

No WSL needed in this topology. File edits on the Windows project (.uproject, ini) happen
via whatever remote access exists (SSH/scp if OpenSSH is enabled, or by hand).

## Linux-specific damage report (moot on Windows/DX12, recorded for posterity)

- UE 5.8.0 + Linux Vulkan + NVIDIA has a known open `VK_ERROR_DEVICE_LOST` crash;
  workaround `-noraytracing`; real fixes slated for 5.8.1.
  https://forums.unrealengine.com/t/ue-5-8-release-instant-vulkan-crash-vk-error-device-lost-on-linux-with-rtx-3090-ti-nvidia-driver/2729632
- NVIDIA driver 595.71.05 additionally has a swapchain-creation regression: opening any
  NEW editor window (Plugins, asset editors) could kill the device. 595.58.03 was the
  fixed stable; Ubuntu archives only carry .71, so the apt path is the 580 branch.
- Both together made the Linux editor a minefield; Windows DX12 sidesteps all of it.

## Next design step

Thin FastMCP server (same skeleton as blender-buttons `server/main.py`) speaking HTTP
to Remote Control instead of a TCP socket to a Blender addon. Starting verbs:
`scene` (what's here), `feel` (bounds/relations), `add` (spawn/place), `transform`
(move/rotate by intent). Then the two genuinely novel fronts, where the projection
must be invented rather than ported:
- **Logic**: Blueprint graphs are not Python-authorable — the path is generated C++ +
  Live Coding, or a text DSL compiled server-side. This is the moonshot crux.
- **Temporal feel**: mechanical ground truth from automation/functional tests, Visual
  Logger, navmesh/EQS queries — the agent proves "it works"; the human judges "it feels".

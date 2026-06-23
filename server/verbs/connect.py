"""connect — choose which Blender instance this session drives (SPEC-05 verb).

Several Blender instances can run at once (each binds its own port), and each Claude
session has its own MCP process — so each session attaches to one instance and drives
it independently. The first real tool call auto-attaches when exactly one instance is
live; when several are, the tools error out and point here.

  list     — show the running instances (port, label/file, mesh count, pid)
  current  — which instance this session is attached to
  attach   — bind to one by port= (or label= / file= substring)
  detach   — release the attachment (next command re-resolves)
  launch   — open a NEW Blender (optionally on a .blend) and attach to it
"""

from typing import Literal

from server._core import mcp
from server import instances
from ._common import tag, unknown

_OPS = ["list", "current", "attach", "detach", "launch"]


@mcp.tool(name="connect")
def connect(
    op: Literal["list", "current", "attach", "detach", "launch"],
    port: tag(int, "[attach] port of the instance to drive") = None,
    label: tag(str, "[attach] attach by instance-label substring") = "",
    file: tag(str, "[attach] .blend-filename substring to match; [launch] .blend path to open") = "",
    blender: tag(str, "[launch] Blender executable path (else $BLENDER_BUTTONS_BLENDER / PATH)") = "",
) -> str:
    """
    Pick / inspect the Blender instance this session drives. `op` selects:

      list     — running instances: port, label/file, mesh count, mode, pid
      current  — the instance currently attached (if any)
      attach   — bind to one: port=<N>, or label=<substr>, or file=<substr>
      detach   — release; the next command auto-attaches if exactly one is live
      launch   — open a new Blender (file=<path.blend> optional) and attach to it

    You normally never need this with a single Blender open — the first command
    auto-attaches. Reach for it when the tools report multiple instances and ask
    which to drive, or to spin up a fresh instance with `launch`.
    """
    o = op.lower().strip()
    if o in ("list", "instances"):
        return instances.list_instances()
    if o == "current":
        return instances.current()
    if o == "attach":
        return instances.attach(port=port, label=label, file=file)
    if o == "detach":
        return instances.detach()
    if o == "launch":
        return instances.launch(file=file, blender=blender)
    return unknown("connect", "op", op, _OPS)

import socket
import json
import threading
from mcp.server.fastmcp import FastMCP

from server._instructions import INSTRUCTIONS

ADDON_HOST = "localhost"
ADDON_PORT = 8765           # legacy default / range start

# Instance discovery: each Blender binds the first free port in this range, so N
# instances coexist. This MCP process (one per Claude session) scans the range,
# `ping`s each, and binds to ONE — held in `_attached_port`, in-process, which makes
# the attachment naturally per-session with zero cross-session coordination.
PORT_MIN = 8765
PORT_MAX = 8785             # exclusive — mirror of extension/state.py
PORT_RANGE = range(PORT_MIN, PORT_MAX)

_attached_port = None       # the Blender this session drives (None = unresolved)
# Serializes attachment resolution so concurrent (batched) tool calls can't race on
# `_attached_port` — one clears it while another reads it (G139). The Blender side
# already serializes the WORK on its main-thread queue; this only guards the pointer.
_resolve_lock = threading.RLock()

# `instructions` is returned at MCP initialize; the spec lets the client inject it
# into the model's system prompt. It bootstraps baseline knowledge of this server
# and points at the `guidance://llms` resource (server/resources.py) for depth.
mcp = FastMCP("blender-buttons", instructions=INSTRUCTIONS)


def _ping(port: int, timeout: float = 0.4) -> dict | None:
    """Identity probe against one port. Returns the instance's `ping` payload (with
    `port` stamped on), or None if nothing alive/answering there. Connection-refused
    on localhost is instant, so scanning the whole range is cheap."""
    try:
        with socket.create_connection((ADDON_HOST, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall((json.dumps({"tool": "ping", "params": {}}) + "\n").encode())
            data = b""
            while b"\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        r = json.loads(data.decode().strip())
    except (ConnectionRefusedError, socket.timeout, OSError, ValueError):
        return None
    if isinstance(r, dict) and r.get("ok_ping"):
        r["port"] = port
        return r
    return None


def discover_instances(timeout: float = 0.4) -> list:
    """Scan the port range and return the live instances (their `ping` payloads).
    Stateless and self-cleaning: a dead instance simply refuses the connection."""
    return [i for i in (_ping(p, timeout) for p in PORT_RANGE) if i]


def attached_port():
    return _attached_port


def set_attached(port):
    global _attached_port
    _attached_port = int(port) if port is not None else None


def _describe(i: dict) -> str:
    name = i.get("label") or i.get("blend_file") or "(unsaved)"
    return (f"  • port {i['port']}: {name}  [{i.get('mesh_count', '?')} meshes, "
            f"mode {i.get('mode', '?')}, pid {i.get('pid', '?')}]")


def _resolve_target():
    """Decide which port this session's tool call should hit.

    Returns (port, None) on success, or (None, error_dict) when the agent must
    choose. Policy: a live attachment wins and is TRUSTED WITHOUT a preflight ping;
    exactly one live instance auto-attaches silently (the common case); zero or 2+
    raise an actionable error. So the 'which Blender?' gate fires at most once per
    session, only when there's a genuine ambiguity.

    G139: the attachment is NOT re-pinged here. A busy instance (mid 4K-texture-load,
    HDRI swap, heavy bind) can't answer a 0.4s liveness probe, and the old re-ping
    read that silence as 'the instance died' — cleared the attachment, re-discovered
    (every probe timing out under the same load), and returned 'No Blender instance is
    reachable' for an instance that was alive the whole time. Instead we trust the
    attachment and let the real call connect; if the instance is genuinely GONE the
    connect is refused instantly and call_blender clears + re-resolves + retries once."""
    if _attached_port is not None:
        return _attached_port, None
    live = discover_instances()
    if not live:
        return None, {"error": (
            "No Blender instance is reachable. Open Blender with the 'Blender Buttons' "
            "extension enabled (it auto-starts its command server), or use "
            "`connect op=launch` to open one.")}
    if len(live) == 1:
        set_attached(live[0]["port"])
        return _attached_port, None
    lines = "\n".join(_describe(i) for i in live)
    return None, {"error": (
        "Multiple Blender instances are running — pick one before issuing commands. "
        "Ask the user which to drive, then call `connect op=attach port=<N>` (or "
        f"label=/file=). Live instances:\n{lines}")}

# SPEC-05 cutover switch. When False (default) the 137 flat tools are pruned from
# the MCP surface after the verbs register, leaving ~15 verb tools. Set True to
# expose the flat tools alongside the verbs (debugging / staged migration).
EXPOSE_FLAT_TOOLS = False


def _unreachable_error(port, exc) -> dict:
    return {"error": (
        f"Cannot reach Blender extension on {ADDON_HOST}:{port} ({type(exc).__name__}). "
        "The instance may have closed — run `connect op=list` to see what's live, "
        "or `connect op=launch` to open one."
    )}


def _send_recv(port: int, payload: str, timeout: float):
    """Connect, send, and read one newline-framed reply. Splits CONNECT from SEND so the
    caller can tell 'never sent' (safe to retry) from 'sent, awaiting reply' (must not be
    retried — the op may be running). Raises the connect error before any byte is sent."""
    sock = socket.create_connection((ADDON_HOST, port), timeout=timeout)  # connect phase
    with sock:
        sock.settimeout(timeout)  # cap each recv too, so long renders aren't cut at 30s
        sock.sendall(payload.encode())  # ── from here on the op is in flight ──
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
    return json.loads(data.decode().strip())


def call_blender(tool: str, params: dict = None, label: str = "", timeout: float = 30,
                 port: int = None) -> dict:
    # Resolve which instance to drive (auto-attach / ask-which / open-one) unless the
    # caller pinned a port explicitly. A resolution error short-circuits the call.
    explicit_port = port is not None
    if not explicit_port:
        with _resolve_lock:
            port, err = _resolve_target()
        if err:
            return err
    payload = json.dumps({"tool": tool, "params": params or {}, "label": label,
                          "timeout": timeout}) + "\n"
    try:
        return _send_recv(port, payload, timeout)
    except ConnectionRefusedError as e:
        # The connection was REFUSED — nothing was sent, so this is safe to retry. G139:
        # an auto-resolved attachment may simply be stale (the instance closed, or a fresh
        # one took a different port). Drop it, re-resolve, and retry the connect ONCE; a
        # genuinely dead-and-not-replaced instance then returns the actionable error. A
        # caller-pinned port is never silently re-routed.
        if explicit_port:
            return _unreachable_error(port, e)
        with _resolve_lock:
            set_attached(None)
            port, err = _resolve_target()
        if err:
            return err
        try:
            return _send_recv(port, payload, timeout)
        except (ConnectionRefusedError, socket.timeout, OSError) as e2:
            return _unreachable_error(port, e2)
    except (socket.timeout, OSError) as e:
        # Connected (or mid-stream) then timed out / dropped. The op may already be
        # running on Blender's main thread, so we DON'T retry (that would stack a second
        # op). The extension itself returns an honest in-band timeout JSON when an op
        # overruns its own ceiling; this path is the transport giving up first.
        return _unreachable_error(port, e)


def _status(result: dict) -> str:
    """Format the blender_status block that every tool response now carries."""
    # A bind-invalidation warning (gaps.md V2) is injected generically onto any
    # edit-mode result whose topology change killed a deform bind. The shape-key
    # shadow warning (gaps.md Y1) rides the same channel. Surface both ahead of the
    # status block so they're never lost regardless of which edit verb ran.
    bind = "\n" + result["bind_warning"] if result.get("bind_warning") else ""
    if result.get("shape_key_warning"):
        bind += "\n" + result["shape_key_warning"]
    # G56: a mutating geometry op that changed nothing — surfaced ahead of the status
    # block so a no-op can never masquerade as a successful edit.
    if result.get("no_op_warning"):
        bind += "\n⚠ " + result["no_op_warning"]
    # G105/G118/G134: the mirror of the no-op warning — an op that succeeded but degraded
    # the geometry (new hole, non-manifold junk, broken Euler), caught at the op itself.
    if result.get("topology_delta_warning"):
        bind += "\n⚠ " + result["topology_delta_warning"]
    # Generalized postcondition-notes channel (SPEC-05 Improvement #4): any handler
    # can attach a `notes` list — e.g. an auto mode-switch the agent should know
    # happened. Surfaced ahead of the block like the bind/shape-key warnings.
    for note in (result.get("notes") or []):
        bind += "\n⚠ " + note
    # SPEC-21 §6.3 (G220): the selection narration — every mutating select answers
    # with what got grabbed (count, patches, extent, position, island identity),
    # so the verify read is free instead of a paid extra call.
    if result.get("selection_report"):
        bind += "\n" + result["selection_report"]
    # SPEC-16: the two forced senses, surfaced ahead of the status block so they're
    # never lost. `feel` (what you just changed — perception, no verdict) then
    # `validate` (what's broken — the always-on correctness floor, report-by-exception).
    # A disabled floor announces its own absence on EVERY block (validate_off), so
    # silence-because-off can never read as silence-because-clean.
    if result.get("feel_delta"):
        bind += "\n" + result["feel_delta"]
    v = result.get("validate")
    if isinstance(v, dict) and v.get("line"):
        mark = "" if v.get("passed") else "⚠ "
        bind += "\n" + mark + v["line"]
    elif result.get("validate_off"):
        bind += "\n⚠ validate: OFF (human override) — floor is down"
    # SPEC-16 P1.6: a periodic re-ground recap — you've changed enough that a stale
    # mental model is a liability; re-read geometry you haven't touched recently.
    rg = result.get("reground")
    if isinstance(rg, dict):
        lines = ["", "── re-ground (significant changes since the last checkpoint) ──",
                 f"  scene: {rg.get('object_count')} mesh object(s): {rg.get('objects')}"]
        if rg.get("declared_clips_holding"):
            lines.append(f"  intended clips holding: {', '.join(rg['declared_clips_holding'])}")
        if rg.get("declared_clips_vanished"):
            lines.append(f"  ⚠ intended clips VANISHED: {', '.join(rg['declared_clips_vanished'])}")
        lines.append("  re-read anything you haven't felt in a while before building on it.")
        bind += "\n" + "\n".join(lines)
    s = result.get("blender_status")
    if not s:
        return bind
    wb = s.get("world_bounds") or {}
    lines = [
        "",
        "── blender status ──────────────────────────────",
        f"  mode:        {s['mode']}",
    ]
    # G76: when the op acted on a name-addressed object that isn't the viewport-active
    # one, the bounds below describe acted_on — label it, and show the lagging active.
    if s.get("acted_on"):
        lines.append(f"  acted_on:    {s['active_object']} ({s['active_type']})  "
                     f"⟵ bounds below are THIS object")
        lines.append(f"  vp_active:   {s.get('viewport_active')}  "
                     f"(viewport-active lags; not the acted-on object)")
    else:
        lines.append(f"  active:      {s['active_object']} ({s['active_type']})")
    basis = s.get("dims_basis")
    if basis == "evaluated":
        dims_note = "(evaluated world bbox)"
    elif basis == "cage":
        dims_note = "(cage world bbox)"
    else:
        dims_note = "(world bbox, rotation-aware)"
    lines.append(f"  selected:    {s['selected_objects']}")
    if basis or s.get("modifiers"):
        parts = []
        for m in s.get("modifiers") or []:
            off = "" if m.get("show_viewport", True) else " (viewport-off)"
            parts.append(f"{m.get('type')} '{m.get('name')}'{off}")
        if basis == "evaluated":
            head = "evaluated"
        elif parts:
            head = "cage"
        else:
            head = "cage (= evaluated)"
        stack = " · ".join(parts)
        lines.append(f"  mesh:        {head}" + (f" · {stack}" if stack else ""))
    lines += [
        f"  dims:        {s.get('dimensions')}     {dims_note}",
        f"  bounds:      x={wb.get('x')}  y={wb.get('y')}  z={wb.get('z')}",
        f"  rot_deg:     {s.get('rotation_deg')}",
        f"  last_action: {s.get('last_action')}",
    ]
    if s.get("selection_line"):
        lines.append(f"  {s['selection_line']}")
    r = s.get("render")
    if r:
        rt = f"  raytracing={r['raytracing']}" if "raytracing" in r else ""
        eng = r['engine'] + ("  ⚠ NOT AVAILABLE in this build" if r.get("engine_unavailable") else "")
        lines.append(
            f"  render:      {eng}  view={r['view_transform']} "
            f"look={r['look']} exp={r['exposure']} gamma={r['gamma']}{rt}"
        )
    if s.get("viewport"):
        lines.append(f"  viewport:    {s['viewport']}  (user's live shading mode)")
    dof = s.get("dof")
    if dof:
        if dof.get("missing_target"):
            lines.append(
                f"  dof:         {dof['camera']} focused on {dof.get('focus_target')} "
                f"at {dof['focus_distance']} m — STALE, that object is gone"
            )
        elif dof.get("stale"):
            lines.append(
                f"  dof:         {dof['camera']} focused on {dof['focus_target']} "
                f"at {dof['focus_distance']} m — STALE, that object is at "
                f"{dof['current_m']} m along the lens now. "
                f"view op=rig recomputes it; "
                f"view op=camera_dof focus_object={dof['focus_target']} refreshes it"
            )
        elif dof.get("focus_target"):
            lines.append(
                f"  dof:         {dof['camera']} focused on {dof['focus_target']} "
                f"at {dof['focus_distance']} m at this camera; not tracking"
            )
        else:
            lines.append(
                f"  dof:         {dof['camera']} focus_distance={dof['focus_distance']} m "
                f"(no focus target)"
            )
    if "edit" in s:
        e = s["edit"]
        lines += [
            f"  ── edit ──",
            f"  component:   {e['component_mode']}",
            f"  selected:    {e['selected']}  /  total: {e['total']}",
            f"  sel_z:       {e.get('selection_z_range', '—')}",
        ]
        # G44: full spatial readout of the live selection, when one exists.
        sb = e.get("selection_bounds")
        if sb:
            lines += [
                f"  sel_bounds:  x={sb.get('x')}  y={sb.get('y')}  z={sb.get('z')}",
                f"  sel_center:  {e.get('selection_centroid')}",
                f"  lr_balance:  {e.get('lr_balance_cm')}cm from X-center "
                f"(~0 = centered on the mirror plane)",
            ]
        ak = e.get("active_key")
        if ak:
            tag = " (Basis — edits show)" if ak.get("is_basis") else \
                  "  ⚠ NON-BASIS — edit-mode moves write HERE, not the rest mesh"
            lines.append(f"  active_key:  '{ak['name']}' value={ak['value']}{tag}")
    lines.append("────────────────────────────────────────────────")
    return bind + "\n".join(lines)


def fmt_provenance(result: dict) -> str:
    """Trailing provenance line for a spatial read — which mesh the number was measured on
    (+ any live modifiers). Appended by every measure/relate formatter so a returned
    distance / gap / clearance / contact is never silent about its underlying geometry."""
    p = result.get("provenance")
    return f"\n  ↳ measured on {p}" if p else ""


def fmt_modifiers(mods: list) -> str:
    """One-line modifier-stack summary for a feel read (type 'name', in stack order) —
    the at-a-glance WHY behind a cage/evaluated divergence on an unfamiliar object."""
    if not mods:
        return ""
    parts = []
    for m in mods:
        off = "" if m.get("show_viewport", True) else " (viewport-off)"
        parts.append(f"{m['type']} '{m['name']}'{off}")
    return "modifiers: " + " · ".join(parts)


def render_dual(result: dict, core_fmt) -> str:
    """Render a feel read that carries a cage block and (when a modifier changes the
    geometry) an evaluated block. `core_fmt(core)` formats one block's body. The
    EVALUATED mesh — what actually renders — leads; the CAGE follows. With no
    geometry-changing modifier the two are identical, so a single block is shown.
    The modifier stack is always surfaced when present, even with one block."""
    cage = result.get("cage", {})
    ev = result.get("evaluated")
    modline = fmt_modifiers(result.get("modifiers") or [])
    # G207: a composite read over an assembly — name the union up front so the map is
    # never mistaken for one object's outline.
    comp = ""
    if result.get("composite"):
        comp = (f"◆ COMPOSITE — union of {result.get('n_objects')} objects: "
                f"{result.get('object')}\n")
    if ev is None:
        body = core_fmt(cage)
        if modline:                       # modifiers present but don't alter geometry
            body = modline + "  [cage = evaluated]\n" + body
        return comp + body + _status(result)
    lines = []
    if modline:
        lines.append(modline)
    lines.append("━━ EVALUATED — what renders, modifiers applied ━━")
    lines.append(core_fmt(ev))
    lines.append("━━ CAGE — the editable base mesh, pre-modifier ━━")
    lines.append(core_fmt(cage))
    return "\n".join(lines) + _status(result)


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

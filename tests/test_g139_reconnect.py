"""Unit test for G139 — the MCP-side transport's reconnect/trust policy.

Pure Python (no Blender): run with the project venv,
    .venv/bin/python tests/test_g139_reconnect.py

Verifies:
  • a live attachment is TRUSTED without a liveness re-ping (a busy instance that
    can't answer a probe must not be mistaken for a dead one);
  • a REFUSED connect (nothing sent) is safely retried once after re-resolving;
  • a timeout AFTER sending is NOT retried (the op may be running — no double-fire).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import socket
from server import _core

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FAIL '} {label}" + ("" if cond else f"   {detail}"))
    if not cond:
        failures.append(label)


# ── 1. attached port is trusted without pinging ──────────────────────────────
_core.set_attached(8770)
_core._ping = lambda *a, **k: (_ for _ in ()).throw(AssertionError("ping must not be called"))
try:
    port, err = _core._resolve_target()
    check("attached port resolves without a liveness ping", port == 8770 and err is None, f"{port},{err}")
except AssertionError as e:
    check("attached port resolves without a liveness ping", False, str(e))

# ── 2. a refused connect retries once after re-resolving, then succeeds ───────
_core.set_attached(8770)
calls = {"n": 0}


def fake_send_refuse_then_ok(port, payload, timeout):
    calls["n"] += 1
    if calls["n"] == 1:
        raise ConnectionRefusedError("refused")
    return {"success": True, "port_used": port}


_core._send_recv = fake_send_refuse_then_ok
_core.discover_instances = lambda *a, **k: [{"port": 8771}]
res = _core.call_blender("ping_tool")
check("refused connect triggers exactly one retry", calls["n"] == 2, f"calls={calls['n']}")
check("retry re-resolves to the live instance and succeeds",
      res.get("success") and res.get("port_used") == 8771, str(res))
check("stale attachment was cleared and replaced", _core.attached_port() == 8771,
      str(_core.attached_port()))

# ── 3. a refused connect with NO live instance returns the actionable error ───
_core.set_attached(8770)
calls["n"] = 0
_core._send_recv = lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError("refused"))
_core.discover_instances = lambda *a, **k: []
res = _core.call_blender("ping_tool")
check("no live instance after refusal → 'No Blender instance is reachable'",
      "No Blender instance is reachable" in res.get("error", ""), str(res))

# ── 4. a timeout AFTER sending is NOT retried (op may be running) ─────────────
_core.set_attached(8772)
calls["n"] = 0


def fake_send_timeout(port, payload, timeout):
    calls["n"] += 1
    raise socket.timeout("recv timed out")


_core._send_recv = fake_send_timeout
res = _core.call_blender("heavy_tool")
check("a post-send timeout is NOT retried (no double-fire)", calls["n"] == 1, f"calls={calls['n']}")
check("post-send timeout returns the unreachable error", "Cannot reach" in res.get("error", ""), str(res))


print(f"\n{'PASSED' if not failures else 'FAILED'} — {len(failures)} failure(s)")
for f in failures:
    print(f"   ✗ {f}")
sys.exit(1 if failures else 0)

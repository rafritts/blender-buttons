"""Backing logic for the `connect` verb — discover, attach to, and launch Blender
instances so several Claude sessions can each drive their own Blender.

The wire/attachment primitives live in `_core` (discover_instances / _ping /
attached_port / set_attached); this module is the human-facing layer that formats
listings and resolves a selector (port / label / file) to one instance.
"""

import os
import shutil
import subprocess
import time

from server import _core

# SPEC-20 R4 — the Blender version this server was BUILT/VERIFIED against. The native
# surface (which verbs are native, the cousin tags, the 5.x primer) was derived from this
# build's release notes + manual. If an attached instance's (major, minor) diverges — a
# future 6.x on this 5.x-era server — the provenance claims may be stale, so `connect`
# raises a tripwire the instant you attach. Bump this (and re-derive the primer) on upgrade.
SERVER_VERIFIED_BLENDER = "5.2"


def _ver_pair(version_str: str):
    """('5','1','2') -> (5, 1); tolerant of junk so a weird string never crashes connect."""
    try:
        parts = str(version_str).split(".")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return None


def _drift_note(version_str: str) -> str:
    """A one-line tripwire when the attached Blender's (major,minor) differs from the
    version this server was verified against. Empty string when they match / unknown."""
    if not version_str:
        return ""
    got, want = _ver_pair(version_str), _ver_pair(SERVER_VERIFIED_BLENDER)
    if got is None or want is None or got == want:
        return ""
    direction = ("NEWER than" if got > want else "OLDER than")
    return (f"\n⚠ version drift: attached Blender {version_str} is {direction} the "
            f"{SERVER_VERIFIED_BLENDER} this server was verified against — its provenance/"
            f"native claims may be out of date. Verify 'is this native?' against the build, "
            f"and treat the 5.x primer as possibly stale.")


def _name(i: dict) -> str:
    return i.get("label") or i.get("blend_file") or "(unsaved)"


def _line(i: dict, attached: int) -> str:
    mark = "   ← attached" if i["port"] == attached else ""
    ver = i.get("blender_version", "?")
    return (f"  • port {i['port']}: {_name(i)}  [Blender {ver}, "
            f"{i.get('mesh_count', '?')} meshes, "
            f"mode {i.get('mode', '?')}, pid {i.get('pid', '?')}]{mark}")


def _fmt(live: list, attached: int) -> str:
    if not live:
        return ("No Blender instances are reachable. Open Blender (the extension "
                "auto-starts its server), or `connect op=launch` to open one.")
    lines = [f"Live Blender instances (server verified against Blender {SERVER_VERIFIED_BLENDER}):"]
    lines += [_line(i, attached) for i in live]
    if attached is None:
        lines.append("(none attached — `connect op=attach port=<N>` to bind one; a "
                      "lone instance auto-attaches on the next command)")
    # Tripwire on the attached instance (or any instance, if none attached yet).
    for i in live:
        if attached is None or i["port"] == attached:
            note = _drift_note(i.get("blender_version", ""))
            if note:
                lines.append(note.lstrip("\n"))
            if attached is not None:
                break
    return "\n".join(lines)


def list_instances() -> str:
    return _fmt(_core.discover_instances(), _core.attached_port())


def current() -> str:
    a = _core.attached_port()
    if a is None:
        return ("Not attached to any Blender instance. `connect op=list` to see "
                "what's running.")
    info = _core._ping(a)
    if info is None:
        _core.set_attached(None)
        return f"Was attached to port {a}, but it's no longer reachable — detached."
    ver = info.get("blender_version", "?")
    return (f"Attached to port {a}: {_name(info)} [Blender {ver}, "
            f"{info.get('mesh_count', '?')} meshes]. "
            f"Server verified against Blender {SERVER_VERIFIED_BLENDER}."
            + _drift_note(ver))


def _pick(matches: list, field: str, val: str):
    """One match → (instance, None); zero/many → (None, error_str)."""
    if not matches:
        return None, f"No live instance matching {field}='{val}'. `connect op=list`."
    if len(matches) > 1:
        ports = ", ".join(str(m["port"]) for m in matches)
        return None, (f"{field}='{val}' matches multiple instances (ports {ports}) — "
                      "disambiguate with port=.")
    return matches[0], None


def attach(port=None, label="", file="") -> str:
    live = _core.discover_instances()
    if not live:
        return "No instances to attach to. Open Blender, or `connect op=launch`."
    if port:
        chosen = next((i for i in live if i["port"] == int(port)), None)
        if chosen is None:
            return f"No live instance on port {port}. `connect op=list` to see live ones."
    elif label:
        chosen, err = _pick(
            [i for i in live if label.lower() in (i.get("label") or "").lower()],
            "label", label)
        if err:
            return err
    elif file:
        chosen, err = _pick(
            [i for i in live if file.lower() in (i.get("blend_file") or "").lower()],
            "file", file)
        if err:
            return err
    elif len(live) == 1:
        chosen = live[0]
    else:
        return ("Several instances are live — say which: `connect op=attach "
                "port=<N>`.\n" + _fmt(live, _core.attached_port()))
    _core.set_attached(chosen["port"])
    ver = chosen.get("blender_version", "?")
    return (f"Attached to port {chosen['port']}: {_name(chosen)} [Blender {ver}]."
            + _drift_note(ver))


def detach() -> str:
    _core.set_attached(None)
    return ("Detached. The next command auto-attaches if exactly one instance is "
            "live, or asks you to pick if several are.")


def launch(file="", blender="") -> str:
    exe = blender or os.environ.get("BLENDER_BUTTONS_BLENDER") or shutil.which("blender")
    if not exe:
        already = _core.discover_instances()
        if already:
            return ("Can't find the Blender executable to launch a NEW one — but "
                    f"{len(already)} instance(s) are already live. You probably don't "
                    "need to launch: `connect op=list` to see them, then "
                    "`connect op=attach port=<N>`.\n" + _fmt(already, _core.attached_port()))
        return ("Can't find the Blender executable. If an instance is already running, "
                "`connect op=list` to find and attach it instead. Otherwise set "
                "BLENDER_BUTTONS_BLENDER=/path/to/blender or put `blender` on PATH, then retry.")
    before = {i["pid"] for i in _core.discover_instances()}
    args = [exe]
    if file:
        args.append(file)
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        return f"Failed to launch Blender: {e}"
    # Blender boots and the extension auto-starts its server on a fresh port. Identify
    # the new instance by pid (== Blender's pid == what `ping` reports); fall back to
    # "the one new instance that appeared" if the pid doesn't line up (wrapper scripts).
    deadline = 40.0
    waited = 0.0
    while waited < deadline:
        new = [i for i in _core.discover_instances() if i["pid"] not in before]
        match = next((i for i in new if i.get("pid") == proc.pid), None) \
            or (new[0] if len(new) == 1 else None)
        if match:
            _core.set_attached(match["port"])
            return (f"Launched Blender (pid {proc.pid}) and attached to port "
                    f"{match['port']}: {_name(match)}.")
        if proc.poll() is not None:
            return (f"Blender exited during startup (code {proc.returncode}). "
                    "Check the executable and the .blend path.")
        time.sleep(1.0)
        waited += 1.0
    return (f"Launched Blender (pid {proc.pid}) but it didn't register within "
            f"{int(deadline)}s — it may still be loading, or the extension isn't "
            "enabled / auto-start is off. Try `connect op=list` shortly.")

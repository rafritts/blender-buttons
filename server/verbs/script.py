"""script — SPEC-23 transport for known, countable repetition.

NOT the default modeling loop (that's one verb at a time). Use for the same
primitive N times, N already known (speaker holes, frets, a bolt ring).
Hard step cap 25. Exec is the usual form (a short loop); batch is a short
enumerated list. See docs/SPEC-23-script-runner.md.
"""

from typing import Literal

from server._core import mcp, call_blender
from ._common import tag, unknown

_OPS = ["batch", "exec", "dry_run"]


def _fmt_bounds(bounds):
    if not isinstance(bounds, dict):
        return ""
    parts = []
    for ax in ("x", "y", "z"):
        r = bounds.get(ax)
        if r and len(r) == 2:
            parts.append(f"{ax}=[{r[0]}, {r[1]}]")
    return " ".join(parts)


def _fmt_dims(dims):
    if not dims or len(dims) < 3:
        return "—"
    return f"[{dims[0]:.3f}, {dims[1]:.3f}, {dims[2]:.3f}]"


def format_receipt(r: dict) -> str:
    """Pretty-print a script receipt: first failure leads; no status-block wall."""
    if not isinstance(r, dict):
        return str(r)

    if r.get("error") and r.get("result") is None and "journal" not in r:
        return f"script error: {r['error']}"

    label = r.get("label") or "?"
    mode = r.get("mode") or ("dry_run" if r.get("dry_run") else "?")
    result = r.get("result") or ("ok" if r.get("success") else "aborted")
    steps = r.get("steps") or {}
    if isinstance(steps, int):
        step_line = f"steps:     {steps}"
    else:
        step_line = (
            f"steps:     {steps.get('total', 0)}  "
            f"(ok={steps.get('ok', 0)}  warn={steps.get('warn', 0)}  "
            f"fail={steps.get('fail', 0)})"
        )

    lines = [
        f"── script receipt · {label} · {mode} ─────",
        f"  result:    {result}",
        f"  {step_line}",
    ]

    if r.get("dry_run"):
        if r.get("resolved") is not None:
            lines.append(f"  resolved:  {len(r['resolved'])} step(s)")
        if r.get("note"):
            lines.append(f"  note:      {r['note']}")
        if r.get("error"):
            lines.append(f"  error:     {r['error']}")
        if r.get("errors"):
            for e in r["errors"][:5]:
                lines.append(f"  · step {e.get('i')}: {e.get('error')}")
        lines.append(f"  cap:       {r.get('cap', 25)}")
        lines.append("──────────────────────────────────────────────")
        return "\n".join(lines)

    created = r.get("created") or []
    touched = r.get("touched") or []
    deleted = r.get("deleted") or []
    lines.append(f"  created:   {', '.join(created) if created else '—'}")
    lines.append(f"  touched:   {', '.join(touched) if touched else '—'}")
    if deleted:
        lines.append(f"  deleted:   {', '.join(deleted)}")
    lines.append(f"  via_bpy:   {'yes' if r.get('via_bpy') else 'no'}")
    lines.append(f"  on_error:  {r.get('on_error', 'abort')}")
    if r.get("duration") is not None:
        lines.append(f"  duration:  {r['duration']}s")
    if r.get("error") and result != "ok":
        lines.append(f"  error:     {r['error']}")

    # ── first failure (lead with diagnosis) ──
    ff = r.get("first_failure")
    if ff:
        lines.append("")
        lines.append("  ── first failure ──")
        lines.append(
            f"  step {ff.get('i')}  {ff.get('verb_op') or ff.get('tool') or '?'}  "
            f"focus={ff.get('focus') or '—'}"
        )
        lines.append(f"  {ff.get('error') or ff.get('message') or 'fail'}")
        if ff.get("dims"):
            lines.append(f"  dims: {_fmt_dims(ff['dims'])}")
        if ff.get("bounds"):
            lines.append(f"  bounds: {_fmt_bounds(ff['bounds'])}")

    # ── journal ──
    journal = r.get("journal") or []
    if journal:
        lines.append("")
        lines.append("  ── journal ──")
        lines.append("  #   verb/op             focus         flag  dims")
        for entry in journal:
            i = entry.get("i", "?")
            vo = (entry.get("verb_op") or entry.get("tool") or "?")[:18]
            focus = (entry.get("focus") or "—")[:12]
            flag = entry.get("flag") or "?"
            dim_s = _fmt_dims(entry.get("dims"))
            if dim_s == "—" and entry.get("bounds"):
                b = entry["bounds"]
                if b.get("z"):
                    dim_s = f"z=[{b['z'][0]}, {b['z'][1]}]"
            note_parts = []
            pl = entry.get("placement")
            if isinstance(pl, dict):
                for k in ("on", "under", "left_of", "right_of", "on_floor", "gap"):
                    if k in pl:
                        note_parts.append(f"{k}={pl[k]}")
            if entry.get("absolute_placement"):
                note_parts.append("abs")
            if flag in ("fail", "warn") and entry.get("findings"):
                msg = entry["findings"][0].get("message", "")
                if msg:
                    note_parts.append(str(msg)[:50])
            elif entry.get("note"):
                note_parts.append(str(entry["note"])[:50])
            note = ("  " + " ".join(note_parts)) if note_parts else ""
            lines.append(f"  {i:>2}  {vo:<18}  {focus:<12}  {flag:<4}  {dim_s}{note}")

    # ── findings rollup ──
    counts = r.get("findings_counts") or {}
    findings = r.get("findings") or []
    lines.append("")
    lines.append("  ── findings (rolled up) ──")
    if not findings and not counts:
        lines.append("  (none)")
    else:
        if counts:
            parts = [f"{k}×{n}" for k, n in sorted(counts.items())]
            lines.append("  " + " · ".join(parts))
        # small sample
        for f in findings[:5]:
            lines.append(f"  · {f.get('kind', '?')}: {f.get('message', f)}")
        if len(findings) > 5:
            lines.append(f"  … +{len(findings) - 5} more (see structured receipt)")

    # ── final validate ──
    fv = r.get("final_validate")
    lines.append("")
    lines.append(f"  ── final validate · scope={r.get('validate') or 'touched'} ──")
    if isinstance(fv, dict):
        if fv.get("off"):
            lines.append("  validate: OFF (human override) — floor is down")
        else:
            mark = "" if fv.get("passed") else "⚠ "
            lines.append(f"  {mark}{fv.get('line') or ('clean' if fv.get('passed') else 'dirty')}")
    else:
        lines.append("  validate: —")

    # ── final focus ──
    fs = r.get("final_status")
    lines.append("")
    lines.append("  ── final focus ──")
    if isinstance(fs, dict):
        name = fs.get("active_object") or fs.get("acted_on") or "—"
        dims = fs.get("dimensions")
        wb = fs.get("world_bounds") or {}
        lines.append(f"  focus:     {name}  mode={fs.get('mode', '?')}")
        if dims:
            lines.append(f"  dims:      {_fmt_dims(dims)}")
        if wb:
            lines.append(f"  bounds:    {_fmt_bounds(wb)}")
    else:
        lines.append("  (none)")

    # ── undo ──
    undo = r.get("undo") or {}
    if undo:
        lines.append("")
        lines.append(
            f"  undo:      {undo.get('unit', '?')}  "
            f"policy={undo.get('policy', '?')}  steps={undo.get('steps', '?')}"
        )
        rest = undo.get("restore")
        if isinstance(rest, dict):
            lines.append(
                f"  restored:  {rest.get('restored')}  "
                f"(undid {rest.get('steps', 0)} step(s))"
            )

    if r.get("checkpoints"):
        lines.append("")
        lines.append(f"  checkpoints: {len(r['checkpoints'])}")
        for cp in r["checkpoints"]:
            lines.append(f"  · {cp.get('label')} focus={cp.get('focus')}")

    lines.append(f"  cap:       {r.get('cap', 25)}")
    lines.append("──────────────────────────────────────────────")
    return "\n".join(lines)


@mcp.tool(name="script")
def script(
    op: Literal["batch", "exec", "dry_run"] = "batch",
    steps: tag(list, "[batch/dry_run] ordered list of {verb, op?, params} or {tool, params}") = None,
    code: tag(str, "[exec/dry_run] inline Python with buttons DSL in scope") = "",
    path: tag(str, "[exec/dry_run] absolute path to a .py file (alt to code=)") = "",
    on_error: tag(str, "[batch/exec] abort (default) | continue (diagnostic only)") = "abort",
    validate: tag(str, "[batch/exec] final validate scope: touched (default) | scene") = "touched",
    verbose: tag(bool, "[batch/exec] include per-step raw status in structured journal") = False,
    label: tag(str, "short name for the run (receipt + undo unit script:<label>)") = "",
    strict: tag(bool, "[batch/exec] undeclared clipping aborts (recipe CI)") = False,
    mode: tag(str, "[dry_run] batch (default) | exec") = "batch",
) -> str:
    """
    SPEC-23 script runner — known, countable repetition with one validation **receipt**.

    NOT the default way to drive the server. Default is one verb at a time
    (look → claim → modify). Use script only when the work is highly repetitive,
    already known, and obviously quantifiable — the same primitive N times, N and
    the pattern already in hand (speaker holes, frets, a bolt ring). If the next
    step still needs a look, a taste call, or a different judgment, stay in the REPL.

    Hard step cap **25**. Read the receipt between phases. Do not megascript a scene.

    op selects:
      batch   — short enumerated list of the same (or near-same) step, no Python.
                steps=[{verb:"add", params:{type:"cylinder", name:"hole_1", …}}, …]
                or {tool:"add_cylinder", params:{…}} for full surface.
      exec    — short Python loop/branch over that repetition (the usual case).
                Still one phase, not a megascript.
      dry_run — resolve/bind/budget only; no mutation.

    Receipt always has: result, created/touched, journal (dims/bounds on create/place),
    first failure (if any), final validate, final focus. Undo on abort is transactional
    (restores pre-script scene).
    """
    o = (op or "batch").lower().strip()
    timeout = 120.0  # multi-step; allow longer than single-op default

    if o == "batch":
        r = call_blender("script_batch", {
            "steps": steps or [],
            "on_error": on_error,
            "validate": validate,
            "verbose": verbose,
            "label": label or "batch",
            "strict": strict,
        }, timeout=timeout)
        return format_receipt(r)

    if o == "exec":
        r = call_blender("script_exec", {
            "code": code or "",
            "path": path or "",
            "on_error": on_error,
            "validate": validate,
            "verbose": verbose,
            "label": label or "exec",
            "strict": strict,
        }, timeout=timeout)
        return format_receipt(r)

    if o == "dry_run":
        m = (mode or "batch").lower().strip()
        payload = {
            "mode": m,
            "label": label or "dry_run",
        }
        if m == "exec":
            payload["code"] = code or ""
            payload["path"] = path or ""
        else:
            payload["steps"] = steps or []
        r = call_blender("script_dry_run", payload, timeout=timeout)
        return format_receipt(r)

    return unknown("script", "op", op, _OPS)

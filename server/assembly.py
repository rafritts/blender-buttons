"""Assembly + map (server side) — SPEC-07 Phase 4 renderers for `feel op=assembly`
and `feel op=map`.

These forward to the extension's `assembly` module and render its relational map /
raycast result as compact text. Both are perception ops (no status block); assembly
mints Class-A boundary handles as a side effect and the render names them so they're
immediately addressable (`transform move_to handle=Cube.top`, `edit op=bridge …`).
"""

from server._core import call_blender


def _pt(p):
    return f"[{p[0]}, {p[1]}, {p[2]}]" if p else ""


def feel_assembly(targets: str = "", group: str = "") -> str:
    """Read a set of objects at once: bounds + boundary catalog + pairwise gaps,
    auto-minting every open boundary as a named Class-A handle."""
    result = call_blender("feel_assembly", {"targets": targets, "group": group})
    if not result.get("success"):
        return result.get("error", "failed")

    objs = result["objects"]
    minted = sum(1 for o in objs for b in o.get("boundaries", []) if not b["reused"])
    lines = [f"assembly — {len(objs)} object(s), {minted} new handle(s) minted:"]
    for o in objs:
        if o.get("skipped"):
            lines.append(f"  {o['name']:<18} — skipped ({o['skipped']})")
            continue
        s = o["size_m"]
        lines.append(f"  {o['name']:<18} {s[0]} × {s[1]} × {s[2]} m")
        if not o["boundaries"]:
            lines.append("      (closed — no open boundaries)")
        for b in o["boundaries"]:
            mark = "↻ exists" if b["reused"] else "✚ minted"
            lines.append(
                f"      ↳ {b['handle']:<22} {mark}  {b['verts']:>3} verts  "
                f"{b['circ_cm']:>6}cm  {_pt(b['point'])}"
            )
    pairs = result.get("pairs", [])
    if pairs:
        lines.append("  relations:")
        for p in pairs:
            t = ("touching " + "".join(p["touching"])) if p["touching"] else f"gap {p['gap'] * 100:.1f}cm"
            lines.append(f"      {p['a']} ↔ {p['b']:<14} {t}")
    # G9 follow-up: the minted boundary handles are now addressable — point at the ops
    # that consume them, so the read isn't a dead end.
    handle_names = [b["handle"] for o in objs for b in o.get("boundaries", [])]
    if handle_names:
        lines.append(
            "  → next: `feel op=map handle=" + handle_names[0] + "` (what an opening "
            "looks out onto) · `feel op=relate a=… b=…` (do two openings line up?) · "
            "`edit op=bridge a=… b=…` (weld two) · `transform move_to handle=…`")
    return "\n".join(lines)


def feel_relate(a: str = "", b: str = "") -> str:
    """Relate two named boundary handles (G16): do these two openings line up? Reports
    centre gap, axis alignment (do they face each other?), and size match — the read a
    bridge/weld needs before it tries."""
    result = call_blender("feel_relate", {"a": a, "b": b})
    if not result.get("success"):
        return result.get("error", "failed")
    lines = [f"relate {result['a']} ↔ {result['b']}:"]
    lines.append(f"  centre gap:  {result['center_gap_cm']}cm")
    lines.append(f"  axis:        {result['facing']}  ({result['axis_angle_deg']}° off-parallel)")
    lines.append(f"  size:        ⌀ {result['diam_a_cm']}cm vs {result['diam_b_cm']}cm "
                 f"(match {result['size_match']})")
    verdict = ("✓ join-ready (parallel, facing, similar size) — fit then "
               "`edit op=bridge`" if result["join_ready"]
               else "✗ not aligned for a clean weld yet (check axis / size / gap)")
    lines.append(f"  {verdict}")
    return "\n".join(lines)


def feel_map(handle: str = "", target: str = "", margin: float = 0.0) -> str:
    """Cast a ray from boundary handle(s) and report what each opening looks out onto."""
    result = call_blender("feel_map", {"handle": handle, "target": target, "margin": margin})
    if not result.get("success"):
        return result.get("error", "failed")

    casts = result["casts"]
    lines = [f"map — {len(casts)} cast(s):"]
    for c in casts:
        if c.get("error"):
            lines.append(f"  {c['handle']:<22} ✗ {c['error']}")
        elif c.get("hit"):
            lines.append(
                f"  {c['handle']:<22} → {c['object']} @ {c['distance_cm']}cm "
                f"({c['region']})  {_pt(c['point'])}"
            )
        else:
            lines.append(f"  {c['handle']:<22} ✗ miss (opening looks out onto nothing)")
    # G9 follow-up: a hit means two openings face each other — the bridge candidate.
    if any(c.get("hit") for c in casts):
        lines.append(
            "  → next: `edit op=bridge a=… b=…` to weld two facing openings "
            "(same object — `object op=join` cross-object parts first)")
    return "\n".join(lines)

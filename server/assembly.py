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
    return "\n".join(lines)

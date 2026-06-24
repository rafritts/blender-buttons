"""MCP wrappers for the quality lints (P3/P5/P6/P12).

These return compiler-style verdicts the agent can act on without a render — the
whole point is to answer "is it sound / framed / game-ready?" deterministically
instead of burning Cycles renders and image tokens on a question with an exact
geometric answer.
"""

from server._core import mcp, call_blender, _status, _targets


@mcp.tool()
def find_coplanar_overlaps(targets: str = "", epsilon: float = 0.0001) -> str:
    """
    Find faces from DIFFERENT objects that are coplanar AND overlapping — the
    invisible-until-render z-fight (e.g. a solid cap sitting exactly on a dial's
    top face shows up as mottling only in a render). Lint the scene before you
    render instead of diagnosing it with three test renders.

    targets: optional object/group list to restrict to. Empty = whole scene.
    epsilon: coplanar/overlap tolerance in meters (default 0.1mm).
    """
    result = call_blender("find_coplanar_overlaps",
                          {"targets": _targets(targets), "epsilon": epsilon})
    if not result.get("success"):
        return result.get("error", "failed")
    overlaps = result["overlaps"]
    if not overlaps:
        return f"PASS — no coplanar overlaps among {len(result['checked'])} object(s)" + _status(result)
    lines = [f"{len(overlaps)} coplanar overlap(s) — z-fight risk:"]
    for o in overlaps:
        lines.append(f"  ⚠ '{o['a']}' ↔ '{o['b']}' at {o['axis']}={o['coord']} "
                     f"(overlap {o['overlap_mm'][0]}×{o['overlap_mm'][1]}mm)")
    return "\n".join(lines) + _status(result)


@mcp.tool()
def validate_scene(targets: str = "", epsilon: float = 0.0001) -> str:
    """
    Pre-render scene lint. Reports cross-object z-fights, likely inverted normals,
    degenerate (zero-area) faces, and objects below the floor plane. Run it before
    a hero render — these all read fine in a fast viewport and wrong in a final image.

    targets: optional object/group list. Empty = whole scene.
    Output: "PASS" or one finding per line.
    """
    result = call_blender("validate_scene",
                          {"targets": _targets(targets), "epsilon": epsilon})
    if not result.get("success"):
        return result.get("error", "failed")
    excl = result.get("excluded_non_mesh") or []
    skip = f"\n  (skipped {len(excl)} non-mesh: {', '.join(excl)})" if excl else ""
    if result["passed"]:
        return f"PASS — {len(result['checked'])} object(s), no issues{skip}" + _status(result)
    lines = [f"{result['count']} finding(s):"]
    for f in result["findings"]:
        lines.append(f"  ⚠ {f['message']}")
    return "\n".join(lines) + skip + _status(result)


@mcp.tool()
def check_mesh(target: str) -> str:
    """
    Single-mesh soundness check for printing, booleans, or game shells: non-manifold
    edges, self-intersections, zero-area faces, and the thinnest wall (the "pinch
    test"). Computed directly from geometry — no add-on needed.

    target: mesh object, group, or comma-separated list.
    """
    result = call_blender("check_mesh", {"target": _targets(target)})
    if not result.get("success"):
        return result.get("error", "failed")
    lines = []
    for r in result["reports"]:
        if r["clean"]:
            tw = f", thinnest wall {r['thinnest_wall_mm']}mm" if r["thinnest_wall_mm"] is not None else ""
            lines.append(f"  ✓ {r['object']}: watertight, no issues{tw}")
            continue
        bits = []
        if r["non_manifold_edges"]:
            bits.append(f"non-manifold ({r['non_manifold_edges']} edges)")
        if r.get("boundary_edges"):
            bits.append(f"open boundary ({r['boundary_edges']} edges — intended for a "
                        f"plane/rim/cloth, a defect for a solid)")
        if r["self_intersections"]:
            bits.append(f"{r['self_intersections']} self-intersection(s)")
        if r["zero_area_faces"]:
            bits.append(f"{r['zero_area_faces']} zero-area face(s)")
        if r["thinnest_wall_mm"] is not None:
            bits.append(f"thinnest wall {r['thinnest_wall_mm']}mm")
        lines.append(f"  ⚠ {r['object']}: " + ", ".join(bits))
    return "\n".join(lines) + _status(result)


@mcp.tool()
def audit_asset(group: str, tri_budget: int = 5000) -> str:
    """
    Game-readiness audit over a group/selection. Per object: missing material slot,
    triangle count (with on-screen coverage % when a camera exists, to flag
    overbuilt parts), unapplied scale/rotation, and loose verts. One report per
    delivery — turns "is this game-ready?" into countable facts.

    group: object, group name, or comma-separated list.
    tri_budget: per-object triangle ceiling to flag (default 5000).
    """
    result = call_blender("audit_asset",
                          {"group": _targets(group), "tri_budget": tri_budget})
    if not result.get("success"):
        return result.get("error", "failed")
    head = (f"audit: {result['object_count']} object(s), {result['total_tris']} tris total"
            f" — {'PASS' if result['passed'] else 'ISSUES'}")
    lines = [head]
    for r in result["reports"]:
        screen = f" @ {r['screen_pct']}% frame" if r["screen_pct"] is not None else ""
        if r["clean"]:
            lines.append(f"  ✓ {r['object']}: {r['tris']} tris{screen}")
        else:
            lines.append(f"  ⚠ {r['object']}: {r['tris']} tris{screen} — " + "; ".join(r["issues"]))
    excl = result.get("excluded_non_mesh") or []
    if excl:
        lines.append(f"  (skipped {len(excl)} non-mesh: {', '.join(excl)})")
    return "\n".join(lines) + _status(result)

"""MCP wrappers for tactile introspection (P4/P7/P9/P10/P11).

Every tool here answers, in scene vocabulary (object names, mm/deg, frame %), a
question the agent's vision can pose but not measure — and that would otherwise
cost a test render or a guess-and-screenshot loop.
"""

from server._core import mcp, call_blender, _status, _targets


@mcp.tool()
def check_contacts(targets: str = "") -> str:
    """
    For each part, its nearest neighbor and how they relate: connected (touching),
    floating (gap in mm), or penetrating (depth in mm). Reports facts without
    judging — interpenetration is correct for chain links and sunk markers.

    One call answers "did that part actually land where I dead-reckoned it?" for
    every part, instead of eyeballing screenshots.

    targets: object/group list to report on. Empty = every mesh in the scene.
    """
    result = call_blender("check_contacts", {"targets": _targets(targets)})
    if not result.get("success"):
        return result.get("error", "failed")
    lines = []
    for c in result["contacts"]:
        if c["relation"] == "alone":
            lines.append(f"  {c['object']}: alone in scene")
        elif c["relation"] == "connected":
            lines.append(f"  {c['object']}: connected to '{c['other']}'")
        elif c["relation"] == "penetrating":
            lines.append(f"  {c['object']}: penetrating '{c['other']}' by {c['depth_mm']}mm")
        else:
            lines.append(f"  {c['object']}: floating — nearest '{c['other']}', gap {c['gap_mm']}mm")
    return "\n".join(lines) + _status(result)


@mcp.tool()
def check_resting(targets: str = "") -> str:
    """
    Gravity sanity per part: what it rests on (floor or another object), how many
    contact points, sink/float height in mm, and whether its center of mass sits
    over the support (else which way it tips). Objects that float or sink 5mm read
    fine in a viewport and wrong in a final render.

    targets: object/group list. Empty = every mesh in the scene.
    """
    result = call_blender("check_resting", {"targets": _targets(targets)})
    if not result.get("success"):
        return result.get("error", "failed")
    lines = []
    for r in result["resting"]:
        bits = [f"on {r['support']}", f"{r['contacts']} contact(s)"]
        if r["state"] == "floating":
            bits.append(f"floats {r['clearance_mm']}mm")
        elif r["state"] == "sunk":
            bits.append(f"sunk {-r['clearance_mm']}mm")
        if not r["com_over_support"]:
            bits.append(f"COM off support — tips toward {r['tip_direction']}")
        lines.append(f"  {r['object']}: " + ", ".join(bits))
    return "\n".join(lines) + _status(result)


@mcp.tool()
def check_framing(targets: str = "", camera: str = "") -> str:
    """
    Camera-space report per target: % of the frame it spans, which edges it clips
    past (and by how much), whether it's behind the camera, and % occluded by other
    objects. The deterministic answer to "is it still cropped / hidden?" — no test
    render, no image tokens.

    targets: object/group list. Empty = every mesh in the scene.
    camera:  camera object name. Empty = the active scene camera.
    """
    params = {"targets": _targets(targets)}
    if camera:
        params["camera"] = camera
    result = call_blender("check_framing", params)
    if not result.get("success"):
        return result.get("error", "failed")
    lines = [f"camera '{result['camera']}':"]
    for f in result["framing"]:
        if f["behind_camera"]:
            lines.append(f"  {f['object']}: BEHIND camera")
            continue
        bits = [f"{f['frame_pct'][0]}%×{f['frame_pct'][1]}% of frame"]
        if f["clipped"]:
            bits.append("clipped " + ", ".join(f"{k} {v}%" for k, v in f["clipped"].items()))
        if f["occluded_pct"] > 1:
            bits.append(f"{f['occluded_pct']}% occluded")
        lines.append(f"  {f['object']}: " + ", ".join(bits))
    return "\n".join(lines) + _status(result)


@mcp.tool()
def trace_profile(target: str, axis: str = "Z", sections: int = 24) -> str:
    """
    Run a fingertip along an axis and narrate the form — the curvature SEQUENCE a
    blind sculptor reads, not a point dump. Reports per-section radius, center
    drift, and detected features: smooth rise/taper, flat runs, sharp creases, and
    bulges (with how far they stand over the trend). Pairs with get_mesh_profile
    (the calipers) by adding per-section verdicts.

    target:   single mesh object.
    axis:     X | Y | Z — the axis to run along (default Z).
    sections: number of cross-sections to sample (6-64, default 24).
    """
    result = call_blender("trace_profile",
                          {"target": _targets(target), "axis": axis, "sections": sections})
    if not result.get("success"):
        return result.get("error", "failed")
    parts = []
    for f in result["features"]:
        if f["kind"] in ("rise", "taper", "flat"):
            parts.append(f"{f['kind']} {f['from_pct']}–{f['to_pct']}%")
        elif f["kind"] == "bulge":
            parts.append(f"bulge apex {f['at_pct']}% (+{f['over_trend_mm']}mm over trend)")
        elif f["kind"] == "crease":
            parts.append(f"{'concave' if f['concave'] else 'convex'} crease at {f['at_pct']}%")
    drift = result["center_drift"]
    head = (f"{result['object']} along {result['axis']}: radius "
            f"{result['radius_range_mm'][0]}–{result['radius_range_mm'][1]}mm, "
            f"center drift {drift['mm']}mm on {drift['axis']}")
    return head + "\n  " + "; ".join(parts) + _status(result)


@mcp.tool()
def diff_since(checkpoint: str = "") -> str:
    """
    Narrate what changed since a history checkpoint: objects added/deleted, and per
    object moved (mm), rotated (deg), scaled, or deformed (max displacement + where
    on the object). Closes the loop on sculpt brushes — after sculpt_crease, ask
    diff_since to feel the change instead of squinting at a screenshot.

    checkpoint: a history op_id (from get_history / a tool's [op_id]). Empty = diff
    against the very first recorded operation.
    """
    params = {}
    if checkpoint:
        params["checkpoint"] = checkpoint
    result = call_blender("diff_since", params)
    if not result.get("success"):
        return result.get("error", "failed")
    lines = [f"since [{result['checkpoint']}]:"]
    if result["added"]:
        lines.append(f"  + added: {result['added']}")
    if result["deleted"]:
        lines.append(f"  - deleted: {result['deleted']}")
    for ch in result["changed"]:
        bits = []
        for c in ch["changes"]:
            if c["kind"] == "moved": bits.append(f"moved {c['mm']}mm")
            elif c["kind"] == "rotated": bits.append(f"rotated {c['deg']}°")
            elif c["kind"] == "scaled": bits.append(f"scaled to {c['to']}")
            elif c["kind"] == "topology": bits.append(f"topology {c['delta_verts']:+d} verts")
            elif c["kind"] == "deformed":
                where = f" on {c['where']}" if c.get("where") else ""
                bits.append(f"deformed {c['mm']}mm{where}")
        lines.append(f"  {ch['object']}: " + ", ".join(bits))
    if not result["added"] and not result["deleted"] and not result["changed"]:
        lines.append("  (no changes)")
    return "\n".join(lines) + _status(result)

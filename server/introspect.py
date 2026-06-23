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
        # The combined one-line read (G32) is the full picture — touch + every
        # penetration, so a deep cross can't hide behind a closer touch.
        summary = c.get("summary")
        if summary:
            lines.append(f"  {c['object']}: {summary}")
        elif c["relation"] == "alone":
            lines.append(f"  {c['object']}: alone in scene")
        elif c["relation"] == "connected":
            lines.append(f"  {c['object']}: connected to '{c['other']}'")
        elif c["relation"] == "penetrating":
            lines.append(f"  {c['object']}: penetrating '{c['other']}' by {c['depth_mm']}mm")
        else:
            lines.append(f"  {c['object']}: floating — nearest '{c['other']}', gap {c['gap_mm']}mm")
    return "\n".join(lines) + _status(result)


@mcp.tool()
def check_clearance(shell: str, surface: str, threshold: float = None, samples: int = 2000) -> str:
    """
    SIGNED nearest-surface clearance — "is my shell everywhere OUTSIDE the surface it
    wraps?". The one cladding read a bbox-overlap contacts number can't give: a garment
    that correctly envelops a torso and one that stabs through the ribs produce the SAME
    alarming overlap figure, because the wrapped body is meant to live inside the shell's
    bounding box. This signs the distance by the surface normal instead.

    Per sampled shell vert: positive ⇒ outside the surface (correct clearance), negative ⇒
    dipping inside it (stabbing through). Reports min/mean clearance, the fraction of the
    shell outside the surface, and the worst penetration patches.

    General: armor over a body, a phone case over a phone, a lid over a jar, a press-fit
    sleeve — anything that must clear what it claddes.

    shell:     the cladding object (garment / case / armor / plating).
    surface:   the surface being wrapped (body / phone / jar).
    threshold: optional min clearance in mm; when set, adds a pass/fail verdict.
    samples:   cap on shell verts sampled (default 2000).
    """
    params = {"shell": shell, "surface": surface, "samples": samples}
    if threshold is not None:
        params["threshold"] = threshold
    result = call_blender("check_clearance", params)
    if not result.get("success"):
        return result.get("error", "failed")
    frac = result["fraction_outside"]
    pen = result["penetrations"]
    minc = result["min_clearance_mm"]
    meanc = result["mean_clearance_mm"]
    head = (f"{result['shell']} vs {result['surface']}: "
            f"{round(frac * 100, 1)}% of the shell clears the surface")
    if minc is not None:
        head += f"; clearance min {minc}mm, mean {meanc}mm"
    lines = [head]
    if pen:
        lines.append(f"  {pen} sampled vert(s) STAB INSIDE the surface — shell is not "
                     f"a clean envelope:")
        for w in result["worst_penetrations"]:
            lines.append(f"    inside by {w['depth_mm']}mm at {w['at']}")
    else:
        lines.append("  no penetrations — shell is everywhere outside the surface")
    if "clears" in result:
        verdict = "PASS" if result["clears"] else "FAIL"
        lines.append(f"  {verdict} — clears by ≥{result['threshold_mm']}mm everywhere"
                     if result["clears"] else
                     f"  {verdict} — does NOT clear by ≥{result['threshold_mm']}mm everywhere")
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
        line = f"  {r['object']}: " + ", ".join(bits)
        if r.get("note"):
            line += f"\n    ↳ {r['note']}"
        lines.append(line)
    return "\n".join(lines) + _status(result)


@mcp.tool()
def check_framing(targets: str = "", camera: str = "", aspect: str = "") -> str:
    """
    Camera-space report per target: % of the frame it spans, which edges it clips
    past (and by how much), whether it's behind the camera, and % occluded by other
    objects. The deterministic answer to "is it still cropped / hidden?" — no test
    render, no image tokens.

    targets: object/group list. Empty = every mesh in the scene.
    camera:  camera object name. Empty = the active scene camera.
    aspect:  'WxH' (e.g. 1000x1400) or 'W:H' ratio — validate framing against an
             INTENDED output frame instead of the scene's current resolution. The
             frame_pct is aspect-relative, so this is what makes readings comparable.
    """
    params = {"targets": _targets(targets)}
    if camera:
        params["camera"] = camera
    if aspect:
        params["aspect"] = aspect
    result = call_blender("check_framing", params)
    if not result.get("success"):
        return result.get("error", "failed")
    ref = result.get("frame_ref", {})
    res = ref.get("resolution")
    ref_str = f" (vs {res[0]}×{res[1]} {ref.get('aspect', '')})" if res else ""
    lines = [f"camera '{result['camera']}'{ref_str}:"]
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
def check_focus(targets: str = "", camera: str = "", aperture: float = None,
                focus_distance: float = None, focus_object: str = "",
                resolve_for: str = "") -> str:
    """
    VALIDATE depth of field (G115) — the deterministic sharpness check the "don't read
    the render back" rule otherwise leaves blind. Reports the near/far in-focus limits at
    the camera's current (or a hypothetical) lens + aperture + focus, and whether each
    target's FULL depth sits inside that slab. Macro-scale sets (a tabletop at f/4) have a
    DOF only millimetres deep — this catches the silent blur before you render.

    targets:        objects to test. Empty = the camera's focus_object, else every mesh.
    camera:         camera name. Empty = the active scene camera.
    aperture:       a hypothetical f-stop to test. Empty = the camera's current f-stop.
    focus_distance / focus_object: a hypothetical focus. Empty = the camera's current focus.
    resolve_for:    object name — also solve the WIDEST aperture (smallest f-number) that
                    keeps this subject fully sharp at the current focus ("keep the whole
                    donut sharp" → an f-stop), instead of dead-reckoning it.
    """
    params = {"targets": _targets(targets)}
    if camera:
        params["camera"] = camera
    if aperture is not None:
        params["aperture"] = aperture
    if focus_distance is not None:
        params["focus_distance"] = focus_distance
    if focus_object:
        params["focus_object"] = focus_object
    if resolve_for:
        params["resolve_for"] = resolve_for
    result = call_blender("check_focus", params)
    if not result.get("success"):
        return result.get("error", "failed")
    far = result["dof_far_m"]
    far_s = "∞" if far is None else f"{far}m"
    slab = result["dof_slab_mm"]
    slab_s = "∞" if slab is None else f"{slab}mm"
    dof_state = "" if result["use_dof"] else "  ⚠ DOF is OFF on this camera (renders fully sharp)"
    lines = [
        f"camera '{result['camera']}': lens {result['lens_mm']}mm  f/{result['aperture_fstop']}  "
        f"focus {result['focus_distance_m']}m"
        + (f" on {result['focus_object']}" if result.get('focus_object') else "") + dof_state,
        f"  in-focus zone: {result['dof_near_m']}m → {far_s}  (slab {slab_s}, "
        f"hyperfocal {result['hyperfocal_m']}m)",
    ]
    for t in result["targets"]:
        verdict = "SHARP" if t["in_focus"] else f"BLURRED ({t['in_focus_pct']}% of its depth in focus)"
        lines.append(f"  {t['object']}: depth {t['depth_mm']}mm at {t['near_m']}–{t['far_m']}m → {verdict}")
    if result.get("resolve_error"):
        lines.append(f"  resolve: {result['resolve_error']}")
    elif "resolved_aperture" in result:
        ra = result["resolved_aperture"]
        lines.append(f"  to keep {result['resolve_for']} fully sharp: "
                     + (f"f/{ra} (or narrower)" if ra is not None
                        else "no aperture up to f/32 holds its whole depth — move it / shrink its depth / refocus"))
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

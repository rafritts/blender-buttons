from server._core import mcp, call_blender, _status, _targets


@mcp.tool()
def match_dimension(target: str, reference: str, axis: str = "Z", label: str = "") -> str:
    """
    Resize `target` so its extent on `axis` equals `reference`'s extent on that axis.
    Bakes scale after resizing.

    Example: match_dimension("slat_3", "slat_1", axis="Z") — make slat 3 the same height as slat 1.
    """
    result = call_blender("match_dimension", {
        "target": target, "reference": reference, "axis": axis,
    }, label=label)
    if result.get("success"):
        return (f"{target}.{axis} → {result['new_size']} m (factor {result['factor_applied']}) "
                f"[{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def mirror_across(targets: str, plane: str = "X", suffix: str = "_mirror",
                  replace: list = None, label: str = "") -> str:
    """
    Duplicate parts and mirror the copies across a world axis plane through origin.
    plane: 'X' mirrors across the YZ plane (flips +X ↔ −X); 'Y' and 'Z' analogous.

    The copies are independent objects (no live constraint). Useful for symmetric construction:
    build the left side, then mirror_across('X') to get the right side.

    targets: single object name, group name, or comma-separated list.
    replace: optional 2-item list — swap a naming token instead of appending suffix.
             ["_R", "_L"] turns 'eye_R' into 'eye_L'. Names without the token
             fall back to suffix appending.
    Examples:
      mirror_across("leg_front_left,leg_back_left", plane="X", suffix="_right")
      mirror_across("eye_R,arm_R,leg_R", plane="X", replace=["_R", "_L"])
    """
    params = {"targets": _targets(targets), "plane": plane, "suffix": suffix}
    if replace is not None:
        params["replace"] = replace
    result = call_blender("mirror_across", params, label=label)
    if result.get("success"):
        return (f"mirrored across {plane}: {result['mirrored_to']} "
                f"[{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def distribute_evenly(targets: str, between: list, axis: str = "X", label: str = "") -> str:
    """
    Position parts so their centers are evenly spaced strictly between two anchor objects' centers.
    Anchor positions themselves are NOT occupied.

    targets: comma-separated object names OR a group name.
    between: ["object_a", "object_b"] — the two anchors.
    axis: X | Y | Z — which axis to distribute along.

    Example: distribute_evenly("slat_1,slat_2,slat_3,slat_4,slat_5",
                              between=["leg_back_left", "leg_back_right"], axis="X")
             → 5 slats evenly spaced between the two back legs along X.
    """
    result = call_blender("distribute_evenly", {
        "targets": _targets(targets), "between": between, "axis": axis,
    }, label=label)
    if result.get("success"):
        names = [p["name"] for p in result["placed"]]
        return (f"distributed {len(names)} parts on {axis} (spacing {result['spacing']} m): "
                f"{names} [{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def array_at_corners(prototype: str, of: str, standing_on_floor: bool = True,
                     keep_original: bool = False, name_prefix: str = "",
                     linked: bool = False, label: str = "") -> str:
    """
    Duplicate a prototype object to all 4 corners of a target's footprint.
    The 4 copies are named "<prefix>_front_left", "<prefix>_front_right", etc.
    Prefix defaults to the prototype name.

    standing_on_floor: if True, copies sit at Z=0 regardless of where prototype was.
    keep_original: if False (default), the prototype is deleted after copying.
    linked: True = the copies share the prototype's mesh datablock (instances) — one
            mesh for all four, an edit to one shows on all. Default False (independent).

    Example: array_at_corners("leg", of="seat") — put four legs at the seat's corners.
    """
    result = call_blender("array_at_corners", {
        "prototype": prototype, "of": of,
        "standing_on_floor": standing_on_floor,
        "keep_original": keep_original,
        "name_prefix": name_prefix or prototype,
        "linked": linked,
    }, label=label)
    if result.get("success"):
        inst = (f" (instances — shared mesh '{result.get('shared_mesh')}')"
                if result.get("linked") else "")
        return (f"placed at corners of {of}: {result['placed']}{inst} "
                f"[{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def array_along(prototype: str, count: int, between: list, axis: str = "X",
                keep_original: bool = False, name_prefix: str = "",
                linked: bool = False, label: str = "") -> str:
    """
    Duplicate a prototype N times, evenly spaced along the SEGMENT between two anchors.
    Copies INCLUDE both endpoints (copy i at A + (B−A)·i/(N−1)). The direction is the
    true A→B vector in 3D — `axis` is ignored (kept for back-compat), so anchors that
    differ on several axes still distribute correctly. Copies named "<prefix>_1".."_N".

    linked: True = the N copies share the prototype's mesh datablock (instances) — one
            mesh for the whole run instead of N, an edit to one shows on all. The right
            choice for a repeated identical part (fence pickets, balusters, slats).
            Default False (independent copies).

    Example: array_along("slat", count=5,
                         between=["back_rail_bottom", "back_rail_top"])
             → 5 evenly spaced copies of "slat" from the bottom rail to the top.
    """
    result = call_blender("array_along", {
        "prototype": prototype, "count": count, "between": between, "axis": axis,
        "keep_original": keep_original, "name_prefix": name_prefix or prototype,
        "linked": linked,
    }, label=label)
    if result.get("success"):
        inst = (f" (instances — shared mesh '{result.get('shared_mesh')}')"
                if result.get("linked") else "")
        span = result.get("span")
        span_str = f", span {span} m" if span is not None else ""
        return (f"placed {count} copies along A→B (spacing {result['spacing']} m{span_str}): "
                f"{result['placed']}{inst} [{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")

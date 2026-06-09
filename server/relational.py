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
                     label: str = "") -> str:
    """
    Duplicate a prototype object to all 4 corners of a target's footprint.
    The 4 copies are named "<prefix>_front_left", "<prefix>_front_right", etc.
    Prefix defaults to the prototype name.

    standing_on_floor: if True, copies sit at Z=0 regardless of where prototype was.
    keep_original: if False (default), the prototype is deleted after copying.

    Example: array_at_corners("leg", of="seat") — put four legs at the seat's corners.
    """
    result = call_blender("array_at_corners", {
        "prototype": prototype, "of": of,
        "standing_on_floor": standing_on_floor,
        "keep_original": keep_original,
        "name_prefix": name_prefix or prototype,
    }, label=label)
    if result.get("success"):
        return (f"placed at corners of {of}: {result['placed']} "
                f"[{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def array_along(prototype: str, count: int, between: list, axis: str = "X",
                keep_original: bool = False, name_prefix: str = "",
                label: str = "") -> str:
    """
    Duplicate a prototype N times, spacing copies evenly between two anchor centers.
    Like distribute_evenly but also creates the copies. Copies are named "<prefix>_1"..."_N".

    Example: array_along("slat", count=5,
                         between=["back_rail_bottom", "back_rail_top"], axis="Z")
             → 5 evenly spaced copies of "slat" between the two rails.
    """
    result = call_blender("array_along", {
        "prototype": prototype, "count": count, "between": between, "axis": axis,
        "keep_original": keep_original, "name_prefix": name_prefix or prototype,
    }, label=label)
    if result.get("success"):
        return (f"placed {count} copies on {axis} (spacing {result['spacing']} m): "
                f"{result['placed']} [{result.get('op_id','')}]" + _status(result))
    return result.get("error", "failed")


@mcp.tool()
def scatter_on_surface(target: str, source: str, count: int = 100,
                       scale_min: float = 0.8, scale_max: float = 1.2,
                       align_normal: bool = True, rotate_z: bool = True,
                       parent_to_target: bool = True, seed: int = 0,
                       name_prefix: str = "", label: str = "") -> str:
    """
    Scatter `count` copies of `source` randomly across `target`'s surface.
    The donut-tutorial sprinkles step.

    target / source: existing mesh object names (required).
    count: number of instances (capped at 5000).
    scale_min/max: per-instance scale jitter range.
    align_normal: rotate each copy's +Z to match the surface normal at its location.
    rotate_z: also apply random spin around that normal.
    parent_to_target: parent every instance to target so they move/animate with it.
    seed: RNG seed for reproducibility.
    name_prefix: name prefix for generated objects (default "<source>_inst").

    All instances share `source`'s mesh data — cheap memory-wise. Target's
    modifiers are evaluated, so sprinkles land on the visible (post-subsurf) surface.
    """
    result = call_blender("scatter_on_surface", {
        "target": target, "source": source, "count": count,
        "scale_min": scale_min, "scale_max": scale_max,
        "align_normal": align_normal, "rotate_z": rotate_z,
        "parent_to_target": parent_to_target, "seed": seed,
        "name_prefix": name_prefix,
    }, label=label)
    if result.get("success"):
        main = (f"scattered {result['scattered']} copies of '{result['source']}' "
                f"onto '{result['target']}' (mesh '{result['source_mesh']}') "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)

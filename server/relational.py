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


@mcp.tool()
def array_radial(prototype: str, count: int, center: list = None, center_object: str = "",
                 axis: str = "Z", start_angle: float = 0.0, end_angle: float = None,
                 radius: float = None, align_to_tangent: bool = False,
                 keep_original: bool = False, name_prefix: str = "",
                 linked: bool = False, label: str = "") -> str:
    """
    Duplicate a prototype in a circle or arc around a center — the native idiom for
    clock markers, bolt circles, spokes, gear teeth, chain links on an arc, petals.
    No hand-computed sin/cos: give a center, a count, and (optionally) an arc.

    center / center_object: the ring's center. Pass center=[x,y,z] for a world point,
                            OR center_object="Dial" to orbit an object's bbox center.
                            Default world origin.
    axis:             X | Y | Z — axis the ring spins around (ring lies in the other
                      two). Default Z (a ring lying flat in the XY plane).
    start_angle/end_angle: degrees. end_angle defaults to a FULL TURN from the start
                      (start_angle+360) = an evenly-spaced full circle with no overlapping
                      seam, for ANY start_angle (start just rotates the ring). Pass
                      end_angle to force an ARC, spread inclusive of both ends (e.g.
                      0→180 with count=5 gives copies at 0,45,90,135,180).
    radius:           force every copy onto this distance from center. Omit to keep the
                      prototype's current distance.
    align_to_tangent: True = each copy also spins to face along the arc (gear teeth,
                      chain links). False = orientation preserved (upright numerals).
    keep_original:    keep the prototype too (default False — it's consumed like array_*).
    name_prefix:      copies are "<prefix>_1".."_N" (default = prototype name).
    linked:           True = copies share the prototype's mesh (instances — one mesh for
                      the whole ring). Default False (independent copies).

    Examples:
      array_radial("marker", count=12, center_object="dial")          # 12 clock markers
      array_radial("tooth", count=24, radius=0.5, align_to_tangent=True)  # gear teeth
      array_radial("link", count=6, start_angle=0, end_angle=120, align_to_tangent=True)
    """
    params = {
        "prototype": prototype, "count": count, "axis": axis,
        "start_angle": start_angle, "end_angle": end_angle,
        "align_to_tangent": align_to_tangent, "keep_original": keep_original,
        "name_prefix": name_prefix or prototype, "linked": linked,
    }
    if center_object:
        params["center"] = center_object
    elif center is not None:
        params["center"] = center
    if radius is not None:
        params["radius"] = radius
    result = call_blender("array_radial", params, label=label)
    if result.get("success"):
        arc = ("full circle" if result.get("full_circle")
               else f"arc {result['start_angle']}→{result['end_angle']}°")
        tan = " +tangent" if result["align_to_tangent"] else ""
        inst = (f" [instances — shared mesh '{result.get('shared_mesh')}']"
                if result.get("linked") else "")
        main = (f"radial array: {len(result['placed'])} copies of '{prototype}' around "
                f"{result['center']} on {result['axis']} ({arc}, r={result['radius']}, "
                f"step {result['step_deg']}°){tan}{inst} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def scatter_on_surface(target: str, source: str = "", count: int = 100,
                       scale_min: float = 0.8, scale_max: float = 1.2,
                       align_normal: bool = True, rotate_z: bool = True,
                       parent_to_target: bool = True, seed: int = 0,
                       name_prefix: str = "", avoid: str = "",
                       avoid_margin: float = 0.0, sources: str = "",
                       within: str = "", within_margin: float = 0.0,
                       density: float = 0.0, up_only: bool = False,
                       max_slope: float = 45.0, seat: bool = False,
                       offset: float = 0.0, min_distance: float = 0.0,
                       jitter_tilt: float = 0.0, label: str = "") -> str:
    """
    Scatter copies of one or more sources across `target`'s surface — the
    donut-tutorial sprinkles step, aimable (G57).

    target: surface mesh to scatter onto (required).
    source: the mesh to instance. Or use `sources` for variety.
    sources: comma-separated mesh names — each instance picks one at random, so the
             scatter has natural variety (3 tuft variants, not N identical clones).
    count: number of instances (capped at 5000). Ignored when `density` is set.
    density: instances per square meter — the size-independent "this thick". Overrides
             count (a raw count is meaningless without the surface area). With `within`,
             applied to the masked region's footprint area.
    within: object/collection name(s) — a region MASK keeping instances INSIDE this
            world XY footprint (the inverse of avoid). Grass only in the bed, denser
            near the path — POSITIVE placement instead of sprinkling the whole plane.
    within_margin: meters to expand the within footprint by (default 0).
    scale_min/max: per-instance scale jitter range.
    align_normal: rotate each copy's +Z to match the surface normal at its location.
    up_only: scatter ONLY onto up-facing faces (normal within max_slope° of +Z) — G104,
             so "sprinkles on top" doesn't also coat the underside and inner walls.
    max_slope: cone half-angle in degrees for up_only (default 45).
    rotate_z: also apply random spin around that normal.
    parent_to_target: parent every instance to target so they move/animate with it.
    seed: RNG seed for reproducibility.
    name_prefix: name prefix for generated objects (default "<source>_inst").
    avoid: object/collection name(s) to keep CLEAR — set-dressing around a hero asset
           without instances landing inside its footprint. Rejected and resampled.
    avoid_margin: meters to expand the avoid footprint by (default 0).
    seat: G136 — lift each copy along the surface normal so its LOWEST point rests ON the
          surface instead of burying its origin (the source's own extent sets the lift —
          no thickness guess). The fix for flat parts (sprinkles, pebbles, leaves) that
          otherwise sink half-under. Default False.
    offset: G136 — explicit signed distance (m) along the surface normal, added on top of
            any seat lift (+ proud, − sunk). Default 0.
    min_distance: G137 — Poisson-disk spacing: no two instances closer than this (m).
            Crowding candidates are resampled then dropped (in `skipped`) — the ceiling on
            believable dense scatter without coplanar z-fighting.
    jitter_tilt: G137 — max random tilt (deg) off the normal so near-coplanar flats CROSS
            at an angle instead of z-fighting. Default 0.

    Instances of each source share its mesh data — cheap memory-wise. Target's
    modifiers are evaluated, so sprinkles land on the visible (post-subsurf) surface.
    """
    result = call_blender("scatter_on_surface", {
        "target": target, "source": source or None, "count": count,
        "scale_min": scale_min, "scale_max": scale_max,
        "align_normal": align_normal, "rotate_z": rotate_z,
        "parent_to_target": parent_to_target, "seed": seed,
        "name_prefix": name_prefix, "avoid": avoid or None,
        "avoid_margin": avoid_margin,
        "sources": sources or None, "within": within or None,
        "within_margin": within_margin, "density": density,
        "up_only": up_only, "max_slope": max_slope,
        "seat": seat, "offset": offset, "min_distance": min_distance,
        "jitter_tilt": jitter_tilt,
    }, label=label)
    if result.get("success"):
        srcs = result.get("sources") or [result.get("source")]
        src_str = srcs[0] if len(srcs) == 1 else f"{len(srcs)} sources {srcs}"
        main = (f"scattered {result['scattered']} copies of '{src_str}' "
                f"onto '{result['target']}'")
        if result.get("density") is not None:
            main += f" (density {result['density']}/m² over {result.get('total_area_m2')}m²)"
        if result.get("within"):
            main += f" within '{result['within']}'"
        main += f" [{result.get('op_id','')}]"
        skipped = result.get("skipped", result.get("skipped_in_avoid", 0))
        if skipped:
            main += f"\n  {skipped} instance(s) dropped — couldn't satisfy within/avoid"
    else:
        main = result.get("error", "failed")
    return main + _status(result)

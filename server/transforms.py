from server._core import mcp, call_blender, _status, _targets


@mcp.tool()
def nudge(targets: str = "", right: float = 0.0, left: float = 0.0,
          up: float = 0.0, down: float = 0.0,
          back: float = 0.0, forward: float = 0.0, label: str = "") -> str:
    """
    Move objects by a relative offset, in SEMANTIC directions instead of XYZ.
    right/left → ±X, back/forward → ±Y, up/down → ±Z. All in meters.

    Prefer placement spec (`on=` on add_*) for FIRST placement. Use nudge for fine
    adjustments after the fact (e.g. "shift this 1cm to the right to align with X").

    targets: single object name, a group name, or comma-separated list. Empty = active object.
    Example: nudge("seat", up=0.02) — raise the seat 2cm.
    """
    result = call_blender("nudge", {
        "targets": _targets(targets),
        "right": right, "left": left, "up": up, "down": down, "back": back, "forward": forward,
    }, label=label)
    if result.get("success"):
        main = f"nudged {result['moved']} by {result['delta']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def move_to(targets: str = "", x: float = None, y: float = None, z: float = None,
            label: str = "") -> str:
    """Set objects' world location ABSOLUTELY (vs nudge's relative offset) — gaps.md
    G8. Any of x/y/z omitted is left unchanged, so 'snap only Z' is one call. Pairs
    with feel op=aim, which returns a world point to drop a marker / move an object to.

    Relational placement (add on=…) is still preferred for FIRST placement; move_to is
    for dropping at a COMPUTED point (e.g. a feel-op=aim hit). The `transform` verb also
    resolves a handle= name to its live point before calling here. Empty targets = active.
    Example: move_to("MARK", x=0.04, y=-0.08, z=0.9)"""
    result = call_blender("move_to",
                          {"targets": _targets(targets), "x": x, "y": y, "z": z}, label=label)
    if result.get("success"):
        main = f"moved {result['moved']} to {result['location']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def rotate_to(targets: str = "", x: float = None, y: float = None, z: float = None,
              label: str = "") -> str:
    """Set objects' euler rotation ABSOLUTELY in degrees (vs rotate's relative spin) —
    gaps.md G8. Any axis omitted is left unchanged. Empty targets = active.
    Example: rotate_to("GUIDE", z=25)  # set yaw to exactly 25°, leave pitch/roll"""
    result = call_blender("rotate_to",
                          {"targets": _targets(targets), "x": x, "y": y, "z": z}, label=label)
    if result.get("success"):
        main = f"rotated {result['rotated']} to {result['rotation_deg']}° [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def aim_axis(targets: str = "", frm: list = None, to: list = None,
             axis: str = "Z", label: str = "") -> str:
    """Rotate objects so their local `axis` points down the frm→to segment (G25) — the
    orient-along-an-edge primitive for solids that don't self-orient like add type=tube.
    Endpoints are world points; the `transform` verb resolves from_handle/to_handle names
    to points before calling here. Orientation only — pair with move_to to position.
    Example: lay a helix along a strut's two ends."""
    if frm is None or to is None:
        return ("aim_axis needs both endpoints — aim_from/aim_to points, "
                "or from_handle/to_handle")
    result = call_blender("aim_axis", {"targets": _targets(targets),
                                       "from": list(frm), "to": list(to), "axis": axis},
                          label=label)
    if result.get("success"):
        main = (f"aimed {result['aimed']} local {result['axis']} along {result['direction']} "
                f"→ rot {result['rotation_deg']}° [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def rest_on(targets: str = "", target: str = "", axis: str = "Z",
            offset: float = 0.0, label: str = "") -> str:
    """Drop objects along −axis until their REAL geometry rests on `target` (G26). Uses
    BVH ray-casts from the source's own verts, so a tilted/irregular part seats by its
    true lowest point (snap_to uses the AABB bottom and mis-seats anything rotated). The
    action half of feel op=contacts 'floating 3mm'. offset leaves a clearance gap."""
    if not target:
        return "rest_on needs 'target' — the surface object to rest on"
    result = call_blender("rest_on", {"targets": _targets(targets), "target": target,
                                      "axis": axis, "offset": offset}, label=label)
    if result.get("success"):
        # G108: a negative dropped_mm means the part STRADDLED/sat below the target and
        # was LIFTED to rest, not dropped — show the direction so it reads true.
        def _mv(d):
            return f"↑{abs(d)}mm (lifted to rest)" if d < 0 else f"↓{d}mm"
        drops = ", ".join(f"{r['name']}{_mv(r['dropped_mm'])}" for r in result["rested"]) or "nothing"
        main = f"rested on {target} ({result['axis']}): {drops} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def seat_into(targets: str = "", target: str = "", axis: str = "Z",
              offset: float = 0.0, label: str = "") -> str:
    """Seat objects DOWN INTO a cavity (G82): lower along −axis until they rest on the
    highest INTERIOR floor of `target` beneath their footprint — a dial in its bezel well,
    a gem in a setting, a lens in a barrel, a panel in a rebate. Unlike rest_on (which
    stops at the first/outer contact and so catches on a recess's rim), seat keeps only
    up-facing floor hits, so the part sinks past the cavity walls onto the floor. offset
    leaves a clearance above the floor."""
    if not target:
        return "seat needs 'target' — the cavity object to seat into"
    result = call_blender("seat_into", {"targets": _targets(targets), "target": target,
                                        "axis": axis, "offset": offset}, label=label)
    if result.get("success"):
        drops = ", ".join(f"{r['name']}↓{r['dropped_mm']}mm" for r in result["seated"]) or "nothing"
        main = f"seated into {target} ({result['axis']}): {drops} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def place(targets: str = "", on: dict = None, label: str = "") -> str:
    """Re-place EXISTING objects with the relational placement DSL — the same `on=`
    vocabulary as add (G30). Closes the 'placement DSL is add-only' gap: seat an
    object already in the scene left_of/on/under/at_corner another without dropping to
    raw coordinates. resolve_placement is evaluated against each object's own dims, so
    place one object at a time (a list converges on the same anchor).

    Example: place("cup", on={"left_of": "base", "gap": 0})  # snug to the base's -X."""
    if not on:
        return ("place needs on=<placement spec> — e.g. "
                "transform op=place targets=cup on={\"left_of\":\"base\",\"gap\":0}")
    result = call_blender("place", {"targets": _targets(targets), "on": on}, label=label)
    if result.get("success"):
        seated = ", ".join(f"{p['name']}→{p['center']}" for p in result["placed"]) or "nothing"
        main = f"placed {seated} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def resize(targets: str = "", width: float = None, depth: float = None, height: float = None,
           label: str = "") -> str:
    """
    Resize objects to ABSOLUTE world-space dimensions (meters). Each axis is optional;
    omitted axes preserve their current size. Scale is baked after resize so modifiers
    (bevel etc.) behave uniformly.

    Prefer creating primitives at the right size up front (add_box etc.) — this is for
    after-the-fact corrections ("make the seat 5cm taller").

    targets: single object name, group name, or comma-separated list. Empty = active object.
    Example: resize("seat", height=0.04) — make the seat 4cm thick.
    """
    params = {"targets": _targets(targets)}
    if width is not None:  params["width"] = width
    if depth is not None:  params["depth"] = depth
    if height is not None: params["height"] = height
    result = call_blender("resize", params, label=label)
    if result.get("success"):
        main = f"resized: {result['resized']} [{result.get('op_id','')}]"
        for warning in result.get("warnings", []):
            main += f"\n⚠ {warning}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def scale_group(targets: str, factor: float, pivot: str = "center", label: str = "") -> str:
    """
    Uniformly scale a whole assembly about a SHARED pivot, preserving relative layout.
    Use when a multi-part construction needs to be N% bigger/smaller in place —
    resize can't do this (it sets each member to the same absolute dims).

    targets: object name, group name, or comma-separated list (required).
    factor:  uniform multiplier — 1.08 = 8% bigger, 0.5 = half size.
    pivot:   "center" (default — combined bbox center) | "bottom_center" (keeps
             feet on the floor) | "origin" (world 0,0,0) | an object name (scale
             about that object's center).

    Example: scale_group("head_assembly", factor=1.08, pivot="center")
    """
    result = call_blender("scale_group", {
        "targets": _targets(targets), "factor": factor, "pivot": pivot,
    }, label=label)
    if result.get("success"):
        b = result["bounds_after"]
        main = (f"scaled {len(result['scaled'])} part(s) ×{result['factor']} about "
                f"{result['pivot']}; now x={b['x']} y={b['y']} z={b['z']} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def apply_transform(targets: str = "", scale: bool = True,
                    rotation: bool = False, location: bool = False, label: str = "") -> str:
    """
    Bake an object's transform into its mesh data. After applying scale, obj.scale = [1,1,1]
    and bevels/modifiers behave uniformly. Apply rotation to clear rotation_euler. Apply
    location only if you really want the origin pinned at world (0,0,0) — usually unwanted.

    Primitives created with add_box etc. already have scale baked, so you rarely need this.
    Reach for it after `resize` if you bypass the built-in bake, or to fix imported objects.

    targets: single object name, group name, or comma-separated list. Empty = active object.
    """
    result = call_blender("apply_transform", {
        "targets": _targets(targets), "scale": scale, "rotation": rotation, "location": location,
    }, label=label)
    if result.get("success"):
        flags = [k for k in ("scale", "rotation", "location") if result.get(k)]
        main = f"applied {flags} on {result['applied_to']} [{result.get('op_id','')}]"
        for w in result.get("warnings", []):
            main += f"\n⚠ {w}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def rotate_object(angle: float, axis: str = "Z", targets: str = "",
                  pivot: list = None, pivot_object: str = "", label: str = "") -> str:
    """
    Rotate objects by `angle` degrees around `axis` (X | Y | Z).
    targets: single object name, group name, or comma-separated list. Empty = active object.

    pivot / pivot_object: rotate about a SHARED point instead of each object's own
    origin — a rigid swing where both position and orientation turn. Pass
    pivot=[x,y,z] for a world point; pivot_object="dial" to pivot about an object's
    bbox center; or a pivot MODE string. The two that bite if confused:
      "self"  — each object spins about its OWN origin (the DEFAULT). Alias: "center".
      "world" — pivot about the WORLD origin (0,0,0). Alias: "origin".
    ("self" and "world" are named after Blender's own vocabulary — "origin" there
    means the object's origin, so the legacy aliases read backwards; prefer the
    explicit names.) Also: "assembly" / "bbox_center" (the targets' combined
    geometric centre — turn several parts as ONE rigid body; the right choice when
    rotating a multi-part assembly, vs "self" which spins each about itself) and
    "cursor" (the 3D cursor). For "self" the status echoes each object's world
    origin (pivot_points), so a hand whose origin sits off the dial is catchable,
    not silently flung — and a multi-target self-spin now warns that the parts may
    have drifted apart.
    """
    parsed = _targets(targets)
    params = {"angle": angle, "axis": axis, "targets": parsed}
    shared_pivot = True
    if pivot_object:
        params["pivot"] = pivot_object
    elif isinstance(pivot, (list, tuple)):
        params["pivot"] = list(pivot)
    elif isinstance(pivot, str) and pivot.strip().lower() not in ("", "center", "self"):
        params["pivot"] = pivot.strip().lower()
    else:
        # pivot="self"/"center"/"": no shared pivot — each object spins about its own
        # origin; the handler echoes those origins back as pivot_points.
        shared_pivot = False
    result = call_blender("rotate_object", params, label=label)
    if result.get("success"):
        about = f" about {result['pivot']}" if result.get("pivot") else ""
        pts = result.get("pivot_points")
        if pts:
            about += f" {pts if len(pts) > 1 else pts[0]}"
        main = f"rotated {result['rotated']} by {angle}° on {axis}{about} [{result.get('op_id','')}]"
        # G154: rotating several parts with the DEFAULT self-pivot spins each about its
        # OWN origin — they drift apart instead of turning as one body. That's almost
        # never what "rotate the assembly" means, and it's invisible until you read
        # clearances. Flag it and name the one-word fix.
        if shared_pivot is False and isinstance(parsed, list) and len(parsed) > 1:
            main += ("\n⚠ each of the " + str(len(parsed)) + " targets spun about its OWN "
                     "origin, not a shared pivot — they may have drifted apart. For a rigid "
                     "assembly turn, add pivot=assembly (shared bbox centre) or "
                     "pivot_object=<name>.")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def snap_to(target: str, side: str = "Z_MAX", source_side: str = "AUTO",
            offset: float = 0.0, label: str = "") -> str:
    """
    Translate the active object so one of its bbox faces aligns with a face of `target`.

    side:        which face of TARGET to snap to.  X_MIN | X_MAX | Y_MIN | Y_MAX | Z_MIN | Z_MAX
    source_side: which face of ACTIVE to align there.
                 AUTO (default) = the opposite face on the same axis (so they touch flush).
                 CENTER = align active's center to target's chosen face.
                 explicit X_MIN..Z_MAX must be on the same axis as `side`.
    offset:      world-units along the side axis, applied AFTER alignment.
                 +ve = move active further in the +axis direction (more overlap when snapping to MAX-side).

    Examples:
      snap_to(target="Crossguard", side="Z_MAX")                          # grip bottom flush with crossguard top
      snap_to(target="Grip", side="Z_MAX", offset=-0.04)                  # pommel sinks 0.04 into grip
      snap_to(target="Wall", side="X_MAX", source_side="X_MAX")           # both right-faces align (flush, not next-to)
    """
    params = {"target": target, "side": side, "source_side": source_side, "offset": offset}
    result = call_blender("snap_to", params, label=label)
    if result.get("success"):
        main = (f"snap_to {target}.{side}: delta={result['delta']} "
                f"({result['source_side']}→{result['target_coord']})  [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def snap_to_grid(size: float = 0.1, axes: str = "XYZ", label: str = "") -> str:
    """
    Round the active object's location to multiples of `size` on the chosen axes.

    size: grid spacing in world units (e.g., 0.05, 0.1, 0.25, 1.0)
    axes: any of "X", "Y", "Z", or combinations like "XZ" — only these axes are snapped.

    Snaps the ORIGIN/pivot — does not change dims, rotation, or geometry.
    Pairs naturally with snap_to: free-place, snap-to-grid for alignment, snap-to for stacking.
    """
    params = {"size": size, "axes": axes}
    result = call_blender("snap_to_grid", params, label=label)
    if result.get("success"):
        moves = result.get("snapped", [])
        moved_summary = ", ".join(f"{m['axis']}:{m['from']}→{m['to']}" for m in moves if abs(m.get('moved', 0)) > 1e-9) or "no change"
        main = f"snap_to_grid {size} on {axes}: {moved_summary}  [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)

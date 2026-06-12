import json
from server._core import mcp, call_blender, _status, _targets


@mcp.tool()
def get_scene_tree(filter: str = "", type: str = "", max_depth: int = None,
                   summarize: int = 20) -> str:
    """List the Blender scene as a tree. Call this first to know what exists.

    On big production scenes the full dump is unreadable, so it scales:
    filter:    substring — show only objects whose name contains it.
    type:      object type (MESH/ARMATURE/EMPTY/LIGHT/CAMERA/…) — show only that type.
    max_depth: cap collection nesting depth.
    summarize: collapse any collection holding more than this many objects into a
               per-type count line (default 20; pass 0 to force a full listing).
               Setting filter/type disables summarization so matches are listed.

    Objects carry tags: (instanced) for shared mesh data, [lib:File.blend] for
    library-linked (read-only) data, [override:File.blend] for a local override.

    Examples:
      get_scene_tree()                       # overview, big collections summarized
      get_scene_tree(filter="hand")          # drill into matching objects
      get_scene_tree(type="ARMATURE")        # just the rigs
    """
    params = {"filter": filter, "type": type, "summarize": summarize}
    if max_depth is not None:
        params["max_depth"] = max_depth
    result = call_blender("get_scene_tree", params)
    return result.get("tree", result.get("error", "unknown error"))


@mcp.tool()
def get_blender_status() -> str:
    """
    Full Blender context snapshot. Returns mode, active + selected objects, dimensions,
    world Z range, last history action, and (in Edit Mode) component type, selection counts,
    and selection Z range. This is also automatically appended to every other tool's output.
    """
    result = call_blender("get_blender_status")
    if not result.get("success"):
        return result.get("error", "failed")
    s = result["status"]
    lines = [
        f"mode:           {s['mode']}",
        f"active_object:  {s['active_object']} ({s['active_type']})",
        f"selected:       {s['selected_objects']}",
        f"location:       {s.get('location')}",
        f"dimensions:     {s.get('dimensions')}     (world bbox)",
        f"rotation_deg:   {s.get('rotation_deg')}",
        f"world_bounds:   {s.get('world_bounds')}",
        f"history_depth:  {s['history_depth']}",
        f"last_action:    {s['last_action']}",
    ]
    if "render" in s:
        r = s["render"]
        rt = f"  raytracing={r['raytracing']}" if "raytracing" in r else ""
        lines.append(
            f"render:         {r['engine']}  view_transform={r['view_transform']} "
            f"look={r['look']} exposure={r['exposure']} gamma={r['gamma']}{rt}"
        )
    if "edit" in s:
        e = s["edit"]
        lines += [
            f"--- edit mode ---",
            f"component_mode: {e['component_mode']}",
            f"selected:       {e['selected']}",
            f"total:          {e['total']}",
            f"sel_z_range:    {e.get('selection_z_range', 'none')}",
        ]
    return "\n".join(lines)


@mcp.tool()
def get_mesh_profile(axis: str = "Z", min: float = None, max: float = None,
                     max_rings: int = 200) -> str:
    """
    Slice the active mesh into rings along an axis and report the width/extent at each ring.
    axis: X | Y | Z — the axis to slice along (default Z for vertical objects like blades)
    min, max: optional WORLD-SPACE window on the profile axis (same units as the table's
              position column, NOT 0..1 factors). e.g. axis="X", min=0.08, max=0.20 returns
              only the rings whose X falls in [0.08, 0.20]. Use to profile one region of a
              production mesh without dumping the whole thing.
    max_rings: cap the number of rings returned (default 200). If the windowed mesh has more,
               rings are EVENLY RESAMPLED (first and last always kept) and the table notes it.
               Pass 0 to uncap. Production meshes (thousands of rings) otherwise blow the
               result budget.
    Returns a table: position along axis, plus min/max/width on the other two axes.
    Use this to understand actual geometry before making edits — no guessing needed.
    """
    params = {"axis": axis, "max_rings": max_rings}
    if min is not None:
        params["min"] = min
    if max is not None:
        params["max"] = max
    result = call_blender("get_mesh_profile", params)
    if not result.get("success"):
        return result.get("error", "failed")
    profile = result["profile"]
    ax = result["axis"]
    other = [n for n in ['X', 'Y', 'Z'] if n != ax]
    lines = [f"{'':>8}  " + "  ".join(f"{n:>22}" for n in other)]
    for r in profile:
        cols = []
        for n in other:
            lo, hi = r[f"{n}_range"]
            w = r[f"{n}_width"]
            cols.append(f"{lo:+.4f}→{hi:+.4f} ({w:.4f})")
        lines.append(f"{ax}={r[ax]:+.4f}  " + "  ".join(cols))
    shown = len(profile)
    total = result.get("rings_total", shown)
    head = f"{shown} rings along {ax}"
    if result.get("windowed"):
        w = result.get("window", [None, None])
        head += f" in window [{w[0]}, {w[1]}]"
    if result.get("resampled"):
        head += f" (resampled from {total} — even spacing, first/last kept)"
    return f"{head}:\n" + "\n".join(lines) + _status(result)


@mcp.tool()
def get_object_info(name: str = "") -> str:
    """
    Detailed state dump of an object: location, scale, rotation, dimensions, world bbox,
    and vertex/edge/face counts.

    Prefer `describe(name)` for normal workflows — it returns a relational sentence
    instead of raw coordinates. Use this when you specifically need the underlying
    coordinate/scale/rotation values (debugging, math).

    name: target object. If omitted, falls back to the active object.
    """
    params = {"name": name} if name else {}
    result = call_blender("get_object_info", params)
    if result.get("success"):
        return json.dumps(result["info"], indent=2) + _status(result)
    return result.get("error", "failed")


@mcp.tool()
def describe(name: str, posed: bool = False) -> str:
    """
    Describe an object in RELATIONAL terms — what it rests on, what it's flush with,
    and its dimensions. No raw world coordinates.

    Prefer this over get_object_info for normal workflows. Coords appear in get_object_info
    when you really need them; describe() is the everyday tool because relational
    descriptions are what you actually reason in.

    posed: when True, report the EVALUATED geometry — bounds/center under current
    modifiers AND armature pose — instead of rest placement, plus how far the posed
    geometry sits from rest. Use this to find where a deformed/posed part actually
    is (e.g. a cup riding a cocked rig) without dead-reckoning the bone pivot.

    Example output:
        "leg_front_left: standing on floor; flush left of seat; size 0.04 × 0.04 × 0.45 m (W×D×H)"
    """
    result = call_blender("describe", {"name": name, "posed": posed})
    if not result.get("success"):
        return result.get("error", "failed")
    return result["description"] + _status(result)


@mcp.tool()
def get_current_selection() -> str:
    """
    Describe the current vertex selection in Edit Mode.
    Returns: selected vert count, world-space centroid, world-space bounding box.
    Use this to understand where your selection actually is before moving or scaling it.
    Must be in Edit Mode.
    """
    result = call_blender("get_current_selection")
    if not result.get("success"):
        return result.get("error", "failed")
    if result["selected_count"] == 0:
        return "No vertices selected." + _status(result)
    lines = [
        f"selected_verts: {result['selected_count']}",
        f"centroid_world: {result['centroid_world']}",
        f"bbox_world:",
        f"  x: {result['bbox_world']['x']}",
        f"  y: {result['bbox_world']['y']}",
        f"  z: {result['bbox_world']['z']}",
    ]
    return "\n".join(lines) + _status(result)


@mcp.tool()
def distance_between(a: str, b: str, axis: str = "ANY") -> str:
    """
    Centre-to-centre distance between two objects, in meters.
    axis: ANY (3D Euclidean) | X | Y | Z (single-axis distance).

    Use this when you'd otherwise be tempted to fetch coords of both and subtract —
    let the server do the math so you don't carry numbers in your head.
    """
    result = call_blender("distance_between", {"a": a, "b": b, "axis": axis})
    if result.get("success"):
        return f"{a} ↔ {b} ({result['axis']}): {result['distance']} m" + _status(result)
    return result.get("error", "failed")


@mcp.tool()
def gap_between(a: str, b: str) -> str:
    """
    Smallest empty distance between two objects' bounding boxes, per axis.
    Negative = overlap. Useful for "are these touching?" and "how much room is left?"
    """
    result = call_blender("gap_between", {"a": a, "b": b})
    if not result.get("success"):
        return result.get("error", "failed")
    touching = result.get("touching_on_axes") or []
    touching_str = f" — touching on {touching}" if touching else ""
    main = (f"gap {a} ↔ {b}: x={result['gap_x']}  y={result['gap_y']}  z={result['gap_z']}"
            f"{touching_str}")
    return main + _status(result)


@mcp.tool()
def check_symmetry(target: str = "", axis: str = "X", plane: float = 0.0,
                   epsilon: float = None) -> str:
    """
    Check symmetry across a world-space plane, at the right zoom level automatically:

    • A single mesh → MESH-LEVEL: mirrors the geometry and reports max/mean vertex
      deviation and WHERE the worst asymmetry is ("asymmetric across X — max 8mm at
      top-left"). The first thing eyes catch on character/sculpt work.
    • Multiple objects / a collection / the whole scene → OBJECT-LEVEL: pairs each
      part with its mirrored counterpart and reports any unmatched parts.

    target:  object, collection, or comma-separated list. Empty = whole scene.
    axis:    X | Y | Z — axis the mirror plane is perpendicular to (default X).
    plane:   world coordinate of the plane on that axis (default 0).
    epsilon: match tolerance in meters (defaults: 0.5mm mesh-level, 10mm object-level).
    """
    params = {"axis": axis, "plane": plane}
    if target:
        params["targets"] = _targets(target)
    if epsilon is not None:
        params["epsilon"] = epsilon
    result = call_blender("check_symmetry", params)
    if not result.get("success"):
        return result.get("error", "failed")
    return result["summary"] + _status(result)


@mcp.tool()
def is_aligned(a: str, b: str, side: str = "TOP", tolerance: float = 0.001) -> str:
    """
    Check whether two objects share an aligned side / center.
    side: TOP | BOTTOM | LEFT | RIGHT | FRONT | BACK | CENTER_X | CENTER_Y | CENTER_Z

    Use this instead of fetching world-bounds for two objects and comparing.
    """
    result = call_blender("is_aligned", {"a": a, "b": b, "side": side, "tolerance": tolerance})
    if not result.get("success"):
        return result.get("error", "failed")
    verdict = "ALIGNED" if result["aligned"] else "NOT aligned"
    return f"{a} vs {b} on {side}: {verdict} (diff={result['difference']})" + _status(result)

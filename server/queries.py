import json
from server._core import mcp, call_blender, _status, _targets


@mcp.tool()
def get_scene_tree(filter: str = "", type: str = "", max_depth: int = None,
                   summarize: int = 20, parts_only: bool = False) -> str:
    """List the Blender scene as a tree. Call this first to know what exists.

    On big production scenes the full dump is unreadable, so it scales:
    filter:    substring — show only objects whose name contains it.
    type:      object type (MESH/ARMATURE/EMPTY/LIGHT/CAMERA/…) — show only that type.
    max_depth: cap collection nesting depth.
    summarize: collapse any collection holding more than this many objects into a
               per-type count line (default 20; pass 0 to force a full listing).
               Setting filter/type disables summarization so matches are listed.
    parts_only: show only the REAL renderable geometry — hide bone-shape widgets
               (the cs_*/WGT- meshes referenced as armature custom shapes) and
               render-hidden helpers. First contact with a rig becomes a map of the
               ~15 actual parts instead of a wall of hundreds of widgets.

    Objects carry tags: (instanced) for shared mesh data, [lib:File.blend] for
    library-linked (read-only) data, [override:File.blend] for a local override.

    Examples:
      get_scene_tree()                       # overview, big collections summarized
      get_scene_tree(filter="hand")          # drill into matching objects
      get_scene_tree(type="ARMATURE")        # just the rigs
      get_scene_tree(parts_only=True)        # just the real renderable parts
    """
    params = {"filter": filter, "type": type, "summarize": summarize,
              "parts_only": parts_only}
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
                     max_rings: int = 200, bands: int = 0, full: bool = False,
                     target: str = "") -> str:
    """
    Sweep the active mesh's cross-section along an axis. BY DEFAULT this aggregates
    into evenly spaced bands and reports each band's real cross-section width, with
    the NARROWEST band (the pinch — armpit, waist, neck) and the widest flagged —
    which is what you actually reach a profile for. Pass full=True for the raw
    per-ring dump.

    axis: X | Y | Z — the axis to slice along (default Z for vertical objects).
    min, max: optional WORLD-SPACE window on the profile axis (same units as the
              position column, NOT 0..1 factors). e.g. axis="X", min=0.08, max=0.20.
    bands: number of aggregation bands (default 24). Ignored when full=True.
    full: True = SHOW_ME_EVERYTHING — one ring per distinct axis position, capped by
          max_rings (evenly resampled, first/last kept). The old raw table.
    max_rings: cap for full mode (default 200; 0 = uncap).
    target: mesh object name. Empty = active object.

    Use this to find WHERE the section changes before a cut — no coordinate guessing.
    """
    params = {"axis": axis, "max_rings": max_rings, "bands": bands, "full": full,
              "target": target or None}
    if min is not None:
        params["min"] = min
    if max is not None:
        params["max"] = max
    result = call_blender("get_mesh_profile", params)
    if not result.get("success"):
        return result.get("error", "failed")
    ax = result["axis"]
    other = [n for n in ['X', 'Y', 'Z'] if n != ax]

    if result.get("mode") == "full":
        profile = result["profile"]
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

    # aggregated bands (default)
    profile = result["profile"]
    ext = result["extent"]
    head = (f"{result['bands']} bands along {ax}  "
            f"(band ≈ {result['band_width']}m, extent [{ext[0]}, {ext[1]}])")
    if result.get("windowed"):
        w = result.get("window", [None, None])
        head += f"  window [{w[0]}, {w[1]}]"
    nb, wb = result["narrowest"], result["widest"]
    lines = [
        f"  ← narrowest: {ax}={nb[ax]:+.4f}  girth {nb['girth']}m   (the pinch)",
        f"  → widest:    {ax}={wb[ax]:+.4f}  girth {wb['girth']}m",
        f"  {ax:>8}  " + "  ".join(f"{n}_width" for n in other) + "   girth     n",
    ]
    for b in profile:
        ws = "  ".join(f"{b[f'{n}_width']:>7.4f}" for n in other)
        lines.append(f"  {b[ax]:+.4f}  {ws}   {b['girth']:>7.4f}  {b['n']:>4}")
    return f"{head}:\n" + "\n".join(lines) + _status(result)


@mcp.tool()
def get_silhouette(axis: str = "X", res: int = 32, selection: bool = False,
                   target: str = "") -> str:
    """Orthographic projected OUTLINE of the active mesh along a view axis — the 2D
    shape read directly, not cross-multiplied from two 1D profile sweeps (gaps.md G37).

    Pure geometry, not a render: projects every vert onto the plane perpendicular to
    `axis` and rasterizes a coarse '#'/'.' occupancy map. Shows drape-vs-projection
    (teardrop vs cone) in one read — the thing a profile sweep is blind to.

    axis: view axis to look ALONG (X|Y|Z). Default X = side view (depth × height).
    res: grid resolution on the wider plane axis (default 32, 4..120).
    selection: True = only the live selection's verts.
    target: mesh object name. Empty = active object.
    """
    result = call_blender("get_silhouette",
                          {"axis": axis, "res": res, "selection": selection,
                           "target": target or None})
    if not result.get("success"):
        return result.get("error", "failed")
    ur, vr = result["u_range"], result["v_range"]
    head = (f"silhouette along {result['axis']} — {result['u_label']}(→)×{result['v_label']}(↑) "
            f"plane, {result['cols']}×{result['rows']} cells @ {result['cell_m']}m\n"
            f"  {result['u_label']} [{ur[0]}, {ur[1]}]   {result['v_label']} [{vr[0]}, {vr[1]}]   "
            f"{result['filled_cells']} filled")
    return head + "\n" + "\n".join("  " + row for row in result["grid"])


@mcp.tool()
def get_section(axis: str = "Z", sections: int = 12,
                min: float = None, max: float = None, target: str = "") -> str:
    """True cross-section PERIMETER + enclosed AREA along an axis (gaps.md G47).

    Unlike profile (bbox width per band), this slices the actual mesh with a plane at
    each position and sums the cut-contour edge lengths (perimeter ≈ girth /
    circumference) plus shoelace area — so circumference and cross-sectional area are
    first-class (cup size, pipe girth, limb circumference, volume reasoning).

    axis: slice axis (X|Y|Z, default Z).
    sections: number of evenly spaced slices (default 12).
    min, max: optional world-space window on the axis.
    target: mesh object name. Empty = active object.
    """
    params = {"axis": axis, "sections": sections, "target": target or None}
    if min is not None:
        params["min"] = min
    if max is not None:
        params["max"] = max
    result = call_blender("get_section", params)
    if not result.get("success"):
        return result.get("error", "failed")
    ax = result["axis"]
    ext = result["extent"]
    nb, wb = result["narrowest"], result["widest"]
    head = (f"{result['sections']} cross-sections along {ax}  (extent [{ext[0]}, {ext[1]}])")
    if result.get("windowed"):
        head += "  (windowed)"
    lines = [
        f"  ← narrowest: {ax}={nb[ax]:+.4f}  perim {nb['perimeter_cm']}cm  area {nb['area_cm2']}cm²",
        f"  → widest:    {ax}={wb[ax]:+.4f}  perim {wb['perimeter_cm']}cm  area {wb['area_cm2']}cm²",
        f"  {ax:>8}   perim_cm   area_cm²   loops",
    ]
    for s in result["profile"]:
        flag = "  ⚠ multi-loop" if s["loops"] > 1 else ""
        lines.append(f"  {s[ax]:+.4f}   {s['perimeter_cm']:>8.2f}   {s['area_cm2']:>8.2f}   "
                     f"{s['loops']:>5}{flag}")
    return f"{head}:\n" + "\n".join(lines)


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
    Distance between two objects, in meters.
    axis: ANY (default) = true NEAREST-SURFACE distance (BVH — reconciles with a
    contacts read and the status-block bounds), X | Y | Z = single-axis centre-to-
    centre projection.

    Use this when you'd otherwise be tempted to fetch coords of both and subtract —
    let the server do the math so you don't carry numbers in your head.
    """
    result = call_blender("distance_between", {"a": a, "b": b, "axis": axis})
    if result.get("success"):
        measured = result.get("measured", "")
        tail = f"  ({measured})" if measured else ""
        btw = result.get("between")
        if btw:
            tail += f"  between {btw[0]}↔{btw[1]}"
        return f"{a} ↔ {b} ({result['axis']}): {result['distance']} m{tail}" + _status(result)
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


def aim_surface(target: str = "", face: str = "-Y", u: float = 0.5, v: float = 0.5,
                margin: float = 0.0) -> str:
    """Cast a normalized bbox-face aim onto the surface — the constructive-side analog
    of `feel structure` → handles (gaps.md G1 / SPEC-06). Turns a framing you CAN
    reason about (a face of the local bbox + two 0..1 coords) into the world point +
    surface normal the coordinate-hungry verbs need — and hands the coordinate back so
    you LEARN it instead of dead-reckoning it.

    face: which local bbox face to cast FROM, as a signed axis — -Y +Y -X +X -Z +Z.
          '-Y' = origin on the −Y face, ray travels +Y INTO the volume.
    u, v: 0..1 on that face over the OTHER two local axes (ascending, X<Y<Z).
          face=-Y → u:X, v:Z. face=-Z → u:X, v:Y. 0=min, 0.5=centre, 1=max.

    Then feed the returned point to a constructive verb:
      sculpt … at_x/y/z=point, radius=…   (push along the returned normal to pull out)
      select op=in_sphere center=point     |   add … on={"at": point}
    Casts onto the EVALUATED surface (subsurf included)."""
    result = call_blender("aim_surface",
                          {"target": target, "face": face, "u": u, "v": v, "margin": margin})
    if not result.get("success"):
        if "note" in result:
            return result["note"]
        return result.get("error", "failed")
    p = result["point"]; n = result["normal"]
    return (f"surface @ {result['region']} (cast {result['cast_axis']}): "
            f"point=[{p[0]}, {p[1]}, {p[2]}]  normal=[{n[0]}, {n[1]}, {n[2]}]\n"
            f"  → sculpt at_x={p[0]} at_y={p[1]} at_z={p[2]} (push along the normal "
            f"to pull out); or select in_sphere center=that point")

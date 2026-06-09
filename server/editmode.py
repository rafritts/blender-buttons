from server._core import mcp, call_blender, _status


@mcp.tool()
def bevel(factor: float = 0.05, segments: int = 1, affect: str = "EDGES", label: str = "") -> str:
    """
    Bevel selected edges or vertices in edit mode.
    factor: bevel size as a fraction of the object's smallest dimension (0.05 = 5%)
    segments: edge loops added (more = smoother curve)
    affect: EDGES | VERTICES
    """
    result = call_blender("bevel", {"factor": factor, "segments": segments, "affect": affect}, label=label)
    if result.get("success"):
        main = f"ok (offset={result.get('offset_world')}) [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def extrude(x: float = 0.0, y: float = 0.0, z: float = 0.0, label: str = "") -> str:
    """
    Extrude selected geometry in edit mode and translate by a fraction of the object's dimensions.
    x/y/z: fraction of object dimension along that axis (0.5 = 50% of width/depth/height).
    Returns the actual world-space translation applied.
    """
    result = call_blender("extrude", {"x": x, "y": y, "z": z}, label=label)
    if result.get("success"):
        main = f"ok translation={result.get('translation_world')} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_all(action: str = "SELECT") -> str:
    """
    Select/deselect geometry in edit mode.
    action: SELECT | DESELECT | INVERT
    """
    result = call_blender("select_all", {"action": action})
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_by_axis(axis: str = "Z", factor: float = 0.5, comparison: str = "GREATER",
                   action: str = "SELECT") -> str:
    """
    Select or deselect vertices in edit mode by position along an axis.
    axis: X | Y | Z
    factor: 0.0 = min extent, 1.0 = max extent of object on this axis.
            e.g. factor=0.8 comparison=GREATER selects the top 20% of the mesh.
    comparison: GREATER | LESS
    action: SELECT (replace selection) | DESELECT (remove matching verts from selection)
            Use DESELECT to select a band: select_all → deselect left → deselect right = center band.
    Returns the actual world-space threshold used.
    """
    result = call_blender("select_by_axis", {"axis": axis, "factor": factor,
                                              "comparison": comparison, "action": action})
    if result.get("success"):
        main = f"ok (threshold_world={result.get('threshold_world')})"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def move_vertices(x: float = 0.0, y: float = 0.0, z: float = 0.0, label: str = "") -> str:
    """
    Translate selected vertices in edit mode using bmesh.
    x/y/z: fraction of object dimension along that axis (0.1 = 10% of width/depth/height).
    Negative values move in the opposite direction.
    Must be in edit mode with vertices selected.
    """
    result = call_blender("move_vertices", {"x": x, "y": y, "z": z}, label=label)
    if result.get("success"):
        main = f"Moved {result['verts_moved']} verts by {result['delta_world']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def scale_vertices(x: float = 1.0, y: float = 1.0, z: float = 1.0,
                   pivot: str = "SELECTION", label: str = "") -> str:
    """
    Scale selected vertices in edit mode using bmesh.
    x/y/z: scale multipliers per axis (0.5 = half, 2.0 = double)
    pivot: SELECTION (around selection center) | ORIGIN (around object origin)
    Must be in edit mode with vertices selected.
    """
    result = call_blender("scale_vertices", {"x": x, "y": y, "z": z, "pivot": pivot}, label=label)
    if result.get("success"):
        main = f"Scaled {result['verts_scaled']} verts [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def proportional_move(x: float = 0.0, y: float = 0.0, z: float = 0.0,
                      radius: float = 0.01, falloff: str = "SMOOTH",
                      label: str = "") -> str:
    """
    Move selected verts with a falloff — drags nearby verts along (proportional editing).
    Selected verts move full amount; verts at radius edge don't move at all.

    x/y/z: translation as a fraction of object dims (same as move_vertices).
    radius: falloff radius in meters (default 1cm).
    falloff: SMOOTH (default — rounded shape) | LINEAR | SPHERE | SHARP | ROOT | CONSTANT.

    For icing drips: select sparse boundary verts, proportional_move(z=-0.5, radius=0.005)
    gives bulbous rounded drops instead of triangular spikes.
    """
    result = call_blender("proportional_move", {
        "x": x, "y": y, "z": z, "radius": radius, "falloff": falloff,
    }, label=label)
    if result.get("success"):
        main = (f"pulled {result['handles']} handles, dragged {result['affected']} verts "
                f"r={result['radius']}m {result['falloff']} delta_world={result['delta_world']} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def random_select(fraction: float = 0.2, seed: int = 0, label: str = "") -> str:
    """
    Randomly thin the current edit-mode selection: keep `fraction` of selected verts,
    deselect the rest. Use to turn a uniform ring/loop into a sparse pattern
    (e.g., pick a handful of boundary verts on the icing to pull down as drip points).
    fraction: 0..1. seed: RNG seed for reproducibility.
    """
    result = call_blender("random_select", {"fraction": fraction, "seed": seed}, label=label)
    if result.get("success"):
        main = f"kept {result['kept']}/{result['from']} verts (seed={result['seed']})"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def jitter_vertices(amount: float = 0.005, axis: str = "NORMAL", seed: int = 0,
                    only_positive: bool = False, label: str = "") -> str:
    """
    Randomly displace selected vertices in edit mode — organic lumpy geometry in one call.
    amount: max displacement in meters (default 5mm).
    axis: NORMAL (puffs along each vert's normal — best for organic dough) | X | Y | Z | XYZ.
    seed: RNG seed for reproducibility.
    only_positive: if true, only displace outward (default both directions).

    Tutorial uses: jitter donut with axis=NORMAL for lumpy dough; jitter icing's bottom ring
    with axis=Z + only_positive (negative amount) for drippy edges.
    """
    result = call_blender("jitter_vertices", {
        "amount": amount, "axis": axis, "seed": seed, "only_positive": only_positive,
    }, label=label)
    if result.get("success"):
        main = (f"Jittered {result['verts_jittered']} verts along {result['axis']} "
                f"±{result['amount']}m (seed={result['seed']}) [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def inflate_selection(amount: float = 0.003, label: str = "") -> str:
    """
    Push selected verts outward along their normals by a fixed amount (sculpt 'Inflate' brush, one-shot).
    amount: meters to move along normal. Positive = outward, negative = inward (deflate). Default 3mm.

    For bulbous drip tips: after pulling tips down with proportional_move,
    select just the tip verts and inflate_selection(amount=0.003) to swell them into teardrop bulbs.
    """
    result = call_blender("inflate_selection", {"amount": amount}, label=label)
    if result.get("success"):
        main = f"inflated {result['verts_inflated']} verts by {result['amount']}m along normals"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def delete_geometry(mode: str = "VERT", label: str = "") -> str:
    """
    Delete the current selection in edit mode.
    mode: VERT | EDGE | FACE | ONLY_FACE | EDGE_FACE
      - VERT       — delete selected verts (and faces/edges touching them)
      - FACE       — delete selected faces (and the edges/verts only used by them)
      - ONLY_FACE  — delete just the faces, leaving an open hole bounded by their edges
      - EDGE_FACE  — delete edges + faces, leave verts
    Must be in edit mode. Pairs with select_by_axis/select_between for "carve away half".
    """
    result = call_blender("delete_geometry", {"mode": mode}, label=label)
    if result.get("success"):
        main = f"deleted ({mode}) [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def loop_cut(axis: str = "Z", cuts: int = 1, label: str = "") -> str:
    """
    Add edge loop cuts perpendicular to the given axis using bmesh.
    Must be in edit mode. axis: X | Y | Z
    Finds all edges running along that axis and subdivides them.
    label: optional name for the history log
    """
    result = call_blender("loop_cut", {"axis": axis, "cuts": cuts}, label=label)
    if result.get("success"):
        main = f"Cut {result['edges_subdivided']} edges x{result['cuts']} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_component_mode(mode: str) -> str:
    """
    Switch the mesh select component mode in Edit Mode.
    mode: VERT | EDGE | FACE
    Must be in Edit Mode. Call this before selection operations that depend on component type.
    """
    result = call_blender("set_component_mode", {"mode": mode})
    main = f"component mode → {mode}" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def grow_selection(direction: str = "GROW", steps: int = 1) -> str:
    """
    Expand or contract the current selection by one topology step per step.
    direction: GROW (add adjacent elements) | SHRINK (remove boundary elements)
    steps: number of times to grow/shrink (default 1)
    Must be in Edit Mode with something selected.
    """
    result = call_blender("grow_selection", {"direction": direction, "steps": steps})
    main = f"{direction} x{steps}" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_between(axis: str = "Z", lo: float = 0.0, hi: float = 1.0,
                   action: str = "SELECT") -> str:
    """
    Select (or deselect) vertices whose world-space position on an axis falls between lo and hi.
    axis: X | Y | Z
    lo, hi: factors from 0.0 (min extent) to 1.0 (max extent) — same scale as select_by_axis.
            e.g. lo=0.4, hi=0.6 selects the middle 20% of the mesh along the axis.
    action: SELECT | DESELECT
    Returns the actual world-space thresholds and total selected vert count.
    Replaces the verbose select_all → deselect_below → deselect_above band pattern.
    """
    result = call_blender("select_between", {"axis": axis, "lo": lo, "hi": hi, "action": action})
    if result.get("success"):
        main = (f"ok  {axis}:[{result['lo_world']} → {result['hi_world']}]"
                f"  selected={result['selected_count']}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def mark_sharp(clear: bool = False, label: str = "") -> str:
    """Mark selected edges as sharp (or clear) in edit mode. Required after SubSurf so
    boxy details (hand/foot edges, jaw line) stay crisp instead of melting into blobs.
    Switch to EDGE component mode first."""
    result = call_blender("mark_sharp", {"clear": clear}, label=label)
    if result.get("success"):
        verb = "cleared" if clear else "marked"
        main = f"{verb} sharp on {result['edges_marked']} edge(s) [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_edge_crease(weight: float = 1.0, label: str = "") -> str:
    """Set the SubSurf edge-crease weight on selected edges in edit mode.
    weight: 0..1. 0 = no crease (smooth), 1 = perfectly sharp under SubSurf.
    Use to preserve hard edges on boxy hands/feet/jaws when a SubSurf modifier is active."""
    result = call_blender("set_edge_crease", {"weight": weight}, label=label)
    if result.get("success"):
        main = f"creased {result['edges_creased']} edge(s) at weight={result['weight']}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def merge_by_distance(threshold: float = 0.001, selected_only: bool = False,
                      label: str = "") -> str:
    """Weld coincident vertices in edit mode.
    After join_objects, run this to fuse the seams between formerly-separate meshes so
    SubSurf treats the result as one continuous skin instead of N disconnected pieces.
    threshold: weld distance in meters (default 1mm).
    selected_only: only merge currently-selected verts. Default: whole mesh."""
    result = call_blender("merge_by_distance",
                          {"threshold": threshold, "selected_only": selected_only}, label=label)
    if result.get("success"):
        main = (f"merged {result['merged']} verts (before={result['verts_before']} "
                f"after={result['verts_after']}, threshold={result['threshold']}m)")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_in_sphere(center_x: float, center_y: float, center_z: float, radius: float,
                     action: str = "SELECT") -> str:
    """Select edit-mode vertices inside a world-space sphere. The right tool for localized
    region edits on a joined mesh (push out the bust, inflate the brow ridge, etc.) when
    ring-based addressing won't reach the area.

    center_x/y/z: world coords. radius: meters. action: SELECT | ADD | DESELECT.
    Pair with proportional_move or inflate_selection to sculpt the region."""
    result = call_blender("select_in_sphere", {
        "center": [center_x, center_y, center_z], "radius": radius, "action": action,
    })
    if result.get("success"):
        main = (f"{action} {result['selected']} verts within {result['radius']}m of "
                f"{result['center']}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)

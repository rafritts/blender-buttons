from server._core import mcp, call_blender, _status


@mcp.tool()
def bevel(width: float = 0.0, factor: float = 0.05, segments: int = 1, affect: str = "EDGES",
          label: str = "", target: str = "") -> str:
    """
    Bevel selected edges or vertices in edit mode.
    width: bevel size in METERS (the documented-primary unit). When > 0 this wins.
    factor: legacy — bevel size as a fraction of the object's smallest dimension (0.05 = 5%).
            Used only when width is left at 0.
    segments: edge loops added (more = smoother curve)
    affect: EDGES | VERTICES
    target: optional object name — auto-selects it, enters edit mode, exits after.
    """
    result = call_blender("bevel", {"width": width, "factor": factor, "segments": segments,
                                    "affect": affect, "target": target}, label=label)
    if result.get("success"):
        main = f"ok (offset={result.get('offset_world')}) [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def extrude(out: float = 0.0, inward: float = 0.0,
            up: float = 0.0, down: float = 0.0, left: float = 0.0, right: float = 0.0,
            forward: float = 0.0, back: float = 0.0,
            until_contact: str = "", until_length: float = 0.0,
            x: float = 0.0, y: float = 0.0, z: float = 0.0,
            label: str = "", target: str = "") -> str:
    """
    Extrude the selected geometry and translate it. Distances are in METERS.

    Direction vocabulary (all composable in one call, e.g. extrude(out=0.05, down=0.01)):
      out / inward            — along the selection's area-weighted average normal,
                                recomputed fresh from the current selection (the ~90%
                                case: "push this face out along where it points"). Works
                                on a tilted face; no need to know the world orientation.
      up/down/left/right/     — world axes (±Z / ±X / ±Y), same words as nudge.
        forward/back
    The result names the resolved 'out' direction in world-semantic words (e.g.
    "out ≈ forward, 15° above level") so you can cross-check your mental model.
    If the selection's normals cancel (a closed ring / band / full loop), 'out' is
    refused — use inflate_selection for a radial puff, or a world direction.

    Closed-loop termination (F2) — stop by a condition instead of dead reckoning:
      until_contact="floor"   — raycast along the direction and stop where the new
                                geometry first touches that object's surface.
      until_length=0.3        — extrude until the moved geometry is 0.3 m from start.
    With a termination set the distance is optional; direction still applies (default out).

    Legacy: x/y/z are a fraction of the object's bbox dimensions (pre-F1 API; prefer
    the meter-based words above).
    target: optional object name — auto-selects it, enters edit mode, exits after.
    """
    result = call_blender("extrude", {
        "out": out, "inward": inward, "up": up, "down": down, "left": left,
        "right": right, "forward": forward, "back": back,
        "until_contact": until_contact, "until_length": until_length,
        "x": x, "y": y, "z": z, "target": target}, label=label)
    if result.get("success"):
        frame = f" ({result['frame']})" if result.get("frame") else ""
        term = f" — stopped at {result['terminated_at']}" if result.get("terminated_at") else ""
        main = (f"ok translation={result.get('translation_world')}{frame}{term} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def extrude_along_curve(curve: str, segments: int = 8, taper: float = 1.0,
                        label: str = "") -> str:
    """Sweep the current edit-mode FACE selection along a curve in ONE call — the
    classic SWEEP. spline_tube sweeps a circle into a NEW object; this aims the same
    idea at the selection, in-mesh. A curved horn, a duct, a tentacle: sweep + taper
    in one call instead of N hand-rotated extrude/taper pairs.

    Must already be in edit mode with at least one FACE selected (the cross-section
    cap — e.g. a single quad). The result leaves the final cap selected so you can
    continue or close it.

    curve:    name of an existing curve object (author it with add_curve; pass a pure
              PATH — bevel_depth=0). The curve gives the SHAPE of the path, not its
              world placement: it's re-rooted so its start sits at the selection's
              centroid with its initial tangent aligned to the selection's `out`
              normal (the F1 frame — same convention as extrude(out=)).
    segments: number of arc-length-EQUIDISTANT steps along the curve (one extruded
              ring each). Equidistant rings double as bend-ready topology. Default 8.
    taper:    end-scale factor applied per-step in the cross-section's tangent plane
              (reuses scale_vertices in_plane). 1.0 = no taper (default), 0.3 = tip
              shrinks to 30%. A horn is sweep + taper together.

    Frames are carried by PARALLEL TRANSPORT (minimal twist), so the cross-section
    doesn't candy-wrap at bends. Guards (refuse, with numbers, rather than ship
    broken geometry):
      • closed-band selection (normals cancel) → no `out` to align the curve to.
      • self-intersection — where the curve's bend radius drops below the profile
        radius, the inner wall folds through itself.
    Reports steps placed, total path length (m), the F1 frame line for the initial
    direction, the profile radius, and the tightest bend radius along the path.
    """
    result = call_blender("extrude_along_curve",
                          {"curve": curve, "segments": segments, "taper": taper},
                          label=label)
    if result.get("success"):
        frame = f" ({result['frame']})" if result.get("frame") else ""
        bend = result.get("min_bend_radius")
        bend_str = f", tightest bend {bend}m" if bend is not None else ""
        main = (f"swept {result['steps']} steps along '{curve}', "
                f"path {result['path_length']}m{frame}{bend_str} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_all(action: str = "SELECT", target: str = "") -> str:
    """
    Select/deselect geometry in edit mode.
    action: SELECT | DESELECT | INVERT
    target: optional object name — auto-selects it, enters edit mode, exits after.
    """
    result = call_blender("select_all", {"action": action, "target": target})
    main = "ok" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_by_axis(axis: str = "Z", factor: float = 0.5, comparison: str = "GREATER",
                   action: str = "SELECT", extend: bool = False, target: str = "") -> str:
    """
    Select or deselect vertices in edit mode by position along an axis.
    axis: X | Y | Z
    factor: 0.0 = min extent, 1.0 = max extent of object on this axis.
            e.g. factor=0.8 comparison=GREATER selects the top 20% of the mesh.
    comparison: GREATER | LESS
    action: SELECT (replace selection) | DESELECT (remove matching verts from selection)
            Use DESELECT to select a band: select_all → deselect left → deselect right = center band.
    extend: True = ADD to the current selection instead of replacing it, so two
            calls union two regions (e.g. select both sleeves before one delete).
    target: optional object name — auto-selects it, enters edit mode, exits after.
    Returns the actual world-space threshold used.
    """
    result = call_blender("select_by_axis", {"axis": axis, "factor": factor,
                                              "comparison": comparison, "action": action,
                                              "extend": extend, "target": target})
    if result.get("success"):
        main = f"ok (threshold_world={result.get('threshold_world')})"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def move_vertices(out: float = 0.0, inward: float = 0.0,
                  up: float = 0.0, down: float = 0.0, left: float = 0.0, right: float = 0.0,
                  forward: float = 0.0, back: float = 0.0,
                  x: float = 0.0, y: float = 0.0, z: float = 0.0,
                  label: str = "", target: str = "") -> str:
    """
    Translate the selected vertices in edit mode. Distances are in METERS.

    Direction vocabulary (composable, e.g. move_vertices(out=0.02, up=0.01)):
      out / inward            — a RIGID translation along the selection's area-weighted
                                average normal (every selected vert moves by the SAME
                                delta). Distinct from inflate_selection, which moves each
                                vert along its OWN normal (puffs/spreads the patch).
      up/down/left/right/     — world axes (±Z / ±X / ±Y), same words as nudge.
        forward/back
    The result names the resolved 'out' direction in world-semantic words. If the
    selection's normals cancel (closed ring/band), 'out' is refused.

    x/y/z: explicit world-axis offsets in METERS (same units as the named directions).
    target: optional object name — auto-selects it, enters edit mode, exits after.
    Must be in edit mode with vertices selected (or provide target).
    """
    result = call_blender("move_vertices", {
        "out": out, "inward": inward, "up": up, "down": down, "left": left,
        "right": right, "forward": forward, "back": back,
        "x": x, "y": y, "z": z, "target": target}, label=label)
    if result.get("success"):
        frame = f" ({result['frame']})" if result.get("frame") else ""
        main = (f"Moved {result['verts_moved']} verts by {result['delta_world']}{frame} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def scale_vertices(in_plane: float = 0.0, x: float = 1.0, y: float = 1.0, z: float = 1.0,
                   pivot: str = "SELECTION", label: str = "", target: str = "") -> str:
    """
    Scale selected vertices in edit mode using bmesh.

    in_plane: uniform scale IN the selection's tangent plane (perpendicular to its
              average normal). 1.0 = no change, 0.5 = half, 2.0 = double. Use this on a
              tilted-surface selection where per-axis x/y/z multipliers are meaningless
              — it dilates/contracts the patch within its own surface and leaves the
              depth (normal) component untouched. Refused if the normals cancel.
              When > 0 this path is taken (ignores x/y/z).
    x/y/z: per-WORLD-axis scale multipliers (0.5 = half, 2.0 = double). Used when
           in_plane is 0.
    pivot: SELECTION (around selection center) | ORIGIN (around object origin)
    target: optional object name — auto-selects it, enters edit mode, exits after.
    Must be in edit mode with vertices selected (or provide target).
    """
    result = call_blender("scale_vertices", {"in_plane": (in_plane or None),
                                             "x": x, "y": y, "z": z, "pivot": pivot,
                                             "target": target}, label=label)
    if result.get("success"):
        frame = f" ({result['frame']})" if result.get("frame") else ""
        main = f"Scaled {result['verts_scaled']} verts{frame} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def snap_loop(handle: str = "", fit_scale: bool = True, fit_rotation: bool = False,
              label: str = "") -> str:
    """Seat the selected boundary loop onto a target opening (transform op=snap_loop /
    gaps.md G17). Operates on the LIVE edit-mode selection — be in edit mode with the
    source loop selected first. Translates its centroid onto the target handle's point;
    optionally scales rim→rim and rotates plane→plane. Returns to OBJECT mode on
    success (so the move is a clean, undoable checkpoint); re-enter edit to keep
    shaping. Note: seating a rim AT a cage opening leaves a visible gap on Subsurf'd
    meshes and does not weld — follow with edit op=bridge to actually close it."""
    result = call_blender("snap_loop", {"handle": handle, "fit_scale": fit_scale,
                                        "fit_rotation": fit_rotation}, label=label)
    if result.get("success"):
        bits = [f"snapped {result['verts']} verts onto '{result['handle']}'",
                f"moved {result['moved_cm']}cm {result.get('delta_world')}"]
        if result.get("scaled") is not None:
            bits.append(f"scaled ×{result['scaled']} "
                        f"(⌀ {result['source_diam_cm']}→{result['target_diam_cm']}cm)")
        else:
            bits.append(f"size kept (⌀ {result['source_diam_cm']}cm, "
                        f"target ⌀ {result['target_diam_cm']}cm)")
        if result.get("rotated"):
            bits.append("plane aligned")
        main = "  ".join(bits) + f" [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def proportional_move(out: float = 0.0, inward: float = 0.0,
                      up: float = 0.0, down: float = 0.0, left: float = 0.0, right: float = 0.0,
                      forward: float = 0.0, back: float = 0.0,
                      x: float = 0.0, y: float = 0.0, z: float = 0.0,
                      radius: float = 0.01, falloff: str = "SMOOTH",
                      connected: bool = False, freeze: str = "",
                      label: str = "", target: str = "") -> str:
    """
    Move selected verts with a falloff — drags nearby verts along (proportional editing).
    Selected verts move full amount; verts at radius edge don't move at all.

    Direction vocabulary (METERS, composable — same words as move_vertices/extrude):
      out / inward            — along the selection's area-weighted average normal.
      up/down/left/right/     — world axes (±Z / ±X / ±Y).
        forward/back
    Legacy: x/y/z are a fraction of object dims (pre-F1 API).

    radius: falloff radius in meters (default 1cm).
    falloff: SMOOTH (default — rounded shape) | LINEAR | SPHERE | SHARP | ROOT | CONSTANT.

    Topology-aware shaping (G60):
    connected: measure the falloff as GEODESIC distance along edges, not straight-line —
               so a big pull can't drag a different shell (or anything merely near in
               space) it isn't connected to. Default false (Euclidean, original).
    freeze:    a handle name whose verts are held RIGID and (in connected mode) wall off
               the falloff. Use it to shape one part while holding a neighbour still.

    For icing drips: select sparse boundary verts, proportional_move(down=0.01, radius=0.005)
    gives bulbous rounded drops instead of triangular spikes.
    target: optional object name — enters edit mode on it first (acts on its live
            selection), exits after. Empty = the active mesh.
    """
    result = call_blender("proportional_move", {
        "out": out, "inward": inward, "up": up, "down": down, "left": left,
        "right": right, "forward": forward, "back": back,
        "x": x, "y": y, "z": z, "radius": radius, "falloff": falloff,
        "connected": connected, "freeze": freeze,
        "target": target,
    }, label=label)
    if result.get("success"):
        frame = f" ({result['frame']})" if result.get("frame") else ""
        mode = " geodesic" if result.get("connected") else ""
        frz = f" froze {result['frozen']}" if result.get("frozen") else ""
        main = (f"pulled {result['handles']} handles, dragged {result['affected']} verts"
                f"{mode}{frz} "
                f"r={result['radius']}m {result['falloff']} delta_world={result['delta_world']}{frame} "
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
                    only_positive: bool = False, label: str = "", target: str = "") -> str:
    """
    Randomly displace vertices in edit mode — organic lumpy geometry in one call.
    amount: max displacement in meters (default 5mm).
    axis: NORMAL (puffs along each vert's normal — best for organic dough) | X | Y | Z | XYZ.
    seed: RNG seed for reproducibility.
    only_positive: if true, only displace outward (default both directions).
    target: mesh to jitter (empty=active). Like loop_cut, passing target auto-enters
            edit mode and exits after; with no narrowed selection it jitters the WHOLE
            mesh, so a one-call "lump up the donut" needs no manual mode/select (G28).

    Tutorial uses: jitter donut with axis=NORMAL for lumpy dough; jitter icing's bottom ring
    with axis=Z + only_positive (negative amount) for drippy edges.
    """
    result = call_blender("jitter_vertices", {
        "amount": amount, "axis": axis, "seed": seed, "only_positive": only_positive,
        "target": target,
    }, label=label)
    if result.get("success"):
        main = (f"Jittered {result['verts_jittered']} verts along {result['axis']} "
                f"±{result['amount']}m (seed={result['seed']}) [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def inflate_selection(amount: float = 0.003, label: str = "", target: str = "") -> str:
    """
    Push selected verts outward along their normals by a fixed amount (sculpt 'Inflate' brush, one-shot).
    amount: meters to move along normal. Positive = outward, negative = inward (deflate). Default 3mm.

    For bulbous drip tips: after pulling tips down with proportional_move,
    select just the tip verts and inflate_selection(amount=0.003) to swell them into teardrop bulbs.
    target: optional object name — enters edit mode on it first (acts on its live
            selection), exits after. Empty = the active mesh.
    """
    result = call_blender("inflate_selection", {"amount": amount, "target": target}, label=label)
    if result.get("success"):
        main = f"inflated {result['verts_inflated']} verts by {result['amount']}m along normals"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def separate_selection(new_name: str = "", label: str = "", target: str = "") -> str:
    """
    Separate the current edit-mode selection into a NEW object (the 'P → Selection'
    shortcut). The split-off geometry leaves the source mesh (source gets a hole).

    new_name: optional name for the new object (else Blender appends '.001').
    target: optional object name — enters edit mode on it first so the stored
            selection is live, then separates. Empty = the active object (must
            already be in edit mode).

    Returns the new object's name. Pair with select_in_sphere/by_axis to lift a
    patch off a mesh (e.g. for shape transfer), then object op=join to weld it back.
    """
    result = call_blender("separate_selection",
                          {"new_name": new_name or None, "target": target or None},
                          label=label)
    if result.get("success"):
        main = f"separated → {result.get('new_object', '?')} (from {result.get('source', '?')})"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def delete_geometry(mode: str = "VERT", label: str = "", target: str = "") -> str:
    """
    Delete the current selection in edit mode.
    mode: VERT | EDGE | FACE | ONLY_FACE | EDGE_FACE
      - VERT       — delete selected verts (and faces/edges touching them)
      - FACE       — delete selected faces (and the edges/verts only used by them)
      - ONLY_FACE  — delete just the faces, leaving an open hole bounded by their edges
      - EDGE_FACE  — delete edges + faces, leave verts
    target: optional object name — auto-selects it, enters edit mode, exits after.
    Must be in edit mode. Pairs with select_by_axis/select_between for "carve away half".
    """
    result = call_blender("delete_geometry", {"mode": mode, "target": target}, label=label)
    if result.get("success"):
        main = f"deleted ({mode}) [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def loop_cut(axis: str = "Z", cuts: int = 1, label: str = "", target: str = "") -> str:
    """
    Add edge loop cuts perpendicular to the given axis using bmesh.
    Finds edges running along that axis and inserts loops crossing it.
    axis: X | Y | Z — edges running along this axis are subdivided,
          producing loops that sit at fixed positions on that axis.
          e.g. axis=Z → horizontal loops; axis=X → vertical loops at constant X.

    SELECTION-SCOPED: if you are already in edit mode with verts selected, only edges
    inside that selection are cut — add a support loop to ONE limb/region without
    ribbing the whole mesh. With nothing selected (incl. the target= path, which
    deselects on entry) it cuts the whole mesh, as before.

    target: optional object name — auto-selects it, enters edit mode, exits after.
            (Note: this clears the selection, so it cuts the WHOLE mesh. To scope a
            cut, enter edit mode yourself and select the region first.)
    Must be in edit mode (or provide target).
    """
    result = call_blender("loop_cut", {"axis": axis, "cuts": cuts, "target": target}, label=label)
    if result.get("success"):
        scope = "in selection" if result.get("scoped_to_selection") else "whole mesh"
        region = result.get("region", "")
        span = result.get("span_world")
        span_str = f", {axis} span {span}" if span else ""
        main = (f"Cut {result['edges_subdivided']} edges across {result.get('loops','?')} "
                f"loop(s) — {region} ({scope}){span_str} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def subdivide_selection(cuts: int = 1, smooth: float = 0.0, label: str = "",
                        target: str = "") -> str:
    """Locally subdivide the SELECTED region — add sculptable resolution exactly where
    you select, with no global edge loops (unlike loop_cut) and no shape-key block
    (unlike apply-Subsurf / dyntopo). The 'add resolution here' affordance for a coarse
    patch (e.g. a ~5-face breast region) before sculpting it.

    cuts:   new cuts per edge (1 = quarter the faces, 2 = ninth, …).
    smooth: 0 = flat (keeps the cage shape, just denser) … ~1 = round the new verts
            toward the Catmull-Clark limit surface. A touch of smooth pre-curves a
            region you're about to push out.
    target: optional object name — auto-selects it, enters edit mode, exits after.
            (Note: target= clears the selection on entry, so select the region first
            in an explicit edit session — subdivide needs a selection to act on.)

    Where the patch meets unselected faces the boundary fans into triangles (normal
    Subdivide behavior) — fine for sculpt clay; retopo later for deformation flow.
    Must be in edit mode with a selection."""
    result = call_blender("subdivide_selection",
                          {"cuts": cuts, "smooth": smooth, "target": target}, label=label)
    if result.get("success"):
        main = (f"subdivided {result['edges_subdivided']} edge(s) ×{result['cuts']} "
                f"(smooth {result['smooth']}) — +{result['verts_added']} verts "
                f"→ {result['verts_total']} verts / {result['faces_total']} faces "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def assign_weight(group: str, weight: float = 1.0, mode: str = "REPLACE",
                  label: str = "") -> str:
    """Assign a vertex-group weight to the CURRENT edit-mode selection — the
    deform-side sibling of select_by_axis / select_in_sphere.

    Select verts (axis band, sphere, ring), then bind just those to a named group at
    a chosen weight. The general primitive the all-or-nothing binders lacked:
    weight_to_bone rigid-binds the WHOLE mesh, auto_weight heat-solves the WHOLE mesh;
    neither can say "these verts → this group, blended N%". A group named after a bone
    is read by an Armature modifier as that bone's influence; an arbitrary group feeds
    a MeshDeform / mask modifier's vertex_group slot.

    group:  vertex-group / bone name (created on the mesh if absent).
    weight: 0..1 (default 1.0).
    mode:   REPLACE (set to weight) | ADD (add, clamp 1) | SUBTRACT (subtract, clamp 0).
            Other groups are untouched — assign partial weights to two groups to blend
            a bridge between two differently-driven meshes (e.g. a shoulder stub
            torso-bound at the root, arm-bound at the tip).

    Must already be in edit mode with verts selected. Example, blend a bridge:
      select_in_sphere(...root...); assign_weight("spine", 1.0)
      select_in_sphere(...tip...);  assign_weight("upper_arm.L", 1.0)
    """
    result = call_blender("assign_weight",
                          {"group": group, "weight": weight, "mode": mode}, label=label)
    if result.get("success"):
        made = " (new group)" if result.get("group_created") else ""
        main = (f"{result['mode']} weight {result['weight']} → group '{result['group']}'"
                f"{made} on {result['verts_assigned']} vert(s) [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_boundary(action: str = "SELECT", from_selection: bool = True,
                    target: str = "") -> str:
    """Select the OPEN-BOUNDARY edges of a mesh — the edges of a hole or rim.

    The only way to grab a mesh rim: a tilted collar / sleeve / armhole loop can't be
    isolated by axis bands (a band always drags in adjacent faces). Switches to EDGE
    component mode, so the selected rim can then be fed to set_edge_crease(1.0) (stop a
    cut boundary curling under SubSurf) or mark_sharp, or extruded into an inset/hem.

    from_selection: if True (default) and verts are already selected, restrict to
                    boundary edges touching that selection — grow a rim from a seed
                    region. With nothing selected, selects EVERY open boundary.
    action: SELECT (replace) | ADD | DESELECT.
    target: optional object name — auto-selects it, enters edit mode, exits after.

    Example — crease a freshly-cut collar so SubSurf keeps the hem crisp:
      select_boundary(); set_edge_crease(1.0)
    """
    result = call_blender("select_boundary",
                          {"action": action, "from_selection": from_selection,
                           "target": target})
    if result.get("success"):
        seed = "from seed selection" if result.get("from_seed") else "all rims"
        main = (f"{result['action']} {result['boundary_edges']} boundary edge(s) "
                f"({seed}) — {result.get('region','')}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def select_limb(which: str = "", extend: bool = False, target: str = "") -> str:
    """Select a whole protrusion (sleeve/limb/finger/spout) anchored to the mesh's
    own topology — no coordinates. Consumes the structural handles `feel structure`
    surfaces. which: cap-region substring filter (e.g. 'top-left'); empty = every
    protrusion. extend: union onto the current selection. target: optional object name
    — auto-selects it, enters edit mode, exits after. Then `edit delete` removes it,
    leaving the base ring as a clean opening (the armhole). Must be in Edit Mode."""
    result = call_blender("select_limb", {"which": which or None, "extend": extend,
                                          "target": target})
    if result.get("success"):
        limbs = ", ".join(result.get("limbs", []))
        bases = ", ".join(result.get("base_regions", []))
        main = (f"selected {result['selected_count']} vert(s) — limb(s) capped @ {limbs}; "
                f"cut line at base @ {bases}. delete to remove (base ring left as opening).")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_component_mode(mode: str, target: str = "") -> str:
    """
    Switch the mesh select component mode in Edit Mode.
    mode: VERT | EDGE | FACE
    target: optional object name — auto-selects it, enters edit mode, exits after.
    Must be in Edit Mode. Call this before selection operations that depend on component type.
    """
    result = call_blender("set_component_mode", {"mode": mode, "target": target})
    main = f"component mode → {mode}" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def grow_selection(direction: str = "GROW", steps: int = 1, target: str = "") -> str:
    """
    Expand or contract the current selection by one topology step per step.
    direction: GROW (add adjacent elements) | SHRINK (remove boundary elements)
    steps: number of times to grow/shrink (default 1)
    target: optional object name — auto-selects it, enters edit mode, exits after.
    Must be in Edit Mode with something selected.
    """
    result = call_blender("grow_selection", {"direction": direction, "steps": steps,
                                             "target": target})
    main = f"{direction} x{steps}" if result.get("success") else result.get("error", "failed")
    return main + _status(result)


def flood_to_crease(angle: float = 25.0, max_verts: int = 20000) -> str:
    """G43 — region-coherent selection. Flood out from the current seed selection across
    the surface, halting at creases (dihedral ≥ angle) and mesh boundaries, so a feature
    fills to its natural edge instead of a guessed box. Tune `angle` down for subtler
    organic creases. Confirm capture with feel op=verify afterward."""
    result = call_blender("flood_to_crease", {"angle": angle, "max_verts": max_verts})
    if not result.get("success"):
        return result.get("note") or result.get("error", "failed")
    main = (f"flooded {result['seed_verts']} seed → {result['selected']} verts "
            f"(crease ≥{result['angle_deg']}°)")
    if result.get("capped"):
        main += f"\n  ⚠ {result['note']}"
    return main + _status(result)


@mcp.tool()
def select_between(axis: str = "Z", lo: float = 0.0, hi: float = 1.0,
                   action: str = "SELECT", extend: bool = False, target: str = "") -> str:
    """
    Select (or deselect) vertices whose world-space position on an axis falls between lo and hi.
    axis: X | Y | Z
    lo, hi: factors from 0.0 (min extent) to 1.0 (max extent) — same scale as select_by_axis.
            e.g. lo=0.4, hi=0.6 selects the middle 20% of the mesh along the axis.
    action: SELECT | DESELECT
    extend: True = ADD to the current selection instead of replacing it.
    target: optional object name — auto-selects it, enters edit mode, exits after.
    Returns the actual world-space thresholds and total selected vert count.
    Replaces the verbose select_all → deselect_below → deselect_above band pattern.
    """
    result = call_blender("select_between", {"axis": axis, "lo": lo, "hi": hi,
                                             "action": action, "extend": extend,
                                             "target": target})
    if result.get("success"):
        main = (f"ok  {axis}:[{result['lo_world']} → {result['hi_world']}]"
                f"  selected={result['selected_count']}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def mark_sharp(clear: bool = False, label: str = "", target: str = "") -> str:
    """Mark selected edges as sharp (or clear) in edit mode. Required after SubSurf so
    boxy details (hand/foot edges, jaw line) stay crisp instead of melting into blobs.
    Switch to EDGE component mode first.
    target: optional object name — auto-selects it, enters edit mode, exits after."""
    result = call_blender("mark_sharp", {"clear": clear, "target": target}, label=label)
    if result.get("success"):
        verb = "cleared" if clear else "marked"
        main = f"{verb} sharp on {result['edges_marked']} edge(s) [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_edge_crease(weight: float = 1.0, label: str = "", target: str = "") -> str:
    """Set the SubSurf edge-crease weight on selected edges in edit mode.
    weight: 0..1. 0 = no crease (smooth), 1 = perfectly sharp under SubSurf.
    Use to preserve hard edges on boxy hands/feet/jaws when a SubSurf modifier is active.
    target: optional object name — auto-selects it, enters edit mode, exits after."""
    result = call_blender("set_edge_crease", {"weight": weight, "target": target}, label=label)
    if result.get("success"):
        main = f"creased {result['edges_creased']} edge(s) at weight={result['weight']}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def merge_by_distance(threshold: float = 0.001, selected_only: bool = False,
                      label: str = "", target: str = "") -> str:
    """Weld coincident vertices in edit mode.
    After join_objects, run this to fuse the seams between formerly-separate meshes so
    SubSurf treats the result as one continuous skin instead of N disconnected pieces.
    threshold: weld distance in meters (default 1mm).
    selected_only: only merge currently-selected verts. Default: whole mesh.
    target: optional object name — auto-selects it, enters edit mode, exits after."""
    result = call_blender("merge_by_distance",
                          {"threshold": threshold, "selected_only": selected_only,
                           "target": target}, label=label)
    if result.get("success"):
        main = (f"merged {result['merged']} verts (before={result['verts_before']} "
                f"after={result['verts_after']}, threshold={result['threshold']}m)")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def bridge(a: str = "", b: str = "", label: str = "", bridge_cuts: int = 0,
           smoothness: float = 1.0, interpolation: str = "path",
           profile: float = 0.0, twist: int = 0) -> str:
    """Weld two open boundary loops into a continuous surface — the bridge-edge-loops
    primitive (SPEC-07 Phase 5, closing gaps.md G10). `a` and `b` are two boundary
    handles (mint them with `feel op=assembly`); their rims get selected and bridged.

    SAME-OBJECT only — `edit` acts on one mesh. Two parts on separate objects: run
    `object op=join names=A,B` first, then bridge the loops on the joined mesh. Keyed/
    rigged meshes are refused (adding faces corrupts the shape-key block / deform bind).
    Bridging is symmetric, so a/b order doesn't matter.

    Curvature dials (G58 — Bridge Edge Loops pass-through). `bridge_cuts=0` is the
    original straight single-ring weld; raise it to subdivide the span so it can bow.
    `smoothness` sets the tangent bow of those cuts, `interpolation` (linear|path|
    surface) how they follow the rims, `profile` bulges the cross-section out, `twist`
    rotates the rim-to-rim vertex mapping (in verts) to kill the spiral when the two
    rims face different directions."""
    result = call_blender("bridge_handles", {
        "a": a, "b": b, "cuts": bridge_cuts, "smoothness": smoothness,
        "interpolation": interpolation, "profile": profile, "twist": twist,
    }, label=label)
    if result.get("success"):
        br = result.get("bridge", {})
        shape = (f", {br['cuts']} cuts/sm{br['smoothness']:g}/{br['interpolation'].lower()}"
                 + (f"/twist{br['twist']}" if br.get('twist') else "")
                 + (f"/prof{br['profile']:g}" if br.get('profile') else "")
                 ) if br.get("cuts") else ""
        main = (f"bridged {result['a']} ↔ {result['b']} on {result['owner']} — "
                f"+{result['faces_created']} faces ({result['edges_bridged']} edge pairs)"
                f"{shape} → {result['faces_total']} faces [{result.get('op_id','')}]")
        # G9 follow-up: a fresh weld usually wants a seam-weld + a lint pass.
        main += ("\n  → next: `edit op=merge target=" + result['owner']
                 + "` to weld any coincident seam verts · `feel op=mesh target="
                 + result['owner'] + "` to lint the new faces (normals / non-manifold)")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def connect(a: str = "", b: str = "", style: str = "arc", tension: float = -1.0,
            sections: int = 12, profile: str = "match", weld: bool = True,
            name: str = "connector", label: str = "") -> str:
    """Weld two open rims with a swept, tapered, tangent-continuous tube — the
    geometry-bound connector (SPEC-10, closing gaps.md G59/G60/G61/G65). `a` and `b`
    are two boundary handles (mint with `feel op=assembly`); the connector binds to
    them, not to coordinates.

    Unlike `edit op=bridge` (one ring of shortest-path quads with curvature dials),
    connect leaves each opening along its OWN OUTWARD NORMAL (G1 continuity at the
    seam), sweeps a hollow cross-section that matches each rim's vertex count 1:1 and
    tapers radius/shape between them on a minimum-twist frame (no crease, no spiral),
    and fuses both ends into one watertight mesh. The thing the agent could not
    express: a curve that leaves the pipe the way the pipe points.

    a, b:     the two boundary handles to connect (order-independent).
    style:    arc (default) | s_curve | direct | slack. arc/s_curve/slack honour the
              openings' normals — a single arc emerges when they face each other, an S
              when they face the same way. direct relaxes toward the straight chord.
    tension:  0..1 — how much it bows (control-handle length as a fraction of the gap).
              -1 (default) uses the style's default.
    sections: rings along the span (length resolution). Default 12.
    profile:  match (default — sweep each rim's own cross-section, tapering between) |
              round (force a clean matched circle mid-span).
    weld:     fuse both ends into the owning shell(s) → one watertight manifold
              (default). False leaves the connector as a separate mesh.
    name:     connector object name (shows only when weld=False; a weld keeps a's owner).

    Cross-object is fine — connect joins the owners itself (re-homing their handles).
    Keyed/rigged meshes and unequal rim vertex counts are refused (the honest v1 limit:
    re-ring one opening to match first). The status block carries the G65 quality reads:
    length, min bend radius, per-seam tangent-vs-normal angle, and sweep feasibility."""
    result = call_blender("connect_handles", {
        "a": a, "b": b, "style": style, "tension": tension, "sections": sections,
        "profile": profile, "weld": weld, "name": name,
    }, label=label)
    if result.get("success"):
        seams = (f"seams {result['seam_angle_a_deg']}°/{result['seam_angle_b_deg']}° "
                 f"off-normal")
        bend = result.get("min_bend_radius_cm")
        bend_str = f", tightest bend {bend}cm" if bend is not None else ""
        twist = (f", twist {result['twist_offset']}"
                 + ("/reversed" if result.get("winding") == "reversed" else "")) \
            if result.get("twist_offset") or result.get("winding") == "reversed" else ""
        if result.get("welded"):
            seam = result.get("seam_merged", 0)
            head = (f"connected {result['a']} ↔ {result['b']} → {result['result_object']} "
                    f"(welded, {seam} seam verts fused)")
        else:
            head = (f"connected {result['a']} ↔ {result['b']} → {result['connector']} "
                    f"(unwelded)")
        main = (f"{head} — {result['style']} t{result['tension']}, {result['sides']}-side, "
                f"{result['length_cm']}cm, taper ⌀{result['diam_a_cm']}→{result['diam_b_cm']}cm"
                f"{bend_str}{twist}; {seams} [{result.get('op_id','')}]")
        if result.get("rehomed_handles"):
            main += f"\n  re-homed {len(result['rehomed_handles'])} handle(s) onto the join"
        if result.get("warning"):
            main += f"\n  ⚠ {result['warning']}"
        if result.get("welded"):
            main += ("\n  → next: `feel op=mesh target=" + result['result_object']
                     + "` to lint the weld (watertight / normals) · welded = committed; "
                     "re-run connect to reshape")
        else:
            main += ("\n  → next: tune it with `edit op=reshape name=" + result['connector']
                     + " tension=…` (re-evaluates against the live handles); "
                     "re-run with weld=true to commit")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def strands(a: str = "", b: str = "", count: int = 0, style: str = "arc",
            tension: float = -1.0, sections: int = 24, sides: int = 8,
            jitter: float = 0.0, seed: int = 0, radius: float = -1.0,
            name: str = "strands", label: str = "") -> str:
    """Generate N thin tubes between two rims — the expressive multi-strand tier
    (SPEC-10 Phase 5). "A sequence of crazy curves" as cheap relational generation:
    variety from a `count` + a `seed`, not K hand-placed Béziers.

    Distributes `count` strands around the two openings, each leaving along the
    opening's OWN outward normal (G1, like `edit op=connect`), with a seeded coherent
    `jitter` bowing each strand its own way. Emitted as ONE editable mesh object
    (capped tubes, not welded into the shells); it stores its recipe, so
    `edit op=reshape name=<strands>` re-bakes the whole bundle against the live
    handles. Re-run with a new `seed` for a different bundle from the same inputs.

    a, b:     the two boundary handles to span (mint with feel op=assembly).
    count:    number of strands (>=2).
    style:    arc (default) | s_curve | direct | slack.
    tension:  0..1 how much each strand bows; -1 (default) = the style default.
    sections: rings along each strand (default 24). sides: cross-section verts (8).
    jitter:   0..1 coherent midspan waywardness (0 = a clean parallel fan).
    seed:     RNG seed — same seed reproduces the same bundle.
    radius:   strand tube radius (m); -1 (default) = auto-pack to the rim + count."""
    result = call_blender("make_strands", {
        "a": a, "b": b, "count": count, "style": style, "tension": tension,
        "sections": sections, "sides": sides, "jitter": jitter, "seed": seed,
        "radius": radius, "name": name,
    }, label=label)
    if result.get("success"):
        bend = result.get("min_bend_radius_cm")
        bend_str = f", tightest bend {bend}cm" if bend is not None else ""
        wind = ", reversed winding" if result.get("winding") == "reversed" else ""
        main = (f"strands {result['a']} ↔ {result['b']} → {result['object']} — "
                f"{result['n_strands']}×{result['sides']}-side {result['style']} "
                f"t{result['tension']}, jitter {result['jitter']} (seed {result['seed']}), "
                f"r={result['strand_radius_cm']}cm each, avg {result['avg_length_cm']}cm, "
                f"taper ⌀{result['diam_a_cm']}→{result['diam_b_cm']}cm{bend_str}{wind} "
                f"[{result.get('op_id','')}]")
        if result.get("warning"):
            main += f"\n  ⚠ {result['warning']}"
        main += ("\n  → next: tune with `edit op=reshape name=" + result['object']
                 + " tension=…` (re-evaluates against the live handles); re-run "
                   "op=strands with a new seed for a different bundle")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def reshape(name: str = "", tension: float = -1.0, label: str = "") -> str:
    """Re-evaluate an UNWELDED connector (or a strands bundle) against its live handles
    (SPEC-10 Phase 4/5).

    A weld=False connector — or any `edit op=strands` object — stored its recipe (the
    two handles + style/tension/…). reshape re-reads the handles' CURRENT positions and
    re-bakes the geometry in place — so if you deform or move a pipe, the connector or
    the whole strand bundle follows. The one editable knob is `tension` (more/less arc);
    -1 keeps the stored value.

    Welded connectors are committed (the rims are fused into the shell, nothing live
    to re-evaluate) — re-run edit op=connect to reshape those.

    name:    the connector/strands object to re-evaluate.
    tension: 0..1 — override the bow; -1 (default) keeps the stored tension."""
    result = call_blender("reshape_connector", {"name": name, "tension": tension},
                          label=label)
    if result.get("success"):
        if result.get("kind") == "strands":
            bend = result.get("min_bend_radius_cm")
            bend_str = f", tightest bend {bend}cm" if bend is not None else ""
            main = (f"reshaped {result['name']} — {result['n_strands']}×"
                    f"{result['sides']}-side {result['style']} t{result['tension']}, "
                    f"jitter {result['jitter']}, r={result['strand_radius_cm']}cm, "
                    f"avg {result['avg_length_cm']}cm{bend_str} "
                    f"(re-evaluated against live {result['a']}/{result['b']}) "
                    f"[{result.get('op_id','')}]")
        else:
            seams = (f"seams {result['seam_angle_a_deg']}°/{result['seam_angle_b_deg']}° "
                     f"off-normal")
            bend = result.get("min_bend_radius_cm")
            bend_str = f", tightest bend {bend}cm" if bend is not None else ""
            main = (f"reshaped {result['name']} — {result['style']} t{result['tension']}, "
                    f"{result['sides']}-side, {result['length_cm']}cm, "
                    f"taper ⌀{result['diam_a_cm']}→{result['diam_b_cm']}cm{bend_str}; {seams} "
                    f"(re-evaluated against live {result['a']}/{result['b']}) "
                    f"[{result.get('op_id','')}]")
        if result.get("warning"):
            main += f"\n  ⚠ {result['warning']}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def resample(a: str = "", count: int = 0, depth: float = -1.0, label: str = "") -> str:
    """Resample a boundary rim to a target vertex count (SPEC-10 — lifts connect's 1:1
    limit). Builds a short arc-length transition collar out to a fresh `count`-vert
    loop and re-homes the handle onto it, so two rims that didn't match (e.g. 16 vs 32)
    can be equalised in one call and `edit op=connect` stays a clean 1:1 weld.

    a:     the boundary handle whose rim to resample (mint with feel op=assembly).
    count: target vertex count (>=3).
    depth: collar length along the rim's outward normal (m); -1 = auto (~5% of the rim
           radius). Extends the opening by this much; the new rim keeps its diameter."""
    result = call_blender("resample_loop", {"a": a, "count": count, "depth": depth},
                          label=label)
    if result.get("success"):
        if result.get("noop"):
            main = (f"'{result['handle']}' already {result['to_count']} verts — no change "
                    f"[{result.get('op_id','')}]")
        else:
            main = (f"resampled {result['handle']} {result['from_count']}→"
                    f"{result['to_count']} verts (collar {result['depth_cm']}cm, "
                    f"⌀{result['rim_diam_cm']}cm) — handle re-baselined "
                    f"[{result.get('op_id','')}]")
            main += (f"\n  → next: `edit op=connect a=<other rim> b={result['handle']}` — "
                     f"the rims now match for a clean 1:1 weld")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_in_sphere(center_x: float, center_y: float, center_z: float, radius: float,
                     action: str = "SELECT", extend: bool = False, target: str = "") -> str:
    """Select edit-mode vertices inside a world-space sphere. The right tool for localized
    region edits on a joined mesh (push out the bust, inflate the brow ridge, etc.) when
    ring-based addressing won't reach the area.

    center_x/y/z: world coords. radius: meters. action: SELECT | ADD | DESELECT.
    extend: True = ADD to the current selection (same as action=ADD), for parity
            with select_by_axis / select_between.
    target: optional object name — auto-selects it, enters edit mode, exits after.
    Pair with proportional_move or inflate_selection to sculpt the region."""
    result = call_blender("select_in_sphere", {
        "center": [center_x, center_y, center_z], "radius": radius, "action": action,
        "extend": extend, "target": target,
    })
    if result.get("success"):
        main = (f"{action} {result['selected']} verts within {result['radius']}m of "
                f"{result['center']}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def relax_selection(iterations: int = 5, factor: float = 0.5, reproject: bool = True,
                    label: str = "", target: str = "") -> str:
    """G49 — RELAX the selected verts: even out their spacing over the existing form
    without changing its shape (Laplacian smooth + reproject onto the pre-relax surface).
    The redistribute primitive for stretched/bunched quads at a feature — moves verts
    ALONG the surface, not through space.

    iterations: smoothing passes (default 5). factor: 0..1 step per pass (default 0.5).
    reproject: snap back onto the original surface each pass (default True; False = a
               plain smooth that also relaxes the shape).
    target: optional object name — enters edit mode on it first, exits after."""
    result = call_blender("relax_selection", {
        "iterations": iterations, "factor": factor, "reproject": reproject,
        "target": target}, label=label)
    if result.get("success"):
        main = (f"relaxed {result['verts_relaxed']} verts ×{result['iterations']} "
                f"(reproject {result['reprojected']}) — avg drift {result['avg_drift_cm']}cm "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def slide_selection(out: float = 0.0, inward: float = 0.0,
                    up: float = 0.0, down: float = 0.0, left: float = 0.0, right: float = 0.0,
                    forward: float = 0.0, back: float = 0.0,
                    label: str = "", target: str = "") -> str:
    """G49 — SLIDE the selected verts ALONG the surface: move them by the metre direction
    words, then reproject onto the pre-slide surface so the net motion is tangential (the
    verts travel over the form; its shape is unchanged). Relocate a pole/loop to a
    feature's high point without denting the mesh. Keep the slide small vs. the curvature.

    Directions (METERS, composable): out/inward (selection normal), up/down/left/right/
    forward/back (world axes).
    target: optional object name — enters edit mode on it first, exits after."""
    result = call_blender("slide_selection", {
        "out": out, "inward": inward, "up": up, "down": down, "left": left,
        "right": right, "forward": forward, "back": back, "target": target}, label=label)
    if result.get("success"):
        frame = f" ({result['frame']})" if result.get("frame") else ""
        main = (f"slid {result['verts_slid']} verts along surface — moved "
                f"{result['avg_slide_cm']}cm{frame} [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def poke_faces(offset: float = 0.0, label: str = "", target: str = "") -> str:
    """G50 — POKE the selected faces: fan each out from a new centre vertex, minting a
    pole (the centre's valence = the face's side count). The way to AUTHOR a radial centre
    where the form wants one and there's no pole — e.g. under a dome. Be in FACE mode with
    faces selected. offset: push the new centre along the face normal (m). The new centre
    verts are left selected.
    target: optional object name — enters edit mode on it first, exits after."""
    result = call_blender("poke_faces", {"offset": offset, "target": target}, label=label)
    if result.get("success"):
        main = (f"poked {result['faces_poked']} face(s) → {result['poles_created']} "
                f"pole(s) [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def inset_faces(thickness: float = 0.01, depth: float = 0.0, individual: bool = False,
                label: str = "", target: str = "") -> str:
    """G50 — INSET the selected faces: ring them with a new band of faces (shrink a copy
    inward). Adds an edge loop around a region so a feature can be defined/tightened. Be
    in FACE mode with faces selected.
    thickness: inset distance (m). depth: push in/out along the normal (m).
    individual: inset each face separately vs. the region as a whole.
    target: optional object name — enters edit mode on it first, exits after."""
    result = call_blender("inset_faces", {"thickness": thickness, "depth": depth,
                                          "individual": individual, "target": target},
                          label=label)
    if result.get("success"):
        main = (f"inset {result['faces_inset']} face(s) ({result['mode']}) → "
                f"+{result['ring_faces']} ring faces [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def grid_fill(span: int = 0, offset: int = 0, label: str = "", target: str = "") -> str:
    """G50 — GRID FILL: fill a selected closed edge loop with a regular quad grid (clean
    four-sided flow across a hole/region, not a fan). The patch primitive for repairing or
    re-flowing topology. Be in edit mode with ONE closed boundary loop (even vert count)
    selected. span/offset tune the grid layout.
    target: optional object name — enters edit mode on it first, exits after."""
    result = call_blender("grid_fill", {"span": span, "offset": offset, "target": target},
                          label=label)
    if result.get("success"):
        main = (f"grid-filled +{result['faces_added']} faces → {result['faces_total']} "
                f"total [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


def verify_selection(steps: int = 1) -> str:
    """G48 — capture verification on the live edit-mode selection. Read-only (perturbs
    then restores), so no status block. Grows + shrinks the selection and reports the
    centroid/extent drift + a captured/clipping/slack verdict + the bounds aspect."""
    result = call_blender("verify_selection", {"steps": steps})
    if not result.get("success"):
        return result.get("note") or result.get("error", "failed")
    g = result["grow"]; s = result["shrink"]; b = result["bounds"]
    lines = [
        f"capture check ({result['selected']} verts, ±{result['steps']} ring):",
        f"  grow   → +{g['verts'] - result['selected']} verts  "
        f"centroid {g['centroid_shift_cm']}cm  extent {g['extent_change_pct']:+}%",
        f"  shrink → {s['verts'] - result['selected']} verts  "
        f"centroid {s['centroid_shift_cm']}cm  extent {s['extent_change_pct']:+}%",
        f"  bounds  W×D×H = {b['W_x_cm']}×{b['D_y_cm']}×{b['H_z_cm']}cm  "
        f"(longest: {result['longest_axis']})",
    ]
    for v in result["verdict"]:
        lines.append(f"  • {v}")
    return "\n".join(lines)

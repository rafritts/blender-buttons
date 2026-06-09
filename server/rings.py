from server._core import mcp, call_blender, _status


@mcp.tool()
def get_rings(axis: str = "Z", target: str = "") -> str:
    """
    List the edge-loop rings of the active mesh along an axis.

    A ring is a set of vertices that share the same world-space coordinate on the axis.
    Rings are returned sorted by position ascending; index 0 = lowest, last = highest.
    Use the index with select_ring / taper_end / taper_section to address geometry by topology,
    not by world coordinates.

    target: optional object name — auto-selects it, enters edit mode, exits after.
    Must be in edit mode (or provide target).
    """
    result = call_blender("get_rings", {"axis": axis, "target": target})
    if not result.get("success"):
        return result.get("error", "failed")
    rings = result["rings"]
    lines = [f"{result['ring_count']} rings along {axis}:"]
    for r in rings:
        lines.append(f"  [{r['index']:>2}]  pos={r['position_world']:+.4f}  verts={r['verts']}")
    return "\n".join(lines) + _status(result)


@mcp.tool()
def select_ring(axis: str = "Z", index: int = 0, action: str = "SELECT",
                target: str = "") -> str:
    """
    Select the vertices belonging to a specific ring along an axis.

    index: 0 = first (lowest on axis), -1 = last (highest). Negative indices wrap.
    action: SELECT (replace current selection) | ADD (add to selection) | DESELECT (remove)
    target: optional object name — auto-selects it, enters edit mode, exits after.

    Call get_rings first to see the available indices. Must be in edit mode (or provide target).
    """
    result = call_blender("select_ring", {"axis": axis, "index": index, "action": action,
                                          "target": target})
    if result.get("success"):
        main = (f"ring {result['ring_index']}/{result['ring_count']-1}  "
                f"pos={result['position_world']:+.4f}  verts={result['verts_in_ring']}")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def select_rings(axis: str = "Z", indices: list = [], action: str = "SELECT",
                 target: str = "") -> str:
    """
    Select the union of vertices belonging to MULTIPLE rings along an axis in one call.

    indices: list of ring indices (negatives wrap, so -1 = last).
             e.g. [2, 4, 6] for three alternating rings.
    action:  SELECT (replace) | ADD | DESELECT
    target:  optional object name — auto-selects it, enters edit mode, exits after.

    Replaces the verbose select_ring + ADD + ADD pattern when shaping repeated detail
    (alternating bulge/pinch on a grip wrap, fluting along a column).
    Pair with scale_rings to scale each selected ring around its own centroid.
    """
    result = call_blender("select_rings", {"axis": axis, "indices": indices, "action": action,
                                           "target": target})
    if result.get("success"):
        main = f"selected rings {result['rings_selected']} of {result['ring_count']}  verts={result['verts_total']}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def scale_rings(axis: str = "Z", indices: list = [], x: float = 1.0, y: float = 1.0,
                label: str = "", target: str = "") -> str:
    """
    Scale each named ring around ITS OWN centroid in the two non-axis directions.

    indices: list of ring indices (negatives wrap, -1 = last)
    x, y:    scale multipliers on the two non-axis directions.
             Axis mapping (x is the lower world-axis index, y is the higher):
               axis=Z → x=X world, y=Y world
               axis=X → x=Y world, y=Z world
               axis=Y → x=X world, y=Z world
    target:  optional object name — auto-selects it, enters edit mode, exits after.

    This is the correct tool for bulge/pinch detail on cylinders, repeating fluting, or any
    per-ring shaping. scale_vertices with pivot=SELECTION collapses all selected verts to
    one centroid (wrong for non-contiguous rings); pivot=ORIGIN only works when the object
    origin happens to lie on the cylinder axis. scale_rings always does the right thing.

    Example — alternating pinches on a grip:
      scale_rings(axis="Z", indices=[2, 4, 6], x=0.85, y=0.85)
    """
    result = call_blender("scale_rings", {
        "axis": axis, "indices": indices, "x": x, "y": y, "target": target,
    }, label=label)
    if result.get("success"):
        main = (f"scaled rings {result['rings_scaled']} by (x={x}, y={y})  "
                f"{result['verts_affected']} verts  [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def taper_end(axis: str = "Z", end: str = "MAX", scale: float = 0.0, label: str = "",
              target: str = "") -> str:
    """
    Scale the extreme ring on an axis toward its own centroid in the two non-axis directions.

    end:    MAX (highest ring on axis) | MIN (lowest ring on axis)
    scale:  0.0 (default) collapses the ring fully to a point.
            0.5 leaves the ring at half its original spread (partial taper / chamfer).
            1.0 is a no-op.
    target: optional object name — auto-selects it, enters edit mode, exits after.

    Use scale=0 for a sword tip; scale=0.4 for "narrow this end a bit" without committing
    to a single point. Faster than the two-ring taper_section equivalent.
    Must be in edit mode (or provide target).
    """
    result = call_blender("taper_end", {"axis": axis, "end": end, "scale": scale,
                                        "target": target}, label=label)
    if result.get("success"):
        verb = "collapsed" if scale == 0.0 else f"scaled→{scale}"
        main = (f"{verb} ring {result['ring_index']}/{result['ring_count']-1} "
                f"({result['end']} of {result['axis']})  "
                f"{result['collapsed_verts']} verts at world={result.get('collapsed_world')}")
        nearby = result.get("nearby_objects") or []
        if nearby:
            nearby_str = ", ".join(f"{n['name']}@{n['dist']}u" for n in nearby)
            main += f"\n  nearby: {nearby_str}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def taper_section(axis: str = "Z", from_ring: int = 0, to_ring: int = -1,
                  x_start: float = 1.0, x_end: float = 1.0,
                  y_start: float = 1.0, y_end: float = 1.0,
                  curve: str = "linear", label: str = "", target: str = "") -> str:
    """
    Linearly interpolate scale across a span of rings — sculpts taper, bulge, or pinch.

    Each ring in [from_ring, to_ring] is scaled around its own centroid in the two non-axis
    directions. The scale at the from_ring is (x_start, y_start); at the to_ring it is
    (x_end, y_end); intermediate rings interpolate linearly.

    Negative indices are allowed (Python-style, so -1 = last ring).
    target: optional object name — auto-selects it, enters edit mode, exits after.

    Examples:
      taper_section(Z, from_ring=0, to_ring=-1, x_end=0.5, y_end=0.5)  → linear taper to 50% at top
      taper_section(Z, from_ring=2, to_ring=4, x_start=1, x_end=0)     → collapse rings 2..4 to a Y-edge

    Must be in edit mode (or provide target).
    """
    result = call_blender("taper_section", {
        "axis": axis, "from_ring": from_ring, "to_ring": to_ring,
        "x_start": x_start, "x_end": x_end, "y_start": y_start, "y_end": y_end,
        "curve": curve, "target": target,
    }, label=label)
    if result.get("success"):
        main = (f"tapered rings {result['from_ring']}..{result['to_ring']} of {result['ring_count']} "
                f"({result['verts_affected']} verts)")
    else:
        main = result.get("error", "failed")
    return main + _status(result)

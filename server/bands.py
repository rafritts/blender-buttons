from server._core import mcp, call_blender, _status, _targets


@mcp.tool()
def band_around(name: str, targets: str, axis: str = "Z", at: float = None,
                width: float = 0.05, thickness: float = 0.02, label: str = "") -> str:
    """
    Wrap a band (strap / hoop / belt / clamp) around the COMBINED silhouette of
    one or more objects. The band follows the convex-hull outline of the targets'
    cross-section, so it bridges gaps between parts — the thing you can't get by
    stretching a box across a multi-part shape.

    name:      object name for the new band (must be unique).
    targets:   object name, group name, or comma-separated list to wrap. The band
               hugs all of them as one silhouette.
    axis:      X | Y | Z — the band wraps AROUND this axis. Default Z (a level
               belt around a standing object). Use Y for a strap over the top of
               a chest (front-to-back), X for a side-to-side strap.
    at:        position along `axis` to place the band (world units). Default: the
               midpoint of the combined extent on that axis.
    width:     how wide the band is along the axis (strap height). Default 0.05 (5cm).
    thickness: how far it stands proud of the surface. Default 0.02 (2cm).

    The result is a closed mesh loop — material it (set_material hex=...), group it,
    duplicate_mirrored it like any object.

    Example — gold strap around a chest (body+lid) two-thirds up:
      band_around("strap", targets="chest_body,chest_lid", axis="Y", at=0.6,
                  width=0.06, thickness=0.015)
    """
    params = {"name": name, "targets": _targets(targets), "axis": axis,
              "width": width, "thickness": thickness}
    if at is not None:
        params["at"] = at
    result = call_blender("band_around", params, label=label)
    if result.get("success"):
        main = (f"band '{result['object_name']}' around {axis}@{result['at']} "
                f"(width={result['width']}, thickness={result['thickness']}, "
                f"{result['hull_points']} hull pts) dims={result['dimensions']} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)

"""SPEC-13 / G99 — server facade for the field deformer (edit op=field).

Thin pass-through to the Blender-side `field` engine (extension/fields.py), mirroring how
rings.* ops are split server⇄extension. All the math lives on the Blender side; this just
marshals the args and formats the status block."""

from server._core import call_blender, _status


def field(axis, about, channel, field_mode, per_component,
          preset, preset_a, preset_b, k, amp, freq, center, bell_width, phase,
          points, interp, expr, expr_x, expr_y, expr_z,
          sigma_x, sigma_y, seed, clamp_min, clamp_max, label, target):
    """Apply an explicit per-vertex field p' = F(vars(p)) over the current selection.

    See the `edit` verb docstring (op=field) for the full parameter language. Exactly one
    function source — preset / points / expr — must be supplied; the engine validates."""
    params = {
        "axis": axis, "about": about, "channel": channel, "field_mode": field_mode,
        "per_component": per_component, "seed": seed,
        "preset": preset, "preset_a": preset_a, "preset_b": preset_b, "k": k,
        "amp": amp, "freq": freq, "center": center, "bell_width": bell_width, "phase": phase,
        "points": points, "interp": interp,
        "expr": expr, "expr_x": expr_x, "expr_y": expr_y, "expr_z": expr_z,
        "sigma_x": sigma_x, "sigma_y": sigma_y,
    }
    if clamp_min is not None:
        params["clamp_min"] = clamp_min
    if clamp_max is not None:
        params["clamp_max"] = clamp_max
    result = call_blender("field", params, label=label)
    if not result.get("success"):
        return result.get("error", "failed") + _status(result)

    fr = result.get("f_range", [None, None])
    bb = result.get("sel_bbox", {})
    main = (f"field {result['channel']} {result['mode']} — "
            f"{result['verts_moved']}/{result['verts_total']} verts moved "
            f"({result['scope']}, {result['components']} component"
            f"{'s' if result['components'] != 1 else ''})  F∈[{fr[0]}, {fr[1]}]")
    if bb:
        main += (f"\n  sel_bbox: x={bb.get('x')} y={bb.get('y')} z={bb.get('z')}")
    for w in result.get("warnings", []):
        main += f"\n⚠ {w}"
    return main + _status(result)

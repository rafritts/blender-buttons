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
    return _format(result)


def _grid_to_moulds(grid):
    """Expand a 2D control grid into the canonical keyed-mould array.

    rows = cross-sections keyed evenly down the line-axis (`at` = i/(R-1)); cols = values
    across the cross-axis u (`u` = j/(C-1)). Pure sugar — the engine's _eval_moulds path is
    unchanged; a hand-authored grid of numbers is just an evenly-sampled, evenly-keyed loft.
    Returns (moulds, error)."""
    if not isinstance(grid, (list, tuple)) or not grid:
        return None, "mould_grid must be a non-empty 2D list of numbers"
    rows, width = [], None
    for i, row in enumerate(grid):
        if not isinstance(row, (list, tuple)) or not row:
            return None, f"mould_grid row {i} must be a non-empty list of numbers"
        if width is None:
            width = len(row)
        elif len(row) != width:
            return None, (f"mould_grid must be rectangular: row {i} has {len(row)} values, "
                          f"expected {width}")
        try:
            rows.append([float(v) for v in row])
        except (TypeError, ValueError):
            return None, f"mould_grid row {i} has a non-numeric value"
    R, C = len(rows), width
    moulds = [
        {"at": (i / (R - 1)) if R > 1 else 0.0,
         "points": [[(j / (C - 1)) if C > 1 else 0.0, vals[j]] for j in range(C)]}
        for i, vals in enumerate(rows)
    ]
    return moulds, None


def loft(axis, moulds, interp, channel, field_mode, label, target, mould_grid=None,
         clamp_min=None, clamp_max=None):
    """Vacuum-form the selection onto an ARRAY of keyed cross-section moulds (the loft).

    The grid is the sheet; each mould is a cross-section profile keyed down the line-axis;
    the engine interpolates between them and pulls every vert onto the result. Varying the
    moulds down the sheet is what gives a real (double-curved) shell — a uniform array
    collapses to a ribbon, which the engine flags. The moulds can be hand-authored profile
    dicts (`moulds=`) OR a raw 2D control grid of numbers (`mould_grid=`), which expands to an
    evenly-keyed mould array. See the edit verb docstring (op=loft) for the full
    language."""
    if mould_grid:
        if moulds:
            return "give either moulds or mould_grid, not both"
        moulds, err = _grid_to_moulds(mould_grid)
        if err:
            return err
    params = {
        "axis": axis, "channel": channel or "normal", "field_mode": field_mode or "add",
        "moulds": moulds, "interp": interp,
    }
    if clamp_min is not None:
        params["clamp_min"] = clamp_min
    if clamp_max is not None:
        params["clamp_max"] = clamp_max
    result = call_blender("field", params, label=label)
    if not result.get("success"):
        return result.get("error", "failed") + _status(result)
    return _format(result, verb="loft")


def _format(result, verb="field"):
    fr = result.get("f_range", [None, None])
    bb = result.get("sel_bbox", {})
    main = (f"{verb} {result['channel']} {result['mode']} — "
            f"{result['verts_moved']}/{result['verts_total']} verts moved "
            f"({result['scope']}, {result['components']} component"
            f"{'s' if result['components'] != 1 else ''})  F∈[{fr[0]}, {fr[1]}]")
    if bb:
        main += (f"\n  sel_bbox: x={bb.get('x')} y={bb.get('y')} z={bb.get('z')}")
    for w in result.get("warnings", []):
        main += f"\n⚠ {w}"
    return main + _status(result)

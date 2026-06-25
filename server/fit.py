"""SPEC-14 / G100 — server facade for geometry fit (feel op=fit).

Thin pass-through to the Blender-side `fit` engine (extension/fit.py), mirroring the
rings/fields split. Read-only (no status block — `feel` IS perception): formats the fitted
param block + residual/coverage/verdict + any detected gaps, and the as_handle/as_curve
minting outcome."""

from server._core import call_blender


def _fmt_num(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, list):
        return "[" + ", ".join(_fmt_num(x) for x in v) + "]"
    return str(v)


def _params_block(model, params):
    """A compact, unit-tagged param dump — meters as cm where it reads better."""
    lines = []
    for key, val in params.items():
        if val is None:
            continue
        if key in ("radius", "major_radius", "minor_radius", "radius_lo", "radius_hi",
                   "length") and isinstance(val, (int, float)):
            lines.append(f"  {key}: {val*100:.2f}cm")
        elif key == "semi_axes" and isinstance(val, list):
            lines.append("  semi_axes: " + ", ".join(f"{a*100:.2f}cm" for a in val))
        elif key == "extent" and isinstance(val, list):
            lines.append("  extent: " + " × ".join(f"{a*100:.2f}cm" for a in val))
        elif isinstance(val, (list, dict)):
            lines.append(f"  {key}: {_fmt_num(val) if isinstance(val, list) else val}")
        else:
            lines.append(f"  {key}: {_fmt_num(val)}")
    return "\n".join(lines)


def _one_quadric(f):
    """SPEC-19 Phase 1 — present the analytic patch as an editable formula: the legible
    h(u,v) face, the shape verdict, the residual honesty stamp, the measured frame, and the
    ready-to-run round-trip apply line (edit the coefficients, then run it)."""
    p = f.get("params", {})
    cap = f.get("captured")
    cap_s = f"{cap*100:.0f}%" if isinstance(cap, (int, float)) else "?"
    out = [f"quadric patch — {p.get('shape', '?')}", f"  {f.get('formula', '')}"]
    out.append(f"  k_max {_fmt_num(p.get('k_max'))}/m · k_min {_fmt_num(p.get('k_min'))}/m   "
               f"(u along {_fmt_num(p.get('axis_u'))}, v along {_fmt_num(p.get('axis_v'))}, "
               f"normal {_fmt_num(p.get('normal'))}, origin {_fmt_num(p.get('frame_origin'))})")
    rmm, tmm = f.get("residual_mm"), f.get("tol_mm")
    clean = isinstance(rmm, (int, float)) and isinstance(tmm, (int, float)) and rmm <= tmm
    verdict = ("clean" if clean else "HIGH residual: region is not height-field-like "
               "(try a finer basis or split the selection)")
    out.append(f"  captured {cap_s} of height · residual {rmm}mm "
               f"(max {f.get('residual_max_mm')}mm) · coverage {f.get('coverage')} · "
               f"tol {tmm}mm — {verdict}")
    out.append(f"  ↻ apply (edit the coefficients first): edit op=field axis=auto "
               f"channel={f.get('apply_channel', 'axis:v')} field_mode=add expr=\"{f.get('expr')}\"")
    return "\n".join(out)


def _one(f):
    if f.get("model") == "quadric":
        return _one_quadric(f)
    head = f.get("verdict", f.get("model", "?"))
    out = [head]
    pb = _params_block(f.get("model"), f.get("params", {}))
    if pb:
        out.append(pb)
    out.append(f"  residual: {f.get('residual_mm')}mm (max {f.get('residual_max_mm')}mm)  "
               f"coverage: {f.get('coverage')}  tol: {f.get('tol_mm')}mm")
    rp = f.get("radius_profile")
    if rp:
        shown = ", ".join(f"[{s},{r*100:.1f}cm]" for s, r in rp[:8])
        out.append(f"  R(s): {shown}" + (f"  …+{len(rp)-8}" if len(rp) > 8 else ""))
    if f.get("gaps"):
        out.append("  gaps: " + ", ".join(f"s∈[{g[0]},{g[1]}]" for g in f["gaps"]))
    cands = f.get("candidates")
    if cands and len(cands) > 1:
        out.append("  tried: " + ", ".join(
            f"{c['model']}={c['residual_mm']}mm/{int(c['coverage']*100)}%" for c in cands))
    return "\n".join(out)


def fit_region(target, model, axis, tol, per_component, bands, as_handle, as_curve, lod):
    params = {
        "target": target, "model": model, "axis": axis,
        "per_component": per_component, "bands": bands,
        "as_handle": as_handle, "as_curve": as_curve, "lod": lod,
    }
    if tol is not None:
        params["tol"] = tol
    result = call_blender("fit", params)
    if not result.get("success"):
        return result.get("error", "failed")

    if result.get("per_component"):
        parts = [f"per_component fit — {result['n_components']} component(s), "
                 f"{result['verts']} verts:"]
        for f in result["components"]:
            parts.append(f"\n[component {f.get('component')}] " + _one(f))
        body = "\n".join(parts)
    else:
        body = _one(result)

    if result.get("handle"):
        body += f"\n  ✓ minted axis handle '{result['handle']}' (addressable by name)"
    elif result.get("handle_error"):
        body += f"\n  ⚠ as_handle: {result['handle_error']}"
    if result.get("curve"):
        body += (f"\n  ✓ minted centerline curve '{result['curve']}' — extend it + "
                 "extrude_along_curve a matching section to continue the form")
    elif result.get("curve_error"):
        body += f"\n  ⚠ as_curve: {result['curve_error']}"
    for w in result.get("warnings", []):
        body += f"\n⚠ {w}"
    return body


def coverage_region(target, na=12, nb=12):
    """G100 — model-free continuity/coverage read for a NON-tubular selection (sheet, patch,
    branching region). Reports disjoint piece count + a 2D occupancy grid over the patch's
    own plane: coverage %, interior holes, and an ASCII map. No model asserted first."""
    result = call_blender("coverage", {"target": target, "na": na, "nb": nb})
    if not result.get("success"):
        return result.get("error", "failed")
    head = (f"coverage of '{result['object']}' ({result['verts']} verts): "
            f"{result['pieces']} disjoint piece(s), {result['coverage_pct']}% of the patch "
            f"span filled, {result['interior_holes']} interior hole-cell(s) "
            f"[{result['grid'][0]}×{result['grid'][1]} grid]")
    body = head + "\n" + "\n".join("  " + row for row in result.get("map", []))
    for w in result.get("warnings", []):
        body += f"\n⚠ {w}"
    return body

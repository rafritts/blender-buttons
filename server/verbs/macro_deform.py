"""buttons-deform-macro — formula/sweep DEFORM macros (SPEC-20 §3, II.2).

blender-buttons MACROS (composite, not native single ops), grouped by purpose with R1
native-cousin tags. Dispatch to the same flat handlers (fields.field / bands.band_around /
editmode.extrude_along_curve).

  field  — explicit per-vertex p'=F(vars(p)) deformer over the selection (SPEC-13)
  band   — author + place a raised band around a form
  extrude_along_curve — sweep the selection along a curve
"""

from typing import Literal

from server._core import mcp
from server import fields, bands, editmode
from ._common import tag, unknown, teach


@mcp.tool(name="buttons-deform-macro")
def buttons_deform_macro(
    op: Literal["field", "band", "extrude_along_curve"],
    target: tag(str, "mesh object to deform (empty=active)") = "",
    axis: tag(str, "[field/band] axis X|Y|Z") = "Z",
    # field (SPEC-13 / G99) — per-vertex p'=F(vars(p)) over the selection
    about: tag(str, "[field] radial pivot: axis (ship) | spine (deferred)") = "axis",
    channel: tag(str, "[field] how F displaces: radial | normal | axis:<X|Y|Z|long|u|v> | twist | vector") = "radial",
    field_mode: tag(str, "[field] add | multiply | set (radial: multiply default; offset channels: add)") = "",
    per_component: tag(bool, "[field] parameterize + apply independently per connected sub-shell") = False,
    frame: tag(str, "[field] channel=vector basis: world | local | tangent_normal") = "world",
    preset: tag(str, "[field] taper|power|smoothstep|bell|sine|lobes (one function source)") = "",
    preset_a: tag(float, "[field] preset endpoint value at t=0 (taper/power/smoothstep)") = 1.0,
    preset_b: tag(float, "[field] preset endpoint value at t=1 (taper/power/smoothstep)") = 1.0,
    k: tag(float, "[field] power preset exponent (k>1 late bulge, k<1 early)") = 1.0,
    amp: tag(float, "[field] amplitude (bell/sine/lobes)") = 1.0,
    freq: tag(float, "[field] frequency: cycles over t (sine) / lobes around theta (lobes)") = 1.0,
    center: tag(float, "[field] bell center in t (0..1)") = 0.5,
    bell_width: tag(float, "[field] bell gaussian width in t") = 0.2,
    phase: tag(float, "[field] sine preset/expr phase (radians)") = 0.0,
    points: tag(list, "[field] control-point curve [[t,val],…] (one function source)") = None,
    interp: tag(str, "[field] points curve interpolation: linear | smooth | cubic") = "smooth",
    expr: tag(str, "[field] sandboxed scalar expression over the var namespace") = "",
    expr_x: tag(str, "[field] channel=vector X-component expression") = "",
    expr_y: tag(str, "[field] channel=vector Y-component expression") = "",
    expr_z: tag(str, "[field] channel=vector Z-component expression") = "",
    sigma_x: tag(float, "[field] radial anisotropy on the U cross-axis (keeps ellipses elliptical)") = 1.0,
    sigma_y: tag(float, "[field] radial anisotropy on the V cross-axis") = 1.0,
    seed: tag(int, "[field] random seed (rnd/crnd vars)") = 0,
    clamp_min: tag(float, "[field] lower bound on F (None=unbounded)") = None,
    clamp_max: tag(float, "[field] upper bound on F (None=unbounded)") = None,
    # band_around
    name: tag(str, "[band] name for the new band object") = "",
    at: tag(float, "[band] position along axis (0..1)") = None,
    width: tag(float, "[band] band width (m)") = 0.0,
    thickness: tag(float, "[band] band thickness (m)") = 0.02,
    # extrude_along_curve
    curve: tag(str, "[extrude_along_curve] curve to sweep along") = "",
    segments: tag(int, "[extrude_along_curve] sweep segments") = 1,
    taper: tag(float, "[extrude_along_curve] end scale (taper)") = 1.0,
    label: str = "",
) -> str:
    """
    DEFORM macros (blender-buttons composites). `op` selects:

      field — THE FIELD DEFORMER (SPEC-13): apply an explicit per-vertex function
              p'=F(vars(p)) over the SELECTION. vars are measured from the selected
              geometry (t/u/v along the frame, r/theta in the cross-plane, arc-length s/L
              per strand, normal, x/y/z local, rnd/crnd). F is a preset (taper|power|
              smoothstep|bell|sine|lobes), a control-point curve (points+interp), or a
              sandboxed expr. Output displaces through channel (field_mode add|multiply|
              set). Smooth F ⇒ smooth surface. The general engine taper_end/scale_rings/
              shape_profile/flute/jitter are named cases of.

              INTENDED USE — VACUUM FORMING. The signature use of field is to drape a flat
              `add type=grid` sheet onto a shape: the grid is the hot plastic, the function
              F is the MOULD, and field is the vacuum that pulls every vert down onto it.
              Author the form by choosing the mould, not by typing coordinates.
              ⚠ A loft is properly an ARRAY of moulds — one per line — and the variation
              ACROSS that array is what gives the sheet its second curvature (a real shell).
              ONE function applied to every line has nothing to vary against, so it can only
              EXTRUDE: a single-curvature RIBBON, not a shell. Vary the mould down the grid;
              a uniform mould drapes flat (sometimes intended — a strap/belt/panel).
      band  — author + place a raised band around a form  (name, target(s), axis, at,
              width, thickness)
      extrude_along_curve — sweep the selection along a curve  (curve, segments, taper)

    NATIVE COUSINS (R1):
      • field ≈ Geometry Nodes' **Set Position** primitive — but there is NO native single
        op "type a formula F(p), apply over a selection." field IS that one-shot evaluator;
        natively you hand-build a node graph each time.
      • band ≈ no stock "band around a form" feature; closest is a GN convex-hull/curve-to-
        mesh sweep or a Shrinkwrapped ring — none authors+places+sizes the band in one call.
      • extrude_along_curve ≈ the **Curve modifier** / 5.0's **Curve to Tube** / Array+Curve;
        the macro sweeps a live selection with taper without rigging a modifier stack.
    """
    o = op.lower().strip()
    bad = teach("buttons-deform-macro", "op", o, {
        "field": (sum([bool(preset), bool(points),
                       bool(expr or expr_x or expr_y or expr_z)]) == 1,
                  "EXACTLY one function source: preset=<name> | points=[[t,val],…] | expr=\"…\"",
                  "buttons-deform-macro op=field axis=Z channel=radial field_mode=multiply preset=smoothstep preset_a=1.0 preset_b=0.6"),
        "extrude_along_curve": (bool(curve), "curve=<curve to sweep along>",
                  "buttons-deform-macro op=extrude_along_curve target=ring curve=path"),
    })
    if bad:
        return bad
    if o == "field":
        return fields.field(axis, about, channel, field_mode, per_component,
                            preset, preset_a, preset_b, k, amp, freq, center,
                            bell_width, phase, points or [], interp, expr,
                            expr_x, expr_y, expr_z, sigma_x, sigma_y, seed,
                            clamp_min, clamp_max, label, target)
    if o == "band":
        return bands.band_around(name, target, axis, at, width or 0.05, thickness, label)
    if o == "extrude_along_curve":
        return editmode.extrude_along_curve(curve, segments, taper, label)
    return unknown("buttons-deform-macro", "op", op, ["field", "band", "extrude_along_curve"])

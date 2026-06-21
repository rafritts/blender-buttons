"""edit — Edit Mode / the Mesh menu (SPEC-05).

Mesh-editing operations on the active object's geometry (its current selection):
extrude, bevel, loop cut, merge, delete, mark sharp, taper, bend, boolean, … `op`
selects the operation. The flat handlers manage entering Edit Mode on `target`.
"""

from typing import Literal

from server._core import mcp
from server import editmode, finishes, rings, bands, introspect, modifiers
from ._common import tag, unknown, teach

_OPS = ["extrude", "bevel", "loop_cut", "merge", "delete", "separate",
        "mark_sharp", "crease", "inflate", "jitter", "noise_displace", "proportional_move",
        "extrude_along_curve", "round", "bend", "smooth_edges", "taper_end",
        "taper_section", "shape_profile", "flute", "scale_rings", "band", "trace",
        "boolean", "subdivide", "bridge",
        "connect", "reshape", "resample", "strands", "relax", "slide", "poke", "inset",
        "grid_fill"]


@mcp.tool(name="edit")
def edit(
    op: Literal["extrude", "bevel", "loop_cut", "merge", "delete", "separate",
                "mark_sharp", "crease", "inflate", "jitter", "noise_displace",
                "proportional_move",
                "extrude_along_curve", "round", "bend", "smooth_edges", "taper_end",
                "taper_section", "shape_profile", "flute", "scale_rings", "band", "trace",
                "boolean", "subdivide",
                "bridge", "connect", "reshape", "resample", "strands", "relax", "slide",
                "poke", "inset", "grid_fill"],
    target: tag(str, "mesh object to edit (empty=active)") = "",
    # bridge — weld two boundary handles (SPEC-07 Phase 5 / G10)
    a: tag(str, "[bridge/connect] first boundary handle (order-independent); [resample] the rim handle to resample") = "",
    b: tag(str, "[bridge] second boundary handle to weld") = "",
    # bridge curvature dials (G58 — pass-through to Bridge Edge Loops; defaults = straight)
    bridge_cuts: tag(int, "[bridge] intermediate loops across the span (0=straight strut; raise to bow it)") = 0,
    smoothness: tag(float, "[bridge] tangent bow of the cuts (native default 1.0; needs bridge_cuts>0)") = 1.0,
    interpolation: tag(str, "[bridge] how cuts follow the rims: linear|path|surface") = "path",
    profile: tag(float, "[bridge] bulge the cross-section outward (profile_factor; 0=none)") = 0.0,
    twist: tag(int, "[bridge] rotate rim-to-rim vertex mapping (verts) to kill the spiral when rims face apart") = 0,
    # connect — geometry-bound swept connector (SPEC-10; a/b are two boundary handles)
    style: tag(str, "[connect/strands] arc | s_curve | direct | slack — the gesture (normal-honoring vs straight)") = "arc",
    tension: tag(float, "[connect/strands] 0..1 how much it bows (handle length as fraction of the gap); -1=style default") = -1.0,
    connect_profile: tag(str, "[connect] cross-section: match (sweep each rim's shape, tapering) | round") = "match",
    weld: tag(bool, "[connect] fuse both ends into one watertight mesh (False = leave a separate connector)") = True,
    # reshape / resample — Phase 4 editability + rim equalising (SPEC-10)
    count: tag(int, "[resample] target vertex count for the rim (>=3); [strands] number of strands (>=2)") = 0,
    # strands — expressive multi-strand tier (SPEC-10 Phase 5)
    sides: tag(int, "[strands] cross-section verts per strand (thin tube)") = 8,
    jitter: tag(float, "[strands] 0..1 coherent midspan waywardness (0=clean parallel fan)") = 0.0,
    strand_radius: tag(float, "[strands] tube radius per strand (m); -1=auto-pack to the rim+count") = -1.0,
    # directional amounts (extrude / move-style ops; meters, local frame)
    out: tag(float, "[extrude/proportional_move] push out along normal (m)") = 0.0,
    inward: tag(float, "[extrude/proportional_move] push inward (m)") = 0.0,
    up: tag(float, "[extrude/proportional_move] +Z (m)") = 0.0,
    down: tag(float, "[extrude/proportional_move] -Z (m)") = 0.0,
    left: tag(float, "[extrude/proportional_move] -X (m)") = 0.0,
    right: tag(float, "[extrude/proportional_move] +X (m)") = 0.0,
    forward: tag(float, "[extrude/proportional_move] -Y (m)") = 0.0,
    back: tag(float, "[extrude/proportional_move] +Y (m)") = 0.0,
    until_contact: tag(str, "[extrude] extrude until hitting this object") = "",
    until_length: tag(float, "[extrude] extrude to this total length (m)") = 0.0,
    x: tag(float, "[extrude/proportional_move] explicit X amount (m)") = 0.0,
    y: tag(float, "[extrude/proportional_move] explicit Y amount (m)") = 0.0,
    z: tag(float, "[extrude/proportional_move] explicit Z amount (m)") = 0.0,
    # bevel
    width: tag(float, "[bevel/round/smooth_edges] bevel width (m)") = 0.0,
    factor: tag(float, "[bevel] bevel amount as a factor (alt to width)") = 0.05,
    segments: tag(int, "[bevel/round/smooth_edges] bevel segments") = 1,
    affect: tag(str, "[bevel] EDGES | VERTICES") = "EDGES",
    # loop_cut / axis-based
    axis: tag(str, "[loop_cut/taper_end/taper_section/scale_rings/band/trace] axis X|Y|Z") = "Z",
    cuts: tag(int, "[loop_cut/subdivide] number of cuts to add") = 1,
    subdivide_smooth: tag(float, "[subdivide] 0=flat (denser cage) … ~1=round toward limit surface") = 0.0,
    # merge / delete / sharp / crease
    threshold: tag(float, "[merge] merge-by-distance threshold (m)") = 0.001,
    selected_only: tag(bool, "[merge] merge only within the selection") = False,
    mode: tag(str, "[delete] VERT|EDGE|FACE|ONLY_FACE|EDGE_FACE") = "VERT",
    clear: tag(bool, "[mark_sharp] clear instead of mark") = False,
    weight: tag(float, "[crease] crease weight 0..1") = 1.0,
    # inflate / jitter / noise_displace / proportional
    amount: tag(float, "[inflate/jitter/noise_displace] displacement amount (m); noise wants ~0.03–0.1") = 0.003,
    seed: tag(int, "[jitter/strands] random seed (same seed reproduces the bundle)") = 0,
    only_positive: tag(bool, "[jitter] jitter outward only") = False,
    # noise_displace (coherent organic surface break-up)
    feature_size: tag(float, "[noise_displace] noise feature size (bigger = broader lumps)") = 0.5,
    detail: tag(int, "[noise_displace] extra noise octaves on top of the big lumps") = 2,
    direction: tag(str, "[noise_displace] push axis NORMAL|X|Y|Z") = "NORMAL",
    radius: tag(float, "[proportional_move] falloff radius (m)") = 0.01,
    falloff: tag(str, "[proportional_move] SMOOTH|SHARP|…") = "SMOOTH",
    connected: tag(bool, "[proportional_move] geodesic (along-edges) falloff — won't drag a disconnected shell") = False,
    freeze: tag(str, "[proportional_move] handle whose verts are held rigid (and wall off the falloff)") = "",
    # separate
    new_name: tag(str, "[separate] name for the split-off object") = "",
    # extrude_along_curve
    curve: tag(str, "[extrude_along_curve] curve to sweep along") = "",
    taper: tag(float, "[extrude_along_curve] end scale (taper)") = 1.0,
    # round_corners
    corners: tag(list, "[round] named corners to round") = None,
    # bend
    angle: tag(float, "[bend] bend angle (deg)") = 0.0,
    apply: tag(bool, "[bend] apply the bend modifier") = True,
    # smooth_edges
    angle_limit: tag(float, "[smooth_edges] shade-smooth angle limit (deg)") = 30.0,
    # taper / rings
    end: tag(str, "[taper_end] which end MAX|MIN") = "MAX",
    scale: tag(float, "[taper_end] end scale: 0=collapse to a point, <1 taper, 1 no-op, >1 flare (e.g. 1.5=bell lip)") = 0.0,
    indices: tag(list, "[scale_rings] ring indices to scale") = None,
    from_ring: tag(int, "[taper_section] first ring") = 0,
    to_ring: tag(int, "[taper_section] last ring (-1 = end)") = -1,
    x_start: tag(float, "[taper_section] X scale at from_ring") = 1.0,
    x_end: tag(float, "[taper_section] X scale at to_ring") = 1.0,
    y_start: tag(float, "[taper_section] Y scale at from_ring") = 1.0,
    y_end: tag(float, "[taper_section] Y scale at to_ring") = 1.0,
    curve_shape: tag(str, "[taper_section] interpolation: linear|ease_in|ease_out|ease_in_out|smoothstep") = "linear",
    # shape_profile / flute (G92 / G94) — absolute-radius lathe + meridional corrugation
    points: tag(list, "[shape_profile] control points [[ring_index, radius_m], ...]; rings between interpolate, outside untouched") = None,
    flute_count: tag(int, "[flute] number of flutes/lobes around the axis (>=1)") = 0,
    flute_depth: tag(float, "[flute] radial depth of each flute (m, >0)") = 0.0,
    flute_profile: tag(str, "[flute] convex (lobes bulge out — gadroons) | concave (grooves cut in — flutes)") = "convex",
    phase: tag(float, "[flute] rotate the lobe pattern (deg)") = 0.0,
    # ring scale (op=scale_rings uses x/y as ring-plane scale factors)
    ring_x: tag(float, "[scale_rings] X scale of the rings") = 1.0,
    ring_y: tag(float, "[scale_rings] Y scale of the rings") = 1.0,
    # band_around
    name: tag(str, "[band] name for the new band object") = "",
    at: tag(float, "[band] position along axis (0..1)") = None,
    thickness: tag(float, "[band] band thickness (m) / [inset] inset distance (m)") = 0.02,
    # trace_profile
    sections: tag(int, "[trace/connect/strands] number of cross-sections / rings along the span") = 24,
    # boolean
    cutter: tag(str, "[boolean] cutter object") = "",
    bool_op: tag(str, "[boolean] DIFFERENCE|UNION|INTERSECT") = "DIFFERENCE",
    solver: tag(str, "[boolean] EXACT|FAST") = "EXACT",
    hide_cutter: tag(bool, "[boolean] hide the cutter afterward") = True,
    # relax (G49) — redistribute spacing, shape preserved
    iterations: tag(int, "[relax] smoothing passes") = 5,
    strength: tag(float, "[relax] per-pass factor 0..1") = 0.5,
    reproject: tag(bool, "[relax] snap back onto the surface each pass (shape preserved)") = True,
    # poke / inset / grid_fill (G50) — face authoring
    offset: tag(float, "[poke] push the new centre vert along the face normal (m)") = 0.0,
    depth: tag(float, "[inset] push the inset in/out along the normal (m); [resample] collar length (-1=auto)") = 0.0,
    individual: tag(bool, "[inset] inset each face separately vs. the region as a whole") = False,
    span: tag(int, "[grid_fill] grid span (0 = auto)") = 0,
    grid_offset: tag(int, "[grid_fill] grid offset") = 0,
    label: str = "",
) -> str:
    """
    Mesh editing — **Edit Mode / Mesh** menu. Operates on the active object's
    current selection. `op` selects:

    ⚠ ONE edit op PER MESSAGE when they build on each other. Tool calls batched in a
    single message reach Blender over separate connections and execute in ARRIVAL order,
    not the order you wrote them — so `loop_cut` then `taper_end` in one batch can run
    taper-first against geometry the cut hasn't made yet, and the taper silently no-ops
    (the no-op detector will flag the byte-identical result). Issue dependent edit ops
    sequentially, one per message, each seeing the previous one's result. Independent
    edits on DIFFERENT meshes are fine to batch.

      extrude     — push the selection out (out/inward/up/down/left/right/forward/back
                    meters, or until_contact=obj / until_length)
      bevel       — round edges/verts   (width OR factor, segments, affect=EDGES|VERTICES)
      loop_cut    — add edge loops       (axis, cuts)
      subdivide   — densify the SELECTED patch locally — sculptable resolution where
                    you select, no global loops, no shape-key block  (cuts, subdivide_smooth)
      merge       — merge by distance    (threshold, selected_only)
      delete      — delete geometry      (mode=VERT|EDGE|FACE|ONLY_FACE|EDGE_FACE)
      separate    — split selection into a new object   (new_name)
      mark_sharp  — mark/clear sharp edges               (clear)
      crease      — set edge crease weight               (weight)
      inflate     — push verts along normals             (amount)
      jitter      — randomize verts (per-vertex WHITE noise → spiky)  (amount, axis,
                    seed, only_positive)
      noise_displace — COHERENT organic surface break-up: a noise-textured DISPLACE so
                    neighbouring verts move together → real LUMPS (foliage, terrain,
                    bark, rock). Needs surface resolution to show. (amount, feature_size,
                    detail, direction, apply)
      proportional_move — soft move with falloff (directional + radius, falloff;
                    connected=geodesic falloff, freeze=hold a handle rigid)
      extrude_along_curve — sweep selection along a curve (curve, segments, taper)
      round       — round named corners    (corners=[...], radius→width, segments)
      bend        — bend the object into an arc  (angle, axis, apply). Pivots about
                    the object ORIGIN and is SYMMETRIC about it — a bar centred on its
                    origin humps both ways ("mustache"); move the origin to one end
                    for a one-way crescent. apply=True forces OBJECT mode.
      smooth_edges— bevel+shade for soft edges  (width, segments, angle_limit)
      taper_end   — taper one end to a scale     (axis, end=MAX|MIN, scale)
      taper_section — taper a ring range (axis, from_ring, to_ring, x_start/x_end/
                    y_start/y_end, curve_shape)
      shape_profile — LATHE: set ring radii in ABSOLUTE meters and interpolate between
                    control points (axis, points=[[ring,radius],…]). Seam-safe and
                    idempotent — unlike taper_section's relative scale, touching ranges
                    don't double-scale a shared ring into a pinhole. The surface-of-
                    revolution shaper (goblet, hourglass, baluster).
      flute       — corrugate a surface of revolution with N vertical flutes/lobes by
                    modulating radius vs azimuth — flutes (concave), gadroons/reeding
                    (convex). (axis, flute_count, flute_depth, flute_profile, phase)
      scale_rings — scale specific rings   (axis, indices=[...], ring_x, ring_y)
      band        — wrap a raised band     (name, target(s), axis, at, width, thickness)
      trace       — trace a cross-section profile  (target, axis, sections)
      boolean     — boolean with a cutter  (cutter, bool_op=DIFFERENCE|UNION|
                    INTERSECT, solver, apply, hide_cutter)
      bridge      — weld two open boundary loops into a continuous surface (the
                    bridge-edge-loops primitive). a/b are two boundary handles (mint
                    with feel op=assembly); their rims get bridged. SAME-OBJECT only —
                    join cross-object parts first (object op=join), then bridge on the
                    joined mesh. Keyed/rigged meshes refused (topology change corrupts
                    the deform). Order-independent. Defaults to a STRAIGHT strut; raise
                    bridge_cuts to subdivide the span so it can bow (smoothness=tangent
                    bow, profile=outward bulge, interpolation=linear|path|surface), and
                    twist to align rims that face apart (kills the spiral).
                    (a, b, bridge_cuts, smoothness, interpolation, profile, twist)
      connect     — GEOMETRY-BOUND swept connector (SPEC-10): weld two rims with a
                    tube that leaves each opening along its OWN outward normal (G1
                    continuity), sweeps a hollow cross-section matched 1:1 to each rim
                    and tapered between them on a minimum-twist frame, and fuses both
                    ends into one watertight mesh. The organic-curve weld that `bridge`
                    (straight quads) and hand-typed Béziers couldn't do. Cross-object OK
                    (joins the owners itself). a/b are two boundary handles.
                    (a, b, style=arc|s_curve|direct|slack, tension, sections,
                    connect_profile=match|round, weld)
      reshape     — RE-EVALUATE an unwelded connector against its LIVE handles
                    (SPEC-10 Phase 4): a weld=False connector stored its recipe, so
                    if you deform/move a pipe, reshape re-bakes the tube to follow.
                    tension overrides the bow (-1 keeps stored). Welded connectors are
                    committed — re-run connect to reshape them.   (name, tension)
      resample    — resample a boundary rim to a target vertex COUNT (an arc-length
                    transition collar), re-homing the handle onto the new loop. Lifts
                    connect's 1:1 weld limit: equalise a 16-vs-32 mismatch in one call.
                    (a=<rim handle>, count, depth)
      strands     — EXPRESSIVE multi-strand tier (SPEC-10 Phase 5): N thin tubes
                    distributed around two rims, each leaving along its opening's
                    normal (G1, like connect), with a seeded coherent jitter bowing
                    each one its own way → "a sequence of crazy curves" from a count +
                    a seed, not K hand-placed Béziers. One editable object (capped
                    tubes); stores its recipe → edit op=reshape re-bakes the bundle
                    against the live handles. a/b are two boundary handles.
                    (a, b, count, style, tension, sections, sides, jitter, seed,
                    strand_radius)
      relax       — RELAX the selection: even out vertex spacing over the form WITHOUT
                    changing its shape (smooth + reproject onto the pre-relax surface).
                    Moves verts ALONG the surface — fixes stretched/bunched quads.
                    (iterations, strength, reproject)
      slide       — SLIDE the selection along the surface: move by the direction words,
                    then reproject onto the pre-slide surface (net motion is tangential).
                    Relocate a pole/loop to a feature without denting the mesh.
                    (out/inward/up/down/left/right/forward/back)
      poke        — fan each selected face out from a new centre vert → mints a POLE
                    (radial centre) where the form wants one. FACE mode.   (offset)
      inset       — ring the selected faces with a new face band (shrink a copy inward);
                    adds an edge loop to define/tighten a feature. FACE mode.
                    (thickness, depth, individual)
      grid_fill   — fill a selected closed edge loop with a clean quad grid (re-flow a
                    hole/region instead of a fan). One even-vert loop selected.
                    (span, grid_offset)
    """
    o = op.lower().strip()
    # G23 move 3 — teaching errors for ops whose key input has no safe default.
    bad = teach("edit", "op", o, {
        "bridge":  (bool(a and b), "a and b (two boundary handles)",
                    "edit op=bridge a=torso.neck b=head.base"),
        "connect": (bool(a and b), "a and b (two boundary handles)",
                    "edit op=connect a=pipe.top b=spout.base style=arc"),
        "reshape": (bool(name), "name=<unwelded connector>",
                    "edit op=reshape name=connector tension=0.8"),
        "resample": (bool(a and count >= 3), "a=<rim handle> and count=N (>=3)",
                    "edit op=resample a=pipe.top count=32"),
        "strands": (bool(a and b and count >= 2), "a,b (two handles) and count=N (>=2)",
                    "edit op=strands a=pipe.top b=spout.base count=7 jitter=0.2"),
        "boolean": (bool(cutter), "cutter=<object to cut with>",
                    "edit op=boolean target=block cutter=drill bool_op=DIFFERENCE"),
        "extrude_along_curve": (bool(curve), "curve=<curve to sweep along>",
                    "edit op=extrude_along_curve target=ring curve=path"),
        "round":   (bool(corners), "corners=[...] (named corners to round)",
                    "edit op=round target=panel corners=[c1,c2] width=0.02"),
        "shape_profile": (bool(points), "points=[[ring_index, radius_m], ...]",
                    "edit op=shape_profile axis=Z points=[[0,0.05],[11,0.009],[22,0.06]]"),
        "flute":   (bool(flute_count >= 1 and flute_depth > 0),
                    "flute_count=N (>=1) and flute_depth=<m> (>0)",
                    "edit op=flute axis=Z flute_count=12 flute_depth=0.004 flute_profile=concave"),
    })
    if bad:
        return bad
    if o == "extrude":
        return editmode.extrude(out, inward, up, down, left, right, forward, back,
                                until_contact, until_length, x, y, z, label, target)
    if o == "bevel":
        return editmode.bevel(width, factor, segments, affect, label, target)
    if o == "loop_cut":
        return editmode.loop_cut(axis, cuts, label, target)
    if o == "subdivide":
        return editmode.subdivide_selection(cuts, subdivide_smooth, label, target)
    if o == "merge":
        return editmode.merge_by_distance(threshold, selected_only, label, target)
    if o == "delete":
        return editmode.delete_geometry(mode, label, target)
    if o == "separate":
        return editmode.separate_selection(new_name, label, target)
    if o == "mark_sharp":
        return editmode.mark_sharp(clear, label, target)
    if o == "crease":
        return editmode.set_edge_crease(weight, label, target)
    if o == "inflate":
        return editmode.inflate_selection(amount, label, target)
    if o == "jitter":
        return editmode.jitter_vertices(amount, axis, seed, only_positive, label, target)
    if o == "noise_displace":
        return finishes.noise_displace(target, amount, feature_size, detail, direction,
                                       apply, label)
    if o == "proportional_move":
        return editmode.proportional_move(out, inward, up, down, left, right,
                                          forward, back, x, y, z, radius, falloff,
                                          connected, freeze, label, target)
    if o == "extrude_along_curve":
        return editmode.extrude_along_curve(curve, segments, taper, label)
    if o == "round":
        return finishes.round_corners(target, corners or [], width or 0.02, segments, label)
    if o == "bend":
        return finishes.bend(target, angle, axis, apply, label)
    if o == "smooth_edges":
        return finishes.smooth_edges(target, width or 0.002, segments, angle_limit, label)
    if o == "taper_end":
        return rings.taper_end(axis, end, scale, label, target)
    if o == "taper_section":
        return rings.taper_section(axis, from_ring, to_ring, x_start, x_end,
                                   y_start, y_end, curve_shape, label, target)
    if o == "shape_profile":
        return rings.shape_profile(axis, points or [], label, target)
    if o == "flute":
        return rings.flute(axis, flute_count, flute_depth, flute_profile, phase,
                           label, target)
    if o == "scale_rings":
        return rings.scale_rings(axis, indices or [], ring_x, ring_y, label, target)
    if o == "band":
        return bands.band_around(name, target, axis, at, width or 0.05, thickness, label)
    if o == "trace":
        return introspect.trace_profile(target, axis, sections)
    if o == "boolean":
        return modifiers.boolean(target, cutter, bool_op, solver, apply, hide_cutter, label)
    if o == "bridge":
        return editmode.bridge(a, b, label, bridge_cuts, smoothness,
                               interpolation, profile, twist)
    if o == "connect":
        return editmode.connect(a, b, style, tension, sections, connect_profile,
                                weld, name or "connector", label)
    if o == "reshape":
        return editmode.reshape(name, tension, label)
    if o == "resample":
        return editmode.resample(a, count, depth if depth > 0 else -1.0, label)
    if o == "strands":
        return editmode.strands(a, b, count, style, tension, sections, sides, jitter,
                                seed, strand_radius, name or "strands", label)
    if o == "relax":
        return editmode.relax_selection(iterations, strength, reproject, label, target)
    if o == "slide":
        return editmode.slide_selection(out, inward, up, down, left, right,
                                        forward, back, label, target)
    if o == "poke":
        return editmode.poke_faces(offset, label, target)
    if o == "inset":
        return editmode.inset_faces(thickness, depth, individual, label, target)
    if o == "grid_fill":
        return editmode.grid_fill(span, grid_offset, label, target)
    return unknown("edit", "op", op, _OPS)

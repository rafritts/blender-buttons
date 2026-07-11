"""edit — Edit Mode / the Mesh menu (SPEC-05).

Mesh-editing operations on the active object's geometry (its current selection):
extrude, bevel, loop cut, merge, delete, mark sharp, bend, boolean, spin, … `op`
selects the operation. The flat handlers manage entering Edit Mode on `target`.

SPEC-22 (native hands): every op here is a single native Blender operator under its
native name — the edit-mode hands the agent drives (extrude, bevel, loop_cut, grab/
scale of the selection, shrink_fatten, randomize, spin, bridge, …). The judgment-sugar
deformer composites were stripped; their bare native operators remain reachable (a
noise-textured Displace or a Bevel via `modifier op=add`, revolves via `op=spin`, etc.).
"""

from typing import Literal

from server._core import mcp
from server import editmode, finishes, introspect, modifiers, primitives
from ._common import tag, unknown, teach

_OPS = ["extrude", "bevel", "loop_cut", "merge", "symmetrize", "delete", "separate",
        "mark_sharp", "crease", "shrink_fatten", "randomize", "grab", "scale", "lattice",
        "bend", "trace", "boolean", "subdivide", "bridge", "spin",
        "poke", "inset", "grid_fill", "recalc_normals"]


@mcp.tool(name="edit")
def edit(
    op: Literal["extrude", "bevel", "loop_cut", "merge", "symmetrize", "delete", "separate",
                "mark_sharp", "crease", "shrink_fatten", "randomize", "grab", "scale",
                "lattice", "bend", "trace", "boolean", "subdivide",
                "bridge", "spin", "poke", "inset", "grid_fill", "recalc_normals"],
    target: tag(str, "mesh object to edit (empty=active); [lattice] the lattice cage object") = "",
    # bridge — weld two boundary handles (SPEC-07 Phase 5 / G10)
    a: tag(str, "[bridge] first boundary handle (order-independent)") = "",
    b: tag(str, "[bridge] second boundary handle to weld") = "",
    # bridge curvature dials (G58 — pass-through to Bridge Edge Loops; defaults = straight)
    bridge_cuts: tag(int, "[bridge] intermediate loops across the span (0=straight strut; raise to bow it)") = 0,
    smoothness: tag(float, "[bridge] tangent bow of the cuts (native default 1.0; needs bridge_cuts>0)") = 1.0,
    interpolation: tag(str, "[bridge] how cuts follow the rims: linear|path|surface") = "path",
    profile: tag(float, "[bridge] bulge the cross-section outward (profile_factor; 0=none)") = 0.0,
    twist: tag(int, "[bridge] rotate rim-to-rim vertex mapping (verts) to kill the spiral when rims face apart") = 0,
    # directional amounts (extrude / grab; meters, local frame)
    out: tag(float, "[extrude/grab] push out along normal (m)") = 0.0,
    inward: tag(float, "[extrude/grab] push inward (m)") = 0.0,
    up: tag(float, "[extrude/grab] +Z (m)") = 0.0,
    down: tag(float, "[extrude/grab] -Z (m)") = 0.0,
    left: tag(float, "[extrude/grab] -X (m)") = 0.0,
    right: tag(float, "[extrude/grab] +X (m)") = 0.0,
    forward: tag(float, "[extrude/grab] -Y (m)") = 0.0,
    back: tag(float, "[extrude/grab] +Y (m)") = 0.0,
    until_contact: tag(str, "[extrude] extrude until hitting this object") = "",
    until_length: tag(float, "[extrude] extrude to this total length (m)") = 0.0,
    x: tag(float, "[extrude/grab] explicit X amount (m)") = 0.0,
    y: tag(float, "[extrude/grab] explicit Y amount (m)") = 0.0,
    z: tag(float, "[extrude/grab] explicit Z amount (m)") = 0.0,
    # bevel
    width: tag(float, "[bevel] bevel width (m)") = 0.0,
    factor: tag(float, "[bevel] bevel amount as a factor (alt to width; unset→0.05); "
                       "[scale proportional] scale at the handle verts (<1 gathers/narrows, "
                       ">1 swells); radius-edge verts stay 1.0, lerped by falloff") = 1.0,
    segments: tag(int, "[bevel] bevel segments") = 1,
    affect: tag(str, "[bevel] EDGES | VERTICES") = "EDGES",
    # loop_cut / axis-based
    axis: tag(str, "[loop_cut/trace/bend/spin/randomize] axis X|Y|Z (bend: the axis to bend "
                   "AROUND — refused if it's the object's own long axis, pick a perpendicular "
                   "one; spin: the axis to REVOLVE around, through the object's origin)") = "Z",
    cuts: tag(int, "[loop_cut/subdivide] number of cuts to add") = 1,
    seed_at: tag(float, "[loop_cut] world coord on `axis` to aim the loop at one cross-section "
                        "(only edges straddling that plane are cut) — seeds a spanning ring on "
                        "forked topology instead of grabbing a stub loop (G183)") = None,
    only_selected: tag(bool, "[loop_cut/recalc_normals] scope to the current selection instead of "
                             "the whole mesh — loop_cut: cut only edges with BOTH ends selected "
                             "(rib one limb); recalc_normals: recalc/flip just one shell. Default "
                             "False = whole mesh (native Ctrl+R / Recalc Outside), so chained ops "
                             "need no reselect") = False,
    inside: tag(bool, "[recalc_normals] recalc to face INWARD (default False=outward)") = False,
    flip: tag(bool, "[recalc_normals] additionally flip every face normal after recalc") = False,
    subdivide_smooth: tag(float, "[subdivide] 0=flat (denser cage) … ~1=round toward limit surface") = 0.0,
    # merge / symmetrize / delete / sharp / crease
    threshold: tag(float, "[merge] merge-by-distance threshold (m); [symmetrize] seam-weld distance") = 0.001,
    selected_only: tag(bool, "[merge] merge only within the selection") = False,
    keep: tag(str, "[symmetrize] which half is the SOURCE mirrored onto the other: '+' | '-' along axis") = "+",
    mode: tag(str, "[delete] VERT|EDGE|FACE|ONLY_FACE|EDGE_FACE") = "VERT",
    clear: tag(bool, "[mark_sharp] clear instead of mark") = False,
    weight: tag(float, "[crease] crease weight 0..1") = 1.0,
    # shrink_fatten / randomize
    amount: tag(float, "[shrink_fatten/randomize] displacement amount (m)") = 0.003,
    seed: tag(int, "[randomize] random seed") = 0,
    only_positive: tag(bool, "[randomize] jitter outward only") = False,
    # grab / scale — proportional-edit option (O) + rigid vert scale
    proportional: tag(bool, "[grab/scale] enable proportional editing (O): a soft falloff drags "
                            "nearby verts along (radius, falloff, connected, freeze). Default "
                            "False = a rigid translate/scale of the selection only") = False,
    radius: tag(float, "[grab/scale proportional] falloff radius (m)") = 0.01,
    falloff: tag(str, "[grab/scale proportional] SMOOTH|SHARP|…") = "SMOOTH",
    connected: tag(bool, "[grab/scale proportional] geodesic (along-edges) falloff — won't drag a disconnected shell") = False,
    freeze: tag(str, "[grab/scale proportional] handle whose verts are held rigid (and wall off the falloff)") = "",
    sx: tag(float, "[scale] X scale factor") = 1.0,
    sy: tag(float, "[scale] Y scale factor") = 1.0,
    sz: tag(float, "[scale] Z scale factor") = 1.0,
    in_plane: tag(float, "[scale] in-plane scale (flatten)") = 0.0,
    vert_pivot: tag(str, "[scale] SELECTION (shared centre, default) | INDIVIDUAL (each connected "
                         "island about its OWN centre — even out N separate features in place) | "
                         "ORIGIN") = "SELECTION",
    # lattice (warp a deform cage's control points — G189)
    lat_u: tag(str, "[lattice] U points to move: all|min|max|mid|<index>|[lo,hi]") = None,
    lat_v: tag(str, "[lattice] V points to move: all|min|max|mid|<index>|[lo,hi]") = None,
    lat_w: tag(str, "[lattice] W points to move: all|min|max|mid|<index>|[lo,hi]") = None,
    lat_translate: tag(list, "[lattice] world-space delta [dx,dy,dz] (m)") = None,
    lat_scale: tag(list, "[lattice] scale the slab about the cage centre [sx,sy,sz]") = None,
    # separate
    new_name: tag(str, "[separate] name for the split-off object") = "",
    # bend / spin
    angle: tag(float, "[bend/spin] angle in degrees — bend arc / spin revolution (spin: "
                      "unset ⇒ a full 360°, seam auto-welded)") = 0.0,
    apply: tag(bool, "[bend] apply the bend modifier") = True,
    # trace / spin
    sections: tag(int, "[trace] cross-sections along the span; [spin] steps around the "
                       "revolution") = 24,
    # boolean
    cutter: tag(str, "[boolean] cutter object") = "",
    bool_op: tag(str, "[boolean] DIFFERENCE|UNION|INTERSECT") = "DIFFERENCE",
    solver: tag(str, "[boolean] EXACT|FLOAT (5.0 renamed 'Fast'->'Float'; legacy FAST ok)") = "EXACT",
    hide_cutter: tag(bool, "[boolean] hide the cutter afterward") = True,
    # poke / inset / grid_fill (G50) — face authoring
    offset: tag(float, "[poke] push the new centre vert along the face normal (m)") = 0.0,
    depth: tag(float, "[inset] push the inset in/out along the normal (m)") = 0.0,
    thickness: tag(float, "[inset] inset distance (m)") = 0.02,
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
    not the order you wrote them — so `loop_cut` then a deform in one batch can run the
    deform first against geometry the cut hasn't made yet, and it silently no-ops (the
    no-op detector flags the byte-identical result). Issue dependent edit ops sequentially,
    one per message. Independent edits on DIFFERENT meshes are fine to batch.

      extrude     — push the selection out (out/inward/up/down/left/right/forward/back
                    meters, or until_contact=obj / until_length)
      bevel       — round edges/verts   (width OR factor, segments, affect=EDGES|VERTICES)
      loop_cut    — add edge loops       (axis, cuts, seed_at=cross-section to seed a ring).
                    WHOLE-MESH by default, like native Ctrl+R — ignores the selection and
                    rings the whole mesh, so you can chain cuts (grid a cube: loop_cut X then
                    loop_cut Y) with NO reselect between them. only_selected=True opts into
                    scoping — cut only edges with BOTH ends selected, to rib one limb.
      recalc_normals — repair flipped normals IN PLACE (Shift-N) — fix a boolean
                    result whose shell inverted, or bad imported winding (inside, flip).
                    WHOLE-MESH by default (ignores leftover selection); only_selected=True
                    recalcs just one selected shell.
      subdivide   — densify the SELECTED patch locally — sculptable resolution where
                    you select, no global loops, no shape-key block  (cuts, subdivide_smooth)
      merge       — merge by distance    (threshold, selected_only)
      symmetrize  — make the mesh bilaterally symmetric across an axis plane through its
                    origin: one half mirrored onto the other and welded. How a SINGLE-MESH
                    organic edit stays bilateral — shape one side freely (grab / sculpt),
                    then symmetrize to reflect it true, with no per-op mirror flag and no
                    half-mesh MIRROR modifier. (axis=X|Y|Z plane normal, keep='+'|'-'
                    source half, threshold=seam weld)
      delete      — delete geometry      (mode=VERT|EDGE|FACE|ONLY_FACE|EDGE_FACE)
      separate    — split selection into a new object   (new_name)
      mark_sharp  — mark/clear sharp edges               (clear)
      crease      — set edge crease weight               (weight)
      shrink_fatten — Alt+S · push the selected verts along their OWN per-vert normals
                    (puffs/spreads a patch); amount in meters, negative = inward.
      randomize   — Mesh ▸ Transform ▸ Randomize · per-vertex WHITE noise → spiky
                    (amount, axis, seed, only_positive)
      grab        — G · MOVE the selection (out/inward/up/down/left/right/forward/back
                    meters, or x/y/z). proportional=True turns on proportional editing
                    (O): a soft falloff drags nearby verts along — the icing-drip pull
                    (radius, falloff, connected=geodesic, freeze=hold a handle rigid).
      scale       — S · SCALE the selection about its pivot (sx/sy/sz, in_plane=flatten
                    in the tangent plane, vert_pivot=SELECTION|INDIVIDUAL|ORIGIN).
                    proportional=True is the soft gather/swell toward the centroid with a
                    falloff — a drip narrows toward its tip (factor<1 gathers, >1 swells;
                    radius, falloff, connected, freeze).
      lattice     — Lattice edit (G/S on control points): warp a bound deform cage by
                    pushing a SLAB of its points; every mesh bound to it follows,
                    non-destructively. (lat_u/lat_v/lat_w slab pickers, lat_translate,
                    lat_scale)
      bend        — bend the object into an arc  (angle, axis, apply). Pivots about
                    the object ORIGIN and is SYMMETRIC about it — a bar centred on its
                    origin humps both ways ("mustache"); move the origin to one end
                    for a one-way crescent. apply=True forces OBJECT mode.
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
      spin        — NATIVE SPIN: revolve the selected PROFILE around a world axis
                    through the object's origin — the surface-of-revolution author
                    (goblet, plate, wheel: trace the silhouette as an edge run, spin it).
                    A full 360° welds the seam and recalcs normals outward.
                    (axis, angle=360, sections=steps around the turn)
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
        "boolean": (bool(cutter), "cutter=<object to cut with>",
                    "edit op=boolean target=block cutter=drill bool_op=DIFFERENCE"),
    })
    if bad:
        return bad
    if o == "extrude":
        return editmode.extrude(out, inward, up, down, left, right, forward, back,
                                until_contact, until_length, x, y, z, label, target)
    if o == "bevel":
        # factor's shared default is 1.0 (neutral for proportional scale); bevel's own
        # legacy default is 0.05, restored here when the caller left factor unset.
        return editmode.bevel(width, 0.05 if factor == 1.0 else factor,
                              segments, affect, label, target)
    if o == "loop_cut":
        return editmode.loop_cut(axis, cuts, label, target, seed_at, only_selected)
    if o == "recalc_normals":
        return editmode.recalc_normals(inside, flip, target, label, only_selected)
    if o == "subdivide":
        return editmode.subdivide_selection(cuts, subdivide_smooth, label, target)
    if o == "merge":
        return editmode.merge_by_distance(threshold, selected_only, label, target)
    if o == "symmetrize":
        return editmode.symmetrize(axis, keep, threshold, target, label)
    if o == "delete":
        return editmode.delete_geometry(mode, label, target)
    if o == "separate":
        return editmode.separate_selection(new_name, label, target)
    if o == "mark_sharp":
        return editmode.mark_sharp(clear, label, target)
    if o == "crease":
        return editmode.set_edge_crease(weight, label, target)
    if o == "shrink_fatten":
        return editmode.inflate_selection(amount, label, target)
    if o == "randomize":
        return editmode.jitter_vertices(amount, axis, seed, only_positive, label, target)
    if o == "grab":
        if proportional:
            return editmode.proportional_move(out, inward, up, down, left, right,
                                              forward, back, x, y, z, radius, falloff,
                                              connected, freeze, label, target)
        return editmode.move_vertices(out, inward, up, down, left, right, forward,
                                      back, x, y, z, label, target)
    if o == "scale":
        if proportional:
            return editmode.proportional_scale(factor, radius, falloff, connected, freeze,
                                               label, target)
        return editmode.scale_vertices(in_plane, sx, sy, sz, vert_pivot, label, target)
    if o == "lattice":
        return primitives.deform_lattice(target, lat_u, lat_v, lat_w,
                                         lat_translate, lat_scale, label)
    if o == "bend":
        return finishes.bend(target, angle, axis, apply, label)
    if o == "trace":
        return introspect.trace_profile(target, axis, sections)
    if o == "boolean":
        return modifiers.boolean(target, cutter, bool_op, solver, apply, hide_cutter, label)
    if o == "bridge":
        return editmode.bridge(a, b, label, bridge_cuts, smoothness,
                               interpolation, profile, twist)
    if o == "spin":
        return editmode.spin(axis, angle or 360.0, sections, label, target)
    if o == "poke":
        return editmode.poke_faces(offset, label, target)
    if o == "inset":
        return editmode.inset_faces(thickness, depth, individual, label, target)
    if o == "grid_fill":
        return editmode.grid_fill(span, grid_offset, label, target)
    return unknown("edit", "op", op, _OPS)

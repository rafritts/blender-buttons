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
        "poke", "inset", "grid_fill", "recalc_normals",
        "duplicate", "rotate", "dissolve", "hide", "reveal", "rip", "split",
        "smooth", "bisect", "shear", "to_sphere", "triangulate", "tris_to_quads",
        "edge_face", "fill", "beautify", "connect", "slide"]


@mcp.tool(name="edit")
def edit(
    op: Literal["extrude", "bevel", "loop_cut", "merge", "symmetrize", "delete", "separate",
                "mark_sharp", "crease", "shrink_fatten", "randomize", "grab", "scale",
                "lattice", "bend", "trace", "boolean", "subdivide",
                "bridge", "spin", "poke", "inset", "grid_fill", "recalc_normals",
                "duplicate", "rotate", "dissolve", "hide", "reveal", "rip", "split",
                "smooth", "bisect", "shear", "to_sphere", "triangulate", "tris_to_quads",
                "edge_face", "fill", "beautify", "connect", "slide"],
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
                       ">1 swells); radius-edge verts stay 1.0, lerped by falloff; "
                       "[smooth] relax strength (unset→0.5); [slide] fraction along the rail "
                       "edge, -1..1, sign picks the side (unset→0.5); [to_sphere] blend toward "
                       "a sphere 0..1 (1=full)") = 1.0,
    segments: tag(int, "[bevel] bevel segments") = 1,
    affect: tag(str, "[bevel] EDGES | VERTICES") = "EDGES",
    # loop_cut / axis-based
    axis: tag(str, "[loop_cut/trace/bend/spin/randomize/rotate/bisect/shear] axis X|Y|Z "
                   "(bend: the axis to bend AROUND — refused if it's the object's own long "
                   "axis, pick a perpendicular one; spin: the axis to REVOLVE around, through "
                   "the object's origin; rotate: rotation axis; bisect: cut-plane normal; "
                   "shear: the direction verts slide)") = "Z",
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
    at: tag(str, "[merge] where to weld the selection: CENTER (median) | CURSOR | FIRST | "
                 "LAST | COLLAPSE (each island to its own centre) | DISTANCE (weld coincident, "
                 "the by-distance path). Native M-menu.") = "CENTER",
    keep: tag(str, "[symmetrize] which half is the SOURCE mirrored onto the other: '+' | '-' along axis") = "+",
    mode: tag(str, "[delete] VERT|EDGE|FACE|ONLY_FACE|EDGE_FACE; [dissolve] VERT|EDGE|FACE") = "VERT",
    clear: tag(bool, "[mark_sharp] clear instead of mark") = False,
    weight: tag(float, "[crease] crease weight 0..1") = 1.0,
    # shrink_fatten / randomize
    amount: tag(float, "[shrink_fatten/randomize] displacement amount (m); [shear] shear "
                       "factor (unitless slant, e.g. 0.5)") = 0.003,
    even: tag(bool, "[shrink_fatten] native 'Offset Even' — correct the push by vertex-normal "
                    "angle so a non-planar patch keeps even wall thickness (native default off)") = False,
    along: tag(str, "[shear] the gradient axis: verts displace along `axis` in proportion to "
                    "their coordinate along this one (X|Y|Z, must differ from axis)") = "Z",
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
    snap_to: tag(str, "[grab] native Snapping mode — 'face_project' drops each moved vert "
                      "onto the surface of snap_target after the grab (drape verts onto "
                      "another mesh's face). Empty = no snapping (default).") = "",
    snap_target: tag(str, "[grab snap_to=face_project] the mesh to project the moved verts onto") = "",
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
    # bend / spin / rotate
    angle: tag(float, "[bend/spin/rotate] angle in degrees — bend arc / spin revolution / "
                      "rotate the selection about its median (spin: unset ⇒ a full 360°, "
                      "seam auto-welded)") = 0.0,
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
    offset: tag(float, "[poke] push the new centre vert along the face normal (m); "
                       "[bisect] the cut plane's position along `axis` (world m)") = 0.0,
    depth: tag(float, "[inset] push the inset in/out along the normal (m)") = 0.0,
    thickness: tag(float, "[inset] inset distance (m)") = 0.02,
    individual: tag(bool, "[inset] inset each face separately vs. the region as a whole") = False,
    span: tag(int, "[grid_fill] grid span (0 = auto)") = 0,
    grid_offset: tag(int, "[grid_fill] grid offset") = 0,
    # SPEC-22 Phase 4 native ops
    repeat: tag(int, "[smooth] smoothing iterations (native default 1)") = 1,
    unselected: tag(bool, "[hide] hide the UNSELECTED elements instead (Shift+H)") = False,
    use_fill: tag(bool, "[bisect] fill the cut plane with a face") = False,
    clear_inner: tag(bool, "[bisect] delete the geometry on the negative-normal side") = False,
    clear_outer: tag(bool, "[bisect] delete the geometry on the positive-normal side") = False,
    use_beauty: tag(bool, "[fill] arrange the fill triangles for better shape (native default on)") = True,
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

      extrude     — E · Mesh ▸ Extrude · push the selection out
                    (out/inward/up/down/left/right/forward/back meters, or
                    until_contact=obj / until_length)
      bevel       — Ctrl+B · Edge/Vertex ▸ Bevel · round edges/verts
                    (width OR factor, segments, affect=EDGES|VERTICES)
      loop_cut    — Ctrl+R · Edge ▸ Loop Cut · add edge loops (axis, cuts,
                    seed_at=cross-section to seed a ring). WHOLE-MESH by default, like
                    native Ctrl+R — ignores the selection and rings the whole mesh, so you
                    can chain cuts (grid a cube: loop_cut X then loop_cut Y) with NO reselect
                    between them. only_selected=True opts into scoping — cut only edges with
                    BOTH ends selected, to rib one limb.
      recalc_normals — Shift+N · Mesh ▸ Normals ▸ Recalculate Outside · repair flipped
                    normals IN PLACE — fix a boolean result whose shell inverted, or bad
                    imported winding (inside, flip). WHOLE-MESH by default (ignores leftover
                    selection); only_selected=True recalcs just one selected shell.
      subdivide   — Edge ▸ Subdivide · densify the SELECTED patch locally — sculptable
                    resolution where you select, no global loops  (cuts, subdivide_smooth)
      merge       — M · Mesh ▸ Merge · weld the selection to one point. at=CENTER (median) |
                    CURSOR | FIRST | LAST | COLLAPSE (each island to its own centre) |
                    DISTANCE (weld coincident verts — threshold, selected_only).
      symmetrize  — Mesh ▸ Symmetrize · make the mesh bilaterally symmetric across an axis
                    plane through its origin: one half mirrored onto the other and welded.
                    How a SINGLE-MESH organic edit stays bilateral — shape one side freely
                    (grab / sculpt), then symmetrize to reflect it true, with no per-op mirror
                    flag and no half-mesh MIRROR modifier. (axis=X|Y|Z plane normal,
                    keep='+'|'-' source half, threshold=seam weld)
      delete      — X · Mesh ▸ Delete · delete geometry, leaving holes
                    (mode=VERT|EDGE|FACE|ONLY_FACE|EDGE_FACE)
      dissolve    — Ctrl+X · Mesh ▸ Dissolve · remove the selected elements but KEEP the
                    surrounding surface (merges neighbours into a larger face) — distinct
                    from delete, which makes a hole. (mode=VERT|EDGE|FACE)
      separate    — P · Mesh ▸ Separate ▸ Selection · split the selection into a NEW object
                    (new_name)
      mark_sharp  — Edge ▸ Mark Sharp · mark/clear sharp edges               (clear)
      crease      — Shift+E · Edge ▸ Crease · set edge crease weight          (weight)
      shrink_fatten — Alt+S · Mesh ▸ Transform ▸ Shrink/Fatten · push the selected verts
                    along their OWN per-vert normals (puffs/spreads a patch); amount in
                    meters, negative = inward. even=native Offset Even.
      randomize   — Mesh ▸ Transform ▸ Randomize · per-vertex WHITE noise → spiky
                    (amount, axis, seed, only_positive)
      grab        — G · Mesh ▸ Transform ▸ Move · MOVE the selection
                    (out/inward/up/down/left/right/forward/back meters, or x/y/z).
                    proportional=True turns on proportional editing (O): a soft falloff drags
                    nearby verts along — the icing-drip pull (radius, falloff,
                    connected=geodesic, freeze=hold a handle rigid). snap_to='face_project'
                    drapes the moved verts onto snap_target's surface (native Snapping).
      scale       — S · Mesh ▸ Transform ▸ Scale · SCALE the selection about its pivot
                    (sx/sy/sz, in_plane=flatten in the tangent plane,
                    vert_pivot=SELECTION|INDIVIDUAL|ORIGIN). proportional=True is the soft
                    gather/swell toward the centroid with a falloff — a drip narrows toward
                    its tip (factor<1 gathers, >1 swells; radius, falloff, connected, freeze).
      rotate      — R · Mesh ▸ Transform ▸ Rotate · rotate the selection about its own
                    median around a world axis (angle degrees, axis=X|Y|Z).
      shear       — Shift+Ctrl+Alt+S · Mesh ▸ Transform ▸ Shear · slant the selection —
                    verts displace along `axis` in proportion to their `along` coordinate
                    (amount=shear factor, axis=direction, along=gradient axis).
      to_sphere   — Shift+Alt+S · Mesh ▸ Transform ▸ To Sphere · blend the selection toward
                    a sphere about its median (factor 0..1).
      duplicate   — Shift+D · Mesh ▸ Duplicate · copy the selected geometry IN-MESH; the copy
                    is selected and (default) unmoved — pass direction words to grab it away
                    in the same call (out/up/x/…).
      rip         — V · Vertex ▸ Rip · tear the mesh open along the selected edge(s)/vert
                    chain, splitting shared verts so the sides part; pass direction words to
                    pull the torn side away.
      split       — Y · Mesh ▸ Split ▸ Selection · disconnect the selected geometry from the
                    rest (stays in the same object as a loose island).
      slide       — Vertex/Edge Slide (Shift+V / GG) · Vertex/Edge ▸ Slide · move the
                    selected verts ALONG their neighbouring edges (factor -1..1, sign picks
                    the rail), staying on the topology.
      smooth      — Vertex ▸ Smooth Vertices · relax selected verts toward their neighbours'
                    average (factor, repeat).
      bisect      — Mesh ▸ Bisect · cut the geometry with an infinite plane (axis + offset;
                    use_fill, clear_inner, clear_outer).
      triangulate — Ctrl+T · Face ▸ Triangulate Faces · quads/n-gons → triangles.
      tris_to_quads — Alt+J · Face ▸ Tris to Quads · merge adjacent triangles back to quads.
      edge_face   — F · Vertex ▸ New Edge/Face from Vertices · 2 selected verts → an edge,
                    3+ / a boundary chain → a face (the "F closes it" reflex).
      fill        — Alt+F · Face ▸ Fill · fill a selected closed edge boundary with triangles
                    (use_beauty).
      beautify    — Shift+Alt+F · Face ▸ Beautify Faces · re-flip shared edges of the selected
                    triangles toward a balanced triangulation.
      connect     — J · Vertex ▸ Connect Vertices · cut a new edge between selected verts
                    across the face they share (split a quad in two).
      hide        — H (Shift+H unselected) · Mesh ▸ Show/Hide ▸ Hide · hide selected elements
                    in edit mode (unselected=True hides the rest).
      reveal      — Alt+H · Mesh ▸ Show/Hide ▸ Reveal · unhide everything hidden in edit mode.
      lattice     — Lattice edit (G/S on control points): warp a bound deform cage by
                    pushing a SLAB of its points; every mesh bound to it follows,
                    non-destructively. (lat_u/lat_v/lat_w slab pickers, lat_translate,
                    lat_scale)
      bend        — Mesh ▸ Transform ▸ Bend · bend the object into an arc  (angle, axis,
                    apply). Pivots about the object ORIGIN and is SYMMETRIC about it — a bar
                    centred on its origin humps both ways ("mustache"); move the origin to one
                    end for a one-way crescent. apply=True forces OBJECT mode.
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
      spin        — Mesh ▸ Extrude ▸ Spin · revolve the selected PROFILE around a world axis
                    through the object's origin — the surface-of-revolution author
                    (goblet, plate, wheel: trace the silhouette as an edge run, spin it).
                    A full 360° welds the seam and recalcs normals outward.
                    (axis, angle=360, sections=steps around the turn)
      poke        — Face ▸ Poke Faces · fan each selected face out from a new centre vert →
                    mints a POLE (radial centre) where the form wants one. FACE mode. (offset)
      inset       — I · Face ▸ Inset Faces · ring the selected faces with a new face band
                    (shrink a copy inward); adds an edge loop to define/tighten a feature.
                    FACE mode. (thickness, depth, individual)
      grid_fill   — Face ▸ Grid Fill · fill a selected closed edge loop with a clean quad grid
                    (re-flow a hole/region instead of a fan). One even-vert loop selected.
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
        return editmode.merge(at, threshold, selected_only, label, target)
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
        return editmode.inflate_selection(amount, even, label, target)
    if o == "randomize":
        return editmode.jitter_vertices(amount, axis, seed, only_positive, label, target)
    if o == "grab":
        if proportional:
            return editmode.proportional_move(out, inward, up, down, left, right,
                                              forward, back, x, y, z, radius, falloff,
                                              connected, freeze, label, target)
        return editmode.move_vertices(out, inward, up, down, left, right, forward,
                                      back, x, y, z, label, target, snap_to, snap_target)
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
    if o == "duplicate":
        return editmode.duplicate_selection(out, inward, up, down, left, right,
                                            forward, back, x, y, z, label, target)
    if o == "rotate":
        return editmode.rotate_selection(angle, axis, label, target)
    if o == "dissolve":
        return editmode.dissolve(mode, label, target)
    if o == "hide":
        return editmode.hide_geometry(unselected, label, target)
    if o == "reveal":
        return editmode.reveal_geometry(label, target)
    if o == "rip":
        return editmode.rip_selection(out, inward, up, down, left, right,
                                      forward, back, x, y, z, label, target)
    if o == "split":
        return editmode.split_selection(label, target)
    if o == "smooth":
        return editmode.smooth_vertices(0.5 if factor == 1.0 else factor, repeat,
                                        label, target)
    if o == "bisect":
        return editmode.bisect(axis, offset, use_fill, clear_inner, clear_outer,
                               label, target)
    if o == "shear":
        return editmode.shear_selection(amount, axis, along, label, target)
    if o == "to_sphere":
        return editmode.to_sphere(factor, label, target)
    if o == "triangulate":
        return editmode.triangulate(label, target)
    if o == "tris_to_quads":
        return editmode.tris_to_quads(label=label, target=target)
    if o == "edge_face":
        return editmode.make_edge_face(label, target)
    if o == "fill":
        return editmode.fill(use_beauty, label, target)
    if o == "beautify":
        return editmode.beautify(label=label, target=target)
    if o == "connect":
        return editmode.connect_verts(label, target)
    if o == "slide":
        return editmode.slide(0.5 if factor == 1.0 else factor, "EDGE", label, target)
    return unknown("edit", "op", op, _OPS)

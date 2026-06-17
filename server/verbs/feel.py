"""feel — the sense (SPEC-04 + measurements + lint).

Understanding a mesh's STRUCTURE, not its bounding box — plus geometric truth
(distances, gaps, alignment, symmetry) and correctness checks (lint). Read-only:
`feel` IS perception, so it does NOT carry the status block. `op` selects what to
feel; op="topology" (default) is the structural sense.
"""

from typing import Literal

from server._core import mcp
from server import topology, queries, rings, introspect, lint, handles, assembly
from ._common import tag, unknown

_OPS = ["topology", "profile", "silhouette", "section", "rings", "distance", "gap",
        "aligned", "symmetry", "mesh", "overlaps", "validate", "audit", "contacts",
        "resting", "aim", "handle", "handles", "accept", "forget", "assembly", "map",
        "relate"]


@mcp.tool(name="feel")
def feel(
    op: Literal["topology", "profile", "silhouette", "section", "rings", "distance",
                "gap", "aligned", "symmetry", "mesh", "overlaps", "validate", "audit",
                "contacts", "resting", "aim", "handle", "handles", "accept", "forget",
                "assembly", "map", "relate"] = "topology",
    target: tag(str, "[topology/rings/symmetry/mesh] mesh object (empty=active); "
                     "[map] cast from every boundary handle on this mesh") = "",
    # topology (SPEC-04)
    method: tag(str, "[topology] comma list of method tokens (empty = cheap bundle: "
                     "components,genus,boundaries,sections,poles,symmetry,frame). "
                     "Extra: structure,curvature,region_form,features,thickness") = "",
    lod: tag(str, "[topology] low|medium|high output verbosity") = "low",
    base: tag(str, "[topology] cage | evaluated mesh to read") = "cage",
    seed: tag(str, "[topology] handle for seeded methods (v2)") = "",
    # profile / rings
    axis: tag(str, "[profile/rings/symmetry] axis X|Y|Z (distance: X|Y for 1-axis)") = "Z",
    min: tag(float, "[profile] window start on axis (m, world-space)") = None,
    max: tag(float, "[profile] window end on axis (m, world-space)") = None,
    bands: tag(int, "[profile] aggregation band count (default 24)") = 0,
    full: tag(bool, "[profile] True = raw per-ring dump instead of aggregated bands") = False,
    max_rings: tag(int, "[profile] max rings in full mode (0 = uncap)") = 200,
    res: tag(int, "[silhouette] occupancy-grid resolution on the wider axis (default 32)") = 32,
    sections: tag(int, "[section] number of evenly spaced slices (default 12)") = 12,
    selection: tag(bool, "[silhouette] project only the live selection's verts") = False,
    # measurements
    a: tag(str, "[distance/gap/aligned] first object; [relate] first boundary handle") = "",
    b: tag(str, "[distance/gap/aligned] second object; [relate] second boundary handle") = "",
    side: tag(str, "[aligned] TOP|BOTTOM|… side to compare") = "TOP",
    tolerance: tag(float, "[aligned] alignment tolerance (m)") = 0.001,
    # symmetry
    plane: tag(float, "[symmetry] mirror plane offset") = 0.0,
    epsilon: tag(float, "[symmetry/overlaps/validate] tolerance") = None,
    # lint / check
    targets: tag(str, "[overlaps/validate/contacts/resting/assembly] object(s) to check; "
                      "assembly: '' = all scene meshes, 'a,b,c' = just those") = "",
    group: tag(str, "[audit/assembly] group/collection (assembly: read this collection's meshes)") = "",
    tri_budget: tag(int, "[audit] triangle budget") = 5000,
    # aim — surface-relative addressing (G1 / SPEC-06)
    face: tag(str, "[aim] local bbox face to cast FROM: -Y +Y -X +X -Z +Z (-Y = ray travels +Y into the volume)") = "-Y",
    u: tag(float, "[aim] 0..1 on the face, first of the other two local axes (X<Y<Z)") = 0.5,
    v: tag(float, "[aim] 0..1 on the face, second of the other two local axes") = 0.5,
    margin: tag(float, "[aim/map] extra cast start distance outside the face/opening (m)") = 0.0,
    # handles — named spatial anchors (SPEC-07)
    name: tag(str, "[handle/accept] handle name (optional at mint — auto-named handle.001-style if empty)") = "",
    handle: tag(str, "[map] boundary handle to cast FROM (run feel op=assembly first to mint them)") = "",
    source: tag(str, "[handle] addressing mode: selection (the live edit-mode selection)") = "selection",
    vertex_parent: tag(bool, "[handle] vertex-parent the Empty to a tracking vert so it rides pose/deform (default off; the vgroup recompute stays the source of truth)") = False,
    prune: tag(bool, "[handles] also garbage-collect orphaned handles (delete the ✗ unresolvable Empties), then list what remains") = False,
) -> str:
    """
    Feel a mesh — structure, measurements, correctness. Read-only (no status block).
    `op` selects:

      topology — STRUCTURE (default). `method` = comma list of these tokens
                 (empty = the cheap bundle, the first seven):
                   structure  — THE structural read (a DISPATCHER): triages the
                                mesh (open holes? solid? through-holes? shells?) and
                                runs the lens(es) that fit. Today: the protrusion
                                lens (cuffs/limbs with cut lines) on open shells;
                                names regimes it can't yet read. (not in bundle)
                   components — separate shells (fused vs not)
                   genus      — sphere/tube/handled + holes through it
                   boundaries — the open holes: size + location (the "openings")
                   sections   — cross-section sweep: coverage, voids, branch splits
                   poles      — valence≠4 verts (quad-flow breaks)
                   symmetry   — best mirror plane + error, per axis
                   frame      — intrinsic principal axes
                   curvature  — flats/ridges/domes/saddles  (not in bundle)
                   region_form— FORM of the current SELECTION: convex/concave verdict,
                                projection (cm), L/R mirror error — the form scalars a
                                bbox can't show. Select a patch, read between strokes.
                                (not in bundle; needs a selection)
                   protrusion — ABSOLUTE protrusion of the SELECTION above its
                                surrounding ring, in cm. Unlike region_form (shape-
                                relative, invariant to self-similar growth), this is a
                                ruler that moves when the form grows — diff before/after
                                to confirm "it got 2cm bigger". (needs a selection)
                   features   — hard dihedral edges in chains (not in bundle)
                   thickness  — local wall/part diameter      (not in bundle)
                 lod=low|medium|high; base=cage|evaluated. (target, method, lod, base)
      profile  — cross-section width sweep along an axis: by default AGGREGATED into
                 bands with the narrowest/widest flagged; full=True dumps every ring
                 (axis, min, max, bands, full)
      silhouette — orthographic projected OUTLINE along a view axis as a coarse '#'/'.'
                 occupancy grid — the 2D shape read directly (teardrop vs cone), not
                 reconstructed from two 1D profiles. Pure geometry, not a render.
                 (axis = look-along axis, res, selection)
      section  — TRUE cross-section perimeter + enclosed area per slice (real contour
                 edge-length & shoelace, not bbox width) — circumference / girth /
                 cross-sectional area as first-class numbers.   (axis, sections, min, max)
      rings    — edge-ring structure along an axis           (axis, target)
      distance — distance between two objects (a, b; default ANY = nearest-surface,
                 reconciles with contacts; axis=X|Y|Z = single-axis centre-to-centre)
      gap      — surface-to-surface gap between two objects   (a, b)
      aligned  — are two objects aligned on a side?    (a, b, side=TOP|BOTTOM|…, tolerance)
      symmetry — mirror symmetry of a mesh    (target, axis, plane, epsilon)
      mesh     — lint one mesh (non-manifold, doubles, normals, …)   (target)
      overlaps — coplanar overlapping faces (z-fighting)     (targets, epsilon→tolerance)
      validate — scene-wide hygiene pass                     (targets)
      audit    — asset budget/quality audit of a group       (group, tri_budget)
      contacts — which objects touch which                   (targets)
      resting  — are objects resting on / floating above surfaces? (targets)
      aim      — cast a normalized bbox-face aim onto the surface → world point +
                 normal, to feed sculpt/select/add. The constructive-side
                 `feel structure`: aim in fractions of the form, get the coordinate
                 back instead of dead-reckoning it.   (target, face, u, v, margin)
      handle   — mint a named spatial anchor from the live edit-mode selection: an
                 Empty in a `Handles` collection + a `HANDLE_<name>` vertex group on
                 the owning mesh, visible/renamable/deletable in the Outliner. The
                 reusable, named alternative to throwaway coordinates. Snapshots
                 provenance (mint point + drift signatures) so it tracks clean/dirty/
                 orphaned thereafter.      (name, source=selection, vertex_parent)
      handles  — list every handle, each VALIDATED: live point + git-style state
                 (● clean / ⚠ dirty / ✗ orphaned), drift in cm, and attribution
                 (self = an agent op moved it; external = the human did). prune=True
                 also garbage-collects the orphaned handles first.    (prune)
      accept   — re-baseline a dirty handle: re-snapshot its provenance from current
                 geometry, clearing the drift (the 'stage it' move).      (name)
      forget   — delete ONE named handle regardless of state (the targeted prune):
                 removes the Empty + its HANDLE_ vgroup.                   (name)
      assembly — the RELATIONAL map over a SET of objects (multi-feel): per-object
                 size, each one's open boundary loops (the catalog — verts, cm,
                 region), and the pairwise gaps. Auto-mints every open boundary as a
                 named Class-A handle `<object>.<region>` (deduped, re-runs reuse), so
                 the relations become addressable by name.  (targets='' = all scene
                 meshes | 'a,b,c', or group=<collection>)
      map      — loose spatial adjacency: cast a ray from a boundary handle's centre
                 along its plane normal and report what OTHER mesh it looks out onto
                 + distance (or a miss). Reports the hit as a coordinate; mints
                 nothing (a smooth-face hit is Class-B, agent-minted only).
                 (handle=<one> OR target=<mesh, all its boundaries>, margin)
      relate   — relate TWO named boundary handles: centre gap, axis alignment (do
                 the openings face each other?), and size match — the read a
                 bridge/weld needs to decide IF two openings can join, before it
                 tries. op=map's loop-plane math on a named PAIR.        (a, b)
    """
    o = op.lower().strip()
    if o == "topology":
        return topology.get_topology(target, method, lod, base, seed)
    if o == "profile":
        return queries.get_mesh_profile(axis, min, max, max_rings, bands, full)
    if o == "silhouette":
        return queries.get_silhouette(axis, res, selection)
    if o == "section":
        return queries.get_section(axis, sections, min, max)
    if o == "rings":
        return rings.get_rings(axis, target)
    if o == "distance":
        return queries.distance_between(a, b, axis if axis != "Z" else "ANY")
    if o == "gap":
        return queries.gap_between(a, b)
    if o == "aligned":
        return queries.is_aligned(a, b, side, tolerance)
    if o == "symmetry":
        return queries.check_symmetry(target, axis, plane, epsilon)
    if o == "mesh":
        return lint.check_mesh(target)
    if o == "overlaps":
        return lint.find_coplanar_overlaps(targets, epsilon if epsilon is not None else 0.0001)
    if o == "validate":
        return lint.validate_scene(targets, epsilon if epsilon is not None else 0.0001)
    if o == "audit":
        return lint.audit_asset(group, tri_budget)
    if o == "contacts":
        return introspect.check_contacts(targets)
    if o == "resting":
        return introspect.check_resting(targets)
    if o == "aim":
        return queries.aim_surface(target, face, u, v, margin)
    if o == "handle":
        return handles.mint_handle(name, source, vertex_parent)
    if o == "handles":
        if prune:
            pruned = handles.prune_handles()
            return pruned + "\n" + handles.list_handles()
        return handles.list_handles()
    if o == "accept":
        return handles.accept_handle(name)
    if o == "forget":
        return handles.forget_handle(name)
    if o == "assembly":
        return assembly.feel_assembly(targets, group)
    if o == "map":
        return assembly.feel_map(handle, target, margin)
    if o == "relate":
        return assembly.feel_relate(a, b)
    return unknown("feel", "op", op, _OPS)

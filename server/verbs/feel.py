"""feel — the sense (SPEC-04 + measurements + lint).

Understanding a mesh's STRUCTURE, not its bounding box — plus geometric truth
(distances, gaps, alignment, symmetry) and correctness checks (lint). Read-only:
`feel` IS perception, so it does NOT carry the status block. `op` selects what to
feel; op="topology" (default) is the structural sense.
"""

from typing import Literal

from server._core import mcp
from server import topology, queries, rings, introspect, lint, handles, assembly, editmode, fit
from ._common import tag, unknown

_OPS = ["all", "topology", "profile", "silhouette", "section", "rings", "distance", "gap",
        "aligned", "linked", "symmetry", "mesh", "overlaps", "validate", "audit", "contacts",
        "clearance", "resting", "aim", "place", "radial", "anchor", "verify", "baseline", "diff",
        "handle", "handles", "accept", "forget", "assembly", "map", "relate", "curve", "fit",
        "coverage", "stats"]

# SPEC-16: the perceptual bundle a bare `feel` / `feel op=all` runs — the whole-mesh
# reads that need only a target (no live selection, no second object). The agent opts
# OUT with exclude=, not in: breadth is free, trimming costs a keystroke.
_ALL_BUNDLE = ["topology", "profile", "section", "silhouette"]


@mcp.tool(name="feel")
def feel(
    op: Literal["all", "topology", "profile", "silhouette", "section", "rings", "distance",
                "gap", "aligned", "linked", "symmetry", "mesh", "overlaps", "validate",
                "audit", "contacts", "clearance", "resting", "aim", "place", "radial",
                "anchor", "verify", "baseline", "diff", "handle", "handles", "accept",
                "forget", "assembly", "map", "relate", "curve", "fit", "coverage",
                "stats"] = "all",
    exclude: tag(str, "[all] comma list of bundle reads to SKIP "
                      "(e.g. silhouette,section) — opt out, don't opt in") = "",
    target: tag(str, "[topology/profile/silhouette/section/rings/symmetry/mesh] mesh "
                     "object (empty=active); "
                     "[map] cast from every boundary handle on this mesh") = "",
    # topology (SPEC-04)
    method: tag(str, "[topology] comma list of method tokens (empty = cheap bundle: "
                     "components,genus,boundaries,sections,poles,symmetry,frame). "
                     "Extra: structure,facing,curvature,region_form,features,thickness,relief "
                     "(facing = signed up/front/left/right frame; relief = salient feature "
                     "discovery: where are the bumps/dents)") = "",
    lod: tag(str, "[topology] low|medium|high output verbosity") = "low",
    seed: tag(str, "[topology] handle for seeded methods (v2)") = "",
    radius: tag(float, "[topology method=relief] feature scale in m (default ~4% of the mesh diagonal)") = 0.0,
    top_n: tag(int, "[topology method=relief] cap on features returned (0 = default by lod)") = 0,
    # profile / rings
    axis: tag(str, "[profile/rings/symmetry] axis X|Y|Z (distance: X|Y for 1-axis)") = "Z",
    min: tag(float, "[profile] window start on axis (m, world-space)") = None,
    max: tag(float, "[profile] window end on axis (m, world-space)") = None,
    bands: tag(int, "[profile] aggregation band count (default 24)") = 0,
    full: tag(bool, "[profile] True = raw per-ring dump instead of aggregated bands") = False,
    max_rings: tag(int, "[profile] max rings in full mode (0 = uncap)") = 200,
    res: tag(int, "[silhouette] occupancy-grid resolution on the wider axis (default 32)") = 32,
    resolution: tag(int, "[curve] samples per Bezier segment (default 24)") = 24,
    profile_radius: tag(float, "[curve] tube radius to test the bend against — min bend radius must exceed it") = None,
    sections: tag(int, "[section] number of evenly spaced slices (default 12)") = 12,
    selection: tag(bool, "[silhouette] project only the live selection's verts") = False,
    # measurements
    a: tag(str, "[distance/gap/aligned/linked] first object; [relate] first boundary handle") = "",
    b: tag(str, "[distance/gap/aligned/linked] second object; [relate] second boundary handle") = "",
    side: tag(str, "[aligned] TOP|BOTTOM|… side to compare") = "TOP",
    tolerance: tag(float, "[aligned] alignment tolerance (m)") = 0.001,
    # symmetry
    plane: tag(float, "[symmetry] mirror plane offset") = 0.0,
    epsilon: tag(float, "[symmetry/overlaps/validate] tolerance") = None,
    # lint / check
    targets: tag(str, "[overlaps/validate/contacts/resting/assembly] object(s) to check; "
                      "assembly: '' = all scene meshes, 'a,b,c' = just those") = "",
    shell: tag(str, "[clearance] the cladding object (garment/case/armor) that must clear the surface") = "",
    surface: tag(str, "[clearance] the surface being wrapped (body/phone/jar)") = "",
    threshold: tag(float, "[clearance] minimum clearance in mm; when set, adds a pass/fail verdict") = None,
    samples: tag(int, "[clearance] cap on shell verts sampled (default 2000)") = 2000,
    group: tag(str, "[audit/assembly] group/collection (assembly: read this collection's meshes)") = "",
    tri_budget: tag(int, "[audit] triangle budget") = 5000,
    # aim — surface-relative addressing (G1 / SPEC-06)
    face: tag(str, "[aim] bbox face to cast FROM: -Y +Y -X +X -Z +Z (-Y = ray travels +Y into the volume)") = "-Y",
    u: tag(float, "[aim] 0..1 on the face, first of the other two axes (X<Y<Z)") = 0.5,
    v: tag(float, "[aim] 0..1 on the face, second of the other two axes") = 0.5,
    aim_frame: tag(str, "[aim] world (default; face/u/v are world axes like every other read) | local (mesh's rotation-baked bbox frame, G39)") = "world",
    margin: tag(float, "[aim/map] extra cast start distance outside the face/opening (m)") = 0.0,
    # handles — named spatial anchors (SPEC-07)
    name: tag(str, "[handle/accept] handle name (optional at mint — auto-named handle.001-style if empty)") = "",
    handle: tag(str, "[map] boundary handle to cast FROM (run feel op=assembly first to mint them)") = "",
    source: tag(str, "[handle] addressing mode: selection (the live edit-mode selection)") = "selection",
    vertex_parent: tag(bool, "[handle] vertex-parent the Empty to a tracking vert so it rides pose/deform (default off; the vgroup recompute stays the source of truth)") = False,
    prune: tag(bool, "[handles] also garbage-collect orphaned handles (delete the ✗ unresolvable Empties), then list what remains") = False,
    # place — surface-relative placement off a named handle (G47); anchor — live-selection anchor (SPEC-09)
    up: tag(float, "[place] offset +Z (m)") = 0.0,
    down: tag(float, "[place] offset -Z (m)") = 0.0,
    front: tag(float, "[place] offset -Y (m)") = 0.0,
    back: tag(float, "[place] offset +Y (m)") = 0.0,
    left: tag(float, "[place] offset -X (m)") = 0.0,
    right: tag(float, "[place] offset +X (m)") = 0.0,
    snap: tag(bool, "[place/radial] ray-snap the offset point onto the surface (default True)") = True,
    anchor: tag(str, "[radial] round object (bbox centre = ring centre) or handle (its point+plane)") = "",
    angle: tag(float, "[radial] clock angle in degrees CLOCKWISE from 12 o'clock (0=top, 90=3 o'clock)") = 0.0,
    crossing: tag(str, "[radial] which wall to land on for a ring/holed anchor: 'outer' (the rim — "
                       "default when radius=0) or 'inner' (the hole wall). Casts from the centre "
                       "outward and resolves the real radius, so radius=0 no longer collapses to "
                       "the empty bbox centre (G102/G128). Omit + give radius= to place at a fixed distance.") = "",
    as_handle: tag(str, "[aim/place/anchor/radial/map] mint a named POINT handle at the read's hit "
                        "so the measured point is addressable by name (transform op=move_to "
                        "handle=, aim_axis, sculpt handle=) — no coordinate ever typed (G78)") = "",
    steps: tag(int, "[verify] rings to grow/shrink the selection when perturbing (default 1)") = 1,
    # fit (SPEC-14 / G100) — describe a selection as parametric form
    model: tag(str, "[fit] auto|plane|sphere|cylinder|cone|ellipsoid|torus|swept_tube | "
                    "quadric (SPEC-19: a region of quads → an editable height-field formula "
                    "h(u,v)=au²+bv²+cuv+du+ev+f you read & edit in coefficient-space, then "
                    "round-trip via edit op=field)") = "auto",
    tol: tag(float, "[fit] residual threshold in mm for the clean/organic verdict (default ~3mm or 1% of the selection diagonal)") = None,
    per_component: tag(bool, "[fit] fit each connected sub-shell separately (never average a model across a gap)") = False,
    as_curve: tag(str, "[fit] mint the fitted swept_tube centerline as a named Bézier curve object (then extend it + extrude_along_curve to continue the form)") = "",
) -> str:
    """
    Feel a mesh — structure, measurements, correctness. Read-only (no status block).
    `op` selects:

      all      — THE DEFAULT (a bare `feel` resolves to it). The full perceptual sweep
                 over the target: topology structure + profile + section + silhouette in
                 one read. Breadth is free; trim with exclude=silhouette,section only
                 when you have a reason — a lazy read is already a broad one (SPEC-16).
                 Targeted reads (op=section …) still resolve to a single read.
      stats    — exclusion telemetry for the op=all bundle (which reads get trimmed most).
      topology — STRUCTURE. `method` = comma list of these tokens
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
                   facing     — SIGNED orientation frame: which world axis is up /
                                front / left / right, each with its evidence (or an
                                honest abstain). Synthesised from frame + symmetry —
                                ask it once instead of re-deriving the handedness
                                cross-product by hand every read. (not in bundle)
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
                 lod=low|medium|high. Reads the EVALUATED mesh (what renders); when a
                 modifier makes the cage differ (SOLIDIFY/MIRROR/SUBSURF/BOOLEAN), reports
                 BOTH cage and evaluated side by side + names the modifier stack, so the
                 split is never silent. (target, method, lod)
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
      linked   — are two closed-loop wire shells LINKED (threaded) or merely touching?
                 The read distance can't give: extracts each loop's centerline and counts
                 signed pierces through the other's spanning disk → boolean + linking
                 number. Confirm a bail/jump-ring actually interlocks.        (a, b)
      symmetry — mirror symmetry of a mesh    (target, axis, plane, epsilon)
      mesh     — lint one mesh (non-manifold, doubles, normals, …)   (target)
      overlaps — coplanar overlapping faces (z-fighting)     (targets, epsilon→tolerance)
      validate — scene-wide hygiene pass                     (targets)
      audit    — asset budget/quality audit of a group       (group, tri_budget)
      contacts — which objects touch which                   (targets)
      clearance— SIGNED nearest-surface read: 'is my shell everywhere OUTSIDE the surface
                 it wraps?'. The cladding check `contacts` can't give — a garment that
                 envelops a torso and one that stabs through it report the SAME bbox
                 overlap. Per shell vert: + = outside (clears), − = stabbing inside.
                 Reports min/mean clearance, % of shell outside, worst penetrations.
                 (shell, surface, threshold, samples)
      resting  — are objects resting on / floating above surfaces? (targets)
      aim      — cast a normalized bbox-face aim onto the surface → world point +
                 normal. The constructive-side `feel structure`: aim in fractions of the
                 form, get the coordinate back instead of dead-reckoning it. Pass
                 as_handle=NAME to MINT the hit as a named point handle you can then act
                 on by name (no coordinate typed).   (target, face, u, v, aim_frame, margin, as_handle)
      anchor   — read the LIVE edit-mode selection as a surface anchor: its centroid
                 snapped onto the surface + normal — the measured seed a point-op uses
                 INSTEAD of a typed coordinate (SPEC-09).            (target)
      verify   — CAPTURE check on the live selection: a plausible centroid certifies
                 WHERE, not WHAT was bounded. Perturbs (grow+shrink) and reports the
                 centroid/extent drift + a captured/clipping/slack verdict + bounds
                 aspect, so a clipped/over-grabbed/wrong-form selection reads as off
                 without a viewport (G48).                           (steps)
      baseline — snapshot the live selection's form (span/projection/curvature/
                 symmetry/centroid) + its verts as a NAMED baseline (this session).
                 The 'before' of a local edit.                       (name)
      diff     — signed change per metric over a baseline's SAME verts after an edit —
                 a local, temporal check a global bbox/symmetry read can't give. 'It
                 grew 2cm and stayed symmetric' in one read (G45).    (name)
      place    — surface-relative placement: anchor on a named handle/landmark + a
                 metric world offset (up/down/front/back/left/right), ray-snap to the
                 surface, get the world point + normal. 'A hand below the bust apex, on
                 the surface' with no typed Z (G47).  (target, handle,
                 up/down/front/back/left/right, snap, as_handle)
      radial   — landmark by ANGLE on a round face: a point on a ring of `radius` around
                 `anchor`'s centre at clock `angle` (deg CLOCKWISE from 12 o'clock). Sub-
                 dials, bolt circles, clock indices, gauge ticks without hand-trig. Pair
                 with as_handle to mint it by name (G81+G78). (anchor, angle, radius, axis,
                 snap, as_handle)
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
      curve    — a CURVE's centreline quality: length, tightest bend (min radius +
                 where), total turning, inflections (S-bends), endpoint tangent
                 directions. 'Clean arc or lump' as numbers; profile_radius= adds the
                 sweep-feasibility preflight. Live read, no bake. (target, resolution,
                 profile_radius)
      fit      — GEOMETRY FIT (SPEC-14): describe the SELECTION as parametric form — the
                 analytic INVERSE of edit op=field. Fits a library of generative models
                 (plane|sphere|cylinder|cone|ellipsoid|torus|swept_tube) and returns the
                 best fit's type, named unit-tagged params, and — the load-bearing output
                 — a RESIDUAL (mm) + COVERAGE that say WHEN the math describes the shape
                 and when it's lying ("cylinder, r=4.6cm, len 31cm, residual 2.8mm,
                 coverage 94% — clean fit" vs "residual 41mm — no clean parametric form").
                 model=auto tries cheap rigid primitives then swept_tube, returns the
                 lowest residual, tie-breaking toward the SIMPLER model. swept_tube
                 decomposes a limb into centerline + R(s) taper + cross-section and reports
                 empty ring bins as gaps (the direct continuity/void read). as_handle mints
                 the fitted axis line; as_curve mints the centerline as a Bézier to extend +
                 re-sweep. Reads the edit-mode selection (whole mesh if none, warned).
                 Read-only (mints only on as_handle/as_curve).
                 ── SHAPING (SPEC-19): model=quadric fits a height-field analytic patch
                 h(u,v)=au²+bv²+cuv+du+ev+f over the selection's best-fit plane (linear least
                 squares). The payoff is the round-trip: it returns the formula + named
                 coefficients (a,b curvature, c twist/saddle, d,e tilt, f offset), the shape
                 verdict (dome/bowl/saddle), the captured-% + residual honesty stamp, AND a
                 ready-to-run `edit op=field` apply line. You read the surface as math, EDIT a
                 coefficient (steepen the dome: −0.31→−0.45), apply it, then re-fit to verify —
                 no vertex typed, no render read. This is how you SHAPE a surface instead of
                 ASSEMBLE primitives. A high residual means the region isn't height-field-like
                 (a fold/overhang) → it refuses honestly rather than emit a fiction (§1.5).
                 (target, model, axis, tol, per_component, bands, as_handle, as_curve, lod)
      coverage — MODEL-FREE continuity/coverage read (G100) for a selection that ISN'T a
                 swept tube — a flat sheet, a doubly-curved patch, a branching region, where
                 feel op=fit's generative models are the wrong frame. Reports how many
                 DISJOINT pieces the selection is and a 2D occupancy grid over the patch's
                 OWN plane: coverage %, count of INTERIOR holes (the surface skips that
                 spot), and a small ASCII map — without asserting any model first. The
                 sibling of fit's swept_tube gap read, for non-tubular regions. (target)
    """
    o = op.lower().strip()
    if o == "all":
        return _feel_all(target, lod, exclude)
    if o == "stats":
        return _feel_stats()
    if o == "topology":
        return topology.get_topology(target, method, lod, seed, radius, top_n)
    if o == "profile":
        return queries.get_mesh_profile(axis, min, max, max_rings, bands, full, target)
    if o == "silhouette":
        return queries.get_silhouette(axis, res, selection, target)
    if o == "section":
        return queries.get_section(axis, sections, min, max, target)
    if o == "rings":
        return rings.get_rings(axis, target)
    if o == "distance":
        return queries.distance_between(a, b, axis if axis != "Z" else "ANY")
    if o == "gap":
        return queries.gap_between(a, b)
    if o == "aligned":
        return queries.is_aligned(a, b, side, tolerance)
    if o == "linked":
        return queries.check_linked(a, b)
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
    if o == "clearance":
        return introspect.check_clearance(shell, surface, threshold, samples)
    if o == "resting":
        return introspect.check_resting(targets)
    if o == "aim":
        return queries.aim_surface(target, face, u, v, margin, aim_frame, as_handle)
    if o == "anchor":
        return queries.selection_anchor(target, as_handle)
    if o == "verify":
        return editmode.verify_selection(steps)
    if o == "baseline":
        return topology.region_baseline(name)
    if o == "diff":
        return topology.region_diff(name)
    if o == "place":
        return queries.place_on_surface(target, handle,
                                        up, down, front, back, left, right, snap, as_handle)
    if o == "radial":
        return queries.radial_landmark(anchor or target, angle, radius, axis, snap, as_handle,
                                       crossing)
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
        return assembly.feel_map(handle, target, margin, as_handle)
    if o == "relate":
        return assembly.feel_relate(a, b)
    if o == "curve":
        return queries.curve_quality(target, resolution, profile_radius)
    if o == "fit":
        # fit's natural default axis is `auto` (PCA), but the shared `axis` param defaults
        # to Z; translate the unset default Z→auto. auto recovers Z for Z-aligned data
        # anyway, so no capability is lost — only X/Y need to be forced explicitly.
        fit_axis = "auto" if axis == "Z" else axis
        return fit.fit_region(target, model, fit_axis, tol, per_component, bands,
                              as_handle, as_curve, lod)
    if o == "coverage":
        return fit.coverage_region(target)
    return unknown("feel", "op", op, _OPS)


def _feel_all(target, lod, exclude):
    """SPEC-16 — the deliberate perceptual sweep. Runs the whole-mesh bundle; the agent
    trims with exclude=. Each read is guarded so one failure never sinks the sweep, and
    the exclusions are recorded so the op=all defaults can be tuned from data, not taste.
    Targeted reads (op=section …) still resolve to a single read — only breadth is free."""
    from server._core import call_blender
    skip = {s.strip().lower() for s in (exclude or "").split(",") if s.strip()}
    runners = {
        "topology": lambda: topology.get_topology(
            target, "components,genus,boundaries,sections,poles,symmetry,frame,facing,curvature",
            lod, "", 0, 0),
        "profile": lambda: queries.get_mesh_profile("Z", None, None, 200, 0, False, target),
        "section": lambda: queries.get_section("Z", 12, None, None, target),
        "silhouette": lambda: queries.get_silhouette("Z", 32, False, target),
    }
    out, excluded = [], []
    for name in _ALL_BUNDLE:
        if name in skip:
            excluded.append(name)
            continue
        try:
            out.append(f"── {name} ──\n{runners[name]()}")
        except Exception as e:                       # a single bad read never sinks the sweep
            out.append(f"── {name} ──\n(skipped: {e})")
    # Record what was trimmed (the weak, preference signal that tunes the bundle).
    if excluded:
        try:
            call_blender("feel_telemetry", {"excluded": excluded})
        except Exception:
            pass
    head = ("feel op=all — full perceptual sweep"
            + (f" (excluded: {', '.join(excluded)})" if excluded else "")
            + ". A lazy read is a broad one; opt out with exclude=, never in.\n")
    return head + "\n\n".join(out)


def _feel_stats():
    """Telemetry for the perceptual bundle — which reads callers exclude most, so the
    op=all default membership is tuned from data (SPEC-16)."""
    from server._core import call_blender
    r = call_blender("validate_stats")
    if r.get("error"):
        return r["error"]
    feel = r.get("feel") or []
    if not feel:
        return "feel: no exclusion telemetry yet — op=all has run clean so far."
    lines = ["feel — exclusion rate per perceptual op (tunes op=all defaults):"]
    for f in feel:
        lines.append(f"  {f['op']}: excluded×{f['excluded']}, auto-skipped×{f['auto_skipped']}")
    return "\n".join(lines)

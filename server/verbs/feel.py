"""feel — the sense (SPEC-04 + measurements + lint).

Understanding a mesh's STRUCTURE, not its bounding box — plus geometric truth
(distances, gaps, alignment, symmetry) and correctness checks (lint). Read-only:
`feel` IS perception, so it does NOT carry the status block. `op` selects what to
feel; op="topology" (default) is the structural sense.
"""

from typing import Literal

from server._core import mcp
from server import topology, queries, rings, introspect, lint
from ._common import tag, unknown

_OPS = ["topology", "profile", "rings", "distance", "gap", "aligned", "symmetry",
        "mesh", "overlaps", "validate", "audit", "contacts", "resting"]


@mcp.tool(name="feel")
def feel(
    op: Literal["topology", "profile", "rings", "distance", "gap", "aligned",
                "symmetry", "mesh", "overlaps", "validate", "audit", "contacts",
                "resting"] = "topology",
    target: tag(str, "[topology/rings/symmetry/mesh] mesh object (empty=active)") = "",
    # topology (SPEC-04)
    method: tag(str, "[topology] comma list of method tokens (empty = cheap bundle: "
                     "components,genus,boundaries,sections,poles,symmetry,frame). "
                     "Extra: curvature,features,thickness") = "",
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
    # measurements
    a: tag(str, "[distance/gap/aligned] first object") = "",
    b: tag(str, "[distance/gap/aligned] second object") = "",
    side: tag(str, "[aligned] TOP|BOTTOM|… side to compare") = "TOP",
    tolerance: tag(float, "[aligned] alignment tolerance (m)") = 0.001,
    # symmetry
    plane: tag(float, "[symmetry] mirror plane offset") = 0.0,
    epsilon: tag(float, "[symmetry/overlaps/validate] tolerance") = None,
    # lint / check
    targets: tag(str, "[overlaps/validate/contacts/resting] object(s) to check") = "",
    group: tag(str, "[audit] group/collection to audit") = "",
    tri_budget: tag(int, "[audit] triangle budget") = 5000,
) -> str:
    """
    Feel a mesh — structure, measurements, correctness. Read-only (no status block).
    `op` selects:

      topology — STRUCTURE (default). `method` = comma list of these tokens
                 (empty = the cheap bundle, the first seven):
                   components — separate shells (fused vs not)
                   genus      — sphere/tube/handled + holes through it
                   boundaries — the open holes: size + location (the "openings")
                   sections   — cross-section sweep: coverage, voids, branch splits
                   poles      — valence≠4 verts (quad-flow breaks)
                   symmetry   — best mirror plane + error, per axis
                   frame      — intrinsic principal axes
                   curvature  — flats/ridges/domes/saddles  (not in bundle)
                   features   — hard dihedral edges in chains (not in bundle)
                   thickness  — local wall/part diameter      (not in bundle)
                 lod=low|medium|high; base=cage|evaluated. (target, method, lod, base)
      profile  — cross-section width sweep along an axis: by default AGGREGATED into
                 bands with the narrowest/widest flagged; full=True dumps every ring
                 (axis, min, max, bands, full)
      rings    — edge-ring structure along an axis           (axis, target)
      distance — distance between two objects (a, b; default = straight-line,
                 or axis=X|Y for a single-axis distance)
      gap      — surface-to-surface gap between two objects   (a, b)
      aligned  — are two objects aligned on a side?    (a, b, side=TOP|BOTTOM|…, tolerance)
      symmetry — mirror symmetry of a mesh    (target, axis, plane, epsilon)
      mesh     — lint one mesh (non-manifold, doubles, normals, …)   (target)
      overlaps — coplanar overlapping faces (z-fighting)     (targets, epsilon→tolerance)
      validate — scene-wide hygiene pass                     (targets)
      audit    — asset budget/quality audit of a group       (group, tri_budget)
      contacts — which objects touch which                   (targets)
      resting  — are objects resting on / floating above surfaces? (targets)
    """
    o = op.lower().strip()
    if o == "topology":
        return topology.get_topology(target, method, lod, base, seed)
    if o == "profile":
        return queries.get_mesh_profile(axis, min, max, max_rings, bands, full)
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
    return unknown("feel", "op", op, _OPS)

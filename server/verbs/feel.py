"""feel — the sense (SPEC-04 + measurements + lint).

Understanding a mesh's STRUCTURE, not its bounding box — plus geometric truth
(distances, gaps, alignment, symmetry) and correctness checks (lint). Read-only:
`feel` IS perception, so it does NOT carry the status block. `op` selects what to
feel; op="topology" (default) is the structural sense.
"""

from server._core import mcp
from server import topology, queries, rings, introspect, lint
from ._common import unknown

_OPS = ["topology", "profile", "rings", "distance", "gap", "aligned", "symmetry",
        "mesh", "overlaps", "validate", "audit", "contacts", "resting"]


@mcp.tool(name="feel")
def feel(
    op: str = "topology",
    target: str = "",
    # topology (SPEC-04)
    method: str = "", lod: str = "low", base: str = "cage", seed: str = "",
    # profile / rings
    axis: str = "Z", min: float = None, max: float = None, max_rings: int = 200,
    # measurements
    a: str = "", b: str = "", side: str = "TOP", tolerance: float = 0.001,
    # symmetry
    plane: float = 0.0, epsilon: float = None,
    # lint / check
    targets: str = "", group: str = "", tri_budget: int = 5000,
) -> str:
    """
    Feel a mesh — structure, measurements, correctness. Read-only (no status block).
    `op` selects:

      topology — STRUCTURE (default): openings, branches, poles, symmetry,
                 curvature, hard edges, thickness, cross-sections. `method` =
                 comma list (empty = the cheap bundle); lod=low|medium|high;
                 base=cage|evaluated; seed for seeded methods. (target, method, lod, base)
      profile  — cross-section area/width sweep of the active mesh (axis, min, max, max_rings)
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
        return queries.get_mesh_profile(axis, min, max, max_rings)
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

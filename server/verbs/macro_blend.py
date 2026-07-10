"""buttons-blend-macro — algebraic mass/patch MERGE macros (SPEC-20 §3, II.2).

blender-buttons MACROS (composite, not native single ops), grouped by purpose with an R1
native-cousin tag. Dispatch to the same flat handlers (compose.graft / compose.stitch).

  graft  — two CLOSED masses → SDFs → smooth-min union → marching-tetrahedra mesh
  stitch — weld two surface patches sharing a boundary into one watertight quilt
"""

from typing import Literal

from server._core import mcp
from server import compose
from ._common import tag, unknown, teach


@mcp.tool(name="buttons-blend-macro")
def buttons_blend_macro(
    op: Literal["graft", "stitch", "bud"],
    a: tag(str, "[graft/stitch] first OBJECT/patch to merge") = "",
    b: tag(str, "[graft/stitch] second OBJECT/patch to merge") = "",
    mode: tag(str, "[graft] union mode (smin)") = "smin",
    blend: tag(float, "[graft] smooth-min fillet radius k (m) — the ONE legible blend number; 0 = a hard union") = 0.0,
    resolution: tag(int, "[graft] marching-tetrahedra samples along the LONGEST axis; cells are kept ~cubic so a tall-thin bbox doesn't crack (default 48; higher = finer, slower)") = 0,
    keep: tag(bool, "[graft/stitch] keep the two source objects (default False = the merge replaces them)") = False,
    name: tag(str, "[graft/stitch] name for the merged result") = "",
    # bud (G214) — grow a closed mass fused at a point, host identity preserved
    host: tag(str, "[bud] the object the bead fuses INTO (kept, with its name/materials/modifiers)") = "",
    at: tag(list, "[bud] [x,y,z] world anchor where the neck fuses (from feel op=radial crossing=rim / aim / place)") = None,
    handle: tag(str, "[bud] alternatively, a named handle whose live point is the anchor") = "",
    diameter: tag(float, "[bud] bead width (m)") = 0.01,
    hang: tag(float, "[bud] how far the body hangs past the neck (m; default = diameter)") = None,
    neck: tag(float, "[bud] neck width where it meets the host (m; < diameter ⇒ teardrop; default diameter/2)") = None,
    direction: tag(str, "[bud] hang direction: down (default, gravity) | up | left | right | forward | back") = "down",
    solver: tag(str, "[bud] boolean solver EXACT (default, clean on a closed host) | FLOAT") = "EXACT",
    label: str = "",
) -> str:
    """
    Algebraic MERGE macros (blender-buttons composites). `op` selects:

      graft  — ALGEBRAIC MERGE (SPEC-19): convert two CLOSED masses to signed-distance
               fields, smooth-min union them, and marching-tetrahedra mesh the result —
               watertight by construction. blend=k is the ONE fillet-radius number (0 =
               hard union). The clean mass-to-mass / handle-to-body weld that join
               topology-nukes and bridge/connect can't do. Replaces the two sources
               (keep=True retains).        (a, b, mode=smin, blend, resolution, name, keep)
      stitch — weld two surface patches that SHARE a boundary into one watertight quilt
               (matched sampling + boundary weld → a C0 seam, no crack). Refuses if the
               seams aren't coincident — align + match sampling first.  (a, b, name, keep)
      bud    — grow a CLOSED teardrop mass fused to a host at a point, PRESERVING the
               host's identity (name, materials, modifiers). The volume author graft
               can't be — graft makes a NEW object and drops the host's materials +
               modifiers (the icing's Scatter sprinkles). A bead of icing dripping off a
               rim, a rivet, a wart, a water drop. Anchor with at=[x,y,z] (from feel
               op=radial crossing=rim) or handle=. (host, at/handle, diameter, hang,
               neck, direction, solver)

    NATIVE COUSINS (R1):
      • graft ≈ Blender 5.0's native **SDF Geometry-Nodes** chain: Mesh to SDF Grid →
        **SDF Grid Boolean** (Union) → **SDF Fillet** → Grid to Mesh. The capability is
        native as of 5.0, but `SDF Grid Boolean` does a HARD union only (no blend param) —
        smoothing is a separate iteration-bound Fillet pass, voxel-resolution-bound, with
        a mesh→grid→mesh round-trip. graft ADDS a single CONTINUOUS smooth-min `k` blend
        radius and direct marching-tetrahedra (no voxel round-trip).
      • stitch ≈ **Bridge Edge Loops** / the **Weld modifier** — but those need the user
        to pick the loops; stitch auto-locates the shared seam and welds it watertight.
    """
    o = op.lower().strip()
    bad = teach("buttons-blend-macro", "op", o, {
        "graft":  (bool(a and b), "a and b (two objects to merge)",
                   "buttons-blend-macro op=graft a=thumb b=palm blend=0.02"),
        "stitch": (bool(a and b), "a and b (two patches sharing a boundary)",
                   "buttons-blend-macro op=stitch a=cheek b=brow"),
        "bud":    (bool(host and (at or handle)), "host and at=[x,y,z] (or handle=)",
                   "buttons-blend-macro op=bud host=Icing at=[0.04,0,0.02] diameter=0.008 hang=0.012"),
    })
    if bad:
        return bad
    if o == "graft":
        return compose.graft(a, b, mode, blend, resolution, name, keep, label)
    if o == "stitch":
        return compose.stitch(a, b, name, keep, label)
    if o == "bud":
        return compose.bud(host, at, handle, diameter, hang, neck, direction, solver, label)
    return unknown("buttons-blend-macro", "op", op, ["graft", "stitch", "bud"])

"""buttons-connector-macro — swept geometry-bound CONNECTOR macros (SPEC-20 §3, II.2).

blender-buttons MACROS (SPEC-10 composites: read two rims → Bézier centreline → minimum-
twist frame → lofted tube), grouped by purpose with an R1 native-cousin tag. Dispatch to
the same flat handlers (editmode.connect / reshape / resample / strands).

  connect  — one geometry-bound swept connector between two rims
  reshape  — re-bake an unwelded connector against its live handles
  resample — resample a rim to a target vertex count (an arc-length collar)
  strands  — N thin tubes between two rims, seeded coherent jitter
"""

from typing import Literal

from server._core import mcp
from server import editmode
from ._common import tag, unknown, teach


@mcp.tool(name="buttons-connector-macro")
def buttons_connector_macro(
    op: Literal["connect", "reshape", "resample", "strands"],
    a: tag(str, "[connect/strands] first boundary handle; [resample] the rim handle to resample") = "",
    b: tag(str, "[connect/strands] second boundary handle") = "",
    style: tag(str, "[connect/strands] arc | s_curve | direct | slack — the gesture (normal-honoring vs straight)") = "arc",
    tension: tag(float, "[connect/reshape/strands] 0..1 how much it bows (handle length as fraction of the gap); -1=style default") = -1.0,
    sections: tag(int, "[connect/strands] number of cross-sections / rings along the span") = 24,
    connect_profile: tag(str, "[connect] cross-section: match (sweep each rim's shape, tapering) | round") = "match",
    weld: tag(bool, "[connect] fuse both ends into one watertight mesh (False = leave a separate connector)") = True,
    name: tag(str, "[connect/reshape/strands] name for the connector object") = "",
    count: tag(int, "[resample] target vertex count for the rim (>=3); [strands] number of strands (>=2)") = 0,
    depth: tag(float, "[resample] collar length (-1=auto)") = 0.0,
    sides: tag(int, "[strands] cross-section verts per strand (thin tube)") = 8,
    jitter: tag(float, "[strands] 0..1 coherent midspan waywardness (0=clean parallel fan)") = 0.0,
    seed: tag(int, "[strands] random seed (same seed reproduces the bundle)") = 0,
    strand_radius: tag(float, "[strands] tube radius per strand (m); -1=auto-pack to the rim+count") = -1.0,
    label: str = "",
) -> str:
    """
    Swept CONNECTOR macros (blender-buttons composites, SPEC-10). `op` selects:

      connect  — GEOMETRY-BOUND swept connector: weld two rims with a tube that leaves each
                 opening along its OWN outward normal (G1 continuity), sweeps a hollow
                 cross-section matched 1:1 to each rim and tapered between them on a
                 minimum-twist frame, fusing both ends into one watertight mesh. Cross-
                 object OK (joins the owners itself). a/b are two boundary handles.
                 (a, b, style=arc|s_curve|direct|slack, tension, sections, connect_profile, weld)
      reshape  — RE-EVALUATE an unwelded connector against its LIVE handles (a weld=False
                 connector stored its recipe). (name, tension)
      resample — resample a boundary rim to a target vertex COUNT (an arc-length transition
                 collar), re-homing the handle. Lifts connect's 1:1 weld limit. (a, count, depth)
      strands  — N thin tubes distributed around two rims, each leaving along its opening's
                 normal (G1), with a seeded coherent jitter bowing each its own way. One
                 editable object; stores its recipe → reshape re-bakes it. (a, b, count,
                 style, tension, sections, sides, jitter, seed, strand_radius)

    NATIVE COUSIN (R1): ≈ **Bridge Edge Loops** (and GN curve-instancing) — but Bridge
    makes straight quads between manually-picked equal-count loops. The connector macros
    add the G1 normal-honoring Bézier sweep, 1:1 cross-section matching with taper, the
    cross-object auto-join, the editable stored recipe, and the multi-strand seeded fan —
    none of which Bridge expresses.
    """
    o = op.lower().strip()
    bad = teach("buttons-connector-macro", "op", o, {
        "connect": (bool(a and b), "a and b (two boundary handles)",
                    "buttons-connector-macro op=connect a=pipe.top b=spout.base style=arc"),
        "reshape": (bool(name), "name=<unwelded connector>",
                    "buttons-connector-macro op=reshape name=connector tension=0.8"),
        "resample": (bool(a and count >= 3), "a=<rim handle> and count=N (>=3)",
                    "buttons-connector-macro op=resample a=pipe.top count=32"),
        "strands": (bool(a and b and count >= 2), "a,b (two handles) and count=N (>=2)",
                    "buttons-connector-macro op=strands a=pipe.top b=spout.base count=7 jitter=0.2"),
    })
    if bad:
        return bad
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
    return unknown("buttons-connector-macro", "op", op,
                   ["connect", "reshape", "resample", "strands"])

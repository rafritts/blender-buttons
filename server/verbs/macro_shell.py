"""buttons-shell-macro — composite SHELL builders (SPEC-20 §3, II.2).

These are blender-buttons MACROS: each orchestrates several native ops into a result no
single Blender operator yields, so they live under a purpose-named `buttons-…-macro` verb
(not a Blender-domain verb) to make their provenance legible at the call site. Every op
carries an R1 native-cousin tag — the shipped feature it parallels and what it adds.

  clad   — duplicate surface → delete interior → inflate → Solidify (+Subsurf)
  hollow — delete a cap → inward Solidify → manifold vessel

The flat engine handlers are unchanged (objects.clad_surface / objects.hollow).
"""

from typing import Literal

from server._core import mcp
from server import objects
from ._common import tag, unknown

_OPS = ["clad", "hollow"]


@mcp.tool(name="buttons-shell-macro")
def buttons_shell_macro(
    op: Literal["clad", "hollow"],
    name: tag(str, "object to shell (empty=active)") = "",
    new_name: tag(str, "[clad] name for the new shell object") = "",
    region: tag(str, "[clad] whole | selection (live vertex selection) | trunk (mesh minus limbs)") = "whole",
    clearance: tag(float, "[clad] outward standoff in m (default 0.005 = 5mm)") = 0.005,
    thickness: tag(float, "[clad/hollow] wall thickness in m (default 0.004 = 4mm)") = 0.004,
    open: tag(str, "[hollow] which end to open: 'top' (+Z, default) | 'bottom' (−Z) | 'none' (closed shell)") = "top",
    label: str = "",
) -> str:
    """
    Composite SHELL macros (blender-buttons, not native single ops). `op` selects:

      clad   — create a watertight offset SHELL following a surface region: clothing,
               armor, a phone case, bark, a rind. region=whole|selection|trunk (trunk =
               mesh minus limbs, to dodge T-posed arms). Verify with feel op=clearance.
               (name, region, clearance, thickness, new_name)
      hollow — carve a solid into an OPEN VESSEL (cup/bowl/vase) in one call: delete the
               end cap → SOLIDIFY inward → a manifold cup (not inset→extrude, which seals
               the wrong end). Reports MEASURED wall thickness. (name, thickness, open)

    NATIVE COUSINS (R1) — what each parallels and ADDS over the stock feature:
      • clad/hollow ≈ the **Solidify modifier** (the thickness engine; for hollow a
        negative-offset Solidify on a closed manifold already yields a shell). What's
        non-native is the surrounding choreography Blender leaves as manual Edit-Mode
        work: isolating/duplicating a surface region, deleting interior/cap faces,
        inflating by a clearance standoff, opening the shell, and VERIFYING watertightness
        + measured thickness. The macro bundles that into one verified call.
    """
    o = op.lower().strip()
    if o == "clad":
        return objects.clad_surface(name, region, clearance, thickness, new_name, label)
    if o == "hollow":
        return objects.hollow(name, thickness, open, label)
    return unknown("buttons-shell-macro", "op", op, _OPS)

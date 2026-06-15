"""select — the Select menu (SPEC-05).

Selecting objects (Object Mode) and components (Edit Mode). `op` selects the
selection method. Component ops run in Edit Mode (handled by the flat handlers).
"""

from server._core import mcp
from server import editmode, objects, rings, queries
from ._common import unknown

_OPS = ["all", "none", "object", "by_axis", "between", "boundary", "grow",
        "shrink", "random", "in_sphere", "ring", "rings", "component_mode", "current"]


@mcp.tool(name="select")
def select(
    op: str,
    # object selection
    name: str = "",
    # generic
    action: str = "SELECT",
    axis: str = "Z",
    target: str = "",
    # by_axis
    factor: float = 0.5, comparison: str = "GREATER",
    # between
    lo: float = 0.0, hi: float = 1.0,
    # boundary
    from_selection: bool = True,
    # grow / shrink
    steps: int = 1,
    # random
    fraction: float = 0.2, seed: int = 0,
    # in_sphere
    center_x: float = 0.0, center_y: float = 0.0, center_z: float = 0.0,
    radius: float = 0.0,
    # ring / rings
    index: int = 0, indices: list = None,
    # component mode
    mode: str = "",
) -> str:
    """
    Make a selection — the **Select** menu. `op` selects:

      all         — select everything       (action=SELECT|DESELECT|INVERT|TOGGLE)
      none        — deselect everything
      object      — select an object by name (Object Mode)        (name)
      by_axis     — verts past an axis threshold  (axis, factor 0..1, comparison=
                    GREATER|LESS, action)
      between     — verts in an axis band         (axis, lo, hi, action)
      boundary    — open-edge boundary loop        (from_selection, action)
      grow        — grow the selection             (steps)
      shrink      — shrink the selection           (steps)
      random      — a random fraction              (fraction, seed)
      in_sphere   — verts inside a sphere   (center_x/y/z, radius, action)
      ring        — one edge ring          (axis, index, action, target)
      rings       — several edge rings     (axis, indices=[...], action, target)
      component_mode — set vert/edge/face mode    (mode=VERT|EDGE|FACE)
      current     — read what's selected right now (—)
    """
    o = op.lower().strip()
    if o == "all":
        return editmode.select_all(action)
    if o == "none":
        return editmode.select_all("DESELECT")
    if o == "object":
        return objects.select_object(name)
    if o == "by_axis":
        return editmode.select_by_axis(axis, factor, comparison, action)
    if o == "between":
        return editmode.select_between(axis, lo, hi, action)
    if o == "boundary":
        return editmode.select_boundary(action, from_selection)
    if o == "grow":
        return editmode.grow_selection("GROW", steps)
    if o == "shrink":
        return editmode.grow_selection("SHRINK", steps)
    if o == "random":
        return editmode.random_select(fraction, seed)
    if o == "in_sphere":
        return editmode.select_in_sphere(center_x, center_y, center_z, radius, action)
    if o == "ring":
        return rings.select_ring(axis, index, action, target)
    if o == "rings":
        return rings.select_rings(axis, indices or [], action, target)
    if o == "component_mode":
        return editmode.set_component_mode(mode)
    if o == "current":
        return queries.get_current_selection()
    return unknown("select", "op", op, _OPS)

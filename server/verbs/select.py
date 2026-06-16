"""select — the Select menu (SPEC-05).

Selecting objects (Object Mode) and components (Edit Mode). `op` selects the
selection method. Component ops run in Edit Mode (handled by the flat handlers).
"""

from typing import Literal

from server._core import mcp
from server import editmode, objects, rings, queries
from ._common import tag, unknown

_OPS = ["all", "none", "object", "by_axis", "between", "boundary", "limb", "grow",
        "shrink", "random", "in_sphere", "ring", "rings", "component_mode", "current"]


@mcp.tool(name="select")
def select(
    op: Literal["all", "none", "object", "by_axis", "between", "boundary", "limb",
                "grow", "shrink", "random", "in_sphere", "ring", "rings",
                "component_mode", "current"],
    # object selection
    name: tag(str, "[object] object name to select") = "",
    # generic
    action: tag(str, "[all/by_axis/between/boundary/in_sphere/ring/rings] SELECT|DESELECT|INVERT|TOGGLE") = "SELECT",
    extend: tag(bool, "[by_axis/between/in_sphere] True = ADD to current selection (union regions across calls) instead of replacing") = False,
    axis: tag(str, "[by_axis/between/ring/rings] axis X|Y|Z") = "Z",
    target: tag(str, "[ring/rings] mesh object (empty=active)") = "",
    # by_axis
    factor: tag(float, "[by_axis] threshold 0..1 along axis") = 0.5,
    comparison: tag(str, "[by_axis] GREATER | LESS") = "GREATER",
    # between
    lo: tag(float, "[between] band low 0..1") = 0.0,
    hi: tag(float, "[between] band high 0..1") = 1.0,
    # boundary
    from_selection: tag(bool, "[boundary] restrict to current selection") = True,
    # limb
    which: tag(str, "[limb] cap-region substring filter (e.g. 'top-left'); empty = every protrusion") = "",
    # grow / shrink
    steps: tag(int, "[grow/shrink] number of steps") = 1,
    # random
    fraction: tag(float, "[random] fraction 0..1 to select") = 0.2,
    seed: tag(int, "[random] random seed") = 0,
    # in_sphere
    center_x: tag(float, "[in_sphere] sphere center X") = 0.0,
    center_y: tag(float, "[in_sphere] sphere center Y") = 0.0,
    center_z: tag(float, "[in_sphere] sphere center Z") = 0.0,
    radius: tag(float, "[in_sphere] sphere radius (m)") = 0.0,
    # ring / rings
    index: tag(int, "[ring] ring index along axis") = 0,
    indices: tag(list, "[rings] list of ring indices") = None,
    # component mode
    mode: tag(str, "[component_mode] VERT | EDGE | FACE") = "",
) -> str:
    """
    Make a selection — the **Select** menu. `op` selects:

      all         — select everything       (action=SELECT|DESELECT|INVERT|TOGGLE)
      none        — deselect everything
      object      — select an object by name (Object Mode)        (name)
      by_axis     — verts past an axis threshold  (axis, factor 0..1, comparison=
                    GREATER|LESS, action, extend)
      between     — verts in an axis band         (axis, lo, hi, action, extend)
      boundary    — open-edge boundary loop        (from_selection, action)
      limb        — a whole protrusion (sleeve/limb/finger), anchored to the mesh's
                    OWN topology — selects out to its base ring (the armhole), no
                    coordinates. delete it to remove the limb cleanly.  (which, extend)
      grow        — grow the selection             (steps)
      shrink      — shrink the selection           (steps)
      random      — a random fraction              (fraction, seed)
      in_sphere   — verts inside a sphere   (center_x/y/z, radius, action, extend)
                    extend=True unions onto the current selection (vs replacing).
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
        return editmode.select_by_axis(axis, factor, comparison, action, extend)
    if o == "between":
        return editmode.select_between(axis, lo, hi, action, extend)
    if o == "boundary":
        return editmode.select_boundary(action, from_selection)
    if o == "limb":
        return editmode.select_limb(which, extend)
    if o == "grow":
        return editmode.grow_selection("GROW", steps)
    if o == "shrink":
        return editmode.grow_selection("SHRINK", steps)
    if o == "random":
        return editmode.random_select(fraction, seed)
    if o == "in_sphere":
        return editmode.select_in_sphere(center_x, center_y, center_z, radius, action, extend)
    if o == "ring":
        return rings.select_ring(axis, index, action, target)
    if o == "rings":
        return rings.select_rings(axis, indices or [], action, target)
    if o == "component_mode":
        return editmode.set_component_mode(mode)
    if o == "current":
        return queries.get_current_selection()
    return unknown("select", "op", op, _OPS)

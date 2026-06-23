"""select — the Select menu (SPEC-05).

Selecting objects (Object Mode) and components (Edit Mode). `op` selects the
selection method. Component ops run in Edit Mode (handled by the flat handlers).
"""

from typing import Literal

from server._core import mcp
from server import editmode, objects, rings, queries, handles
from ._common import tag, unknown

_OPS = ["all", "none", "object", "by_axis", "between", "group", "material", "boundary", "limb",
        "grow", "shrink", "flood", "random", "in_sphere", "ring", "rings", "component_mode",
        "current"]


@mcp.tool(name="select")
def select(
    op: Literal["all", "none", "object", "by_axis", "between", "group", "material", "boundary",
                "limb", "grow", "shrink", "flood", "random", "in_sphere", "ring", "rings",
                "component_mode", "current"],
    # object selection
    name: tag(str, "[object] object name to select; [group] vertex-group name substring; [material] material-name substring (case-insensitive, unions all matches; empty = LIST every vgroup/material slot)") = "",
    # generic
    action: tag(str, "[all/by_axis/between/boundary/in_sphere/ring/rings] SELECT|DESELECT|INVERT|TOGGLE; on by_axis/between/in_sphere also INTERSECT (keep only verts BOTH already selected AND matching — 'frontmost ∩ chest-band' in one call instead of a deselect dance)") = "SELECT",
    extend: tag(bool, "[by_axis/between/in_sphere] True = ADD to current selection (union regions across calls) instead of replacing") = False,
    axis: tag(str, "[by_axis/between/ring/rings] axis X|Y|Z") = "Z",
    target: tag(str, "[edit-mode ops: all/none/by_axis/between/boundary/limb/grow/shrink/in_sphere/ring/rings/component_mode] mesh object to auto-select + enter edit on (empty=active); pass it so a stray click can't hijack the op") = "",
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
    # flood (grow-to-crease)
    angle: tag(float, "[flood] crease threshold (deg) the flood halts at (default 25; lower = subtler creases stop it)") = 25.0,
    max_verts: tag(int, "[flood] safety cap; hitting it means the region didn't close at a crease") = 20000,
    # random
    fraction: tag(float, "[random] fraction 0..1 to select") = 0.2,
    seed: tag(int, "[random] random seed") = 0,
    # in_sphere
    radius: tag(float, "[in_sphere] sphere radius (m)") = 0.0,
    handle: tag(str, "[in_sphere] center the sphere on a named handle's live point "
                     "(recomputed)") = "",
    center: tag(str, "[in_sphere] center on an OBJECT (its bbox center) or on 'selection' "
                     "(the current selection's center) — an alternative to handle= that "
                     "needs no minted handle (e.g. select a boundary loop, then "
                     "center='selection' to isolate it by radius)") = "",
    # ring / rings
    index: tag(int, "[ring] ring index along axis") = 0,
    indices: tag(list, "[rings] list of ring indices") = None,
    # component mode
    mode: tag(str, "[component_mode] VERT | EDGE | FACE") = "",
    # group
    min_weight: tag(float, "[group] a vert counts as in the group only if its weight there exceeds this (0 = any non-zero; raise to shed faint seam bleed)") = 0.0,
) -> str:
    """
    Make a selection — the **Select** menu. `op` selects:

      all         — select everything       (action=SELECT|DESELECT|INVERT|TOGGLE)
      none        — deselect everything
      object      — select an object by name (Object Mode)        (name)
      by_axis     — verts past an axis threshold  (axis, factor 0..1, comparison=
                    GREATER|LESS, action, extend). action=INTERSECT keeps only verts
                    already selected AND past the threshold.
      between     — verts in an axis band         (axis, lo, hi, action, extend).
                    action=INTERSECT keeps only already-selected verts inside the band.
      group       — verts in a named VERTEX GROUP   (name substring, min_weight, action,
                    extend). name='' LISTS every vgroup (the grep). Unions all matches,
                    so name='skirt' grabs every skirt layer at once. The named-handle
                    selector for IMPORTED rigs — address a garment/part by its own name
                    instead of box-selecting a shell out of a fused mesh.
      material    — faces in a named MATERIAL SLOT  (name substring, action, extend).
                    name='' LISTS every slot with its face count (the grep). For garments
                    that SHARE bone weights with the body — a jacket torso rides the same
                    chest/spine bones as the skin, so no vgroup isolates it — the material
                    IS the garment's handle. Unions all matching slots.
      boundary    — open-edge boundary loop        (from_selection, action)
      limb        — a whole protrusion (sleeve/limb/finger), anchored to the mesh's
                    OWN topology — selects out to its base ring (the armhole), no
                    coordinates. delete it to remove the limb cleanly.  (which, extend)
      grow        — grow the selection             (steps)
      shrink      — shrink the selection           (steps)
      flood       — region-coherent grow: flood from the seed selection out to the
                    feature's natural edge, halting at creases (dihedral ≥ angle) and
                    mesh boundaries — snaps to a form instead of a guessed box
                    (angle, max_verts). Confirm with feel op=verify.
      random      — a random fraction              (fraction, seed)
      in_sphere   — verts inside a sphere   (handle=<name>, radius, action, extend)
                    — extend=True unions onto the current selection.
      ring        — one edge ring          (axis, index, action, target)
      rings       — several edge rings     (axis, indices=[...], action, target)
      component_mode — set vert/edge/face mode    (mode=VERT|EDGE|FACE)
      current     — read what's selected right now (—)
    """
    o = op.lower().strip()
    if o == "all":
        return editmode.select_all(action, target)
    if o == "none":
        return editmode.select_all("DESELECT", target)
    if o == "object":
        return objects.select_object(name)
    if o == "by_axis":
        return editmode.select_by_axis(axis, factor, comparison, action, extend, target)
    if o == "between":
        return editmode.select_between(axis, lo, hi, action, extend, target)
    if o == "group":
        return editmode.select_by_vgroup(name, action, extend, min_weight, target)
    if o == "material":
        return editmode.select_by_material(name, action, extend, target)
    if o == "boundary":
        return editmode.select_boundary(action, from_selection, target)
    if o == "limb":
        return editmode.select_limb(which, extend, target)
    if o == "grow":
        return editmode.grow_selection("GROW", steps, target)
    if o == "shrink":
        return editmode.grow_selection("SHRINK", steps, target)
    if o == "flood":
        return editmode.flood_to_crease(angle, max_verts)
    if o == "random":
        return editmode.random_select(fraction, seed)
    if o == "in_sphere":
        if center:
            return editmode.select_in_sphere_at(center, radius, action, extend, target)
        if not handle:
            return ("select op=in_sphere: needs handle=<name> or center=<object|'selection'> "
                    "— center the sphere on a named handle's live point, an object's bbox "
                    "center, or the current selection's center (no typed coordinates).")
        pt, err, drift = handles.resolve_point(handle)
        if err:
            return err
        note = drift or ""
        return note + editmode.select_in_sphere(pt[0], pt[1], pt[2], radius, action, extend, target)
    if o == "ring":
        return rings.select_ring(axis, index, action, target)
    if o == "rings":
        return rings.select_rings(axis, indices or [], action, target)
    if o == "component_mode":
        return editmode.set_component_mode(mode, target)
    if o == "current":
        return queries.get_current_selection()
    return unknown("select", "op", op, _OPS)

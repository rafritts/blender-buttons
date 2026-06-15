"""modifier — the Modifier Properties tab (SPEC-05).

Add / modify / move / remove / list modifiers. `op` selects the operation.
(Apply-to-mesh and boolean live here too; convert-to-mesh is `object convert`;
deform binding and weights are `pose`.)
"""

from server._core import mcp
from server import modifiers
from ._common import unknown

_OPS = ["add", "modify", "move", "remove", "list", "apply"]


@mcp.tool(name="modifier")
def modifier(
    op: str,
    target: str = "",
    # add
    type: str = "", name: str = "",
    levels: int = None, render_levels: int = None,
    width: float = None, segments: int = None,
    offset: float = None, wrap_method: str = "",
    axis: str = "X", merge_threshold: float = None, mirror_object: str = "",
    precision: int = None, rest_source: str = "",
    factor: float = None, iterations: int = None,
    # modify (extra dials)
    modifier_name: str = "", thickness: float = None, angle_limit: float = None,
    count: int = None, strength: float = None,
    show_viewport: bool = None, show_render: bool = None, target_object: str = "",
    # move
    modifier: str = "", index: int = None, before: str = "", after: str = "",
    label: str = "",
) -> str:
    """
    Modifiers — the **Modifier Properties** tab. `op` selects:

      add    — add a modifier   (type=SUBSURF|MIRROR|SOLIDIFY|BEVEL|ARRAY|…, target,
               name, + the dials that type uses: levels/render_levels, width/segments,
               offset, axis/mirror_object, factor/iterations, …)
      modify — tweak an existing modifier (target, modifier_name, + any dial:
               levels, width, thickness, angle_limit, count, factor, strength,
               show_viewport/show_render, …)
      move   — reorder in the stack (target, modifier, index OR before/after)
      remove — delete a modifier   (target, modifier_name)
      list   — list a target's modifiers (target)
      apply  — apply all modifiers to the mesh (target→name)

    (object convert → real mesh; edit boolean → boolean cut; pose bind/rebind →
    mesh-deform binding.)
    """
    o = op.lower().strip()
    if o == "add":
        return modifiers.add_modifier(
            type, name, levels if levels is not None else 2,
            render_levels if render_levels is not None else 2,
            width if width is not None else 0.1,
            segments if segments is not None else 1,
            target, offset, wrap_method or "NEAREST_SURFACEPOINT", axis,
            merge_threshold, mirror_object, precision, rest_source, factor,
            iterations, label)
    if o == "modify":
        return modifiers.modify_modifier(
            target, modifier_name or modifier, levels, render_levels, width, segments,
            thickness, offset, angle_limit, count, factor, strength, iterations,
            show_viewport, show_render, wrap_method, target_object, label)
    if o == "move":
        return modifiers.move_modifier(target, modifier, index, before, after, label)
    if o == "remove":
        return modifiers.remove_modifier(target, modifier_name or modifier, label)
    if o == "list":
        return modifiers.list_modifiers(target)
    if o == "apply":
        return modifiers.apply_modifiers(target or name)
    return unknown("modifier", "op", op, _OPS)

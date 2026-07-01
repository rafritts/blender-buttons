"""modifier — the Modifier Properties tab (SPEC-05).

Add / modify / move / remove / list modifiers. `op` selects the operation.
(Apply-to-mesh and boolean live here too; convert-to-mesh is `object convert`;
deform binding and weights are `pose`.)
"""

from typing import Literal

from server._core import mcp
from server import modifiers
from ._common import tag, unknown

_OPS = ["add", "add_asset", "modify", "move", "remove", "list", "apply"]


@mcp.tool(name="modifier")
def modifier(
    op: Literal["add", "add_asset", "modify", "move", "remove", "list", "apply"],
    target: tag(str, "object whose modifier stack to act on") = "",
    # add
    type: tag(str, "[add] SUBSURF|MIRROR|SOLIDIFY|BEVEL|ARRAY|CURVE|CLOTH|COLLISION|…") = "",
    # add_asset — bundled Geometry-Nodes Essentials node-group (Blender 5.0+)
    asset: tag(str, "[add_asset] Essentials node-group: 'Scatter on Surface' | 'Array' | "
                    "'Instance on Elements' | 'Randomize Instances' | 'Curve to Tube' | "
                    "'Geometry Input'") = "",
    collection: tag(str, "[add_asset] collection to assign to the asset's Collection input "
                         "(e.g. the instance source / prototypes for Scatter on Surface)") = "",
    inputs: tag(dict, "[add_asset/modify] {socket-name: value} GN dials, e.g. {'Density': 250, "
                      "'Seed': 3}; the result lists every settable input name. On op=modify this "
                      "edits a live NODES modifier's sockets in place (no remove+re-add)") = None,
    name: tag(str, "[add] name for the new modifier · [apply] object (alias of target)") = "",
    levels: tag(int, "[add/modify] subsurf viewport levels") = None,
    render_levels: tag(int, "[add/modify] subsurf render levels") = None,
    width: tag(float, "[add/modify] bevel/solidify width") = None,
    segments: tag(int, "[add/modify] bevel segments") = None,
    offset: tag(float, "[add/modify] solidify/mirror offset; ARRAY constant spacing (m) along axis") = None,
    wrap_method: tag(str, "[add/modify] shrinkwrap method: NEAREST_SURFACEPOINT (flattens bumps) | PROJECT (casts along axis, keeps bump height)") = "",
    vertex_group: tag(str, "[add/modify] SHRINKWRAP region to wrap — pins weight-0 verts so a partial transfer leaves the rest (and the seam) in place; mint via edit/assign_weight") = "",
    axis: tag(str, "[add/modify] mirror axis X|Y|Z; SHRINKWRAP PROJECT cast axis (default Y); ARRAY offset run direction (default X)") = "X",
    merge_threshold: tag(float, "[add] mirror merge threshold") = None,
    mirror_object: tag(str, "[add] mirror across this object") = "",
    precision: tag(int, "[add] mesh-deform bind precision") = None,
    rest_source: tag(str, "[add] corrective-smooth rest source") = "",
    host: tag(str, "[add] for PARTNER mods (SHRINKWRAP/MESH_DEFORM/ARMATURE/LATTICE/CURVE) the "
                   "object that RECEIVES the modifier; name it instead of relying on the active "
                   "object (must differ from target)") = "",
    pin_group: tag(str, "[add] CLOTH pinning vertex group — the seam/waistband the garment hangs "
                        "from (else it falls); mint via pose op=assign_weight") = "",
    factor: tag(float, "[add/modify] generic strength/factor; ARRAY relative offset (×bbox) along axis") = None,
    iterations: tag(int, "[add/modify] smooth iterations") = None,
    # modify (extra dials)
    modifier_name: tag(str, "[modify/remove] modifier to act on") = "",
    thickness: tag(float, "[add/modify] solidify thickness (m)") = None,
    angle_limit: tag(float, "[add/modify] bevel angle limit (deg)") = None,
    count: tag(int, "[add/modify] ARRAY copy count") = None,
    strength: tag(float, "[modify] displace/other strength") = None,
    show_viewport: tag(bool, "[modify] show in viewport") = None,
    show_render: tag(bool, "[modify] show in render") = None,
    target_object: tag(str, "[modify] modifier's target object") = "",
    # move
    modifier: tag(str, "[move/remove] modifier name") = "",
    index: tag(int, "[move] target stack index") = None,
    before: tag(str, "[move] move before this modifier") = "",
    after: tag(str, "[move] move after this modifier") = "",
    label: str = "",
) -> str:
    """
    Modifiers — the **Modifier Properties** tab. `op` selects:

      add    — add a modifier   (type=SUBSURF|MIRROR|SOLIDIFY|BEVEL|ARRAY|…, target,
               name, + the dials that type uses: levels/render_levels, width/segments,
               offset, axis/mirror_object, factor/iterations, …)
      add_asset — add a Geometry-Nodes modifier pointing at a BUNDLED Essentials
               node-group (Blender 5.0+): asset='Scatter on Surface'|'Curve to Tube'|…,
               target (host), collection (instance source), inputs={dial: value}. The
               native scatter/instancer/array path. (Emits instances; op=apply realizes.)
      modify — tweak an existing modifier (target, modifier_name, + any dial:
               levels, width, thickness, angle_limit, count, factor, strength,
               show_viewport/show_render, …; inputs={socket: value} for a live
               Geometry-Nodes modifier — the same dials add_asset takes)
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
            iterations, vertex_group, count, label, host=host,
            thickness=thickness, angle_limit=angle_limit, pin_group=pin_group)
    if o == "add_asset":
        return modifiers.add_asset_modifier(
            asset, host or target, name, collection, inputs, label)
    if o == "modify":
        return modifiers.modify_modifier(
            target, modifier_name or modifier, levels, render_levels, width, segments,
            thickness, offset, angle_limit, count, factor, strength, iterations,
            show_viewport, show_render, wrap_method, target_object, vertex_group, axis,
            inputs, label)
    if o == "move":
        return modifiers.move_modifier(target, modifier, index, before, after, label)
    if o == "remove":
        return modifiers.remove_modifier(target, modifier_name or modifier, label)
    if o == "list":
        return modifiers.list_modifiers(target)
    if o == "apply":
        return modifiers.apply_modifiers(target or name)
    return unknown("modifier", "op", op, _OPS)

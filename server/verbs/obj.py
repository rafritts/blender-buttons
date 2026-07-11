"""object — Object Mode / the Object menu (SPEC-05).

Object-level operations on whole objects: rename, delete, duplicate, join, group,
visibility, custom props, convert, and reading an object's info. `op` is the
operation; fill the params it needs. Auto-managed in Object Mode.
"""

from typing import Literal

from server._core import mcp
from server import objects, groups, modifiers, queries, scene as _scene
from ._common import tag, unknown

_OPS = ["info", "describe", "rename", "delete", "duplicate",
        "join", "separate", "group", "ungroup", "add_to_group", "parts",
        "convert", "visibility", "particle_visibility", "props", "set_prop", "light",
        "aim", "mode", "remesh"]


@mcp.tool(name="object")
def object_verb(
    op: Literal["info", "describe", "rename", "delete", "duplicate",
                "join", "separate", "group", "ungroup",
                "add_to_group", "parts", "convert", "visibility",
                "particle_visibility", "props", "set_prop", "light", "aim", "mode",
                "remesh"],
    name: tag(str, "object name (empty=active for info/describe)") = "",
    # delete — bulk by name pattern
    pattern: tag(str, "[delete] glob ('Sprinkle_inst*') or bare prefix ('Sprinkle_inst') "
                      "to bulk-delete many objects in one call — clears a whole scatter/array") = "",
    # rename / duplicate
    new_name: tag(str, "[rename/duplicate] new object name") = "",
    old_name: tag(str, "[rename] source name (alias of name)") = "",
    linked: tag(bool, "[duplicate] make an INSTANCE (Alt+D) sharing the source mesh — "
                      "N copies cost one mesh; edit one, all change") = False,
    # join / group membership
    names: tag(list, "[join] objects to weld together") = None,
    parts: tag(list, "[group/add_to_group] member object names") = None,
    merge_threshold: tag(float, "[join] weld distance") = None,
    # visibility
    viewport: tag(bool, "[visibility] show in viewport") = None,
    render: tag(bool, "[visibility] show in render") = None,
    show: tag(bool, "[particle_visibility] show particles") = False,
    # custom properties
    key: tag(str, "[set_prop] property key") = "",
    value: tag(str, "[set_prop] property value") = "",
    bone: tag(str, "[props/set_prop] bone name (for bone props)") = None,
    # describe / info
    posed: tag(bool, "[describe] evaluate the posed/deformed mesh") = False,
    # explicit mode override (auto-switching usually makes this unnecessary)
    mode: tag(str, "[mode] OBJECT|EDIT|SCULPT|POSE / [remesh] voxel|quad") = "",
    # remesh (G50) — auto-retopology of the whole mesh
    voxel_size: tag(float, "[remesh mode=voxel] voxel grid size (m)") = 0.05,
    target_faces: tag(int, "[remesh mode=quad] QuadriFlow target face count") = 5000,
    # light tweaks (op=light — modify an existing light)
    energy: tag(float, "[light] strength") = None,
    color: tag(list, "[light] [r,g,b] 0..1") = None,
    hex: tag(str, "[light] #RRGGBB color") = "",
    size: tag(float, "[light] soft-shadow size") = None,
    spot_angle: tag(float, "[light] SPOT cone angle (deg)") = None,
    target: tag(str, "[light/aim] object to re-aim at (its -Z points at the target's centre)") = "",
    label: str = "",
) -> str:
    """
    Object-level operations — the **Object** menu / Object Mode. `op` selects:

      info        — object's placement, dims, material  (name; empty=active)
      describe    — fuller report; posed=True evaluates the rig    (name)
      rename      — F2 · name → new_name                           (name, new_name)
      delete      — X · Object ▸ Delete · remove the object (name); or bulk-delete by
                    pattern=<glob|prefix> to clear a whole scatter/array in one call
      duplicate   — Shift+D (Alt+D linked) · Object ▸ Duplicate Objects · copy it
                    (name, new_name, linked=True for a mesh-sharing instance)
      join        — Ctrl+J · Object ▸ Join · weld several into one  (names=[...], merge_threshold)
      separate    — P ▸ By Loose Parts · split active into objects by LOOSE PARTS  (—)
      group       — gather parts into a named collection; move/rotate the whole
                    group as one by passing its name to a transform's targets=
                    (name, parts=[...])
      ungroup     — dissolve the group                             (name)
      add_to_group— add parts to an existing group (name, parts=[...])
      parts       — list a group's members                        (name)
      convert     — Object ▸ Convert To · convert curve/text/etc to a real mesh    (name)
      visibility  — H / Alt+H · Object ▸ Show/Hide · show/hide  (name, viewport=bool, render=bool)
      particle_visibility — toggle particle systems  (name, show=bool)
      props       — read custom properties           (name, bone)
      set_prop    — write a custom property   (name, key, value, bone)
      light       — tweak an existing light  (name, energy/color/hex/size/spot_angle/target);
                    to MOVE it, use transform op=place/nudge (relational)
      aim         — re-aim an object's -Z at a named target (camera, spotlight, any
                    object). To position AND aim by angle+distance, use view op=rig.
                    (name, target=<object to look at>)
      mode        — Tab (mode pie) · explicit mode switch; pass name to guarantee it lands
                    on that object despite a stray click  (name, mode=OBJECT|EDIT|SCULPT|POSE)
      remesh      — auto-retopology of the whole mesh (mode=voxel → uniform sculpt-ready
                    grid at voxel_size; mode=quad → QuadriFlow clean quad flow at
                    ~target_faces). Destructive; rigged/keyed meshes refused.
                    (name, mode=voxel|quad, voxel_size, target_faces)

    (Object SELECTION is the `select` verb; modifiers are `modifier`; materials
    are `material`; armature/weights/shape-keys are `pose`.)
    """
    o = op.lower().strip()
    if o == "info":
        return queries.get_object_info(name)
    if o == "describe":
        return queries.describe(name, posed)
    if o == "rename":
        return objects.rename_object(old_name or name, new_name)
    if o == "delete":
        return objects.delete_object(name, label, pattern)
    if o == "duplicate":
        return objects.duplicate_object(name, new_name, linked)
    if o == "join":
        return objects.join_objects(names or [], merge_threshold)
    if o == "separate":
        return objects.split_by_part(label)
    if o == "group":
        return groups.group(name, parts or [], label)
    if o == "ungroup":
        return groups.ungroup(name, label)
    if o == "add_to_group":
        return groups.add_to_group(name, parts or [], label)
    if o == "parts":
        return groups.parts_in(name)
    if o == "convert":
        return modifiers.convert_to_mesh(name)
    if o == "visibility":
        return objects.set_object_visibility(name, viewport, render, label)
    if o == "particle_visibility":
        return objects.set_particle_visibility(name, show, label)
    if o == "props":
        return objects.get_custom_properties(name, bone)
    if o == "set_prop":
        return objects.set_custom_property(name, key, value, bone, label)
    if o == "light":
        return _scene.modify_light(name, energy, color, hex, size, spot_angle,
                                   None, None, None, target, label)
    if o == "aim":
        return _scene.aim_object(name, target, label)
    if o == "mode":
        return objects.set_mode(mode, name)
    if o == "remesh":
        return objects.remesh(name, mode or "voxel", voxel_size, target_faces, label)
    return unknown("object", "op", op, _OPS)

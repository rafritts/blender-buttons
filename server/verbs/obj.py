"""object — Object Mode / the Object menu (SPEC-05).

Object-level operations on whole objects: rename, delete, duplicate, join, group,
visibility, custom props, convert, and reading an object's info. `op` is the
operation; fill the params it needs. Auto-managed in Object Mode.
"""

from typing import Literal

from server._core import mcp
from server import objects, groups, modifiers, queries, scene as _scene
from ._common import tag, unknown

_OPS = ["info", "describe", "rename", "delete", "duplicate", "duplicate_mirrored",
        "join", "split", "group", "ungroup", "add_to_group", "parts", "convert",
        "visibility", "particle_visibility", "props", "set_prop", "light", "mode"]


@mcp.tool(name="object")
def object_verb(
    op: Literal["info", "describe", "rename", "delete", "duplicate",
                "duplicate_mirrored", "join", "split", "group", "ungroup",
                "add_to_group", "parts", "convert", "visibility",
                "particle_visibility", "props", "set_prop", "light", "mode"],
    name: tag(str, "object name (empty=active for info/describe)") = "",
    # rename / duplicate
    new_name: tag(str, "[rename/duplicate/duplicate_mirrored] new object name") = "",
    old_name: tag(str, "[rename] source name (alias of name)") = "",
    # join / group membership
    names: tag(list, "[join] objects to weld together") = None,
    parts: tag(list, "[group/add_to_group] member object names") = None,
    merge_threshold: tag(float, "[join] weld distance") = None,
    # mirror-duplicate
    axis: tag(str, "[duplicate_mirrored] mirror axis X|Y|Z") = "X",
    pivot: tag(str, "[duplicate_mirrored] WORLD|CURSOR|…") = "WORLD",
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
    mode: tag(str, "[mode] OBJECT|EDIT|SCULPT|POSE") = "",
    # light tweaks (op=light — modify an existing light)
    energy: tag(float, "[light] strength") = None,
    color: tag(list, "[light] [r,g,b] 0..1") = None,
    hex: tag(str, "[light] #RRGGBB color") = "",
    size: tag(float, "[light] soft-shadow size") = None,
    spot_angle: tag(float, "[light] SPOT cone angle (deg)") = None,
    x: tag(float, "[light] move to X") = None,
    y: tag(float, "[light] move to Y") = None,
    z: tag(float, "[light] move to Z") = None,
    target: tag(str, "[light] re-aim at object") = "",
    label: str = "",
) -> str:
    """
    Object-level operations — the **Object** menu / Object Mode. `op` selects:

      info        — object's placement, dims, material  (name; empty=active)
      describe    — fuller report; posed=True evaluates the rig    (name)
      rename      — name → new_name                                (name, new_name)
      delete      — remove the object                              (name)
      duplicate   — copy it                                        (name, new_name)
      duplicate_mirrored — mirrored copy   (name, axis=X|Y|Z, pivot=WORLD|.., new_name)
      join        — weld several into one  (names=[...], merge_threshold)
      split       — split active by loose parts into objects       (—)
      group       — parent parts under an empty (name, parts=[...])
      ungroup     — dissolve the group                             (name)
      add_to_group— add parts to an existing group (name, parts=[...])
      parts       — list a group's members                        (name)
      convert     — convert curve/text/etc to a real mesh          (name)
      visibility  — show/hide      (name, viewport=bool, render=bool)
      particle_visibility — toggle particle systems  (name, show=bool)
      props       — read custom properties           (name, bone)
      set_prop    — write a custom property   (name, key, value, bone)
      light       — tweak an existing light  (name, energy/color/hex/size/spot_angle/x/y/z/target)
      mode        — explicit mode switch; pass name to guarantee it lands on that
                    object despite a stray click   (name, mode=OBJECT|EDIT|SCULPT|POSE)

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
        return objects.delete_object(name, label)
    if o == "duplicate":
        return objects.duplicate_object(name, new_name)
    if o == "duplicate_mirrored":
        return objects.duplicate_mirrored(name, axis, pivot, new_name, label)
    if o == "join":
        return objects.join_objects(names or [], merge_threshold)
    if o == "split":
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
                                   x, y, z, target, label)
    if o == "mode":
        return objects.set_mode(mode, name)
    return unknown("object", "op", op, _OPS)

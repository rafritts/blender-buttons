"""Blender Buttons — MCP bridge that lets an LLM drive Blender like a human would.

This package is split into single-topic modules. To find a tool, look in the
module whose name matches the tool family:

  primitives.py   add_box / add_plane / add_cylinder / add_sphere / add_cone
  curves.py       spline_tube (interpolating curve swept into a tube mesh)
  objects.py      select / delete / rename / duplicate / join / mode / info / profile / selection
  transforms.py   nudge / resize / rotate / apply_transform / snap_to / snap_to_grid
  queries.py      describe / distance_between / gap_between / is_aligned
  relational.py   match_dimension / mirror_across / distribute_evenly / array_at_corners / array_along
  groups.py       group / parts_in / ungroup
  finishes.py     smooth_edges / round_corners / add_modifier / modify_modifier /
                  remove_modifier / list_modifiers / apply_modifiers
  editmode.py     bevel / extrude / loop_cut / select_* / grow_selection / move/scale_vertices /
                  delete_geometry / separate_selection / jitter_vertices / random_select /
                  proportional_move / inflate_selection
  rings.py        get_rings / select_ring(s) / scale_rings / taper_end / taper_section
  shading.py      shade_smooth / shade_flat / set_material (Principled BSDF)
  lighting.py     add_light / modify_light / set_world_background / set_camera_dof
  scatter.py      scatter_on_surface (the donut-tutorial sprinkle step)
  sculpt.py       sculpt_grab / inflate / draw / smooth / crease / pinch / flatten
  viewport.py     view angle / shading mode / framing / orbit / camera positioning
  shaders.py      set_toon_material (cel/anime) / add_outline / remove_outline
  history.py      get_history / undo_steps / redo_steps / undo_to
  designs.py      save_design / open_design / list_designs
  status.py       get_scene_tree / get_blender_status
  lint.py         find_coplanar_overlaps / validate_scene / check_mesh / audit_asset
  introspect.py   check_contacts / check_resting / check_framing / trace_profile / diff_since

Shared support:
  state.py        port, server flags, request queue, history log, NO_LOG/NO_STATUS sets
  common.py       world_bbox / world_center / nearby_objects / resolve_targets / activate / apply_scale
  placement.py    `on=...` DSL — resolve_placement / describe_placement
  server.py       dispatcher, socket server, queue processing
  ui.py           Blender operators + panel
"""

import bpy
from bpy.app.handlers import persistent

from . import server, state, ui


@persistent
def _on_load_post(*_args):
    """A file opened by hand (File > Open) replaces the scene without going through
    any tool, leaving the history/undo/diff bookkeeping describing the dead scene
    (gaps.md U11). Reset it on every load, the same reset new_scene does inline."""
    state.reset_history_state()


def register():
    # Dev hot-reload: Blender keeps an add-on's submodules cached in sys.modules across
    # a disable→enable, so edited tool code wouldn't load without a full restart. Since
    # register() runs on every enable, drop the package subtree and re-import it fresh
    # here — a plain add-on toggle is then enough to pick up code changes. No-op on the
    # first enable of a session (nothing cached yet); guarded so a bad reload can't brick
    # the enable (falls back to the cached modules).
    import sys
    global server, state, ui
    _stale = [m for m in list(sys.modules) if m.startswith(__name__ + ".")]
    if _stale:
        try:
            for _m in _stale:
                del sys.modules[_m]
            from . import server as _s, state as _st, ui as _ui
            server, state, ui = _s, _st, _ui
        except Exception as _e:                       # pragma: no cover
            print(f"[blender_buttons] hot-reload failed, using cached modules: {_e}")

    for cls in ui.CLASSES:
        bpy.utils.register_class(cls)
    # SPEC-11: the chat panel's single-line input box.
    bpy.types.WindowManager.bb_chat_input = bpy.props.StringProperty(
        name="Message", description="Type a message to the agent, then Send")
    # SPEC-07: right-click → Save as Handle in the edit-mode component context menu.
    bpy.types.VIEW3D_MT_edit_mesh_context_menu.append(ui._draw_save_as_handle)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)
    # One MCP tool call == one undo step, so a long build needs deep undo history.
    # Raise the limit (never lower it) so undo stays 1:1 with the log past the
    # default 32 steps — the E1 disaster was 27 ops in.
    try:
        prefs = bpy.context.preferences.edit
        if prefs.undo_steps < 256:
            prefs.undo_steps = 256
    except Exception:
        pass
    ui.start_server()


def unregister():
    state._running = False
    try:
        bpy.types.VIEW3D_MT_edit_mesh_context_menu.remove(ui._draw_save_as_handle)
    except Exception:
        pass
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    if bpy.app.timers.is_registered(server.process_queue):
        bpy.app.timers.unregister(server.process_queue)
    if bpy.app.timers.is_registered(ui._chat_drain_timer):
        bpy.app.timers.unregister(ui._chat_drain_timer)
    if hasattr(bpy.types.WindowManager, "bb_chat_input"):
        del bpy.types.WindowManager.bb_chat_input
    for cls in reversed(ui.CLASSES):
        bpy.utils.unregister_class(cls)

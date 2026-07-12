"""Blender UI: start/stop operators, the Properties-panel UI, and the SPEC-12
shared-state Collab panel (phase + action recording + handles)."""

import threading

import bpy

from . import collab, handles, server, state, validation


def start_server():
    """Start the TCP server + queue processor. Safe to call when already running.

    Binds the first free port in the instance range (so multiple Blenders coexist)
    before spinning up the accept loop. Returns False if already running OR the port
    range is exhausted."""
    if state._running:
        return False
    sock = server.bind_free_port()
    if sock is None:
        return False
    state._running = True
    state._server_thread = threading.Thread(
        target=server.server_loop, args=(sock,), daemon=True)
    state._server_thread.start()
    if not bpy.app.timers.is_registered(server.process_queue):
        bpy.app.timers.register(server.process_queue, persistent=True)
    return True


class BB_OT_StartServer(bpy.types.Operator):
    bl_idname = "bb.start_server"
    bl_label = "Start Server"

    def execute(self, context):
        if state._running:
            self.report({'INFO'}, f"Already running on port {state.PORT}")
            return {'FINISHED'}
        if not start_server():
            self.report({'ERROR'}, f"No free port in range "
                                   f"{state.PORT_MIN}-{state.PORT_MAX - 1}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Blender Buttons listening on port {state.PORT}")
        return {'FINISHED'}


class BB_OT_StopServer(bpy.types.Operator):
    bl_idname = "bb.stop_server"
    bl_label = "Stop Server"

    def execute(self, context):
        state._running = False
        if bpy.app.timers.is_registered(server.process_queue):
            bpy.app.timers.unregister(server.process_queue)
        self.report({'INFO'}, "Server stopped")
        return {'FINISHED'}


class BB_OT_SaveAsHandle(bpy.types.Operator):
    """Save the current vertex selection as a named handle (SPEC-07).

    The human's half of the shared mint path: select geometry in the viewport,
    right-click → Save as Handle, name it. Produces the same Empty + vgroup the
    agent's `feel op=handle` does — identical citizens."""
    bl_idname = "bb.save_as_handle"
    bl_label = "Save as Handle"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(
        name="Handle Name",
        description="Name for the handle (blank = auto-named handle.001-style)",
        default="",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        result = handles.mint_from_active_selection(self.name)
        if not result.get("success"):
            self.report({'ERROR'}, result.get("error", "failed to mint handle"))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Handle '{result['name']}' "
                              f"({result['vert_count']} verts) → Handles collection")
        return {'FINISHED'}


def _draw_save_as_handle(self, context):
    self.layout.operator(BB_OT_SaveAsHandle.bl_idname, icon='EMPTY_ARROWS')


class BB_PT_Panel(bpy.types.Panel):
    bl_label = "Blender Buttons"
    bl_idname = "BB_PT_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        layout.operator("bb.start_server", icon='PLAY')
        layout.operator("bb.stop_server", icon='PAUSE')
        layout.label(text=f"Status: {'Running' if state._running else 'Stopped'}")
        layout.label(text=f"Port: {state.PORT}")
        # The name an agent sees when it lists running instances to pick which to drive.
        layout.prop(context.window_manager, "bb_label", text="Label")


# ── SPEC-12: shared-state collaboration panel ─────────────────────────────────

class BB_OT_CollabRecordToggle(bpy.types.Operator):
    """Start or stop recording UI/mesh operators into a session the agent can pull."""
    bl_idname = "bb.collab_record_toggle"
    bl_label = "Toggle action recording"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if collab.is_recording():
            res = collab.stop_recording()
            self.report({'INFO'}, f"Recording stopped — {res.get('steps', 0)} step(s)")
        else:
            res = collab.start_recording()
            self.report({'INFO'}, "Recording started — model, then Stop")
        return {'FINISHED'}


class BB_OT_CollabRecordClear(bpy.types.Operator):
    """Clear the recorded action session."""
    bl_idname = "bb.collab_record_clear"
    bl_label = "Clear recording"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        collab.clear_recording()
        self.report({'INFO'}, "Recording cleared")
        return {'FINISHED'}


class BB_OT_CollabHandleSelect(bpy.types.Operator):
    """Select the handle's owner mesh and, in edit mode, just its verts."""
    bl_idname = "bb.collab_handle_select"
    bl_label = "Select"
    name: bpy.props.StringProperty()

    def execute(self, context):
        res = collab.select_handle(self.name)
        if res.get("error"):
            self.report({'ERROR'}, res["error"])
            return {'CANCELLED'}
        return {'FINISHED'}


class BB_OT_CollabHandleDelete(bpy.types.Operator):
    """Delete the handle (Empty + its owner's HANDLE_ vgroup)."""
    bl_idname = "bb.collab_handle_delete"
    bl_label = "Delete"
    name: bpy.props.StringProperty()

    def execute(self, context):
        res = collab.delete_handle(self.name)
        if res.get("error"):
            self.report({'ERROR'}, res["error"])
            return {'CANCELLED'}
        self.report({'INFO'}, f"Deleted handle '{self.name}'")
        return {'FINISHED'}


# ── SPEC-16: the human's governance of the validate floor ────────────────────
# Asymmetry: the agent gets the fine instrument (narrow `expect`); the human gets the
# blunt ones — revoke a declaration, add one, exclude a mesh from computation, or pull
# the whole floor down. All live here in the panel.

class BB_OT_ValidateRevoke(bpy.types.Operator):
    """Revoke a declared-intent assertion — overruling the agent ('that clip is a bug,
    fix it'). Re-arms the finding."""
    bl_idname = "bb.validate_revoke"
    bl_label = "Revoke"
    a: bpy.props.StringProperty()
    b: bpy.props.StringProperty()
    check: bpy.props.StringProperty(default="clipping")

    def execute(self, context):
        res = validation.revoke_intent(self.a, self.b, self.check)
        if res.get("error"):
            self.report({'ERROR'}, res["error"])
            return {'CANCELLED'}
        self.report({'INFO'}, f"Revoked {self.a}↔{self.b}")
        return {'FINISHED'}


class BB_OT_ValidateAddIntent(bpy.types.Operator):
    """Declare a clip intended on the agent's behalf — the human adding to the registry."""
    bl_idname = "bb.validate_add_intent"
    bl_label = "Declare intended clip"
    a: bpy.props.StringProperty(name="Object A")
    b: bpy.props.StringProperty(name="Object B")
    reason: bpy.props.StringProperty(name="Reason",
                                     description="Why this clip is intended (required)")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        res = validation.add_intent(self.a, self.b, self.reason, source="human")
        if res.get("error"):
            self.report({'ERROR'}, res["error"])
            return {'CANCELLED'}
        self.report({'INFO'}, f"Declared {self.a}↔{self.b} intended")
        return {'FINISHED'}


class BB_OT_ValidateExcludeMesh(bpy.types.Operator):
    """Toggle the active object's per-mesh validation override — EXCLUSION FROM
    COMPUTATION (the check never runs on it), for a huge imported part the agent
    shouldn't burn cycles validating."""
    bl_idname = "bb.validate_exclude_mesh"
    bl_label = "Toggle validate-exclude (active object)"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        now = not bool(obj.get("bb_no_validate"))
        obj["bb_no_validate"] = now
        collab.tag_redraw()
        self.report({'INFO'}, f"'{obj.name}' validate-exclude {'ON' if now else 'OFF'}")
        return {'FINISHED'}


def _wrap(text, width):
    """Greedy word-wrap for panel labels (Blender labels don't wrap)."""
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out or [""]


class BB_PT_CollabPanel(bpy.types.Panel):
    """Collab panel: action recording, validate floor, handles.
    Sidebar (N-panel) → 'Blender Buttons' tab."""
    bl_label = "Collab"
    bl_idname = "BB_PT_collab"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Blender Buttons"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        # The panel is useless with the socket down — expose start/stop here too.
        row = layout.row(align=True)
        row.operator("bb.start_server", icon='PLAY', text="Start")
        row.operator("bb.stop_server", icon='PAUSE', text="Stop")

        # ── Action recording (teach-by-doing journal for the agent) ──
        box = layout.box()
        box.label(text="Action recording", icon='REC')
        rec = collab.is_recording()
        n = len(collab.session_steps())
        row = box.row(align=True)
        if rec:
            row.alert = True
            row.operator("bb.collab_record_toggle", text="Stop recording",
                         icon='PAUSE')
        else:
            row.operator("bb.collab_record_toggle", text="Start recording",
                         icon='REC')
        row.operator("bb.collab_record_clear", text="", icon='TRASH')
        if rec:
            box.label(text=f"● REC — {n} step(s)", icon='SORTTIME')
        elif n:
            box.label(text=f"{n} step(s) ready for agent", icon='CHECKMARK')
        else:
            box.label(text="Click Start, model, then Stop")
        # Tail of the journal so you can see it's working.
        tail = collab.session_steps()[-6:]
        if tail:
            sub = box.column(align=True)
            for s in tail:
                label = s.get("name") or s.get("op") or "?"
                for i, line in enumerate(_wrap(f"{s.get('i', '?')}. {label}", 32)):
                    sub.label(text=line)

        # ── Validate floor (SPEC-16: the human's governance) ──
        box = layout.box()
        off = getattr(wm, "bb_validate_off", False)
        box.label(text="Validate floor", icon='SHADERFX')
        box.prop(wm, "bb_validate_off", text="Floor OFF (global override)")
        if off:
            box.label(text="⚠ floor is down — agent is blind", icon='ERROR')
        # Per-mesh exclusion for the active object.
        act = context.active_object
        if act is not None:
            excl = bool(act.get("bb_no_validate"))
            row = box.row(align=True)
            row.label(text=f"{act.name}: {'EXCLUDED' if excl else 'validated'}")
            row.operator("bb.validate_exclude_mesh", text="",
                         icon='CHECKBOX_HLT' if excl else 'CHECKBOX_DEHLT')
        # The intended-clip registry.
        intents = validation.list_intents()
        sub = box.column(align=True)
        sub.label(text=f"Declared clips ({len(intents)}):")
        if not intents:
            sub.label(text="(none)")
        else:
            for e in intents:
                vanished = e.get("status") != "holding"
                col = sub.column(align=True)
                head = col.row(align=True)
                head.label(text=f"{e['a']}↔{e['b']}",
                           icon='ERROR' if vanished else 'CHECKMARK')
                rev = head.operator("bb.validate_revoke", text="", icon='TRASH')
                rev.a, rev.b, rev.check = e["a"], e["b"], e.get("check", "clipping")
                for i, line in enumerate(_wrap(e.get("reason", ""), 34)):
                    col.label(text=("  " + line) if not i else line)
                if vanished:
                    col.label(text="  VANISHED — confirm or revoke", icon='ERROR')
        box.operator("bb.validate_add_intent", text="Declare clip", icon='ADD')

        # ── Handles (live scaffold) ──
        box = layout.box()
        box.label(text="Handles", icon='EMPTY_ARROWS')
        hs = collab.list_for_panel()
        if not hs:
            box.label(text="(no handles yet)")
        else:
            for h in hs:
                row = box.row(align=True)
                row.label(text=h["name"])
                row.operator("bb.collab_handle_select", text="",
                             icon='RESTRICT_SELECT_OFF').name = h["name"]
                row.operator("bb.collab_handle_delete", text="",
                             icon='TRASH').name = h["name"]


class BB_AddonPreferences(bpy.types.AddonPreferences):
    """Extension preferences. `auto_start` gates whether register() spins up the
    command server on enable/load — default ON so every Blender with the extension
    is immediately discoverable, with an opt-out for users who'd rather click Start."""
    bl_idname = __package__

    auto_start: bpy.props.BoolProperty(
        name="Auto-start server on enable",
        description="Start the command server automatically when the extension is "
                    "enabled or Blender loads, so this instance is immediately "
                    "discoverable by an agent. Off = start it manually from the panel.",
        default=True,
    )

    def draw(self, context):
        self.layout.prop(self, "auto_start")


CLASSES = (BB_AddonPreferences,
           BB_OT_StartServer, BB_OT_StopServer, BB_OT_SaveAsHandle,
           BB_OT_CollabRecordToggle, BB_OT_CollabRecordClear,
           BB_OT_CollabHandleSelect, BB_OT_CollabHandleDelete,
           BB_OT_ValidateRevoke, BB_OT_ValidateAddIntent, BB_OT_ValidateExcludeMesh,
           BB_PT_Panel, BB_PT_CollabPanel)

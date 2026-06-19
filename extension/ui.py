"""Blender UI: start/stop operators, the Properties-panel UI, and the SPEC-12
shared-state Collab panel (phase + sign-off queue + handles)."""

import threading

import bpy

from . import collab, handles, server, state


def start_server():
    """Start the TCP server + queue processor. Safe to call when already running."""
    if state._running:
        return False
    state._running = True
    state._server_thread = threading.Thread(target=server.server_loop, daemon=True)
    state._server_thread.start()
    if not bpy.app.timers.is_registered(server.process_queue):
        bpy.app.timers.register(server.process_queue, persistent=True)
    return True


class BB_OT_StartServer(bpy.types.Operator):
    bl_idname = "bb.start_server"
    bl_label = "Start Server"

    def execute(self, context):
        if not start_server():
            self.report({'INFO'}, "Already running")
            return {'FINISHED'}
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


# ── SPEC-12: shared-state collaboration panel ─────────────────────────────────

class BB_OT_CollabAccept(bpy.types.Operator):
    """Keep the applied edit; report it accepted on the agent's next status read."""
    bl_idname = "bb.collab_accept"
    bl_label = "Accept"
    op_id: bpy.props.StringProperty()

    def execute(self, context):
        res = collab.accept(self.op_id)
        if res.get("error"):
            self.report({'ERROR'}, res["error"])
            return {'CANCELLED'}
        self.report({'INFO'}, "Accepted")
        return {'FINISHED'}


class BB_OT_CollabReject(bpy.types.Operator):
    """Undo the applied edit (back to before it) and report it rejected. Rejecting a
    non-tail op also rewinds every op after it — the agent is told what to rebuild."""
    bl_idname = "bb.collab_reject"
    bl_label = "Reject"
    op_id: bpy.props.StringProperty()

    def execute(self, context):
        res = collab.reject(self.op_id)
        if res.get("error"):
            self.report({'ERROR'}, res["error"])
            return {'CANCELLED'}
        n = res.get("rewound", 0)
        self.report({'INFO'}, "Rejected (undone)"
                              + (f", +{n} later op(s) rewound" if n else ""))
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
    """SPEC-12 V1: the shared-state surface — phase, sign-off queue, handles.
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

        # ── Phase (human-owned signal) ──
        box = layout.box()
        box.label(text="Phase", icon='SEQUENCE')
        box.prop(wm, "bb_phase", text="")

        # ── Sign-off queue (apply, then review) ──
        box = layout.box()
        box.label(text="Sign-off queue", icon='CHECKMARK')
        pending = collab._pending
        if not pending:
            box.label(text="(nothing awaiting review)")
        else:
            for e in pending:
                col = box.column(align=True)
                for i, line in enumerate(_wrap(e["label"], 30)):
                    col.label(text=line if i else f"• {line}")
                row = col.row(align=True)
                row.operator("bb.collab_accept", text="Accept",
                             icon='CHECKMARK').op_id = e["op_id"]
                row.operator("bb.collab_reject", text="Reject",
                             icon='X').op_id = e["op_id"]

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


CLASSES = (BB_OT_StartServer, BB_OT_StopServer, BB_OT_SaveAsHandle,
           BB_OT_CollabAccept, BB_OT_CollabReject,
           BB_OT_CollabHandleSelect, BB_OT_CollabHandleDelete,
           BB_PT_Panel, BB_PT_CollabPanel)

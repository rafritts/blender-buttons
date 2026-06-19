"""Blender UI: start/stop operators and the Properties-panel UI."""

import threading

import bpy

from . import chat, handles, server, state


def _tag_chat_redraw():
    """Tag every VIEW_3D N-panel region for redraw so freshly-drained agent
    replies show up without the user nudging the UI."""
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'UI':
                        region.tag_redraw()


def _chat_drain_timer():
    """SPEC-11: move agent replies from the outbound queue into the displayed log
    and redraw when any arrived. Runs on the main thread (bpy.app.timers)."""
    if chat.drain_outbound():
        _tag_chat_redraw()
    return 0.2  # 5 Hz — responsive for chat, negligible cost


def start_server():
    """Start the TCP server + queue processor. Safe to call when already running."""
    if state._running:
        return False
    state._running = True
    state._server_thread = threading.Thread(target=server.server_loop, daemon=True)
    state._server_thread.start()
    if not bpy.app.timers.is_registered(server.process_queue):
        bpy.app.timers.register(server.process_queue, persistent=True)
    if not bpy.app.timers.is_registered(_chat_drain_timer):
        bpy.app.timers.register(_chat_drain_timer, persistent=True)
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
        if bpy.app.timers.is_registered(_chat_drain_timer):
            bpy.app.timers.unregister(_chat_drain_timer)
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


class BB_OT_ChatSend(bpy.types.Operator):
    """Send the typed message to the agent (SPEC-11). Enqueues onto the inbound
    queue the agent long-polls via `chat op=poll`."""
    bl_idname = "bb.chat_send"
    bl_label = "Send"

    def execute(self, context):
        wm = context.window_manager
        if not chat.push_inbound(wm.bb_chat_input):
            return {'CANCELLED'}
        wm.bb_chat_input = ""
        _tag_chat_redraw()
        return {'FINISHED'}


def _wrap(text, width):
    """Greedy word-wrap for the panel log (Blender labels don't wrap)."""
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


class BB_PT_ChatPanel(bpy.types.Panel):
    """SPEC-11 V1: chat with the agent from inside Blender, routed entirely
    through the MCP server. Sidebar (N-panel) → 'Blender Buttons' tab."""
    bl_label = "Chat"
    bl_idname = "BB_PT_chat"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Blender Buttons"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        # Chat needs the socket server up — expose start/stop here too.
        row = layout.row(align=True)
        row.operator("bb.start_server", icon='PLAY', text="Start")
        row.operator("bb.stop_server", icon='PAUSE', text="Stop")

        box = layout.box()
        msgs = chat.log()
        if not msgs:
            box.label(text="(no messages yet)")
        else:
            for m in msgs[-30:]:
                who = "You" if m["role"] == "human" else "Claude"
                col = box.column(align=True)
                for i, line in enumerate(_wrap(m["text"], 34)):
                    col.label(text=(f"{who}: " if i == 0 else "    ") + line)

        layout.prop(wm, "bb_chat_input", text="")
        layout.operator("bb.chat_send", icon='EXPORT')
        layout.label(text=f"Status: {chat.status_text()}")


CLASSES = (BB_OT_StartServer, BB_OT_StopServer, BB_OT_SaveAsHandle,
           BB_OT_ChatSend, BB_PT_Panel, BB_PT_ChatPanel)

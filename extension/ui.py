"""Blender UI: start/stop operators and the Properties-panel UI."""

import threading

import bpy

from . import handles, server, state


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


CLASSES = (BB_OT_StartServer, BB_OT_StopServer, BB_OT_SaveAsHandle, BB_PT_Panel)

"""Blender UI: start/stop operators and the Properties-panel UI."""

import threading

import bpy

from . import server, state


class BB_OT_StartServer(bpy.types.Operator):
    bl_idname = "bb.start_server"
    bl_label = "Start Server"

    def execute(self, context):
        if state._running:
            self.report({'INFO'}, "Already running")
            return {'FINISHED'}
        state._running = True
        state._server_thread = threading.Thread(target=server.server_loop, daemon=True)
        state._server_thread.start()
        bpy.app.timers.register(server.process_queue, persistent=True)
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


CLASSES = (BB_OT_StartServer, BB_OT_StopServer, BB_PT_Panel)

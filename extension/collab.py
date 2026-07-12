"""Collab — action recording + handles for the Collab N-panel.

  • recording — human action journal: Start/Stop in the panel; agent pulls via
                collab_status / collab_session
  • handles   — live Handles collection (list/select/delete in the panel)

Recorder design (crash-hardening):
  • Poll only the *tail* of wm.operators (last few), never walk the whole stack.
  • Never open bmesh from the timer (edit-mode races with Extrude/modals).
  • Props are best-effort; a failed prop read never aborts the step.
  • Panel redraw is throttled (not every step).
  • All timer work is wrapped so a bad op never escapes to crash Blender.
"""

import time

import bpy

from . import handles

# ── recording state ──────────────────────────────────────────────────────────

_recording = False
_session = []          # list of step dicts (newest last)
_last_op_key = None    # (bl_idname, name, prop_fingerprint) of last recorded step
_started_at = 0.0
_POLL_INTERVAL = 0.35  # slower = less main-thread pressure during modeling
_last_redraw_t = 0.0
_REDRAW_MIN_GAP = 1.0  # seconds between panel refreshes while recording
_MAX_STEPS = 500       # hard cap so a long session can't balloon memory


# Viewport / UI noise. bl_idname may be dotted ("view3d.rotate") OR RNA
# ("VIEW3D_OT_rotate") depending on how the stack exposes it — match both.
_NOISE_IDS = frozenset({
    "view3d.rotate", "view3d.move", "view3d.zoom", "view3d.dolly",
    "view3d.view_all", "view3d.view_selected", "view3d.view_axis",
    "view3d.view_orbit", "view3d.view_pan", "view3d.view_persportho",
    "view3d.smoothview", "view3d.ndof_orbit", "view3d.ndof_pan",
    "view3d.walk", "view3d.fly", "view3d.camera_to_view", "view3d.ruler_add",
    "VIEW3D_OT_rotate", "VIEW3D_OT_move", "VIEW3D_OT_zoom", "VIEW3D_OT_dolly",
    "VIEW3D_OT_view_all", "VIEW3D_OT_view_selected", "VIEW3D_OT_view_axis",
    "VIEW3D_OT_view_orbit", "VIEW3D_OT_view_pan", "VIEW3D_OT_view_persportho",
    "VIEW3D_OT_smoothview", "VIEW3D_OT_ndof_orbit", "VIEW3D_OT_ndof_pan",
    "VIEW3D_OT_walk", "VIEW3D_OT_fly", "VIEW3D_OT_camera_to_view",
    "screen.frame_offset", "screen.animation_play", "screen.screen_full_area",
    "SCREEN_OT_frame_offset", "SCREEN_OT_animation_play",
    "wm.window_close", "wm.window_fullscreen_toggle", "wm.redraw_timer",
    "WM_OT_window_close", "WM_OT_redraw_timer",
    "outliner.item_activate", "OUTLINER_OT_item_activate",
    "info.reports_display_update", "INFO_OT_reports_display_update",
    "bb.collab_record_toggle", "bb.collab_record_clear",
})
_NOISE_PREFIXES = (
    "screen.", "SCREEN_OT_",
    "info.", "INFO_OT_",
    "file.", "FILE_OT_",
    "text.", "TEXT_OT_",
    "console.", "CONSOLE_OT_",
    "preferences.", "PREFERENCES_OT_",
    "nla.", "NLA_OT_",
    "clip.", "CLIP_OT_",
    "sequencer.", "SEQUENCER_OT_",
    "bb.", "BB_OT_",
)


def tag_redraw(force=False):
    """Tag VIEW_3D N-panel regions. Throttled unless force=True."""
    global _last_redraw_t
    now = time.time()
    if not force and (now - _last_redraw_t) < _REDRAW_MIN_GAP:
        return
    _last_redraw_t = now
    try:
        wm = bpy.context.window_manager
        for window in (wm.windows if wm else []):
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'UI':
                            region.tag_redraw()
    except Exception:
        pass


# ── selection / prop helpers ─────────────────────────────────────────────────

def _selection_summary():
    """Light context only — no bmesh (unsafe from a timer during Extrude)."""
    try:
        obj = bpy.context.view_layer.objects.active if bpy.context.view_layer else None
    except Exception:
        return {"active": None, "mode": None, "selection": "?"}
    if obj is None:
        return {"active": None, "mode": None, "selection": "none"}
    try:
        mode = getattr(obj, "mode", "?")
        out = {"active": obj.name, "type": obj.type, "mode": mode}
        if mode == 'OBJECT':
            try:
                n = len(bpy.context.selected_objects)
            except Exception:
                n = 0
            out["selection"] = f"{n} object(s) selected"
        else:
            # Edit/sculpt/etc.: name the mode only. Face counts need bmesh and
            # race with modal mesh ops (a crash vector we hit in dogfood).
            out["selection"] = f"{mode} mode"
        return out
    except Exception:
        return {"active": "?", "mode": "?", "selection": "?"}


def _json_safe(val, _depth=0):
    """Recursively coerce anything into json.dumps-able data (no Vector/Matrix)."""
    if _depth > 6:
        return None
    if val is None or isinstance(val, (bool, int, str)):
        return val
    if isinstance(val, float):
        return round(val, 6)
    # mathutils Vector/Color/Euler/Quaternion — avoid leaving nested Vectors (Matrix rows)
    try:
        # Matrix / multi-dim: to_tuple() if present
        if hasattr(val, "to_tuple") and callable(val.to_tuple):
            t = val.to_tuple()
            return _json_safe(t, _depth + 1)
    except Exception:
        pass
    if isinstance(val, dict):
        out = {}
        for k, v in val.items():
            sk = str(k)
            sv = _json_safe(v, _depth + 1)
            if sv is not None:
                out[sk] = sv
        return out
    if isinstance(val, (list, tuple)):
        out = []
        for x in val:
            sx = _json_safe(x, _depth + 1)
            if sx is None and not isinstance(x, (type(None), bool, int, float, str)):
                continue
            out.append(sx)
        return out
    try:
        if hasattr(val, "__len__") and not isinstance(val, (str, bytes)):
            out = []
            for x in val:
                sx = _json_safe(x, _depth + 1)
                if sx is None and not isinstance(x, (type(None), bool, int, float, str)):
                    return None  # nested RNA / unknown
                out.append(sx)
            return out
    except Exception:
        pass
    try:
        return str(val)
    except Exception:
        return None


def _serialize_prop(val):
    return _json_safe(val)


# Props worth trying on mesh/transform ops; skip the rest (walking every RNA
# property on a live operator has been a crash vector).
_INTERESTING_PROPS = (
    "value", "constraint_axis", "orient_type", "orient_matrix_type",
    "mirror", "use_proportional_edit", "proportional_edit_falloff",
    "proportional_size", "release_confirm", "use_accurate",
    "thickness", "depth", "offset", "factor", "number_cuts",
    "smoothness", "falloff", "profile", "segments",
    "xmin", "xmax", "ymin", "ymax", "mode", "deselect_all",
    "location", "direction", "magnitude", "matrix",
    "TRANSFORM_OT_translate", "MESH_OT_extrude_region",  # nested macros sometimes
)


def _operator_props(op):
    props = {}
    try:
        pr = op.properties
    except Exception:
        return props
    for ident in _INTERESTING_PROPS:
        try:
            if not hasattr(pr, ident):
                continue
            val = getattr(pr, ident)
            # Nested operator (macro child)
            if hasattr(val, "bl_rna") and hasattr(val, "properties"):
                nested = {}
                for nid in _INTERESTING_PROPS:
                    try:
                        if hasattr(val, nid):
                            nv = getattr(val, nid)
                            ser = _serialize_prop(nv)
                            if ser is not None and ser not in (0, 0.0, False, "", "DEFAULT", "NONE"):
                                nested[nid] = ser
                    except Exception:
                        continue
                if nested:
                    props[ident] = nested
                continue
            ser = _serialize_prop(val)
            if ser is None or ser in (0, 0.0, False, "", "DEFAULT", "NONE"):
                continue
            props[ident] = ser
        except Exception:
            continue
    return props


def _is_noise(bl_idname):
    if not bl_idname:
        return True
    if bl_idname in _NOISE_IDS:
        return True
    for pref in _NOISE_PREFIXES:
        if bl_idname.startswith(pref):
            return True
    return False


def _op_identity(op):
    """Read only id + name — the cheapest, safest fields."""
    try:
        bl_id = getattr(op, "bl_idname", "") or ""
    except Exception:
        return "", ""
    try:
        name = getattr(op, "name", "") or bl_id
    except Exception:
        name = bl_id
    return bl_id, name


def _append_step_from_op(op):
    global _last_op_key
    try:
        bl_id, name = _op_identity(op)
    except Exception:
        return False
    if _is_noise(bl_id):
        return False
    try:
        props = _operator_props(op)
    except Exception:
        props = {}
    # fingerprint without selection (selection no longer fine-grained)
    key = (bl_id, name, tuple(sorted((k, repr(v)) for k, v in props.items())))
    if key == _last_op_key:
        # same op still head of stack — don't spam
        return False
    _last_op_key = key
    if len(_session) >= _MAX_STEPS:
        return False
    step = {
        "i": len(_session) + 1,
        "t": round(time.time() - _started_at, 2),
        "op": bl_id,
        "name": name,
        "props": props,
        "context": _selection_summary(),
    }
    _session.append(step)
    return True


def _poll_operators():
    """Timer: look only at the last operator on the stack."""
    if not _recording:
        return None
    try:
        wm = bpy.context.window_manager
        if wm is None:
            return _POLL_INTERVAL
        ops = wm.operators
        n = len(ops)
        if n == 0:
            return _POLL_INTERVAL
        # Only inspect the newest entry — walking older ops re-touches freed RNA.
        op = ops[n - 1]
        if _append_step_from_op(op):
            tag_redraw(force=False)
    except Exception:
        # Never let a timer exception bubble into Blender's C stack.
        pass
    return _POLL_INTERVAL


def _ensure_timer(on):
    running = bpy.app.timers.is_registered(_poll_operators)
    if on and not running:
        bpy.app.timers.register(_poll_operators, first_interval=_POLL_INTERVAL, persistent=True)
    elif not on and running:
        try:
            bpy.app.timers.unregister(_poll_operators)
        except Exception:
            pass


# ── public recording API (panel + socket) ────────────────────────────────────

def start_recording():
    """Begin a new session (clears any previous journal)."""
    global _recording, _session, _last_op_key, _started_at
    _session = []
    _last_op_key = None
    _started_at = time.time()
    _recording = True
    _ensure_timer(True)
    tag_redraw(force=True)
    return {"success": True, "recording": True, "steps": 0}


def stop_recording():
    """Stop capturing; keep the journal for the agent to pull."""
    global _recording
    _recording = False
    _ensure_timer(False)
    tag_redraw(force=True)
    return {"success": True, "recording": False, "steps": len(_session)}


def clear_recording():
    """Drop the journal (also stops if running)."""
    global _recording, _session, _last_op_key
    _recording = False
    _session = []
    _last_op_key = None
    _ensure_timer(False)
    tag_redraw(force=True)
    return {"success": True, "recording": False, "steps": 0}


def is_recording():
    return _recording


def session_steps():
    return list(_session)


def format_session_transcript(steps=None):
    steps = steps if steps is not None else _session
    lines = [
        f"# Action session ({len(steps)} step(s)"
        + (", RECORDING" if _recording else ", stopped")
        + ")",
        "",
    ]
    if not steps:
        lines.append("(empty — click Start Recording, model, then Stop)")
        return "\n".join(lines)
    for s in steps:
        props = s.get("props") or {}
        prop_s = ", ".join(f"{k}={v!r}" for k, v in props.items()) if props else "—"
        ctx = s.get("context") or {}
        active = ctx.get("active") or "?"
        sel = ctx.get("selection") or "?"
        mode = ctx.get("mode") or "?"
        lines.append(
            f"{s.get('i', '?')}. [{s.get('t', 0):.1f}s] **{s.get('name') or s.get('op')}** "
            f"(`{s.get('op')}`)"
        )
        lines.append(f"   props: {prop_s}")
        lines.append(f"   context: active={active} mode={mode} · {sel}")
        lines.append("")
    return "\n".join(lines)


# ── agent side (via the socket — MUST be instant) ────────────────────────────

def _safe_steps(steps):
    """Copy steps with every value forced JSON-safe (pull must never crash / fail)."""
    out = []
    for s in steps:
        try:
            out.append(_json_safe(dict(s)) or {})
        except Exception:
            out.append({
                "i": s.get("i"),
                "op": str(s.get("op", "")),
                "name": str(s.get("name", "")),
                "props": {},
                "context": {},
            })
    return out


def collab_status(params):
    """Recording state + short tail of the action journal."""
    tail = _session[-12:] if _session else []
    return {
        "success": True,
        "recording": _recording,
        "session_steps": len(_session),
        "session_tail": _safe_steps(tail),
    }


def collab_session(params):
    """Full action journal (or clear=True to drop it).

    Always JSON-safe. Prefer transcript if structured session ever fails.
    """
    if params.get("clear"):
        clear_recording()
        return {"success": True, "recording": False, "steps": 0, "transcript": "(cleared)"}
    try:
        transcript = format_session_transcript()
    except Exception as e:
        transcript = f"(transcript format failed: {e})"
    try:
        session = _safe_steps(_session)
    except Exception:
        session = []
    return {
        "success": True,
        "recording": _recording,
        "steps": len(_session),
        "session": session,
        "transcript": transcript,
    }


def collab_record(params):
    """Agent-side start/stop/clear (mirrors the panel button)."""
    action = (params.get("action") or "status").lower().strip()
    if action == "start":
        return start_recording()
    if action == "stop":
        return stop_recording()
    if action == "clear":
        return clear_recording()
    return {
        "success": True,
        "recording": _recording,
        "steps": len(_session),
    }


# ── handles (panel list / select / delete) ────────────────────────────────────

def _handles_in_collection():
    coll = bpy.data.collections.get(handles.HANDLES_COLLECTION)
    if coll is None:
        return []
    return [o for o in coll.objects if o.get("bb_handle")]


def list_for_panel():
    return [{"name": o.name, "owner": o.get("bb_owner", "?")}
            for o in sorted(_handles_in_collection(), key=lambda o: o.name)]


def select_handle(name):
    empty = handles._find_handle(name)
    if empty is None:
        return {"error": f"handle '{name}' not found"}
    owner = bpy.data.objects.get(empty.get("bb_owner", ""))
    if owner is None or owner.type != 'MESH':
        return {"error": f"handle '{name}' has no live owner mesh"}
    vg = owner.vertex_groups.get(empty.get("bb_vgroup", ""))
    if vg is None:
        return {"error": f"handle '{name}' vertex group is gone"}
    if bpy.context.active_object and bpy.context.active_object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    owner.select_set(True)
    bpy.context.view_layer.objects.active = owner
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    import bmesh
    bm = bmesh.from_edit_mesh(owner.data)
    deform = bm.verts.layers.deform.verify()
    gi = vg.index
    for v in bm.verts:
        if gi in v[deform]:
            v.select = True
    bm.select_flush(True)
    bmesh.update_edit_mesh(owner.data)
    return {"success": True, "owner": owner.name}


def delete_handle(name):
    empty = handles._find_handle(name)
    if empty is None:
        return {"error": f"handle '{name}' not found"}
    handles._delete_handle_empty(empty)
    tag_redraw(force=True)
    return {"success": True, "deleted": name}


TOOLS = {
    "collab_status": collab_status,
    "collab_session": collab_session,
    "collab_record": collab_record,
}

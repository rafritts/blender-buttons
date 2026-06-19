"""Collab — shared-state collaboration surface (SPEC-12).

Three things the human and agent share through the N-panel, carried as ordinary
addon commands over the existing socket + main-thread queue (no new transport):

  • phase     — where we are in the pipeline (a WindowManager EnumProperty the
                human sets; the agent reads it via `collab op=status`).
  • sign-off  — edits the agent applied and surfaced for the human's Accept/Reject.
  • handles   — the live Handles collection (listed/selected/deleted in the panel).

This module owns the sign-off-queue state and the agent-facing read/submit
commands; it also holds the accept/reject/handle logic the panel operators call.
The panel + operators live in ui.py; the `bb_phase` property in __init__.py.

DISCIPLINE (same as every socket command): collab_status / collab_submit run on
Blender's MAIN THREAD via the request queue, so the plain lists below need no
locking, and they must return instantly. The accept/reject/handle helpers run from
panel operators — also the main thread.

Unlike SPEC-11's chat, decisions flow back to the agent ON DEMAND: the agent calls
`collab op=status` whenever it wants to know the phase or whether the human acted.
There is no long-poll loop to hold open — SPEC-11's #1 risk is gone by design.

The sign-off queue is AUTOMATIC and the agent cannot curate it: every mutating op
auto-enqueues via `enqueue()`, called from the dispatch (extension/server.py) at the
exact point each op gets its op_id + undo step. So the queue == the undo stack since
the last review — the whole diff, not what the agent chose to surface (like a PR
showing every changed line). Reject == undo. The agent only READS, via `op=status`.
"""

import bpy

from . import handles, state

# Edits the agent applied and surfaced, awaiting the human's call.
_pending = []   # list of {"op_id": str, "label": str}
# Decisions the human made but the agent hasn't read yet (drained by collab_status).
# {"op_id", "label", "verdict": "accepted"|"rejected", "rewound": [labels], "verified"}
_decided = []


def tag_redraw():
    """Tag every VIEW_3D N-panel region so a freshly submitted/decided row shows
    without the human nudging the UI. Safe on the main thread (queue + operators)."""
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'UI':
                        region.tag_redraw()


# ── agent side (via the socket — MUST be instant) ────────────────────────────

def collab_status(params):
    """The agent's read of shared state: current phase, the waiting sign-off queue,
    and any decisions made since the last read. DRAINS _decided (each decision is
    reported once). Instant."""
    wm = bpy.context.window_manager
    phase = getattr(wm, "bb_phase", "blockout") if wm else "blockout"
    decided = [dict(e) for e in _decided]
    _decided.clear()
    return {"success": True, "phase": phase,
            "pending": [dict(e) for e in _pending],
            "decided": decided}


def enqueue(op_id, label):
    """Auto-enqueue a just-applied mutating op for sign-off. Called from the dispatch
    (extension/server.py) at the point the op gets its op_id + undo step, so the queue
    stays 1:1 with the undo stack — the whole diff, not an agent-curated subset. Not a
    socket command: the agent has no way to add to or withhold from the queue."""
    if not op_id or any(e["op_id"] == op_id for e in _pending):
        return
    _pending.append({"op_id": op_id, "label": label or op_id})
    tag_redraw()


# ── human side (panel operators call these — main thread) ─────────────────────

def _pop_pending(op_id):
    for i, e in enumerate(_pending):
        if e["op_id"] == op_id:
            return _pending.pop(i)
    return None


def accept(op_id):
    """Keep the edit; move its row pending → decided (accepted)."""
    entry = _pop_pending(op_id)
    if entry is None:
        return {"error": f"op '{op_id}' is not in the pending queue"}
    _decided.append({"op_id": op_id, "label": entry["label"],
                     "verdict": "accepted", "rewound": []})
    tag_redraw()
    return {"success": True}


def reject(op_id):
    """Undo back to BEFORE this op (sequential undo), then move pending → decided
    (rejected). Because undo is 1:1 and sequential, rejecting a non-tail op also
    rewinds every op logged after it — those labels ride along in `rewound` so the
    agent learns what to rebuild."""
    entry = _pop_pending(op_id)
    if entry is None:
        return {"error": f"op '{op_id}' is not in the pending queue"}
    from . import history
    idx = next((i for i, h in enumerate(state._history) if h["id"] == op_id), None)
    if idx is None:
        # Already gone from the log (a prior reject rewound past it). Nothing to undo.
        _decided.append({"op_id": op_id, "label": entry["label"],
                         "verdict": "rejected", "rewound": []})
        tag_redraw()
        return {"success": True, "rewound": 0}
    # Capture the collateral (everything logged after op_id) BEFORE undo pops it.
    collateral = [(h["id"], h["label"]) for h in state._history[idx + 1:]]
    steps = len(state._history) - idx          # include op_id itself
    result = history.undo_steps({"steps": steps})
    if not result.get("success"):
        _pending.append(entry)                 # undo failed — keep state honest
        return {"error": result.get("error", "undo failed")}
    # Collateral ops are no longer applied: drop any that were themselves pending so
    # the panel can't offer Accept on a vanished edit.
    collateral_ids = {cid for cid, _ in collateral}
    _pending[:] = [e for e in _pending if e["op_id"] not in collateral_ids]
    _decided.append({"op_id": op_id, "label": entry["label"], "verdict": "rejected",
                     "rewound": [lbl for _, lbl in collateral],
                     "verified": result.get("verified", True)})
    tag_redraw()
    return {"success": True, "rewound": len(collateral)}


# ── handles (panel list / select / delete) ────────────────────────────────────

def _handles_in_collection():
    coll = bpy.data.collections.get(handles.HANDLES_COLLECTION)
    if coll is None:
        return []
    return [o for o in coll.objects if o.get("bb_handle")]


def list_for_panel():
    """Lightweight handle list for the panel — name + owner, no drift validation."""
    return [{"name": o.name, "owner": o.get("bb_owner", "?")}
            for o in sorted(_handles_in_collection(), key=lambda o: o.name)]


def select_handle(name):
    """Select the handle's owner mesh and, in edit mode, just its vgroup verts."""
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
    """Delete one handle (Empty + its owner's HANDLE_ vgroup) — native + registry tidy."""
    empty = handles._find_handle(name)
    if empty is None:
        return {"error": f"handle '{name}' not found"}
    handles._delete_handle_empty(empty)
    tag_redraw()
    return {"success": True, "deleted": name}


TOOLS = {
    "collab_status": collab_status,
}

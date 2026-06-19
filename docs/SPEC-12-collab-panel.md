# SPEC-12 — Shared collaboration panel: handles, sign-off queue, phase (V1)

_Status: **IMPLEMENTED (2026-06-19), pending live validation.** Addon side:
`extension/collab.py` (the `_pending`/`_decided` queues + `collab_status`/
`collab_submit` socket commands + the accept/reject/handle helpers the panel calls),
registered in `extension/server.py`'s `_TOOL_MODULES` and exempted from history/undo/
status in `extension/state.py`; the Collab N-panel (phase dropdown + sign-off queue +
handles list) + its operators + the `bb_phase` EnumProperty in `extension/ui.py` /
`extension/__init__.py`. Server side: the `collab` verb (`op=status`, `op=submit`) in
`server/verbs/collab.py`, wired into `server/verbs/__init__.py` — registers and
survives the prune (16 verbs; `chat` removed). SPEC-11 chat fully torn down.
Remaining: the human reinstalls the addon + reconnects MCP, then we run the four
success criteria live. Original spec text below._

_Supersedes the in-Blender chat of SPEC-11 —
that V1 proved you can chat with the agent through the MCP server (all four gates
passed live), but the dogfood surfaced that conversation was never the gap: the
terminal handles talking fine. The gap is **shared state** — a window inside Blender
into what the agent is building (handles), what's waiting on the human's call
(sign-off queue), and where we are (phase). This spec drops the chat pipe and builds
that state panel instead. SPEC-11 stays in the repo as a documented dead-end._

## The problem

The collaboration is real but the human is blind to the agent's working state. The
agent mints handles, makes edits, and reasons about "what phase are we in" — all of
it lives in the terminal transcript and the agent's head. The human, watching
Blender, sees only the geometry change; they can't see the **relational scaffold**
(which handles exist), they have no place to **sign off** on an edit, and there's no
**shared marker** for where in the pipeline we are. Every collab affordance founders
on there being no shared-state surface — only a shell and a viewport.

Chat (SPEC-11) was the wrong fix: it added a second conversation channel next to the
one that already works. The right fix is to surface the **structured state** the
collaboration turns on, and give the human the two controls they actually need over
it: **accept/reject an edit**, and **set the phase**.

## The principle

Same plumbing insight as SPEC-11, pointed at state instead of text: the shared state
is **a few more fields of addon state**, read and written through **one more verb**
and **one more panel**, over the socket + main-thread queue that already carry every
other call. No new transport.

But unlike chat, decisions flow back to the agent **on demand**, not by long-poll:
the agent reads `collab op=status` whenever it wants to know the phase or whether the
human has acted. That erases SPEC-11's #1 risk (turn liveness / context growth from
an idle poll loop) entirely — there is no loop to hold open. The panel is a control
surface the agent **writes to** and the human **acts on**; the human can still just
say things in the terminal.

This is collaboration plumbing, not a geometry primitive — a different axis (how we
coordinate), kept off the mesh-tool surface, same as the chat justification.

## The surface (V1)

One N-panel (VIEW_3D sidebar) tab, **"Collab"**, three sections:

### 1. Phase  (human-owned signal)

A dropdown: **blockout → secondary → detail → retopo → uv → bake**. The human sets
it; the agent reads it via `collab op=status` and lets it shape how it works. **No
op-gating in V1** — it is a shared signal, not a lock. (Op-gating and auto-progress
are V2.)

Implemented as a `bpy.types.WindowManager` EnumProperty (`bb_phase`); `collab
op=status` reads it directly — no mirror, no callback.

### 2. Sign-off queue  (apply, then review)

Edits the agent has applied and surfaced for the human's call. The flow:

1. The agent makes the edit (immediate, as always) and notes the returned `op_id`.
2. The agent calls `collab op=submit label="extrude nub +0.04"` (op_id defaults to
   the last logged op) → the edit appears in the queue.
3. Each row shows the label + **[Accept] [Reject]**.
   - **Accept** → the edit is kept; the row moves to "decided: accepted".
   - **Reject** → undo back to **before** that op (via the existing undo stack), then
     the row moves to "decided: rejected".
4. The agent reads the verdicts via `collab op=status`, which **drains** the decided
   list (each decision is reported once), and proceeds accordingly.

**Honest caveat (Reject):** undo is sequential and 1:1 with ops, so rejecting a
**non-tail** op also rewinds every op after it. Review promptly / newest-first, or
reject only the most recent. `collab op=status` reports the rewind so the agent can
rebuild the ops it still wanted. (A surgical mid-stack revert is out of V1 scope —
it needs op replay, the same machinery SPEC-11's "propose-then-apply" would have.)

### 3. Handles  (live view of the relational scaffold)

Lists the **Handles** collection (already minted as Empty + vgroup by `feel
op=handle` / Save as Handle, SPEC-07). Each row: the handle name + its point, with
**[Select]** (select the owner mesh and the handle's verts) and **[Delete]** (native
delete + registry tidy). Read-only otherwise. This is the window into the anchors the
agent is building on — the human can see, pick, and prune them.

## New addon state + commands (`extension/collab.py`)

State (mutated only on the main thread, like every other addon queue — no locks):

- `_pending`  — waiting entries: `{op_id, label}`.
- `_decided`  — entries the human acted on but the agent hasn't read yet:
  `{op_id, label, verdict, rewound?}`.

Commands (registered in `extension/server.py` `_TOOL_MODULES`; exempt from
history/undo/status in `extension/state.py`, like the SPEC-11 chat commands were):

- `collab_status(params)` → `{phase, pending:[…], decided:[…]}` and **drains**
  `_decided`. Instant.
- `collab_submit(params)` → append `{op_id (default = last logged op), label}` to
  `_pending`; tag the panel for redraw. Instant.

Panel operators (local, main thread — never touch the socket):

- set phase (the EnumProperty itself).
- `bb.collab_accept(op_id)` → move row `_pending → _decided` (accepted).
- `bb.collab_reject(op_id)` → undo to before `op_id` (reuse the history undo path),
  then move row `_pending → _decided` (rejected, rewound).
- `bb.collab_handle_select(name)` / `bb.collab_handle_delete(name)`.

## New MCP verb (`server/verbs/collab.py` → `collab`)

- `collab op=status` — the agent's read of shared state: current phase, the waiting
  sign-off queue, and any decisions made since the last read. The one call the agent
  makes to "check in."
- `collab op=submit label=<text> [op_id=<id>]` — surface an applied edit for sign-off.

Wired into `server/verbs/__init__.py` `VERB_NAMES` (→ 16 verbs; `chat` removed).

## What gets removed (SPEC-11 teardown)

- `extension/chat.py`; `chat` out of `_TOOL_MODULES`; `chat_*` out of state.py sets.
- The chat panel / Send operator / drain timer / `bb_chat_input` prop in
  `extension/ui.py` + `extension/__init__.py`.
- `server/verbs/chat.py`; `chat` out of `verbs/__init__.py`.
- SPEC-11 doc kept, status flipped to SUPERSEDED.

## Success criteria (the V1 done-bar)

1. **Phase round-trips.** Set the dropdown to "secondary"; `collab op=status` reports
   `phase: secondary`.
2. **Sign-off round-trips.** Agent edits + `collab op=submit`; the row appears with
   Accept/Reject. Accept → next `collab op=status` reports it accepted. Reject →
   the op is undone in the viewport **and** the next status reports it rejected.
3. **Handles list is live.** A freshly minted handle appears in the panel; Select
   selects it; Delete removes it.
4. **No loop, no terminal nudge for reads.** The agent learns the human's decisions
   by calling `collab op=status` inside an ordinary turn — no long-poll, no boot.

## Non-goals (V2+)

- Op-gating / auto-progress per phase.
- Surgical mid-stack reject (op replay), propose-before-apply, ghosted before/after.
- Shared pointing as a referent stream; autonomy modes ("back in 30 minutes").
- Persistence across a Blender restart.

## Implementation steps

1. Teardown SPEC-11 chat (list above).
2. `extension/collab.py` — `_pending`/`_decided` + `collab_status`/`collab_submit`;
   register in `server.py`; exempt in `state.py`.
3. `extension/ui.py` + `__init__.py` — the Collab panel (phase dropdown + sign-off
   queue + handles list), the operators, the `bb_phase` EnumProperty, redraw.
4. `server/verbs/collab.py` — the `collab` verb (status, submit); register in
   `verbs/__init__.py`.
5. Validate against the four success criteria.
6. Deploy: rebuild the zip (`build_extension.sh`) → **the human reinstalls the addon
   and reconnects the MCP server**.

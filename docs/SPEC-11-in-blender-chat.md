# SPEC-11 — In-Blender chat: talking to the agent through the MCP server (V1 collaboration surface)

_Status: V1 IMPLEMENTED (2026-06-19), pending live validation. Addon side:
`extension/chat.py` (the `inbound`/`outbound` queues + displayed log + `chat_poll`/
`chat_say`/`chat_history` handlers), registered in `extension/server.py`'s
`_TOOL_MODULES` and exempted from history/undo/status in `extension/state.py`; the
N-panel + Send operator + `_chat_drain_timer` + `bb_chat_input` prop in
`extension/ui.py` / `extension/__init__.py`. Server side: the `chat` verb
(`op=poll` long-poll in-process, `op=say`, `op=history`) in `server/verbs/chat.py`,
wired into `server/verbs/__init__.py`. Verb registers and survives the prune (16
verbs). Remaining: the user reinstalls the addon + reconnects MCP, then we run the
four success criteria live (the proof demo can't pass until then). Original spec
text below._

_PROPOSED (2026-06-19). V1 of the collaboration surface discussed in the anime-head
dogfory session. Deliberately minimal: this spec proves **one** thing — that you can hold a
continuous conversation with the agent from a panel inside Blender, routed entirely through the
existing MCP server, while the agent can still drive the geometry verbs in the same loop. The
phase/gate state machine, propose→accept review, shared pointing, and the two autonomy modes
("don't ask every edit" / "back in 30 minutes") are explicitly OUT of V1 and parked for a
follow-up spec. Build only the chat pipe; prove it; then layer._

## The problem

The collaboration is real but the surface is split. The human has Blender open; the agent is
driven from a separate terminal (a Ghostty shell). The two never share a window. Every
"collab" affordance we want — see the edit, accept it, say "this cheekbone", advance the phase —
founders on the fact that the conversation lives in one process and the artifact in another.

Underneath sits a protocol inversion that makes "just add a chat box" non-obvious:

**MCP is client-driven.** The data flow is strictly agent → server → Blender:

```
agent (LLM)  ──MCP/stdio──▶  server/main.py  ──TCP 8765──▶  extension (addon)  ──bpy──▶  Blender
   │ decides to call a tool          │ thin wrapper            │ runs on main thread             │
   └──────────────◀──────────────────┴───────────◀────────────┴── returns status block ─────────┘
```

The agent *initiates*; everything else *responds*. A message typed in Blender has no path back
to the agent — the agent is not a listening process, it only acts when it takes a turn. So
"chat with the agent through the MCP server" means making a human-typed message arrive at the
agent **as a tool result**, and the agent's reply travel back **as a tool call** — i.e. carrying
the conversation as ordinary tool I/O over the channel that already exists.

The open question this spec exists to answer: **is that loop actually viable, and does it feel
like talking to the agent — without touching the shell after boot?**

## The principle

Don't build new transport. The conversation is just **two more queues of addon state**, read and
written through **two more dispatch commands**, exactly like every other capability. The chat
pipe rides the socket + main-thread queue that already carry every `add`/`edit`/`feel` call.
There is precedent for the human→agent direction: `Save as Handle` (`extension/ui.py`) already
lets the human mint, from the viewport, the same handle the agent reads via `feel op=handle`.
Chat is the same move — human-side state the agent consumes through a verb.

This is plumbing for the collaboration surface, **not a geometry primitive** — so it does not
bend the "build only generic modelling primitives" rule; it's a different axis (how we talk),
deliberately kept off the mesh-tool surface.

## The surface (V1)

### New addon state + commands (`extension/chat.py`)

Two FIFO queues held in addon state, mutated only on Blender's main thread (same discipline as
the command queue):

- `inbound`  — messages the human typed, awaiting the agent.
- `outbound` — replies the agent sent, awaiting display.

Two dispatch commands (registered in `extension/server.py`'s `_TOOL_MODULES`):

- `chat.poll` → pops and returns the next `inbound` message, or an `{empty: true}` sentinel.
  **Returns immediately** — it must not block, because it runs on Blender's main thread and a
  block would freeze the UI.
- `chat.say` → pushes a reply onto `outbound`. Returns ack.

### New MCP verb (`server/` → `chat`)

One verb, matching house style (verb + `op=`):

- `chat op=poll` — **the long-poll lives here, in the MCP server process** (not the addon).
  It calls the addon's `chat.poll` on a short interval (~1 s) for up to a `window` seconds
  (default ~20 s, configurable, must stay < the MCP client's per-tool timeout), returning the
  instant a message appears, or a timeout sentinel. Blocking happens in the server process,
  which is free to wait; the addon handler stays instant.
- `chat op=say  text=<reply>` — forwards to the addon's `chat.say`.
- (optional) `chat op=history` — dump the transcript for debugging.

### Blender panel (`extension/ui.py`)

An N-panel (sidebar) tab: a scrollable message log, a single-line input, a **Send** button, and
a small status line ("Claude is working…" / "waiting"). Send enqueues to `inbound`. A
`bpy.app.timers` tick drains `outbound` into the log. No rich constructs in V1 — plain text both
ways.

## The loop (how the agent behaves)

Booted once from the shell ("enter Blender chat mode"), the agent sits in a poll-respond loop —
all ordinary tool calls inside one turn:

```
loop:
  msg = chat op=poll            # long-polls ~20s; returns a message or a timeout sentinel
  if timeout: continue          # tiny result; re-poll
  ... think / optionally call add|edit|feel|... to do what was asked ...
  chat op=say text=<reply>      # reply lands in the Blender panel
  goto loop
```

The conversation continuity is automatic: it is all one agent conversation, so earlier messages
are simply earlier in context.

## Success criteria (the V1 done-bar — gates, not vibes)

1. **Round-trip.** Type in the Blender panel → the agent's reply appears in the panel. The shell
   shows the loop running; the human never types there.
2. **Continuity.** A ≥5-message exchange retains context (the agent refers back to earlier turns).
3. **The proof demo.** From the Blender panel: *"add a 10 cm sphere and tell me its height."*
   The sphere appears in the viewport **and** the agent's reply (quoting the world-bbox height
   from the status block) appears in the panel — shell untouched after boot.
4. **Latency.** A reply begins appearing within a few seconds of Send.

If all four pass, the loop is viable and the rest of the collaboration surface can be layered on
this pipe.

## Non-goals (V2+ — a later spec)

- Phase/gate state machine (blockout → … → ready) and op-locking per phase.
- Propose → ghosted before/after → accept/reject; rewind-to-gate.
- Shared pointing as a first-class referent stream (partly seeded by `Save as Handle`).
- Autonomy modes: "don't ask every edit" (batch at the phase gate) and "back in 30 minutes"
  (full ladder, self-critique, variants, review queue — never self-accept).
- Token streaming, inline rich constructs, multi-user, persistence across a Blender restart.

## Open questions / risks

- **Turn liveness + context growth (the #1 risk).** The agent loops by re-polling; a long idle
  chat accumulates poll results in context, and an agentic turn may have practical call limits.
  Mitigations: a wide long-poll window (fewer polls), tiny timeout sentinels, a session-bounded
  loop the human can re-boot. Compaction / `ScheduleWakeup` re-entry are the path to spanning
  longer gaps — deferred past V1.
- **Long-poll window vs client tool timeout.** The `window` must stay below the MCP client's
  per-tool timeout; make it configurable and default conservative.
- **Boot honesty.** V1 still needs **one** shell command to launch the loop; only after that is
  the conversation in Blender. Eliminating that (a saved `/loop`, a routine) is V2.
- **Main-thread discipline.** `chat.poll`/`chat.say` must be instant; all waiting lives in the
  MCP server process.
- **Ordering.** V1 is single-threaded, strict request/response. Two messages sent while the
  agent works queue FIFO.

## Implementation steps

1. `extension/chat.py` — the two queues + `chat.poll`/`chat.say` handlers; register in
   `server.py` `_TOOL_MODULES`.
2. `extension/ui.py` — the N-panel (log + input + Send) and the drain timer.
3. `server/` — the `chat` verb (`op=poll` long-poll in-process, `op=say`, optional `op=history`);
   wire into `main.py`'s registry.
4. Boot path — a short instruction/command that drops the agent into the poll-respond loop.
5. Validate against the four success criteria.
6. Deploy per the standing workflow: edit `extension/` → rebuild the zip (`build_extension.sh`)
   → **the human reinstalls the addon and reconnects the MCP server** (every change).

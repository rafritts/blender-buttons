# SPEC-15 — External-mutation interlock: a dirty-world lock, not a warning

_Status: Implemented 2026-06-22. Net-new **safety** primitive. Makes THE ONE RULE
("ground truth is perishable") operational against the one mutator the server cannot
observe: the human (and autosaves / scripts) editing the scene between the agent's calls._

---

## The problem

The agent's whole method rests on **read-then-act**: `feel`/status hand back ground truth,
the agent derives from it, then mutates. That contract silently assumes the scene is *static
between calls*. It is not. The user can grab a vertex in the Blender UI, an autosave can fire,
a script can run — none of it routes through the server, so the agent never learns the scene
moved. Its last read becomes "a guess wearing a fact's clothes," and it builds on it.

There was machinery that *could* have caught this but didn't close the loop:
- `state._history` already logs every op with an id and a per-object geometry snapshot
  (`state._snapshots`, the `diff_since` checkpoints).
- `introspect.diff_since` already narrates moved/rotated/scaled/deformed/topology per object.

Nothing compared *live-now* against *the last server-known state* automatically, and nothing
stopped the agent from acting on a stale read.

## The design

A hard **interlock**, enforced at the client/socket boundary (`server.handle_client`), not a
warning:

1. **Baseline.** Every logged op records the scene's geometry hash as the *clean baseline*
   (`state.set_clean_baseline`, called from `state.log_operation`). This is the "edit hash."
2. **Detect.** Before each client command runs, re-hash the live scene
   (`state.detect_external_mutation`). A mismatch means *something the server didn't do*
   changed the world → **latch a lock** and record what changed (object + moved/rotated/
   scaled/deformed/topology, via the pure `state._diff_snapshots`).
3. **Block.** While locked, any tool **not** on a fail-closed allowlist returns a hard error
   (`state.lock_error`) naming the mutated objects and how to clear the lock. The op never
   runs.
4. **Stay grounded.** The allowlist (`server.LOCK_EXEMPT_TOOLS`) keeps **reads, selection,
   feel, render, and the acknowledge op** open — exactly the tools the agent needs to
   *re-ground* itself before it trusts anything. Selection mutates only the selection, never
   world geometry, so it is safe.
5. **Acknowledge.** `history op=acknowledge` (`state.acknowledge_mutation`) clears the lock
   and re-baselines to the live scene — the agent explicitly accepting current reality as the
   new ground truth. An honest no-op when nothing was locked.

### Why the socket boundary, not `execute_command`

The interlock guards real *client turns*. Headless test harnesses orchestrate the scene via
direct `bpy` + `execute_command` calls — they are the legitimate orchestrator and must not be
treated as "external mutators." Placing the check in `handle_client` (the only socket entry)
covers every real MCP-client call while leaving in-process test setup free.

### Fail-closed allowlist

The block is an allowlist, not a denylist: anything not explicitly named safe is blocked. A
new mutating tool added later is therefore locked by default until someone vets it — the safe
direction for a safety feature.

## What it deliberately does not do

- **No taste judgement.** It detects *that* geometry changed and *roughly how much*, not
  whether the change was good. Sensitivity matches `diff_since` (TRS always; deformation via
  the downsampled 150-vert/object sample, so a sub-sample edit can be missed — acceptable, as
  transforms and topology are always caught).
- **No auto-revert.** It refuses to build on a dirty world; it never undoes the user's change.
- **One latch per mutation.** Detection is idempotent while locked (it preserves the original
  culprit list); the first `acknowledge` re-grounds.

## Surface

- Verb: `history op=acknowledge` (alias `ack`).
- Error shape: `{"error": "…WORLD STATE IS DIRTY — ACTION BLOCKED…", "world_locked": true,
  "mutated": {since_op, since_label, added, removed, changed}}`.

## Tests

`tests/e2e_spec15_interlock.py` — 30 checks: baseline set on a logged op, clean scene stays
unlocked, a direct-bpy mutation latches + names the culprit, the allowlist (blocked vs
exempt), the error is actionable, detection is idempotent + a no-op before the first op, and
acknowledge clears + re-grounds (with an honest no-op on an already-clean world).

# MCP gaps

> **This file is a live worklist of CURRENT, OPEN gaps only.** No history lives here.
> Shipped, fixed, or retired gaps are **deleted, not archived** — use `git log -- gaps.md`
> / `git blame` to see anything past. No changelogs, no "what we shipped," no "considered
> and declined." When a gap is closed, **delete its entry**. G-numbers are **stable and
> never reused** — a missing number just means that gap was retired.

## North star

The agent's vision can **judge** but cannot **measure**; it reasons over outlines,
profiles, scalars, and named regions — never coordinate dumps. The server's job is to let
it stay in **intent-space** ("wrap the grip", "seat the bulb", "rest it on the desk") and
hand back **legible ground truth** instead of making it dead-reckon coordinates. Every gap
below is a place the agent was forced out of intent-space — into hand-trig, a self-managed
mode, or a number it couldn't trust. A gap is a general Blender primitive, never a
task-specific shortcut.

---

## G77 — effortless spatial verification: the remaining auto-surfaces 🧭 NORTH-STAR

**Shipped.** After a placement op (add primitive / nudge / place / move_to / rest_on / seat / snap /
rotate / scale), the status block now auto-flags any NEW penetration of the placed part into a
neighbour, unasked (`introspect.auto_proximity_note`) — so the agent verifies clearance by reading,
never by differencing bounds. Guidance + THE ONE RULE reinforce "read, don't compute."

**Still open — the other half of "effortless."**
- **Loss-of-contact.** The auto-surface flags new *penetrations* but not a part that was meant to
  rest on something and now *floats* (or a rest that was lost when a neighbour moved). A "floats Xmm
  above its nearest support" note would close the symmetric case — but it's noisier (many parts float
  by design), so it needs a "was-resting / should-rest" signal to fire only when it matters.
- **Staleness signal.** A read could echo how many calls ago an object was last mutated, so the agent
  knows when its *remembered* bounds have gone stale (a value derived 50 calls ago is a guess wearing
  a fact's clothes). Cheap via the op-log; deferred — lower signal than the collision surface.


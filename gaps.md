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

## G203 — `file op=import` is a stranger to its own interlock

`file op=import` mutates the world (adds objects) but does not stamp that mutation into
the SPEC-15 clean baseline the way every other mutating verb does. Result: the very next
mutating op trips the external-mutation lock on the object the server itself just
imported — "added: rung1_recovered" reported as if a human or script had done it. In an
import-heavy session (lining up 10 OBJ exports) the lock fired on effectively every
import→place pair, costing an `history op=acknowledge` round-trip each time and training
the agent to reflex-acknowledge — which dulls the one alarm that must stay sharp (it
ALSO fired correctly mid-session when the human really did move the character; that
catch is the feature working). The general primitive: any mutation routed through the
bridge is FIRST-PARTY — every world-mutating verb, `file` included, must update the
baseline it will later be diffed against. An interlock that cries wolf on the server's
own actions erodes exactly the trust it exists to protect.

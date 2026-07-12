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

## G226 — Collection-instancing scatter: per-point variety is invisible until you know the magic input

**Verb:** `modifier op=add_asset asset="Scatter on Surface"` (and any GN instancer) fed a multi-prototype collection.

**Friction (blind donut run, 2026-07-11):** Scattering a 5-color sprinkle collection stacks **all five prototypes on every point** until the non-obvious `Pick Instance` input is flipped — the agent only found it by reading the input dump and guessing. The existing density-floor warning (1/m² floors to 0 emits on a 0.009 m² icing) fired and was genuinely helpful; instance-semantics gets no equivalent teaching.

**Why it's a gap:** the modifier's effective behavior (N overlapping copies per point) is visually wrong but numerically plausible; nothing on the surface says "collection sources need Pick Instance for one-random-per-point." Same class as the density warning the server already ships — the input dump knows the source is a collection and could say so.

**Fix direction:** when a GN instancer's source input is a collection and `Pick Instance` is off, attach the same style of advisory the density floor gets ("all K prototypes will stack per point; Pick Instance=True draws one at random").

## G227 — `validate` can't bless intended contact: self_intersection has no expect path

**Verb:** `validate` / `validate op=expect`.

**Friction (blind donut run, 2026-07-11):** Realized scatter instances seated *into* the icing (correct, intended nesting) tripped 2678 `self_intersection` findings. `expect` has declaration paths for open boundaries etc., but none for self-intersection, so a legitimately-overlapping assembly can't be declared and the floor stays noisy. The agent's workaround (un-realize the instances) happened to be right for other reasons, but the check drove it, not intent.

**Why it's a gap:** intended overlap is a normal end-state (parts pressed into parts, scattered instances bedded into a substrate). A verification floor that can't record "this contact is by design" forces either noise-blindness or geometry contortions — both exits from intent-space.

**Fix direction:** give `validate op=expect` a `check=self_intersection` declaration scoped like the others (object/pair/region + optional depth bound), mirroring how the icing↔donut contact is already declared and quieted.

## G228 — The teaching layer has a single point of failure: agents without resource readers never see guidance

**Verb:** the `guidance://llms` MCP resource (and `guidance://techniques/*`).

**Friction (blind donut run, 2026-07-11):** the modeling agent's harness exposed the blender-buttons *tools* but no MCP resource-read tool, so `guidance://llms` was unreachable; the whole run went in on schemas + training alone. It succeeded anyway — but the server's one deliberate teaching channel silently didn't exist for that client.

**Why it's a gap:** resources are optional in MCP clients; tools are the only surface every agent reliably gets. A guidance layer that only ships over resources reaches some agents and silently skips others — worse than a uniform surface either way.

**Fix direction:** expose the same guidance text through a read-only tool op (SENSE-class, substrate: it mutates nothing) — e.g. a `guide` op on an existing verb — with the resource kept as the secondary route. Verify a resource-less client can pull it.

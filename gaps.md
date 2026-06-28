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

### G185 — address individual components by label, not just by coordinate band

Today the only vertex/edge/face selector is a **spatial band** (`select between` on
X/Y/Z, intersect to combine). That works on big axis-aligned features but breaks down the
moment a feature is small or its topology is irregular — building the thumb base, the band
repeatedly fell *between* loop positions (selected 0), caught a shared finger-wall vert it
didn't want, or returned 2 verts when 4 were expected, costing a long binary-search of
coordinate slabs to discover where the geometry actually sat. The agent can *judge* "I want
those two verts on the thumb-web rim" but has no way to *say* it.

The missing primitive: when the working set is already small (a tight band, the current
selection, a `feel`-named region), **enumerate the components in it with stable labels**
(e.g. `v0..vN` with their positions + valence) and let the agent **select by those labels**
("select v3, v7"). That keeps it in intent-space — point at the components it can already
see — instead of dead-reckoning a coordinate window narrow enough to isolate them. Pairs
with the named-handle machinery (`feel as_handle`) but for raw mesh components, not just
ray-hit points. General primitive: "list what's here, let me pick by name."

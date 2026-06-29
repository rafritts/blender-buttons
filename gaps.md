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

### G188 — Poliigon addon is installed, but only Poly Haven has a search→download→apply path

`material op=search_textures` / `op=search_hdris` query Poly Haven, and `op=textured` then
fetches and wires the chosen id in one call — a full *find-by-intent → download → apply*
pipeline for one library. For **Poliigon there is no equivalent**, even though the Poliigon
addon is installed in the build. The guidance tells the agent to "download via its own addon,
then apply with `material op=pbr folder=`" — i.e. drop out of the server entirely, drive the
Poliigon addon by hand in Blender's UI, and only rejoin once the maps are sitting on disk.
`op=pbr folder=` is the *apply* half only; the *find* and *fetch* halves are a manual,
out-of-band detour.

The cost is intent-space: a recipe that says "marble PBR from Poliigon / ceramic / icing /
pottery" (donut2.md does, four times) can't be satisfied by naming the look. The agent either
asks the human to hand-download four sets, or silently substitutes Poly Haven / procedural and
quietly changes what was asked for. The library the artist actually licensed is the one the
server can't reach by name.

The missing primitive: a Poliigon search/fetch path that mirrors the Poly Haven one — e.g.
`material op=search_textures source=poliigon query="marble"` returning asset ids, and
`op=textured source=poliigon asset_id=...` driving the installed addon to download + apply
(falling back to the existing `folder=` apply once local). Same find→fetch→apply shape, just
pointed at the second library that's already authenticated in the build. Until then, "from
Poliigon" in a brief is an instruction the server can read but not honor.

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

### G186 — transform about each element's OWN origin (individual-origins pivot)

`transform op=scale_verts` / `op=rotate` pivot about the whole selection's centre (or the
cursor). But a routine artist instruction — "select the four inset finger faces, **S-Y to
even them out** so each becomes square" — means scale *each face about its own centre*
(Blender's Individual Origins pivot). With only a shared-centre pivot, a multi-face even-out
drifts the faces toward the common centre instead of squaring each in place.

Building hand2.md this bit: the four inset faces happened to share z-centre 0, so a single
`scale_verts sz=` was *coincidentally* equivalent to a per-face S-Y. On geometry where the
faces don't share a centre on the scaled axis, the only workaround is N separate one-face
calls — exactly the per-element loop the verb should absorb.

The missing primitive: a `pivot=individual` (per-connected-island, or per-face) option on
scale_verts / scale_rings / rotate, so "even out / fan / shrink these N features each about
itself" is one intent-call. Pairs with select op=list/by_index (G185) — list the features,
then transform them each in place.

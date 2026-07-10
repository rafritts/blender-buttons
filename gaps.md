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

_G203–G216 (the bead-of-icing donut-dogfood autopsy) were fixed and verified against
headless scenes — see `git log -- gaps.md` and `tests/e2e_g203_g216_deform.py`,
`e2e_g204_g207_scatter.py`, `e2e_g209_g212_handles.py`. Live re-verify on the motivating
donut scene (2026-07-10): G208/G212/G213/G215 hold up._

_G217 (bud's failure mode is "success") closed by SPEC-21 §4: `bud` and the macro verbs
are DELETED; the missing primitive was native Bridge Edge Loops (`edit op=bridge`, long
shipped) and the drip is a technique (`guidance://techniques/drip`). G218 (declared
intents are scene facts) closed in SPEC-21 phase 5: the registry already persisted into
the .blend (G125) but an addon reinstall reset the module without a scene load — grounding
is now lazy, so the first registry access after a reload re-reads `scene["bb_intents"]`
and the tripwires re-arm. G219–G221 (the VRoid semantic-selection autopsy) shipped in
SPEC-21 phase 1. Live re-verify of the whole SPEC-21 surface on the VRoid scene pending
the next dogfood session._

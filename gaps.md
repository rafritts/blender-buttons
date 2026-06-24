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

## G130 — there is no path to a volumetric light shaft (god-ray); the verbs expose no world/volume scatter and the addon bridge is bpy.ops-only

**DEFERRED 2026-06-24 → `docs/SPEC-17-lighting.md`.** Not fixed in the gaps pass: lighting reads
as a whole under-built domain rather than one gap, so the god-ray flag is parked in the SPEC-17
stub to be designed holistically later. Recommended MVP when picked up: `scene op=world
volume=density,color` (medium + volumetric enable) so a normal spot reads as a beam; `light …
beam=true` is sugar to follow. Kept open here as the live pointer; the design seed lives in SPEC-17.

The brief explicitly asked for a visible morning "beam through the scene." A real volumetric shaft
needs EEVEE/Cycles volumetrics enabled plus a scattering medium (a world Volume Scatter node or a
volume domain) — none of which any verb exposes: `scene world` sets a flat colour/HDRI, `material`
has emission but no volume scatter, `render` has no volumetric toggle, and `addon op=run` only
dispatches registered operators, not node/property setup. The beam had to be faked with a tight
warm spot pooling light on the hero — a legible approximation, but not the literal shaft. Candidate
fix: a `scene world volume=` (density/colour) and/or `add type=volume` + a `light … beam=true`
helper that turns on volumetrics and sizes a cone, so atmosphere/god-rays/fog are reachable without
hand-editing nodes.

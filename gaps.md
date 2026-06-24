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

---

## G135 — clip/penetration depth is unreliable on thin or instanced meshes; the agent can't trust the number

`feel op=contacts` and the `validate` clipping floor report penetration *depths* that are physically
impossible — 66–185mm reported for cm-scale parts (a 5mm sprinkle "penetrating" the donut 87mm, a
handle "penetrating" the mug 66mm, a coffee disc vs mug 8mm that can't exceed the 4mm wall). Any thin
shell (icing skirt, swept-tube handle, hollow vessel) or scatter instance triggers it. The depth is
the agent's honesty check — it's what `validate op=expect max_depth=` keys off to tell a *real*
poke-through from a surface contact — so when it's garbage the agent is forced to bless clips at "any
depth" blind, losing the tripwire. Candidate fix: compute signed penetration from a closed-surface
test (or clamp against the pair's bbox overlap) so the reported depth is bounded by reality, and
special-case open/thin shells instead of returning a raw BVH ray distance.

## G136 — `transform op=scatter` seats instances by their origin, so they sink into the surface; no normal-offset

Scatter places each copy's *object origin* (the prototype's mesh centroid) on the surface, so a flat
part — a sprinkle, a pebble, a leaf — buries half its thickness below the surface. There is no way to
seat it *proud*. The workaround is to lift the whole scatter group along world-Z afterward, which is
wrong on any curved/sloped surface: it lifts shoulder instances off while barely freeing the ones at
the dome top. (On the donut this left the sprinkles ~60% buried until hand-lifted, and even then the
lift is uneven.) Candidate fix: a `scatter offset=` measured along the *surface normal* (proud-by-N),
or a per-instance "drop lowest point to the surface" seat so origin placement doesn't dictate depth.

## G137 — `scatter` has no minimum-spacing/Poisson control, so dense scatters z-fight

Normal-aligned flat instances that land near each other are coplanar, so at any real density they
z-fight (55 sprinkles → 44 coplanar z-fights; even 45 → 1). z-fight is a never-OK defect, so the only
recourse is to lower the count below what "reads as scattered" and hand-prune the offenders — a hard
ceiling on believable dense scatter (sprinkles, gravel, seeds, crumbs). Candidate fix: a
`min_distance=`/poisson-disk option, and/or an auto random-tilt so overlapping instances cross at an
angle (a declarable *clip*) instead of fighting as coplanar faces.

## G138 — `material` ops reject the comma-list multi-target that every other verb accepts

`material op=pbr target="Mug,Handle"` fails with "no object or collection by that name", yet
`transform`, `feel`, `select`, `object` all take `targets='a,b,c'`. Shading two parts with one
material (a mug and its handle) then needs two calls and produces two duplicate material datablocks.
Candidate fix: parse comma-lists and group names in `material target=` like the rest of the surface.

## G139 — heavy/batched ops intermittently report "No Blender instance is reachable" though the instance is alive

4K PBR texture loads, HDRI (re)loads, and batches of independent calls regularly return "No Blender
instance is reachable"; `connect op=list` then shows the instance alive and a re-attach + retry
succeeds. Batching makes it worse — parallel calls reach Blender over separate sockets and race. Over
a long build this dropped the connection ~a dozen times, each costing a re-attach and retry, and it
makes batching independent ops (the documented speedup) unsafe for anything heavy. Candidate fix: a
longer per-op timeout for load-bound ops, server-side serialization/queueing of concurrent requests,
and transparent auto-retry so a slow texture read doesn't masquerade as a dead instance.

## G140 — group transforms emit a false "no-op: byte-identical" warning

`transform op=nudge targets=<group>` (and likely other group transforms) warns "no-op: this op
reported success but the geometry is byte-identical … nothing moved" even when the group demonstrably
moved (the per-object world bounds change). The no-op detector inspects the *active* object — which
for a group op is not one of the moved members — so every successful group move looks like a failure.
The agent has to cross-check bounds to know the warning is spurious. Candidate fix: run the no-op
check against the objects actually acted on (the group members), not the viewport-active object.

## G141 — no real-world-scale awareness for PBR/textured materials; texture scale is a blind guess

`material op=pbr`/`textured` take a unitless `scale` with no surfaced physical size, so the agent
cannot map a texture 1:1 onto a real-world-sized object. The *same* `scale=1` that gives believable
grain on a 2m table is far too coarse on a 9cm donut (reads as a smooth blank patch) — and the agent,
forbidden from reading its own render, can only discover this through render→blind-judge rounds (it
took several here to land wood grain and dough crumb at a plausible size). This is a number the agent
is forced to dead-reckon. Candidate fix: surface the texture set's intended real-world tile size (it's
in the Poliigon/MTLX metadata) and/or accept `physical_size=`, so box-projection scale is *derived*
from the part's measured dims instead of guessed.

# SPEC-17 — Lighting (placeholder)

_Status: **Stub / flag-planted 2026-06-24.** Not yet specced. Lighting is likely a whole
domain to address, not a single gap — this file reserves the number and captures the trigger
so the deep pass has a starting point._

## Why this exists

The volumetric god-ray (gaps.md **G130**) was deferred out of the gaps-fixing pass because it
isn't really one gap — it's the first symptom of lighting being under-built. Rather than bolt a
god-ray onto the side, we flag lighting as its own spec to design holistically later.

## What already exists (so the deep pass doesn't re-derive it)

`extension/lighting.py` already covers: `add_light` (POINT/SUN/SPOT/AREA), `aim_at`,
`rig_around` (azimuth/elevation/distance), `set_world_background` (HDRI / colour / strength),
`set_camera_dof`, `modify_light`, `set_color_management` (view transform / look). Surfaced via
the `scene` / `view` / `render` verbs.

## The god-ray flag (G130, deferred here)

A visible light shaft needs (a) volumetrics enabled on the engine and (b) a scattering medium —
a world Volume Scatter node or a volume domain. No verb exposes either today. Recommended MVP
when this is picked up: `scene op=world volume=density,color` (medium + volumetric enable) so a
normal spot reads as a beam; a `light … beam=true` cone helper is sugar to follow. Build the
world-volume so it survives a future general node-graph surface.

## To flesh out later (rough seed list — not a design)

- Volumetrics / atmosphere / fog (the G130 trigger).
- A `check_lighting` perception/validation analogue to `check_framing` / `check_focus`
  (exposure, blown highlights, subject-in-shadow, key/fill ratio).
- Light linking / per-object light influence.
- Area-light shaping, IES profiles, exposure / EV controls.
- Render-engine awareness (EEVEE vs Cycles differences in what's even possible).

> Deliberately shallow. Do the real design in a later pass.

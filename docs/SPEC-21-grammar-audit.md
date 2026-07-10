# SPEC-21 §3 — verb-grammar audit

**Deliverable of SPEC-21 §3:** one pass over every verb, checking the family frame —
WHAT (member as a parameter), WHERE (the shared scope block: `target=`, `at=`/`handle=`,
`radius=`, the live selection), HOW MUCH (`amount` in meters + a falloff) — and naming
every drift. Fixed drifts are deleted from this file when they ship (gaps.md
discipline); the **accepted** section records deliberate non-conformance with its
rationale, so the next audit doesn't re-litigate it.

Audited 2026-07-10 against the phase-1 tree.

## Fixed in phase 1

- **`sculpt brush=gravity` took `strength`/`pin` while its siblings took `amount`**
  (the spec's canonical example). `amount` is now the family's one magnitude word,
  with per-member defaults (strength-brushes 1.0, gravity 0.02 m); `strength`
  survives as gravity's legacy alias.
- **Select return-voice drift** — object-mode `by_axis` answered "ok
  (threshold_world=…)" with no count, edit-mode `between` answered "selected=N",
  `grow` answered neither. Every mutating select now answers in one voice: count +
  the G220 narration line (patches, extent, position, island identity, open-rim
  flag), attached centrally in the dispatch. `grow`/`shrink`/`flood` report
  before → after and say why on Δ=0 (G219).
- **`select op=random` was the wrong shape for "click a face"** — it thins by a
  fraction of the mesh. `select op=pick` (G221) is the one-arbitrary-element
  primitive; `random` stays for its real job (sparse patterns from a uniform set).

## Accepted non-conformance (deliberate, with rationale)

- **`grab`'s directional words (`out/inward/up/down/left/right/forward/back`)** are
  not drift — they ARE the shared WHERE/direction frame, identical across `extrude`,
  `move_verts`, `proportional_move`, `slide`, and `nudge`. A single `amount` +
  direction-enum would *add* a frame, not remove one.
- **`width` on bevel/solidify, `thickness` on inset/solidify-modifier** — native
  Blender parameter names (vocabulary law §2 outranks frame purity: the tutorial
  bridge wins).
- **`factor` means three things** (`transform op=scale` multiplier; `edit op=bevel`
  fraction-of-dim legacy; `select op=by_axis` 0..1 axis fraction). All three are
  dimensionless fractions and each is documented per-op; renaming breaks verified
  recipes for marginal gain. Revisit only if a live session actually confuses them.
- **`add`'s per-primitive dimension tail** (`major_radius`, `subdivisions`, …) —
  the WHAT discriminator (`type=`) carries the frame; a torus genuinely needs two
  radii. This is the small-tail case §3 explicitly allows.

## Deferred (real drift, needs its own change)

- **`modifier op=add/modify` has both `strength` and `factor`** as "generic
  strength" — they shadow native modifier property names unevenly. The clean fix
  follows the macro disposition (phase 5), when the modifier surface is next
  touched; fold into a gap entry if it bites live before then.

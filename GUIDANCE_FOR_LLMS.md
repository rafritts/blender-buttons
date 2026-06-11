# Guidance for LLMs driving blender-buttons

Field notes from real builds (chair, treasure chest, sword-in-the-stone, pocket watch).
Read this before modeling. It is the distilled version of every mistake already made.

## The one rule that explains everything else

**You cannot reason reliably about coordinates in a scene you didn't just author.**
Your coordinate math works only in the narrow regime where the pocket watch lived:
single object, centered at origin, axis-aligned, every number self-authored moments
ago, trig outsourced to a script. Outside that regime — compound rotations, curved
surfaces, scenes edited over hours — dead-reckoning fails silently (a fob bar
computed from a tangent heading landed 14cm adrift; a bow's resting tilt was
guessed and eyeballed). Therefore:

- Use the placement DSL (`on`, `between`, `left_of`, `snap_to`, `gap`) wherever its
  vocabulary covers the relationship. Absolute `at` is the ripcord, not the default.
- When you must compute positions (radial layouts have no relational vocabulary yet —
  see gaps P1/P2), do the trig in a script (`python3 -c ...`), never in your head,
  and generate all positions in one pass.
- Prefer tools that treat **the mesh itself as the coordinate system**
  (`select_ring`, `get_rings`, `band_around`, `scatter_on_surface`, `snap_to`)
  over remembered numbers.

## Vision judges; it cannot measure

Screenshots answer "is this what I was going for?" — proportion, material read,
composition. They **cannot** answer "is this 1mm proud or 1mm sunk", "is the chain
actually connected", "what is causing this artifact". Every correctness question
this maxim was learned from looked *misleading* in a screenshot:

- A z-fight rendered as brown triangular mottling that perfectly imitated a
  normals/material bug. Three diagnostic Cycles renders to isolate.
- A 19mm gap between chain and fob bar read as "slightly cluttered".

Get correctness from numbers (status-block bounds, `distance_between`,
`gap_between`, `is_aligned`), and screenshots for taste only. The deterministic
inspection family (gaps P4–P12) exists to close this hole; use those tools as they land.

## The status block is your instrument panel

Every mutating call returns exact world bounds. **Trust and use them.** A whole
case stack can be built as arithmetic on previous bounds without a single
screenshot — and on the pocket watch, zero placement corrections were needed in
~45 parts. Maintain a Z stack-up table as you go (caseback 0→0.035, band
0.035→0.135, ...). `get_object_info` is almost never needed; the answer was in the
last status block.

**But watch for exact equality.** Two numbers that *match* in your stack-up table
are a bug, not a coincidence: coplanar faces from different objects z-fight.

## Traps (each of these has burned a session)

1. **Coplanar caps z-fight.** Stacked cylinders/boxes share exact face planes
   (solid case top at z=0.135 + dial top at z=0.135). Symptom: triangular mottling
   that looks like a shading bug. Fix: offset the covering part ~1mm. Check your
   stack-up table for duplicate values before rendering.
2. **`rotate_object` pivots on each object's own origin.** No pivot override (gap
   P2). Anything that pivots around a shared point (clock hands, hinges) must be
   *created pre-rotated* via `rot_z` + a center computed along the pointing
   direction.
3. **Rotating a GROUP disassembles it** — each part spins around its own origin.
   `join_objects` first, then rotate.
4. **Euler order is XYZ (X applied first, then Y, then Z).** A torus stood up with
   `rot_x=72` then oriented with `rot_z=φ` keeps its ring plane containing the
   direction at angle φ. Derive once, verify with one screenshot, then batch.
5. **`orbit_viewport(auto_frame=True)` frames the SELECTION**, and every `add_*`
   leaves its object selected — so right after an add it frames a 2cm torus, not
   your model. Call `frame_scene()` first (it excludes lights/cameras).
6. **`select_by_axis` requires Edit Mode and has no `target` param** (unlike
   `bevel`/`taper_end` which auto-enter). `set_mode("EDIT")` first.
7. **Smooth-shaded flat NGON caps band/mottle** in matcap and renders. Flat discs
   (dials, plates) want `shade_flat`; only curved surfaces want `shade_smooth`.
8. **`set_viewport_angle(CAMERA)` is a trap for screenshots** — narrow telephoto
   FOV, camera-border crop, sometimes stale/black in RENDERED. Use
   `orbit_viewport` + `get_viewport_screenshot` for checks;
   verify *final* framing with a small `render_to_file`.
9. **`BLENDER_EEVEE_NEXT` is not a valid engine id in this build** — use
   `BLENDER_EEVEE` (or `CYCLES`).
10. **Live-session `undo` has history; still checkpoint.** `save_design` after
    every milestone (it's one call). Reopening a checkpoint beats forensic undo.

## What reliably works (recipes)

- **Build order for hero props:** case/body primitives (high vertex counts: 96–128
  for close-ups) → bevels → detail parts → group by material → materials → floor +
  HDRI → `set_render_quality(raytracing=True)` for EEVEE preview → low-res Cycles
  test (1280×720, 64spp) → fix → final (1920×1080, 256spp).
- **Groups as material targets.** `group()` parts by material family, then one
  `set_material(group)` each. Five calls materialized the whole watch.
- **Sink details into their parent.** Markers/trim sit 1–2mm *into* the surface
  beneath (never exactly flush — see trap #1, never floating above).
- **Glass/crystal:** dome = sphere → `resize` height → delete bottom half
  (`select_by_axis` LESS + `delete_geometry`). Material: `alpha` 0.04–0.06,
  roughness ~0.02, ior 1.5. Higher alpha (0.08+) hazes everything beneath —
  dark dial print read gray until alpha dropped.
- **Color matching: always `hex=`,** never raw `base_color` from a picked color —
  the sRGB→linear conversion is the difference between gold and beige.
- **Metals:** metallic 1.0, roughness 0.15–0.25. In EEVEE they look like plastic
  until `set_render_quality(raytracing=True)`.
- **Chains:** alternate flat / standing-tilted (~72°) torus links along a scripted
  arc, spacing ≈ 0.65 × link outer diameter so links interpenetrate —
  interpenetration *is* the connection. Align standing links to the path tangent
  (`rot_z = 90 − heading`).
- **Time on a watch/clock:** 10:09 with seconds at ~37 — the classic catalog pose;
  hour hand angle = (h + m/60) × 30°, clockwise from +Y; box hands created
  pre-rotated with center offset along the pointing direction.
- **Isolation debugging:** no hide tool exists — `nudge` the suspect part up 1m,
  re-render, nudge back. Crude, decisive.
- **Test-render ladder:** never iterate at final quality. 64spp/720p answers every
  correctness question; 256spp/1080p+ is only for the money shot. Renders are
  synchronous and freeze the viewport — keep `timeout` generous.

## Scene dressing

- `search_textures` / `search_hdris` → Poly Haven ids; `set_textured_material`
  needs no UVs (box projection). `dark_wood` + `brown_photostudio_02` is a proven
  warm product-shot combo.
- One soft AREA key light angled across the subject adds sparkle the HDRI alone
  doesn't give. Aim with `target=`.
- DOF: `set_camera_dof(focus_object=...)`; f/4 keeps a tabletop scene readable,
  f/2.8 for macro drama.
- AgX (default) for PBR realism; `set_color_management(view_transform="Standard")`
  for toon/NPR or saturated emission.

## Process expectations

- **Screenshot frequently while blocking out** (the user watches live), but keep
  them 960×540 — they are the single biggest context cost of a session.
- **Checkpoint with `save_design`** at every milestone; final scene + renders go
  to `~/blender-designs/` and `~/renders/`.
- **Log every gap you hit in `gaps.md`** — framed as a *general* Blender
  primitive (radial array, pivot override), never a domain-specific helper
  ("bezel tool"). Commit and push gap logs without being asked.
- Effort/complexity/risk is what "effort" means here — never wall-clock time.

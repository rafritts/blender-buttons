# Donut — a Claude-native build recipe for blender-buttons

A verified transcript-recipe (every number ran). Written in the server's own verbs, so
you execute it with little interpretation. The "donut tutorial" outcome: a pink-glazed,
sprinkled, slightly-organic donut on a tabletop, lit and rendered.

---

## Contract (read once — it disambiguates every step below)

- **Units:** meters. Target donut ≈ 8.6 cm outer Ø, 3.4 cm hole, 2.1 cm tall.
- **Frame:** donut lies in the XY plane, hole on the **Z** axis, **top = +Z**, centered at origin.
- **Provenance:** every number derives from the torus you author — `R = major 0.03`,
  `r = minor 0.013`. Outer radius `R+r = 0.043`; tube top `z = +0.0105`, equator `z = 0`.
  Don't invent spatial values; read the status-block bbox / `feel`.
- **Cadence:** one *dependent* edit op per message; the status block's bbox is ground truth;
  `verify` each phase with `feel` before building on it.
- **Floor:** `validate` auto-runs after every op. Intended overlaps (glaze on dough,
  sprinkles on glaze) must be *declared* with `validate op=expect` — there is no "ignore".
- **Scene hygiene:** a fresh Blender keeps a default **Cube / Light / Camera**. Delete the
  Cube; you may keep the Light as free fill; make *your* camera the active one before render.

---

## Phase 1 — Dough body

**1 · Torus.**
`add type=torus name=Donut major_radius=0.03 minor_radius=0.013 major_segments=32 minor_segments=16`
→ 512-vert torus. *Verify:* `feel topology method=genus` ⇒ **closed genus-1 (χ=0)** — the hole
is the donut's defining feature; if you ever see genus-0 you sealed it.

**2 · Squash slightly** (donuts aren't a perfect torus).
`transform op=resize targets=Donut height=0.021` (≈ ×0.81), then bake it:
`transform op=apply targets=Donut scale=true`. ⚠ `apply` reports a "no-op byte-identical" —
that's correct: applying scale leaves *world* geometry unchanged, it only zeroes the object
scale so later modifiers (incl. the scatter modifier) behave.

**3 · Smooth dough.**
`modifier op=add target=Donut type=SUBSURF levels=2 render_levels=2`, then
`edit op=smooth_edges target=Donut angle_limit=60`.

**4 · Organic lumps** (along normals, softened by subsurf).
`select op=all target=Donut action=SELECT` → `edit op=noise_displace target=Donut amount=0.0012
feature_size=0.35 detail=2 direction=NORMAL`. *Provenance:* amount ≈ 9 % of the tube radius
(0.013) — visible but not blobby. *Verify:* still 1 shell, still genus-1.

---

## Phase 2 — Icing (the server does the hard part: `clad`)

**5 · Pick the iced region.**
`select op=component_mode target=Donut mode=FACE` →
`select op=by_axis target=Donut axis=Z factor=0.5 comparison=GREATER` (the upper half, `z>0`).

**6 · Mint the shell.**
`buttons-shell-macro op=clad name=Donut region=selection clearance=0.0008 thickness=0.003 new_name=Icing`.
This is the icing in one verb — an offset shell hugging the selected dome.
⚠ Two things `clad` does for you: it **auto-stacks SUBSURF+SOLIDIFY** on the new object, and the
editable **cage is an open shell with 2 rims** (outer ≈ 27 cm + inner ≈ 11 cm). Those rims are
how you drip.

**7 · Drape the outer rim.**
`select op=boundary target=Icing` (both rims, 64 v) →
`select op=by_radius target=Icing action=INTERSECT shape=CYLINDER radius_inner=0.025 radius_outer=0.06`
(keeps the **outer** rim, 32 v) → `transform op=move_verts target=Icing z=-0.004` (drape it down
past the equator so it hangs over the edge).

**8 · Make the drip edge organic.** With the rim still selected:
`edit op=noise_displace target=Icing amount=0.003 feature_size=0.2 detail=2 direction=Z`
→ a wavy, dribbling rim.

**9 · Declare the contact + smooth.** The drips now rest on the dough:
`validate op=expect a=Icing b=Donut max_depth=2 reason="glaze rests/melts onto the dough; shallow drip contact intended"`
then `edit op=smooth_edges target=Icing angle_limit=60`. (The `max_depth=2` envelope still flags a
*deep* poke-through.)

---

## Phase 3 — Sprinkles (the NATIVE "Scatter on Surface" GN modifier; SPEC-20)

Blender 5.0 ships **"Scatter on Surface"** as a bundled Geometry-Nodes Essentials modifier —
a full superset of the old bespoke `scatter` verb (Density/Amount, Poisson-Disk min-distance,
distribution mask, **Collection instance source**, Align-Rotation/Alignment-Axis/Surface-Offset,
Randomize Rotation/Scale). Drive it with **`modifier op=add_asset asset="Scatter on Surface"`**.
It emits **instances on points**, not separate objects (so `feel`/`info` see ONE modified Icing,
not `Spr_0000…`); `modifier op=apply` realizes them into editable geometry when you need it.

**10 · One prototype.**
`add type=cylinder name=Sprinkle radius=0.0011 height=0.006 segments=6` (≈ 1×6 mm; length along Z).
You don't pre-rotate for the native scatter — its **Alignment Axis** input picks which local axis
aligns to the surface normal, and **Align Rotation** lays the rest down (set them in step 12).

**11 · Four colors → one Collection.** `material op=set target=Sprinkle hex=#e23b3b roughness=0.35
material_name=Sprinkle_red`, then `object op=duplicate name=Sprinkle new_name=Sprinkle_y` +
`material op=set target=Sprinkle_y hex=#f2c33d material_name=Sprinkle_yellow`; repeat for `_b #3d7bf2`
and `_w #f0f0f0`. Group the four into one collection the modifier will instance from:
`object op=group targets=Sprinkle,Sprinkle_y,Sprinkle_b,Sprinkle_w name=Sprinkles`. Per-prototype
materials in the collection = the multi-color sprinkles (the modifier picks among the members).

**12 · Scatter onto the glaze (native modifier).**
`modifier op=add_asset asset="Scatter on Surface" host=Icing collection=Sprinkles
inputs={"Amount": 120, "Seed": 3, "Align Rotation": true, "Surface Offset": 0.0,
"Randomize Scale": 0.35}` — then read back the result's `inputs:` list (the exact socket names
come from the live node group) and set **Alignment Axis** / **Poisson Disk** + min-distance /
**Density Mask** as needed. The base mesh stays the Icing; the sprinkles are instances on it.
Bake to real geometry only if a later step must edit individual sprinkles: `modifier op=apply
target=Icing` (Realize Instances).

---

## Phase 4 — Materials

- `material op=set target=Donut hex=#9c6233 roughness=0.75 material_name=Dough`
- `material op=set target=Icing hex=#f49ac1 roughness=0.3 material_name=Glaze`
- Sprinkle colors are already on the prototypes (step 11).

---

## Phase 5 — Stage, light, shoot

**13 · Retire the prototypes — don't delete them.** The Scatter-on-Surface modifier instances the
**Sprinkles collection**, so its 4 members must stay (deleting them empties the scatter). But they
still sit at the origin and would render there (and overlap). Move them out of frame below the floor:
`transform op=nudge targets=Sprinkle,Sprinkle_y,Sprinkle_b,Sprinkle_w down=0.3`, then nudge three of
them sideways (`right=0.06 / 0.12 / 0.18`) so no two are coplanar. Now they're alive, hidden, silent.

**14 · Floor.** `add type=floor size=0.5` → `transform op=nudge targets=floor down=0.0104` (seat the
donut's underside `z=-0.0104` on it) → `material op=set target=floor hex=#e7ddcf roughness=0.9`.

**15 · Light + camera.**
`add type=light name=Key subtype=AREA energy=25 size=0.35 target=Donut` and
`add type=camera name=Cam target=Donut lens=85`.
Rig both relationally: `view op=rig rig=Cam subject=Donut azimuth=55 elevation=38 fit=true` and
`view op=rig rig=Key subject=Donut azimuth=120 elevation=55 distance=0.4`.

**16 · Tune by reads, not by trial renders.**
`view op=check_framing targets=Donut,Icing camera=Cam` (want it filling ~½–¾ of frame) and
`view op=check_exposure resolve_for=Key` — it prints the energy for ~0 stops; set it
(`object op=light name=Key energy=14`). **Make Cam active:** `view op=active_camera camera=Cam`
(a fresh scene's default camera will otherwise win).

**17 · Render.** `render op=image filepath=donut_hero resolution_x=1400 resolution_y=1050 samples=96`.
The image is for the human — hand them the path; verify *correctness* from the ground-truth reads
above (genus-1 body, declared contacts, per-instance materials), not by reading the render back.

---

## Gotcha index (why this recipe is shorter than your first attempt would be)

1. `clad region=selection` = instant icing, but it **auto-adds SUBSURF+SOLIDIFY** and leaves a
   **2-rim open cage** — reach for the rims with `select op=boundary`, not a coordinate guess.
2. Native **Scatter on Surface** orients via its **Alignment Axis** + **Align Rotation** inputs —
   set those instead of pre-rotating the prototype; read the modifier result's `inputs:` for the
   exact socket names (they come from the live node group, not from memory).
3. The native modifier instances from a **Collection** — per-prototype materials in that collection
   give the multi-colour mix; it emits **instances** (one modified Icing), so `op=apply` to realize
   real geometry before editing individual sprinkles.
4. In-place duplicate prototypes **z-fight** if their origins coincide; keep the collection members
   spread, and use Poisson-Disk + min-distance on the scatter to avoid instance overlap.
5. Fresh Blender ships a default **Cube/Light/Camera** — delete the Cube, set your Cam active.
6. `transform op=apply scale` legitimately reports "no-op" (world geometry is unchanged by design).

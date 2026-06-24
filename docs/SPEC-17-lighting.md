# SPEC-17 — Lighting, Atmosphere & Presentation Perception

_Status: **Designed 2026-06-24.** Supersedes the flag-planted stub. This is the full-domain
design (not an MVP cut). It closes **gaps.md G130** (no path to a volumetric light shaft) and
builds out the whole presentation stage — atmosphere, particles, mood, and the deterministic
"is the render going to be wrong?" perception that the project's no-screenshot rule otherwise
leaves blind._

Scope discipline: this designs a **photographer's/gaffer's instrument**, not a real-time
engine. We are not rebuilding Unreal. Where Blender already does the physics (Cycles volume
integration, the view transform, particle solvers), we expose the **knobs and the relational
seating**, and we add the **deterministic checks** — we do not reimplement the renderer, and we
never ask the model to eyeball a frame.

---

## 0. What already exists (do not re-derive)

`extension/lighting.py` (surfaced through `scene` / `view` / `render`):

| Op | Verb | What it does |
|----|------|--------------|
| `add_light` | (light surface) | POINT/SUN/SPOT/AREA, positioned, optional aim at named subject |
| `modify_light` | (light surface) | energy/color/size/spot_angle/position/target on an existing light |
| `aim_at` | `view` | re-aim any object's −Z at a named subject (general) |
| `rig_around` | `view op=rig` | spherical placement (azimuth/elevation/distance) + aim inward; `fit=True` auto-distance |
| `set_world_background` | `scene op=world` | solid colour / `hex` / HDRI + strength |
| `set_camera_dof` | `view op=camera_dof` | DoF on evaluated geometry; focus distance/object + f-stop |
| `set_color_management` | `render op=color` | view_transform / look / exposure / gamma |
| `set_render_quality` | `render op=quality` | Eevee raytracing/AO/shadows/samples |
| `set_cycles_quality` | `render op=cycles` | device/backend/denoise/adaptive/samples |

Perception templates to copy: `check_framing` and `check_focus` (`extension/introspect.py`,
surfaced via `view`). Both are **deterministic, Python-computed, no test render** — `check_focus`
is a closed-form thin-lens DoF model. New presentation checks follow that shape exactly.

Confirmed **absent** (greenfield): any Volume Scatter / Volume Principled / volume domain, any
Eevee volumetric toggle, light linking, IES, area-light shaping beyond `size`, Kelvin colour
temperature, compositor post (bloom/glare/vignette), particle *creation* (particles are today
read-only: `feel` sees them, `set_particle_visibility` hides them). The World Output node's
`Volume` input is **never written anywhere** — that is the clean insertion point for atmosphere.

---

## 1. The laws this domain must obey

Lighting is the most dangerous domain for these violations because it is the most "aesthetic."
Restating the binding constraints from `docs/vision.md` and THE ONE RULE, specialised to light:

1. **The model sets lights; it never judges them.** "The sculptor may set a material or light
   (mechanical), but the judgment of how it *looks* always routes to the human — it literally
   cannot see it." Every verb here is a **mechanical setter** or a **deterministic measurer**.
   There is **no auto-mood engine, no auto-grade, no "make it cinematic" verb.** Where a choice
   is taste, we **render precise variants and hand the call to the human** — we never guess it.

2. **Derive, don't divine; provenance for every number.** No light position/angle/energy/EV
   typed from intuition. It comes from a read (subject bbox, a `feel`, a `check_exposure`) or
   from an authored dimension whose returned status we then trust. Relational seating
   (`rig_around subject=`, `aim_at subject=`) is the embodiment; new light verbs take **named
   subjects + relational quantities** (azimuth/elevation/distance, key:fill ratio, Kelvin,
   stops), never raw coordinates.

3. **Perception may report coordinates and physical scalars; action may not consume them.** A
   check may return "subject receives 3.2 EV, key:fill 6:1, 38% of the key cone misses the
   subject." Measured truth cannot gaslight. But no verb takes a dead-reckoned coordinate as a
   ripcord — if an agent tries, refuse with an intent-capturing diagnostic and log a gap.

4. **Deterministic Python verdicts, never the render, never an in-server model.** This is the
   crux of the whole spec (§5). Exposure/blur/shadow verdicts are computed from scene data
   (lamp energies, geometry, camera lens, view transform) by closed-form math — the same
   discipline that lets `check_focus` answer "is it sharp?" without a frame. The render stays
   **for the human** (and the cold judge at milestones); the model does not read it back.

5. **General primitives, not bespoke shortcuts.** The fix for the god-ray is a general
   **world volume medium** + a general **volume domain object**, from which a god-ray *falls out*
   for free. `beam=true` and `three_point` are allowed **only as sugar layered on the general
   primitive**, never as the primitive itself.

6. **Effortless gate — zero arithmetic, floor test.** Kelvin in (not RGB the model computed),
   ratios in (not per-light watts the model balanced by hand), `fit`/resolver out. The weakest
   shippable model must light a blockout from the verb surface alone.

---

## 2. Atmosphere — volumetrics, fog, haze, god-rays, steam, clouds

This is G130 and the bulk of the "effects" ask (steam, clouds, god rays). One physical idea
underlies all of them: **a scattering/absorbing medium in the path of light.** Blender already
integrates the physics; we expose two general primitives and let the effects emerge.

### 2.1 Primitive A — world medium (global atmosphere)  → `scene op=atmosphere`

Writes the **World Output `Volume` socket** (currently unwritten) with a `ShaderNodeVolumeScatter`
(+ optional `ShaderNodeVolumeAbsorption` mixed via `ShaderNodeAddShader`). This is the global
haze/fog that fills the scene; **god-rays are an emergent consequence** — once the air scatters,
any bright shadow-casting SPOT or SUN throws a visible shaft with no further work.

```
scene op=atmosphere
  density=        # float, scattering coefficient. 0 = clear. ~0.01 thin haze, ~0.1 thick fog.
  color=  /hex=   # tint of the scattered light (warm dusk air, cold morning)
  absorption=     # optional, darkens/“thickens” (smoke vs mist). default tracks density
  anisotropy=     # -1..1 forward/back scatter. + (≈0.6) = strong god-ray bias toward light
  height=         # optional: falloff so fog pools low (uses a Gradient/Noise→density map)
  clear=true      # tear the volume back out (restore empty Volume socket)
```

- **Find-or-create** each node (mirror `set_world_background`'s idiom), link into the World
  Output `Volume` input, guard sockets with the `_set_input` portability helper.
- `height` pooling is the one graph that needs a coordinate→density map; build it once,
  generally, so it survives a future node surface (per SPEC-17's original instruction).

### 2.2 Primitive B — volume domain object (localized fog/steam/cloud)  → `add op=volume`

A bounded volume (a box domain with `ShaderNodeVolumePrincipled`) you **seat relationally** on
or around a named subject — for a steam plume over a cup, a fog bank in a doorway, a cloud bank.

```
add op=volume name=
  on= / around=   # relational seating on/around a named subject (NOT coordinates) — reuse
                  #   the rig_around / world_bbox seating already in lighting.py + common.py
  size=           # extent (dimension, derived from subject if 'around=')
  density=
  color= /hex=
  noise=          # 0..1 procedural turbulence → cloud/steam look (Noise/Musgrave→density)
  rising=         # optional gradient so a plume thins upward (steam) vs uniform (fog bank)
```

- **Steam** = small `around=<cup_rim>` domain, moderate `noise`, `rising` gradient, warm tint.
- **Cloud** = large domain, high `noise`, low density, white. **Fog bank** = wide flat domain,
  low `noise`. All the same primitive; the *recipe* differs, and recipes are documented sugar,
  not new verbs.
- **Out of scope (the "within reason" line):** no Mantaflow fluid/smoke *simulation*. We ship
  **static/procedural** volumes (instant, deterministic, no bake). True simmed smoke is a
  separate large spec; flag it as a future gap if a build actually needs billowing dynamics.

### 2.3 Engine awareness (required, not optional)

- **Eevee** renders volumetrics only when enabled. `render op=atmosphere_quality` (or fold into
  `render op=quality`) gates `scene.eevee` volumetric props (`volumetric_start/end`,
  `volumetric_tile_size`, `volumetric_samples`, `use_volumetric_shadows`) with the same
  per-attr `hasattr` guarding `set_render_quality` already uses (Eevee-Next renamed these).
  **Without this, `scene op=atmosphere` silently does nothing in Eevee** — the op must detect
  the active engine and either enable volumetrics or return a clear `skipped`/diagnostic.
- **Cycles** renders volumes with no toggle but needs step control for clean shafts
  (`scene.cycles.volume_step_rate`, `volume_max_steps`) — surface alongside `set_cycles_quality`.
- The atmosphere op should **report which engine it configured for** and what it enabled, so the
  agent isn't left guessing why a beam didn't appear.

### 2.4 `beam=true` — sugar, last

Once §2.1 exists, a beam is: atmosphere present + a SPOT/SUN with shadows on. `light … beam=true`
is a **one-call convenience** that (a) ensures a thin world medium exists, (b) ensures the light
casts shadows, (c) for a SPOT tightens the cone. It authors nothing the general primitives can't;
it just collapses the sequence. Build it only after A/B land.

---

## 3. Mood — colour temperature, ratios, shaping, linking

"Mood lighting" decomposes into mechanical knobs (ship these) and a taste verdict (route to
human, §6). The knobs:

### 3.1 Kelvin colour temperature (the big effort-reducer)

Add `temperature=` (Kelvin) to `add_light` / `modify_light`, computed to linear RGB **in Python**
(blackbody approximation — deterministic, no node needed on the lamp). 3200 = tungsten warm,
5600 = daylight, 6500 = overcast, 8000+ = cool shade. This is how gaffers think; it removes the
model dead-reckoning an RGB triple. Same for `scene op=world` ambient and `scene op=atmosphere`.

### 3.2 Photographic ratios + three-point sugar

The model should balance lights by **ratio, not by hand-tuned watts**.

```
light op=three_point subject=        # sugar over rig_around: places key+fill+rim relationally
  key_kelvin= fill_ratio= rim=        #   fill_ratio=4 → 4:1 key:fill; rim optional
```

This is a **general photographic primitive** (key/fill/rim is universal), seated on a named
subject via the existing `rig_around` machinery — admissible sugar, not a bespoke one-shot. The
ratio is enforced by computing fill energy from key energy + estimated falloff (see §5.2), so the
model never balances watts itself.

### 3.3 Area-light shaping, IES, EV

- **Shaping:** expose AREA `shape` (SQUARE/RECTANGLE/DISK/ELLIPSE), independent `size_x/size_y`,
  and `spread` (Eevee) — softness control beyond today's single `size`.
- **IES:** `add_light … ies=<path>` loads a real-world `.ies` photometric profile via a Light
  IES node. General primitive, validate the file exists like `set_world_background` does for HDRI.
- **EV/exposure on lights:** keep energy in watts as ground truth, but accept `ev=` /
  `stops=±N` as relative adjustments ("two stops brighter") resolved against current energy —
  again, ratio-thinking over absolute watts.

### 3.4 Light linking (per-object influence)

Blender 4.x light-linking collections: `light op=link light= include=/exclude=<subjects>` so a
rim light hits only the hero, or a light is blocked from the background. General primitive,
named subjects in/out — no coordinates.

### 3.5 Post: bloom / glare / vignette  → `render op=post`

Eevee-Next moved bloom to the compositor; build a small **compositor node graph** (greenfield,
same find-or-create discipline as the world tree): `glare` (bloom/streaks for that god-ray/emission
glow), `vignette`, exposure/contrast already partly in `set_color_management`. This is the
art-pipeline Stage-10 "post-processing" intention. Mechanical setter; the *amount* is a human call.

---

## 4. Particles — DEFERRED (out of scope)

Atmospheric particles (dust motes, snow, sparks/embers) are **deferred to their own future
spec** and intentionally not built here. Creation is greenfield (today particles are read-only:
`feel` sees them, `set_particle_visibility` hides them), the surface is large, and the
atmosphere work in §2 carries the "effects" ask on its own — a god-ray shaft reads without motes.
When a build actually needs floating dust/snow/embers, spec a single **general particle emitter**
(seated relationally on a named subject; `kind=motes|falling|rising` driven by a gravity sign),
not bespoke `add_snow()`/`add_sparks()` verbs. Simmed fire/smoke stays excluded (§2.2).

---

## 5. Presentation perception — the deterministic "will the render be wrong?" checks

This is the heart of the spec and the answer to "check if it's blurry / tell if there's too much
light **automatically**." The rule is absolute: **we do not read the render back.** Every verdict
is closed-form Python over scene data, mirroring `check_focus`. New impls live in
`extension/introspect.py` (or a new `extension/lighting_checks.py`), NL formatters in
`server/introspect.py`, surfaced via **`view`** beside `check_framing`/`check_focus`.

### 5.1 `view op=check_focus` — extend to all blur (the "is it blurry" check)

`check_focus` already deterministically answers **DoF blur** (thin-lens near/far/hyperfocal vs
each subject's depth). Extend the same op to cover the other two ways a frame goes soft, all
without a render:

- **Motion blur** — if the scene is animated, compute per-object/camera screen-space velocity ×
  shutter (`scene.render.motion_blur_shutter`) → blur length in px. Report `motion_blur_px` and a
  `would_smear` bool. (No animation → reported as `n/a`, honestly.)
- **Effective resolution** — a subject occupying X% of frame at output resolution has an effective
  pixel footprint; flag when a hero subject is so small it will read soft regardless of focus.
- Verdict shape stays `check_focus`'s: per-target booleans + magnitudes, `None` where a regime
  (e.g. no animation) genuinely doesn't apply. **Resolver** already exists (`resolve_for` →
  aperture); extend with "what focus_distance centers the slab on the subject."

Explicitly: blur is **always derived** here (aperture/focus/depth, velocity/shutter,
coverage/resolution) — never detected by sampling pixels. State this in the docstring with the
"don't read the render back" citation, as the other checks do.

### 5.2 `view op=check_exposure` — the "too much / too little light" check

The centerpiece, and the most physically interesting. Deterministic **irradiance estimate** at
each named subject:

- For each light, estimate irradiance reaching the subject bbox center:
  POINT/SPOT/AREA inverse-square from distance (`E ≈ power / (4π d²)`, Blender watt convention),
  with the SPOT cone gate and a cosine term from light direction; SUN as constant irradiance;
  world background + atmosphere as an ambient floor. Sum → total irradiance → relative **EV**.
- Apply the scene **view transform + exposure** (AgX/Filmic/Standard rolloff, the same color
  management `set_color_management` reads) to map estimated luminance toward display range.
- **Report (per subject):** estimated `ev`, `stops_over`/`stops_under` vs a mid-grey target,
  `likely_blown` / `likely_crushed` booleans, and **`key_fill_ratio`** (brightest vs next
  contributor) with a `% of subject in shadow` from `scene.ray_cast` toward each key light
  (reuse the occlusion sampling `check_framing` already does).
- **Resolver:** "what key energy / `stops` yields a 3:1 ratio?" or "...puts the subject at
  mid-grey?" — solving the value beats the model dead-reckoning it (the `check_focus.resolve_for`
  pattern).

**Honesty boundary (this is load-bearing).** This is an *estimate*, not the renderer: it ignores
indirect bounce/GI, doesn't know surface albedo unless the material is read, and approximates the
tonemap rolloff. So it must, per the project's "names the regimes it can't read" convention,
**state its limits in the result** and confine itself to catching **gross, mechanical error** —
a light 100× too strong, a subject lit only by a 0.01 ambient floor, a key:fill of 200:1, the
hero entirely in shadow. The fine call — "is *this* highlight pleasingly clipped?" — is
appearance, and **routes to the human (§6).** The check tells the agent when the lighting is
*physically broken*; it never tells it the lighting is *good*. That division is exactly principle
#1, and it's why this can be deterministic without pretending to see.

### 5.3 `view op=check_lighting` — the umbrella roll-up

A breadth-first `feel`-style aggregate (à la `feel op=all`) that runs exposure + shadow + focus +
ratio for the framed subjects and returns one prose block: "Hero: 0.0 EV (mid-grey), key:fill
6:1, 4% in shadow, in focus. Background: −3.2 EV (crushed), not in DoF." One call, no render, the
deterministic state of the whole presentation. This is most of the "better feedback range" ask.

### 5.4 Feedback floor integration (the rest of "better feedback range")

Wire lighting mutations into the SPEC-16 two-sense floor so they *self-report*:

- Every lighting op's result carries the **scene-light delta** ("key now 850 W, subject +1.4 EV"),
  so the agent perceives the consequence without a separate query.
- Add a `validate` predicate for **physically-broken lighting** (no light reaches the active
  subject; subject fully in shadow; key:fill beyond a sane bound) — a verdict-bearing check that
  fires automatically after mutations, exactly as mesh `validate` does. Descriptive delta from
  `feel`; broken/not-broken verdict from `validate`.

---

## 6. Where taste lives — the human handoff

Per principle #1, the following are **never** auto-decided; the system surfaces **precise
variants and asks**:

- Overall mood / "make it cinematic" / final grade amount → render a small ladder of variants
  (e.g. key:fill 2:1 / 4:1 / 8:1, or AgX vs Standard, or warm 3200K vs neutral 5600K) and ask
  the human which reads right. The model picks the *axis and the precise steps* (mechanical); the
  human picks the *winner* (taste).
- "Is this highlight nicely blown / is this bloom too much / does this fog feel right" → human,
  optionally with the intent-blind **cold judge** at milestones.
- `check_exposure` flags *broken*; it never asserts *good*. "The render sells the asset" (art
  pipeline Stage 10 done-when) is a human verdict.

---

## 7. Build phasing (effort = complexity/risk)

Ordered so each phase is independently shippable and earns its keep:

1. **Atmosphere world medium** (`scene op=atmosphere`) + **Eevee/Cycles volumetric gating**.
   *Closes G130 directly — god-rays fall out.* Moderate complexity (one new world graph + engine
   guards), low risk (additive, `clear=true` reverses it).
2. **`check_exposure` + `check_lighting`** (§5.2/5.3) + feedback-floor wiring (§5.4). Moderate
   complexity (the irradiance math), low risk (read-only). High payoff for "too much light" +
   "better feedback."
3. **`check_focus` blur extension** (§5.1). Low complexity (extends existing op), low risk.
4. **Mood knobs**: Kelvin temperature, EV/stops, area shaping, IES (§3.1/3.3). Low–moderate, low
   risk (parameter additions to existing setters).
5. **Volume domain object** (`add op=volume`) for steam/fog/cloud (§2.2). Moderate complexity
   (relational seating + procedural density graph), low risk.
6. **`beam=true`** + **`three_point`** sugar (§2.4/§3.2). Low complexity, only after 1/4 land.
7. **Light linking** (§3.4) + **`render op=post`** bloom/glare/vignette (§3.5). Moderate.

(Particles, §4, are deferred to a future spec — not part of this build.)

---

## 8. Non-goals (the "don't reinvent Unreal" line)

- No real fluid/smoke/fire **simulation** (Mantaflow bakes) — static/procedural volumes only.
- No real-time/interactive viewport relighting loop — this is a batch instrument.
- No general node-graph editor surface — each new graph stays bespoke-but-reusable via the
  existing idioms (`_set_input`, find-or-create, `hex_to_linear_rgba`) until a real node spec is
  warranted.
- No pixel/AI analysis of the render — perception stays deterministic and scene-derived, always.
- No in-server model judging look — taste routes to the human (§6).

---

## 9. Wiring checklist (per new op, from the architecture survey)

1. **Extension handler** in `extension/lighting.py` (it already owns lights + world tree + render
   quality and is in `_TOOL_MODULES`) — return `{"success": True, ...}` / `{"error": ...}`; add
   to that module's `TOOLS` dict. Checks go in `extension/introspect.py` (or new
   `lighting_checks.py` added to `_TOOL_MODULES` + the import block in `extension/server.py`).
2. **Server adapter** in `server/scene.py` (or `server/introspect.py` for checks): `call_blender(...)`
   + `_status(result)` NL formatting.
3. **Verb wiring**: add op to `_OPS` + the `op: Literal[...]`, add params with `tag(type, "[op] …")`,
   add the dispatch line. Homes: atmosphere/volume/world → **`scene`**; light setters → the
   existing light surface; checks → **`view`**; post/quality → **`render`**.
4. **Engine guard**: `getattr(scene, "eevee"/"cycles", None)` + per-attr `hasattr`, report
   `skipped` honestly (the `set_render_quality` pattern).

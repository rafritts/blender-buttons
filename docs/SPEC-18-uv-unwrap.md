# SPEC-18 — UV Unwrap & Texture-Space Wiring

_Status: **Designed 2026-06-24, verb home signed off — ready to build (not yet built).** Closes
**gaps.md G152** (no UV-unwrap verb; `material op=pbr`/`textured` assumes box projection forever)
and fills **Stage 6** of `docs/art_pipeline.md`, which `project-vision.md` lists as in-scope.
The one open decision — the verb home (§2.0) — is resolved: a **dedicated `uv` verb**._

Scope discipline: this exposes Blender's existing unwrappers and the UV-map material wiring
as **mechanical setters + one deterministic check**. We do not build a UV editor, manual
island layout, pinning, or UDIM. Where Blender already does the math (`smart_uv_project`,
`pack_islands`, the angle-based solver), we expose the **knobs and the relational seam
sourcing**, and we add the **Python-computed quality verdict** — we never ask the model to
eyeball the UV editor.

---

## 0. What already exists (do not re-derive)

| Thing | Where | Relevance |
|-------|-------|-----------|
| Box-projection texturing | `extension/textures.py` (`set_textured_material`, `set_pbr_material`) | `TexCoord.Object → Mapping → Image(projection='BOX')`. **Never touches a UV layer.** This is the node graph UV mode must branch from. |
| Physical-scale derivation | `textures.py` G141 | `physical_size` → per-axis Mapping scale from world transform. UV mode needs its **own** texel-density story (§4). |
| Edge-tag ops | `edit op=mark_sharp` / `edit op=crease` | The template for **seam marking**: operate on the live edit-mode edge selection, manage mode on `target=`. A UV seam is the same shape of operation. |
| Feature selection | `select` verb (`by_axis`, sharp edges, region boundaries, open boundaries) | The **relational source of seams** — we mark seams from features the agent already addresses by name, never by hand-picked edge indices. |
| Deterministic check template | `view op=check_focus` / `check_framing` (`extension/introspect.py`) | Closed-form, no test render. The UV-quality check (§5) follows this exactly. |
| `object op=convert` | `extension/modifiers.py` | Curve/text → mesh. Relevant only as the precondition: UVs need real mesh faces. |

Confirmed **absent** (greenfield): any `uv_layers` read or write, any `bpy.ops.uv.*` call, any
seam tagging, any `projection='FLAT'`/UV-driven image node, any UV introspection. Nothing in
the codebase reads or reasons about a UV map today.

---

## 1. The laws this domain must obey

UV is the second-most "aesthetic-feeling" domain after lighting, so THE ONE RULE binds hard:

1. **The model unwraps; it never judges the look.** Running `smart_uv_project` or packing
   islands is mechanical. Whether the seams land in ugly places, or whether grain *reads
   right*, is taste → it routes to the human (§6). Every op here is a **mechanical setter** or
   a **deterministic measurer**. No "make the UVs good" verb.

2. **Seams are derived from features, not divined from edge picks.** Hand-selecting a seam
   loop by eye is coordinate-divination wearing a different hat. The intent-space sources:
   *auto* (angle-based, no manual seams — the hard-surface default), or seams **inherited from
   a named feature** — sharp edges, a region boundary, an open boundary, a selected loop the
   agent put there relationally. Provenance for every seam: it came from a feature, not a guess.

3. **The check may report UV-space scalars; action may not consume a divined one.** `uv
   op=check` may return "island 3 stretches 2.4× in V, texel density CV 0.38, 4% of UV area
   used." Measured truth can't gaslight. But no setter takes a typed UV coordinate as a
   ripcord — there is no "move this island to (0.3, 0.6)." If that's ever needed, refuse with
   an intent diagnostic and log a gap.

4. **Deterministic Python verdict, never a render, never an in-server model.** Stretch, texel
   density, packing efficiency, overlap, and unmapped faces are all computed from the `uv_layer`
   loop data + face areas by closed-form math. The "checker texture to spot stretching" trick
   is replaced by a number; the checker itself stays only as an optional **human** preview (§6).

---

## 2. The verb surface

### 2.0 Verb home — DECIDED: a dedicated `uv` verb

The gap floated either "a `uv` verb" or "`edit op=unwrap`". **Resolved (signed off): a
dedicated `uv` verb.** UV is a distinct coordinate space (the 2D map), and grouping
`unwrap / mark_seam / clear_seam / pack / check / checker` under one verb is the most legible —
one place the agent looks for "everything UV," with `feel`/`edit` left focused. The
material-consumption knob (§4) still lives on `material`, since that's where shading is wired.

The cost we accept: it's a new verb, against the SPEC-05 collapse's bias toward few. The
counter is that a new coordinate space earns one, and the alternative (scattering unwrap across
`edit`, the check across `feel`/`view`) hurts discoverability more than one extra verb hurts
the collapse. Recorded for posterity: the rejected option was folding the ops into `edit`
(`edit op=unwrap`/`mark_seam`/`pack`) + `feel op=uv` / `view op=check_uv`.

### 2.1 The `uv` verb

```
uv op=unwrap     target= method=smart|angle|conformal|cube|cylinder|sphere
                 [angle_limit=66] [island_margin=0.02] [scale_to_bounds=false]
                 [seams_from=auto|sharp|region|boundary|selection] [region=<name>]
   op=mark_seam  target= from=sharp|region|boundary|selection [region=<name>] [clear_first=true]
   op=clear_seam target=
   op=pack       target= [margin=0.02] [rotate=true]
   op=check      target=                         # the deterministic quality verdict (§5)
   op=checker    target= [squares=10]            # apply a checker material — HUMAN preview (§6)
```

- **`target`** is one object, a group, or `a,b,c` (each unwrapped independently — UVs are
  per-mesh). Handlers manage entering Edit Mode and selecting all faces, like the `edit`
  family; they leave the object in the mode they found it (G157 hygiene — echo the mode back).
- **`unwrap`** is the one-call path: pick a method, optionally source seams first, pack. For
  `method=smart` (default) seams are implicit (angle-based) and `seams_from`/`mark_seam` are
  irrelevant. For `method=angle|conformal` the seams matter, so `seams_from=` runs a
  `mark_seam` pass first (default `auto` = leave whatever seams exist; the agent can pre-mark).
- **`cube|cylinder|sphere`** are the parametric projections — a mug belly is `cylinder`, a flat
  plate face is effectively `cube`/`smart`. They need no seams.

### 2.2 The mug/plate example (the gap's actual failure), end to end

```
uv op=unwrap target=Mug method=cylinder island_margin=0.02      # belly grain follows the wall
uv op=unwrap target=Plate method=smart angle_limit=66           # plate: angle-based islands
material op=pbr target=Mug,Plate folder=<glaze> space=uv        # §4 — consume the UVs
uv op=check target=Mug                                          # verdict: stretch/density/pack
# → hand a checker render to the human only if they want to eyeball seam placement (§6)
```

No `bpy.ops` in a one-off script, no "do it by hand in Blender."

---

## 3. Unwrap methods & relational seam marking

| `method` | Blender op | When | Seams |
|----------|-----------|------|-------|
| `smart` (default) | `uv.smart_project(angle_limit, island_margin)` | hard-surface props, "just give me sane UVs" | auto (angle-based); manual seams ignored |
| `angle` | `uv.unwrap(method='ANGLE_BASED')` | organic / when seams are placed deliberately | uses marked seams (`seams_from=`) |
| `conformal` | `uv.unwrap(method='CONFORMAL')` | low distortion on developable shapes | uses marked seams |
| `cube` | `uv.cube_project` | boxy props | none |
| `cylinder` | `uv.cylinder_project` | mugs, bottles, pipes, columns | none |
| `sphere` | `uv.sphere_project` | balls, domes | none |

**Seam sourcing (`seams_from=` / `uv op=mark_seam from=`)** — the intent-space part:

- `auto` — leave existing seams as-is (default for `unwrap`); `smart` ignores them anyway.
- `sharp` — every edge already tagged sharp (from `edit op=mark_sharp` / auto-smooth) becomes
  a seam. The common hard-surface move: seams = the silhouette breaks.
- `region` — the **boundary loop of a named region** (`region=<name>`) becomes the seam — the
  relational "cut around the label patch / the rim band."
- `boundary` — open mesh boundaries (a hollow vessel's rim) become seams.
- `selection` — the live edit-mode edge selection (the agent already placed it relationally).

Every source resolves to edges the agent addressed **by feature or name**, never by index — law 2.

---

## 4. Material consumption — the payoff (`material op=*` gains `space=`)

Unwrapping is inert until a material reads the UVs. Today the image nodes hardwire
`TexCoord.Object → Mapping → Image(projection='BOX')` (`textures.py:88–110`). Add one knob to
`material op=textured` and `material op=pbr`:

```
space = box (default) | uv
```

- `space=box` — unchanged. The current behaviour stays the default so nothing regresses and
  blockout/portfolio renders keep working with zero UV work (the guidance's whole "needs no
  UVs" story holds).
- `space=uv` — image nodes switch to `TexCoord.UV` (the active `uv_layer`) and
  `projection='FLAT'`; the `Mapping` node becomes a UV-space scale/offset (tiling in UV units)
  instead of the world-derived box scale. Refuse with an intent diagnostic if the target has
  **no UV layer** ("`Mug` has no UVs — run `uv op=unwrap` first"), so the failure is legible,
  not a silently-black texture.

`physical_size` (G141) is a **box-mode** concept (world metres per tile via the object
transform); in UV mode the texel story is the UV layout itself, so `physical_size` is ignored
with a one-line note and `scale` means UV tiling. State this in the schema so the two scale
models don't blur.

This is the only change outside the new verb, and it's the reason the verb is worth building.

---

## 5. UV perception — `uv op=check` (the deterministic verdict)

Mirrors `check_focus`: Python-computed from the `uv_layer`, **no render**. Returns, per mesh:

- **unmapped faces** — count of faces with no/zero-area UV (the "you forgot to unwrap this
  part" catch). Non-zero is the headline failure.
- **island count** — connected UV components (the art_pipeline "packed islands" tell).
- **packing efficiency** — Σ island UV area ÷ bounding [0,1]² area, as a %. Low % = wasted
  texel budget.
- **overlap** — do any islands overlap in UV space? (broad-phase island-bbox test; flag, don't
  enumerate). Overlap = two surfaces fight for the same texels.
- **stretch / distortion** — per face, the ratio of 3D area to UV area, normalised; report the
  **coefficient of variation** (texel-density uniformity — the art_pipeline "uniform texel
  density / no stretching" DONE-WHEN) and the worst island's max stretch factor.
- **out-of-bounds** — any UVs outside [0,1] (intentional tiling vs. accident — report, don't
  fail).

Verdict line is a roll-up: `Mug UVs: 1 island, 71% packed, density CV 0.12 (even), max stretch
1.2×, 0 unmapped, no overlap — clean.` Gross failures (unmapped faces, overlap, CV ≫ baseline)
read as warnings; whether the seams are *placed well* stays the human's call.

---

## 6. Where taste lives — the human handoff

Two things are taste, never auto-judged:

1. **Seam placement aesthetics.** The check says density is even; it can't say a seam runs
   down the visible front. If the human wants to see, `uv op=checker target= squares=N` applies
   a checker material so a **render handed to the human** shows stretching/seam placement —
   the "render a variant, hand the call over" pattern (SPEC-17 §6), not an in-server judgment.
   `uv op=checker` is sugar for that preview and nothing else; it does not gate anything.
2. **Method choice when ambiguous.** If a prop is part-cylindrical, part-flat, the model picks
   a reasonable method and reports the check; the human can ask for a different cut. We don't
   guess a "best" unwrap and present it as correct.

---

## 7. Build phasing (effort = complexity/risk)

1. **Phase 1 — core unwrap + material consumption (the gap's literal ask).**
   `uv op=unwrap` (`smart`/`cube`/`cylinder`/`sphere`, no-seam methods) + `material space=uv`
   + the no-UV refusal. This alone closes G152 for the mug/plate case. Lowest risk: all
   `bpy.ops.uv.*` on a full-face selection, plus one node-graph branch.
2. **Phase 2 — relational seams + seam-based methods.** `uv op=mark_seam`/`clear_seam`,
   `seams_from=`, `method=angle|conformal`. Depends on the `select` feature sources resolving
   cleanly to edges.
3. **Phase 3 — perception.** `uv op=check` (the §5 verdict) + `uv op=pack` (explicit repack)
   + `uv op=checker` human preview. Verdict math is the bulk of the effort.

Each phase is independently shippable and independently dogfoodable.

---

## 8. Non-goals (the "don't build a UV editor" line)

- No manual island layout, move/rotate/scale of islands, pinning, or stitching.
- No UDIM / multi-tile.
- No texture **painting** (a separate stage) and no **baking** (art_pipeline Stage 7 — its own
  spec; UV is its precondition, not its home).
- No per-face UV coordinate writes; no typed UV coordinates anywhere (law 3).
- No automatic seam *aesthetics* engine; no "best unwrap" auto-judge (law 1).
- No reimplementation of the solvers — we call Blender's.

---

## 9. Wiring checklist (per the architecture)

- **`server/uv.py`** (new) — flat helper fns (`unwrap`, `mark_seam`, `clear_seam`, `pack`,
  `check_uv`, `apply_checker`) that `call_blender(...)` + format the status line. Mirror
  `server/transforms.py` shape.
- **`server/verbs/uv.py`** (new) — the `@mcp.tool(name="uv")` dispatcher (fat flat signature,
  `op=` discriminator, `teach()` errors for missing required params), like `verbs/transform.py`.
- **`server/verbs/__init__.py`** — add `uv` to the import list **and** to `VERB_NAMES` (else
  `prune_to_verbs` drops it).
- **`extension/uv.py`** (new) — the bpy handlers + a `TOOLS = {...}` dict (auto-aggregated by
  `extension/server.py:91–93`; no build-script change needed — `build_extension.sh` globs
  `*.py`).
- **`extension/textures.py`** — the `space=box|uv` branch in `set_textured_material` and
  `set_pbr_material` (the only edit to existing code).
- **`server/verbs/material.py`** — add the `space=` param + thread it through to both
  `textures.*` calls.
- **`extension/server.py`** — classify the new tools: `unwrap`/`mark_seam`/`pack`/`checker`
  are mutating + EDIT-mode (add to `EDIT_MODE_TOOLS`); `check_uv` is a read (add to the
  read/non-undoable sets so it doesn't take the undo lock).
- **`GUIDANCE_FOR_LLMS.md`** — a short "UVs: box projection is the default and needs none;
  reach for `uv op=unwrap` + `material space=uv` only when grain must follow a curved
  surface" note, so the agent knows the box-default still stands and when to escalate.
- **`docs/art_pipeline.md`** — Stage 6 gains the verb names in its TELLS/DONE-WHEN.
- **Tests** — `tests/e2e_uv_*.py`: unwrap a cylinder, assert a UV layer with N islands; apply
  `space=uv`, assert the image node reads UV + `projection='FLAT'`; `check` on a known-stretched
  vs. clean unwrap asserts the CV ordering.

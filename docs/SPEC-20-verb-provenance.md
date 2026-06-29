# SPEC-20 — Verb Provenance: native vs blender-buttons, and version anchoring

**Status:** research COMPLETE (2026-06-29) — see **Part II** for the full findings
(classification of all 245 ops, cousin audit, kill-list, completed 5.x primer,
extension-health API breaks, and bucket assignments). Decisions in §1–§7 are the agreed
framing; Part II is the grounded result. Implementation follows the Part II checklist.

**Target build:** Blender **5.1** (released 2026-03-17; confirmed from the flatpak
`org.blender.Blender 5.1` and the `BLENDER_EEVEE` render id). Blender 5.0 shipped
2025-11-18. All native claims in Part II are sourced from the 5.0/5.1 release notes and
the 5.1 (`latest`) manual — derived from the build, not model memory (R3).

---

## 1. Problem

The agent (and the human reading a recipe) cannot currently tell, at the call site,
whether a verb is **a native Blender operation made drivable** or **a blender-buttons
invention**. Three live failures motivated this spec:

- **`clad`** "makes shit up" — it's `duplicate → region-delete → inflate → solidify (+subsurf)`,
  but nothing at the call site says so; the agent has to magically know the decomposition.
- **`scatter`** *impersonates* a native feature: the verb/file is `scatter_on_surface`, almost
  the exact name of Blender's shipped **Scatter on Surface** GN modifier, while sharing none
  of its code (it's a from-scratch area-weighted Python sampler). The source even annotates it
  "the donut-tutorial sprinkle step." The agent classified it wrong **to the user's face**.
- **Version skew:** the agent's training is densest on Blender ≤4.x; it reached for a 4.x-era
  reference and asserted "no native equivalent" for things 5.x may ship natively. Provenance
  claims routed through model memory are version-stale **and self-confirming**.

The fix is to make provenance **legible in the verb name** and **derived from the build, never
from model memory**.

## 2. The cut: native vs macro vs sense

The line is **binary** for actions, with a third read-only family off to the side.

- **NATIVE** — resolves to a **single** native operator/feature, no matter how much
  agent-ergonomics (params, defaults, selection grammar, status feedback) wraps it. That
  wrapping *is* the eyes/hands the agent lacks; the outcome is exactly the Blender thing.
  Litmus: **"one operator, or several?"** `loop_cut` (whole-mesh default + `only_selected` +
  `seed_at`) is still a loop cut → native. Ergonomics never demote a native op.
- **MACRO** — **orchestrates several** native ops into a result no single operator yields.
  The agent would have to know a multi-step recipe to predict the output. `clad`, `hollow`,
  `graft`, `field`, etc.
- **SENSE** — read-only perception/measurement (`feel`, `validate`, `view check_*`). Not
  operator-impersonators (nobody mistakes `feel op=all` for a menu item) and they mutate
  nothing, so they sit **off this axis** and keep their plain names.

"Reconstructible by a human in N steps?" is **not** the boundary (clad is reconstructible but
still a macro). It becomes a **schema tag**, not a namespace (see §4).

## 3. Naming & grouping

Rejected `-bb` / `object-bb`: it tags **authorship** ("ours") when the agent needs **behavior**
("expands to several native ops"). Chosen scheme:

- **Native ops → grouped by Blender domain**, unchanged: `object`, `edit`, `transform`, …
  (matches how the agent and Blender both organize primitive operations).
- **Macros → grouped by PURPOSE under `buttons-`**, suffixed `-macro`:
  `buttons-clothing-macro op=clad`, `buttons-scatter-macro op=…`, `buttons-deform-macro op=field`.
  - prefix `buttons` = "belongs to no Blender domain — this is ours" (the one place an
    authorship tag is the *load-bearing* fact, so it earns its keep here).
  - middle = **purpose**, because the agent reaches for fabrications by **outcome** ("I want to
    coat this surface"), not by Blender domain.
  - suffix `-macro` = "composite, expand the docs for its native steps."
  - The space **subdivides by purpose as it grows** (a grab-bag of useful tools is an
    acceptable outcome; when a coherent cluster forms it splits, e.g. `buttons-clothing-macro`).
- Use a plain `<domain>-macro` (e.g. `edit-macro`) **only** for the rare composite that is
  genuinely just a multi-step version of one domain's op with no standalone concept. Default is
  `buttons-<purpose>-macro`.
- `macro` was chosen over `forge/synth/compose`: established meaning ("one name expands into a
  sequence of primitive ops"), aligns with Blender's own "operator macro," and fits both
  object-makers (clad) and deformers (field), which creation-words don't.

## 4. Rules that fall out

**R1 — Native-cousin tag (mandatory).** Any macro that parallels a shipped native feature must,
in its schema, **cite the native feature and state what it adds** — e.g. *"≈ Blender's 'Scatter
on Surface' GN modifier, but emits real per-instance objects it can't."* This is what would have
stopped the `scatter` mislabel and the name collision.

**R2 — No cousin reimplementations.** A verb that **re-implements a shipped native feature gets
deleted.** If it adds something native genuinely lacks, it survives **only as a thin wrapper over
the native feature**, never a from-scratch cousin. (`scatter` = case #1, see §5.)

**R3 — Provenance is derived from the build, never from memory.** Model memory is version-stale
and self-confirming (same failure mode as reading one's own renders).
- *native-vs-macro* ← read the **verb's implementation** (what `bpy.ops.*`/modifiers it calls).
  Version-pinned ground truth, zero recall. (Proven on `clad`, `scatter`.)
- *native-cousin tags & the primer* ← **introspect the live 5.1 build** + authoritative release
  notes, never recall.

**R4 — Version anchoring.**
- `connect` reports **two** versions: the **attached** Blender version *and* the version the
  server was **built/verified against**. Divergence (a future 6.x on a 5.x-era server) is a
  **tripwire** ("this server may be out of date"), surfaced the instant the agent connects.
- A concise **"5.x deltas" primer** (§6) lives in the server `instructions`, **version-stamped**,
  **sourced** (not recalled), re-derived on a version bump.

## 5. `scatter` — the worked example (decision: delete)

The native **Scatter on Surface** GN modifier covers the full need, confirmed from the user's
5.1 UI: Density/Amount, Random/Poisson Disk, Seed, Distribution Mask, **Instance Type: Collection**
(→ per-prototype materials = the multi-color sprinkles), and **Transform → Align Rotation /
Alignment Axis / Surface Offset / Randomize (Rotation, Scale, Offset)**. The bespoke verb's only
extras — `seat` (rest lowest point) and `up_only` — are marginal and unused. **No wrapper; the
verb is deleted.**

⚠ **Deletion is blocked on a missing capability.** The MCP's `modifier add` only does **typed**
modifiers (`modifiers.new(type='SUBSURF'|'ARMATURE'|…)`); a grep found **no path to append a
Geometry-Nodes asset node-group** like "Scatter on Surface." So deleting `scatter` today leaves
the agent unable to scatter at all. **Deletion must ship with** GN-asset-modifier support, e.g.
`modifier add type=NODES asset="Scatter on Surface" collection=<prototypes>`. Then `donut.md`
migrates off the bespoke verb to that modifier + a prototype collection.

## 6. The 5.x primer (starter — to be completed from full release notes)

Goal: a few one-sentence bullets in the server instructions so an agent walking in with a 4.x
model is corrected on contact. **Sourced, version-stamped.** Modeling/render-relevant only
(Grease Pencil / VR / compositor / theme churn dropped). Blender 5.0 (2025-11-18); build 5.1:

- We're on **Blender 5.x, not 4.x** — recalibrate any "is this native?" reflex.
- **Geometry Nodes gained SDF + Volume nodes**; Adaptive Subdivision is stable (non-experimental),
  with object-space edge length. *(Live lead: native SDF may now cousin `graft`/`field`.)*
- **Color/render:** full ACES pipeline + HDR/wide-gamut read+write, reworked color management.
- **Subsurface scattering:** multi-bounce random-walk SSS (less darkening) — skin/wax/organic.
- **Files:** blend compression on by default; data-block names up to 255 bytes.
- Native **"Scatter on Surface"** GN modifier is the current native scatter path (retires §5).

Sources: developer.blender.org/docs/release_notes/5.0/ · blender.org/download/releases/5-0/ ·
developer.blender.org/docs/release_notes/ (index for 5.0/5.1/5.2).

## 7. Open / gray-case rulings needed

Each resolved by the §2 litmus ("one operator, or several?") once the implementations are read:
- `graft` (smooth-min union via marching tetrahedra) — **does 5.0's native SDF now cousin it?**
- `field`, `feel op=fit` (formula-driven) — native GN path now, or genuinely no-native?
- `array_radial` (Array modifier + hidden Empty pivot) — native technique but multi-object.
- `relax`, `smooth_edges`, `remesh`, `noise_displace` (Displace-modifier-baked?) — likely native,
  confirm by code.

---

## TODO — research after compact

Pick up here; everything below needs the **build/release notes**, not recall (R3).

1. **Introspect the live 5.1 native surface** as the grounding substrate: operator inventory
   (`bpy.ops`), the modifier enum, and the **bundled essentials GN node-groups** (does "Scatter
   on Surface" et al. enumerate?). Prefer a query against the running instance; else a headless
   `--background --python` dump.
2. **Re-run the cousin audit against 5.0's new GN nodes** (SDF + Volume): do `graft` and `field`
   now have native cousins? Resolve every §7 gray case. Produce the complete **kill-list**, not
   just `scatter`.
3. **Read ~150 verb implementations** and build the **op → {native | macro | sense}** table
   (the spec's centerpiece). For each macro, write its R1 native-cousin tag.
4. **Verify the GN-asset-modifier gap** (§5) and design the capability that lets `modifier add`
   point a NODES modifier at a bundled asset node-group + collection. Prereq for deleting `scatter`.
5. **Pull the full 5.0/5.1 release notes incl. the Python API page** — (a) finish the §6 primer,
   (b) flag any API changes that affect whether the extension itself still works on 5.1.
6. **Decide the `buttons-<purpose>-macro` bucket list** (clothing, scatter, deform, blend, …) and
   assign every macro a bucket; flag macros that span two purposes.
7. **Wire R4:** `connect` returns attached-version + server-verified-against version + drift flag;
   add the §6 primer (stamped) to the server `instructions`.
8. **Migrate `donut.md`** off bespoke `scatter` once #4 lands; keep it as the recipe-side proof.

### Decisions already locked (don't relitigate post-compact)
- Native = grouped by Blender domain; macros = grouped by **purpose** under `buttons-<purpose>-macro`;
  senses keep plain names. Word is **`macro`** (not `bb`/`-bb`).
- Reconstructibility is a **schema tag**, not a namespace boundary.
- Native-cousin tag is **mandatory** for any paralleling macro (R1); no from-scratch cousins (R2).
- Provenance derived from the **build**, never model memory (R3); version-anchored (R4).
- `scatter` is **deleted** (not wrapped), gated on GN-asset-modifier support landing first.

---

# PART II — RESEARCH FINDINGS (2026-06-29)

Method: 5 code-reading passes classified all **245 flat ops** by reading each handler's
actual `bpy.ops`/modifier/bmesh calls (R3 native-vs-macro from the implementation); 3 web
passes audited the macros against the Blender 5.0/5.1 native surface (R3 cousin/primer from
release notes + the 5.1 manual). Counts: **~150 NATIVE**, **~60 SENSE**, **31 MACRO/geometry +
look** (plus 11 selection-helper composites reclassified — see §II.1).

## II.1 Refinement: SELECTION HELPERS are a fourth family (not macros)

The code read surfaced 11 ops the strict "one operator?" litmus calls MACRO **only because
they have no single native operator**, yet they mutate **no geometry** — they set the
selection by world-space geometry: `select_by_axis`, `select_between`, `select_by_index`,
`select_in_sphere`, `select_by_radius`, `select_limb`, `flood_to_crease`, `select_boundary`,
`select_by_vgroup`, `select_by_material`, `snap_loop`. **Ruling:** the native/macro cut is for
**geometry-MUTATING** ops. Selection helpers stay under the `select` verb with **plain names**
(like SENSE) — they are the eyes/hands grammar, not fabricated geometry. The `-macro` scheme
applies only to ops that author/deform geometry or build a look.

## II.2 The MACRO inventory — verdict, native cousin (R1 tag), purpose bucket

| op (current verb·op) | native cousin in 5.x | verdict | bucket |
|---|---|---|---|
| `object·clad` | Solidify (+Subsurf) — choreography (isolate/inflate/open) non-native | **keep + tag** | `buttons-shell-macro` |
| `object·hollow` | Solidify neg-offset on closed manifold (partial; no open/verify) | **keep + tag** | `buttons-shell-macro` |
| `object·duplicate_mirrored` | Mirror modifier (but baked, one-shot) | keep + tag | `object` (stays; near-native) |
| `edit·graft` (compose) | **5.0 SDF chain**: Mesh→SDF Grid → SDF Grid Boolean(Union) → SDF Fillet → Grid→Mesh. **No smooth-min `k`** natively (hard union + iteration-bound fillet, voxel-res-bound) | **keep + tag** | `buttons-blend-macro` |
| `edit·stitch` (compose) | Bridge Edge Loops (manual loop pick) / Weld modifier | keep + tag | `buttons-blend-macro` |
| `edit·field` (fields) | GN Set Position primitive — **no native formula operator** | keep + tag | `buttons-deform-macro` |
| `edit·band_around` | **none** — no stock "band around a form" | keep | `buttons-deform-macro` |
| `edit·extrude_along_curve` | Curve modifier / Array+Curve / Screw | keep + tag | `buttons-deform-macro` |
| `edit·relax` (relax_selection) | LoopTools Relax / Smooth Vertices | keep + tag | `edit` (selection-region smooth; stays) |
| `edit·slide` (slide_selection) | Vertex/Edge Slide + reproject | keep + tag | `edit` (stays) |
| `edit·flute` `edit·shape_profile` `add·taper*`/`scale_rings`/`taper_end`/`taper_section` (rings) | Transform-scale w/ Individual-Origins; **no native lathe/turning** | keep | `buttons-lathe-macro` |
| `add·spline_tube` (curves) | **NEW 5.0 "Curve to Tube" modifier** + Curve-Bevel | **keep + tag** (cite Curve to Tube) | `buttons-lathe-macro` |
| `add·helix` (helix_coil) | Screw modifier; **Curve to Tube** for the sweep | keep + tag | `buttons-lathe-macro` |
| connectors: `connect_handles`/`reshape_connector`/`resample_loop`/`make_strands` | Bridge Edge Loops / GN curve instances | keep + tag | `buttons-connector-macro` |
| `material·toon` (set_toon_material) | **Shader-to-RGB node** (native, EEVEE-only, Cycles unsupported) — **no stock toon preset** | keep + tag | `buttons-npr-macro` |
| `material·outline`/`remove_outline` | **Line Art** (GP, real-time, the "real" native path) / Freestyle / Solidify inverted-hull (what the verb automates) | keep + tag | `buttons-npr-macro` |
| `material·textured` (set_textured_material) | Node-Wrangler "Principled Texture Setup" (an add-on, not core) | keep + tag | `buttons-npr-macro` |
| `transform·mirror_across` / `relational·array_at_corners` / `array_along` | Mirror / Array modifiers (baked, multi-object) | keep + tag | `transform` (stays; near-native) |
| `add·primitives` (add_primitives) | bulk add loop — none | keep | `add` (stays) |
| `pose·weight_to_bone` | parent-to-bone + Armature modifier | keep + tag | `pose` (stays) |
| `object·bake_shape_keys_to_basis` | none | keep | `object` (stays) |
| sculpt `sculpt_*` (8) | native sculpt **brushes** — **can't be driven headless** (need interactive strokes) | keep (R2-exempt) | `sculpt` (stays) |

## II.3 KILL-LIST (R2 — delete cousin reimplementations)

1. **`scatter` (scene/obj·scatter → scatter_on_surface) — DELETE.** Native **"Scatter on Surface"**
   bundled GN essentials modifier (new in 5.0) is a full superset: Density/Amount, Random/Poisson-Disk
   + min-distance, Seed, vgroup **and** image distribution mask, **Instance source = Collection**
   (→ multi-color sprinkles), Keep-Surface, full Transform (Surface Offset, Align Rotation, Alignment
   Axis, Scale XYZ, Randomize Rotation/Scale, Random Flip). Behavioral delta to flag: native emits
   **instances-on-points**, not separate objects — bake via **Realize Instances** if real geometry is
   needed. The bespoke verb's only extras (`seat`, `up_only`) are marginal. **Gated on II.5 landing.**
2. **`array_radial` (transform/view·array_radial) — DELETE/REWRITE (NEW this audit).** Blender **5.0
   rebuilt the Array modifier with a native Circular mode** (radius, full-circle/arc, gizmos,
   randomization). The macro's hidden-Empty pivot is the **pre-5.0 workaround**, now superseded stock
   functionality. Rewrite as a thin wrapper over the native circular Array, or delete — do **not** keep
   the from-scratch cousin (R2). (Once II.5 GN-asset support lands, the native GN **Array** modifier is
   also reachable directly.)

## II.4 Extension-HEALTH — real 5.x API breaks in our code (TODO #5b)

Found by grepping `extension/` for the documented 5.0/5.1 API renames. These are live bugs on 5.1,
independent of the provenance work:

- **`boolean` is broken on 5.x.** `extension/finishes.py:1271` sets `mod.solver = "FAST"`, but 5.0
  renamed the enum value **`"FAST"→"FLOAT"`** (PR#141686, across operator+modifier+API). `solver="FAST"`
  now throws, and the validator (`finishes.py:1255`) *rejects* the new `"FLOAT"`. **Fix:** accept `FLOAT`,
  map legacy `FAST→FLOAT`, update the error text and the `solver` tag.
- **FBX import likely broken.** `extension/designs.py:118` uses `bpy.ops.import_scene.fbx` — the legacy
  Python FBX add-on, **off by default in 5.0**; the C++ default is **`bpy.ops.wm.fbx_import`**. **Fix:**
  switch to `wm.fbx_import` (fall back to the legacy op only if absent).
- **Stale EEVEE id in help.** `extension/render.py:85` advertises `'BLENDER_EEVEE_NEXT'` — renamed to
  **`BLENDER_EEVEE`** in 5.0. Cosmetic (help text) but mis-teaches the agent. **Fix:** update the string.
- **`use_nodes` no-ops** (6 files: shading/lighting/shaders/textures/common/introspect). Deprecated in
  5.0 (always True, no effect), **removed in 6.0**. Harmless now — **note only**, clean up opportunistically.

## II.5 GN-asset-modifier capability (§5 gate — unblocks the `scatter` delete)

Confirmed buildable today. `modifier add` only does typed `modifiers.new(type=…)`; add a path that
points a `type='NODES'` modifier at a **bundled essentials node-group asset**. Two API routes:

- **Route A (one call):** `bpy.ops.object.modifier_add_node_group(asset_library_type='ESSENTIALS',
  relative_asset_identifier="geometry_nodes/<file>.blend/NodeTree/<Name>")` — the exact op the GUI's
  "Add Modifier ▸ <asset>" fires. Caveat: the literal identifier string couldn't be byte-confirmed
  headless (dev site 403s); needs one GUI read of the auto-logged operator.
- **Route B (R3-clean, preferred — discover, don't hardcode):** glob
  `os.path.join(bpy.utils.system_resource('DATAFILES'), "assets", "geometry_nodes", "*.blend")`,
  `bpy.data.libraries.load(path, link=False, assets_only=True)` to append the node group **whose name
  matches** the requested asset, then `mod = obj.modifiers.new(name, 'NODES'); mod.node_group = ng`.
  No hardcoded identifier — derived from the live build, robust to the exact filename. Essentials assets
  can only be **appended** (`link=False`), never linked.
  Set exposed inputs by **socket identifier** (not name/index): enumerate `ng.interface.items_tree`
  (`item.identifier → item.name`), then write `mod["Socket_N"]`; for a Collection input assign the
  datablock (`mod["Socket_7"] = bpy.data.collections["Sprinkles"]`), then `mod.id_data.update_tag()`.

**Design:** new op `modifier op=add_asset asset="Scatter on Surface" host=<obj> collection=<protos>
inputs={...}` via Route B + a generic "set input by identifier" helper. One addition reaches all six new
5.0 essentials modifiers (Scatter on Surface, GN Array, Instance on Elements, Randomize Instances, Curve
to Tube, Geometry Input). Note: `modifier.node_group` assignment and `modifiers.new(...,'NODES')` are
**unchanged** in 5.x (confirmed: no python_api entry) — only the asset *bundling* is new.

## II.6 §6 PRIMER — completed, sourced, version-stamped (Blender 5.1; 5.0 = 2025-11-18, 5.1 = 2026-03-17)

Modeling/render-relevant deltas an agent with a ≤4.x model needs (each sourced to
`developer.blender.org/docs/release_notes/`):

1. We're on **Blender 5.x, not 4.x** — recalibrate any "is this native?" reflex; verify against the build.
2. EEVEE's engine id is **`BLENDER_EEVEE`** (was `BLENDER_EEVEE_NEXT`); Cycles unchanged. *(5.0/eevee)*
3. Boolean solver value **`"FAST"` is now `"FLOAT"`** (modifier + operator + Python). *(5.0/modeling)*
4. **Six GN-based modifiers** ship in the stack — **Array (with native Circular mode), Scatter on Surface,
   Instance on Elements, Randomize Instances, Curve to Tube, Geometry Input** (Essentials assets). The
   legacy Array modifier still exists. *(5.0/modeling)* — retires `array_radial` (II.3) and is the native
   scatter path (II.3 #1).
5. Geometry Nodes gained a full **volume-grid + SDF family** — Mesh/Points to SDF Grid, **SDF Grid Boolean**
   (hard union only, no blend param), SDF filters (Fillet/Mean/Laplacian/Median/Offset), Grid↔Mesh — plus
   **Bundle** and **Closure** socket types. *(5.0/geometry_nodes)* — cousins `graft` (II.2).
6. **Color/render:** blend files now carry a **Working Color Space** (Linear Rec.709 default; Rec.2020 /
   **ACEScg** options); full **ACES 1.3/2.0 + HDR + wide-gamut** views/displays; new `BLENDER_OCIO` env var.
   *(5.0/color_management)*
7. **Cycles:** multi-bounce random-walk **SSS** (less darkening); unbiased **null-scattering volumes** by
   default (no step-size); **Metallic thin-film** iridescence; **Adaptive Subdivision no longer
   experimental**. *(5.0/cycles)*
8. **Materials & Worlds always use nodes** — `use_nodes` is a deprecated no-op (gone in 6.0);
   `scene.node_tree` removed → `scene.compositing_node_group`. *(5.0/python_api)*
9. **Files:** blend **compression on by default**; data-block names up to **255 bytes** (breaks linking
   from 4.5). Default **FBX importer is C++ `wm.fbx_import`**; **Collada removed**. *(5.0/core, 5.0/pipeline_io)*
10. **5.1:** Python **3.13** (rebuild compiled add-ons); `sculpt.sample_color`→`paint.sample_color`; Node
    Tools need a unique idname (re-save old files); new shader **Raycast** node; GN **UV Unwrap** gained
    SLIM. *(5.1/python_api, 5.1/rendering, 5.1/geometry_nodes)*

Sources: developer.blender.org/docs/release_notes/{5.0,5.1}/ and sub-pages (geometry_nodes, modeling,
core, color_management, cycles, eevee, pipeline_io, python_api); docs.blender.org/manual/en/latest (=5.1).

## II.7 IMPLEMENTATION CHECKLIST (supersedes the §"TODO — research after compact")

Research items 1–3, 5(notes), 6 above are **done**. Remaining build work, in commit order:

- [ ] **A. Extension-health fixes (II.4):** boolean `FAST→FLOAT`, FBX `wm.fbx_import`, EEVEE id string.
- [ ] **B. GN-asset capability (II.5):** `modifier op=add_asset` (Route B) + set-input-by-identifier.
- [ ] **C. Kill-list (II.3):** delete `scatter`/`scatter_on_surface`; delete/rewrite `array_radial`;
      migrate `donut.md` and any recipe to the native modifier path.
- [ ] **D. Cousin tags (R1, II.2):** add the native-cousin citation to every surviving macro's op `tag`.
- [ ] **E. Version anchoring (R4):** `connect` returns attached-version + server-verified-against (5.1) +
      drift flag; add the II.6 primer (stamped) to `server/_instructions.py`.
- [ ] **F. Rename (§3):** lift the II.2 macros into `buttons-<purpose>-macro` verbs
      (shell/blend/deform/lathe/connector/npr); selection helpers stay plain under `select` (II.1);
      update `VERB_NAMES`; migrate all `recipies/`.

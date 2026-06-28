# SPEC-20 — Verb Provenance: native vs blender-buttons, and version anchoring

**Status:** draft, pre-implementation. Decisions below are agreed in discussion; the
classification table and code changes are TODO (see end).

**Target build:** Blender **5.1** (confirmed from the flatpak `org.blender.Blender 5.1`
and the `BLENDER_EEVEE` render id). Blender 5.0 shipped 2025-11-18.

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

# SPEC-22 — Native Hands: strip judgment sugar, complete the native operator basis

**Status:** APPROVED DIRECTION (2026-07-10). Written for an executor agent (no conversation
context assumed). Phases 1→4 are sequential; Phase 5 is parallel-shippable.

**One-line law:** **high-level eyes, low-level hands.** The server may be inventive in
perception, selection, addressing, and placement (the substrate the agent lacks hardware
for). The mutation surface must be the *native Blender operator basis*, under native
names, with hotkeys and menu paths as retrieval keys. A mutation idea with no native name
is a **technique** (prose), never a verb.

---

## 1. Problem & evidence

**The donut experiment (2026-07-10).** Asked cold — no tools, no docs — the agent recited
the Blender Guru donut tutorial as a flawless *procedure* in native vocabulary: duplicate
the top half (Shift+D) and separate, solidify, snap-to-face-projected dragging for the
drips, Inflate brush on the drip tips, proportional-editing nudges for lumpiness. Asked to
then drive the server, the same agent maps narrative steps onto minted verbs and stops:
"`noise_displace` — lumpiness: done, one call." In every observed session across models,
**no LLM has ever attempted the long icing drip** — the signature craft step — despite
provably knowing it. LLM donuts are "ok," never excellent, and "ok" is precisely the
parametric skeleton with the craft skipped.

Four mechanisms, all converging on the same fix:

1. **Outcome-named verbs are semantic checkboxes.** The agent's completion-checking runs
   over narrative steps; a verb whose *name matches the step's name* lets the step check
   off syntactically without the work that made the step matter. A verb named for an
   **outcome** (`gravity`, `field`, `noise_displace`≈"make lumpy") claims the outcome. A
   verb named for an **action** (extrude, inflate, grab) claims nothing — the agent still
   has to look at what it got.
2. **Training-distribution stranding.** The agent's Blender knowledge — deep and reliable
   — is *indexed* by GUI vocabulary: hotkeys, menu paths, tutorial phrasing. Minted
   mutation verbs are keyed to terms that appear nowhere in that corpus, so the agent's
   strongest asset (a lifetime of Blender text) is traded for its weakest (one-pass
   in-context schema comprehension). SPEC-21 §2 established this for retrieval; the new
   finding is that it also sets **effort expectations**: a surface of primitives says
   "work is done stroke by stroke here"; a surface of outcome-verbs says "vending
   machine," and the agent calibrates effort to the perceived affordance.
3. **RLVR gradient.** Training rewards reaching a verifiable end-state efficiently. Craft
   has no verifiable end-state, so under reward pressure it collapses to the minimal path
   satisfying the nominal description. Sugar verbs are that path.
4. **Attention competition.** A 30-op × 80-param schema is a second object the agent must
   model, and it competes with the mesh. Planning degrades from "what does the mesh need"
   (recall over Blender knowledge) to "which tool fits best" (search over the schema).

**Consequence:** missing verbs are not the gap; the *grain and naming* of the mutation
surface is. Sugar sets the effort ceiling.

## 2. The criterion

Applied to **every op that mutates geometry, materials, or object placement-affecting
data**. Read-only ops (SENSE, per SPEC-20 §2) are out of scope and keep plain names.

### 2.1 The cut

**SUBSTRATE (keep — server invention allowed).** An op earns invention rights iff it
substitutes for hardware the agent lacks — the mouse, the eyes, the viewport:

- **Selection & addressing** — all of `select`, handles, `claim`, windows/`look`.
- **Perception & verification** — `feel`, `validate`, `view op=check_*`.
- **Relational placement** — the `on=` DSL, `rest_on`, `seat`, `snap`, `place`,
  `move_to`, `aim_axis`, `distribute`, `array_*` (multi-object placement is mouse work).
- **Invisible plumbing inside native ops** — auto mode switching, selection guards,
  densification (G213), unit discipline, auto-status. Robustness is absorbed, never
  exposed as a separately-named op.

**JUDGMENT SUGAR (strip → technique).** A mutating op is judgment sugar if ANY of:

- **(a) Outcome/use-case naming** — named for what the result *is for* rather than for a
  native operator (`gravity` = "a hanging drip", `field`, `loft`, `trace`,
  `shape_profile`).
- **(b) Compiled adaptation** — composes ≥2 native operators whose intermediate states an
  artist would inspect and react to. (SPEC-21 §4's one-status-block test, retained — but
  see §3: passing it is now *necessary, not sufficient*.)
- **(c) Shape divination** — accepts a declarative description of a form (keyed moulds,
  preset curves, sandboxed expressions) and interpolates the shape on the agent's behalf.
  This is the vending machine: it substitutes for the exact pointwise judgment loop that
  distinguishes craft from checkbox.

**RENAME-TO-NATIVE (keep, renamed).** Some ops are native operators wearing minted names
(`jitter` ≈ Mesh ▸ Transform ▸ **Randomize**). The operation stays; the name and docs
become the native ones. Misnaming a native op is the same stranding defect as minting.

**Litmus one-liner:** *if a human does it with a keystroke, give the keystroke; if a
human does it with the mouse or their eyes, the server may invent.*

### 2.2 Classification is derived, never recalled

SPEC-20 R3 governs both audits: classify by **reading the op's implementation** (what
`bpy.ops`/bmesh/modifier calls it makes) and by **introspecting the live 5.x build's
menus/operators** — never from model memory, which is version-stale and self-confirming.

## 3. Relationship to SPEC-20 / SPEC-21 (what this keeps and what it overrules)

**Keeps:** SPEC-20 R1–R4 (cousin tags, no cousin reimplementations, derive-from-build,
version anchoring). SPEC-21 §1 (three headspaces), §3 (family grammar: WHAT as parameter,
shared WHERE scope block, `amount` in meters), §5 (techniques/recipes shelves,
form-analysis-first).

**Tightens SPEC-21 §2 (vocabulary law).** Old: "the server may mint vocabulary only where
Blender is silent." New: **for mutation, Blender is never silent.** The operator basis is
complete as a basis; a mutation method Blender has no single name for is by definition a
*multi-step method* → it lives on the techniques shelf in native words. Minting rights
now apply only to non-mutating vocabulary (substrate).

**Explicitly overruled (do not be whipsawed by the older text):**

- SPEC-21 §4, `buttons-deform-macro` row: *"formula deforms remain primitive (Blender is
  silent → minting allowed) if they pass the status-block test."* **Overruled.**
  `field`/`loft` and kin are criterion (a)+(c) judgment sugar regardless of
  verifiability. The one-status-block test survives as a *necessary* condition only.
- SPEC-20 II.8 "stays put with a tag" as applied to construction macros `add type=tube` /
  `type=helix`: **overruled** — criterion (a)/(b); native paths exist (curve +
  `bevel_depth`, the 5.0 "Curve to Tube" GN modifier, Screw modifier) and the methods
  become techniques. (II.8 remains valid for the *substrate* ops it covered.)

## 4. Phase 1 — audit for judgment sugar

**Scope:** every mutating op on the surface — all of `edit`, `sculpt`, `add`,
`transform`, `modifier`, `material`, `object`, `uv`, `pose` ops that write. (Server
verb definitions in `server/`, implementations in `extension/` — e.g. `fields.py`,
`compose.py`, `rings.py`, `curves.py`, `connectors.py`, `bands.py`, `sculpt.py`,
`editmode.py`, `finishes.py`.)

**Method:** for each op, read the implementation (§2.2), then classify into exactly one:
`NATIVE-KEEP` | `RENAME-TO-NATIVE` | `SUBSTRATE-KEEP` | `STRIP→technique` |
`BORDERLINE`. Every `STRIP` and `BORDERLINE` row must name the native decomposition (the
operator sequence a human would use) — this becomes the Phase-2 technique.

**Pre-made rulings** (worked examples of the criterion; the audit fills in the rest):

| op | ruling | rationale |
|---|---|---|
| `edit op=field`, `op=loft` | STRIP | (a)+(c); overrules SPEC-21 §4 allowance |
| `edit op=shape_profile`, `op=trace` | STRIP | (a); lathe work = Spin/Screw + per-ring scaling technique |
| `edit op=jitter` | RENAME-TO-NATIVE | it is Mesh ▸ Transform ▸ Randomize |
| `edit op=noise_displace` | audit by code | if ≈ Randomize/Displace-modifier semantics → RENAME; if bespoke sampler → STRIP, technique over Randomize/Displace |
| `edit op=proportional_move/scale` | NATIVE-KEEP | proportional editing (O) — this IS the native craft primitive |
| `edit op=spin` | NATIVE-KEEP | native Spin operator |
| `edit op=bend` | audit by code | if thin Simple Deform wrapper → NATIVE-KEEP (modifier vocabulary); else STRIP |
| `sculpt brush=grab/draw/inflate/smooth/crease/pinch/flatten` | NATIVE-KEEP | native brush names |
| `sculpt brush=gravity` | STRIP | (a) outcome-named ("hanging drip"); technique: proportional/grab strokes + inflate, per the drip technique |
| `add type=tube/helix` | STRIP | (a)/(b); native: curve+bevel, Curve to Tube, Screw (overrules SPEC-20 II.8 for these) |
| `add` mesh primitives + `on=` DSL | KEEP | native Add menu + substrate placement |
| `transform op=rest_on/seat/place/move_to/aim_axis/snap/distribute/array_*` | SUBSTRATE-KEEP | multi-object placement = mouse work |
| `material op=toon/outline` | STRIP per SPEC-21 §4 | already ruled; confirm executed |
| `select` (all), `look`, `feel`, `validate`, `view` | SUBSTRATE/SENSE | out of scope, keep |

**Gate:** `BORDERLINE` rows are presented to the user for a ruling **before Phase 2
deletes anything**. The user owns the direction; the audit owns the evidence.

**Deliverable:** the classification table appended to this spec as Part II (house style,
cf. SPEC-20). **Verification:** every op in the registered tool surface appears in
exactly one row; every STRIP row names its native decomposition.

## 5. Phase 2 — remove judgment sugar

For each `STRIP` op, in order:

1. **Write (or update) the technique first** — `techniques/` in native vocabulary,
   capturing the method the verb compiled: the operator sequence, where perception reads
   go between steps, and what to check at each. Deleting a verb without landing its
   technique is knowledge loss and is **blocked**.
2. **Techniques carry effort norms.** Each craft technique states its expected cost in
   plain terms — e.g. *"the drip is 5–15 stroke→look cycles per drip; if you did it in
   one call, you skipped it."* The guidance entry point states the general norm: craft
   steps are loops, not calls. (The tool surface stops advertising effort; the teaching
   layer must start.)
3. Delete the op: server verb entry, extension implementation, flat-tool registration,
   validation entries, schema text.
4. Migrate references: `recipes/`, `GUIDANCE_FOR_LLMS.md`, technique cross-links, tests.

**Verification:** server registers cleanly; test suite passes; `grep -r` over the repo
finds no dangling references to deleted op names; each deleted op's technique is
reachable from the techniques index.

## 6. Phase 3 — audit missing native actions

**Method:** enumerate the native operator basis **from the live build** (§2.2): the
edit-mode **Mesh / Vertex / Edge / Face / UV** menus, the Select menu, and the daily
hotkey set; cross-check each against the surface. Object-mode dailies too (most already
exist: duplicate, join, apply).

**Seed list** (found missing or unverified while mapping the donut procedure — the audit
completes and corrects this against the build):

| native action | hotkey / menu | status on surface |
|---|---|---|
| Duplicate selection (in-mesh, leaves copy selected) | Shift+D | **missing** (its absence broke the icing step: `separate` rips, it doesn't copy) |
| Shrink/Fatten (per-vert normals) | Alt+S | `move_verts` out/inward exists — **verify per-vert-normal semantics**, fix if centroid-normal, add retrieval key |
| Rotate selection (with pivot) | R | missing (`move_verts`/`scale_verts` exist, no rotate) |
| Merge at Center / First / Last / Cursor | M | only merge-by-distance exists |
| Rip / Rip-Fill | V / Alt+V | missing |
| Split | Y | missing |
| Bisect | Mesh ▸ Bisect | missing |
| Shear | Shift+Ctrl+Alt+S | missing |
| To Sphere | Shift+Alt+S | missing |
| Smooth Vertices | Vertex ▸ Smooth | `relax` exists — RENAME/verify vs native |
| Dissolve Verts/Edges/Faces | Ctrl+X | missing (delete ≠ dissolve) |
| Hide / Reveal (edit mode) | H / Alt+H | missing |
| Edge Crease | Shift+E | `crease` exists — verify + retrieval key |
| Fill / Beautify | F | grid_fill exists; plain fill unverified |
| Triangulate / Tris-to-Quads | Ctrl+T / Alt+J | missing |
| Snap-to-face-projected vert dragging | Snapping: Face + Project | **missing as a transform mode** — the icing-drip trick; native name is Snapping, so this is basis work, not sugar (likely a `snap_to=<object>` flag on `move_verts`/`proportional_move`) |

**Deliverable:** the gap table appended to Part II, each row prioritized
(daily-driver first: the ops that appear in every tutorial outrank menu completeness).
**Verification:** every item in the live build's edit-mode menus has a row (present /
missing / renamed / deliberately-skipped-with-reason).

## 7. Phase 4 — implement missing native actions

Rules for every new (and retrofitted) mutating op:

1. **Native name, native semantics, native defaults.** The op does what the tutorial
   says it does. Robustness (mode switches, selection guards, G213 densification) is
   absorbed invisibly per §2.1 — never a separately-named variant.
2. **Hotkey + menu path as retrieval keys — mandatory.** The schema description begins
   with the native anchor, e.g.:
   `duplicate — Shift+D · Mesh ▸ Duplicate: copy the selected geometry in-mesh; the copy
   is selected and unmoved.`
   The hotkey is not decoration; it is the index the agent's training actually uses.
3. **Retrofit existing native ops** with the same retrieval keys (`extrude — E`,
   `bevel — Ctrl+B`, `loop_cut — Ctrl+R`, `inset — I`, `proportional_move — G with O`,
   `grow/shrink — Ctrl+Numpad±`, …).
4. **Family grammar** per SPEC-21 §3: shared WHERE scope block, `amount` in meters,
   member as parameter.
5. **Live-verify each op** on a real scene per the `gaps.md` discipline before marking
   done.

## 8. Phase 5 — stroke economics (parallel-shippable; the enabler)

The barebones bet multiplies call counts 5–10× (forty proportional nudges instead of one
`noise_displace`). Two costs currently punish exactly that behavior:

- **Ordered execution.** Dependent edit ops are serialized one-per-message today because
  batched calls race on arrival order (see the ⚠ in the `edit` verb docs). A craft loop
  cannot afford a full round-trip per micro-stroke. Deliverable: guaranteed in-order
  execution for batched dependent ops (server-side queue/sequence numbers), or an
  equivalent cheap sequencing mechanism.
- **Status weight.** Full status blocks on every micro-stroke bury signal. Deliverable:
  a terse status voice for small strokes (one line: what moved, how much, no-op flag),
  with the full block on demand or on anomaly.

Without Phase 5, economics quietly rebuilds the crutch: the agent that *knows* it should
do forty strokes still won't.

## 9. Definition of done — the acceptance experiment

Re-run the donut, blind (per the standing dogfood discipline: server instructions +
`guidance://llms` only, no repo docs). Success is **not** "a donut exists"; success is
that the transcript shows the craft steps being *worked*: the top-half duplicate for the
icing (Shift+D vocabulary), rim verts pulled into drips of varied depth with snapping,
inflate strokes on drip tips, stroke→look cycles in the double digits on at least one
craft step. The mesh is the evidence; the transcript is the measurement.

## 10. Open questions

- **Knife (K)** — inherently interactive (screen-space cut path); is a headless
  equivalent (bisect-per-segment) worth having, or is it deliberately-skipped?
- **`modifier` surface** — `strength`/`factor` drift deferred from SPEC-21 §3 audit;
  fold into Phase 4 if the modifier surface is touched.
- **Terse-status format** (Phase 5) — one line per stroke vs. rolling digest every N
  strokes; decide from a real craft-loop transcript.
- **Technique index discoverability** — SPEC-21 §5 requires technique-lookup to feel
  like the fast path; after Phase 2 the techniques shelf grows substantially. Does the
  guidance entry point need a per-form-class index (vessels, shells, drips, lathes)?

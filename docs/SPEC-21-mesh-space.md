# SPEC-21 — Mesh Space: the three-headspace constitution, landmark LOD windows, and selections that offer themselves

**Status: IMPLEMENTED — phases 1–5 shipped (2026-07-10); live re-verified on the VRoid scene same day (one gap found in the sweep: G222).**
Origin: design session 2026-07-10 (human + agent), grounded in two live dogfood runs —
the donut inflate retest (G208–G218) and the VRoid semantic-selection test
(G219–G221). This spec supersedes the *interface* philosophy of SPEC-02/-04/-06/-09
where they conflict; the machinery those specs built survives as plumbing.

---

## 0. Summary

Five decisions, each a corollary of the first:

1. **The three-headspace constitution** — the agent must live in *mesh space*; the
   server absorbs *Blender space*; *MCP space* must not exist.
2. **Vocabulary law** — mesh mutations answer to native Blender names; the server may
   mint words only for mesh-space concepts Blender has no word for.
3. **Verb grammar** — a verb is a *family*: one shared frame (WHAT / WHERE / HOW MUCH),
   discriminators as parameters, scope and magnitude vocabulary identical across verbs.
4. **Macros are retired as a category** — each is promoted to a native-named operation
   or demoted to a *technique* (prose over primitives). The test: if correct execution
   requires a perception read between steps, it cannot be a tool.
5. **Landmark LOD windows + offered selections** — the centerpiece, and *the loop*:
   look → descend → claim → modify is the agent's primary interface at all times, not
   a feature beside the old one. Perception becomes a recursive, self-similar descent
   through salience windows; selections are pre-computed candidates the agent *claims*
   rather than predicates it compiles; world coordinates never cross the wire. `feel`
   is relegated to diagnostics.

---

## 1. The constitution: three headspaces

There are three places an agent can spend a call:

- **Mesh space** — flow state. Every sentence is a fact about the form: "the shell is
  3mm thick", "the hem sits 2mm below the rim", "the bead hangs 9mm." This is where
  taste meets precision, where THE ONE RULE lives (provenance chains are mesh-space
  objects), and where the agent must spend as close to 100% of its calls as possible.
- **Blender space** — battling the machine: modes, modifier stacks, selection-state
  plumbing, boolean solvers, flipped normals. Humans struggle here too (half of every
  tutorial's comment section). The server's job is to *absorb* this space: keep the
  native vocabulary (that's the tutorial bridge) but eat the machinery — auto mode
  handling, auto-status, the validate floor, unit discipline, densification (G213).
- **MCP space** — the server's own inventions: minted verbs, op discriminators,
  schema-shaped detours, `teach()` correction loops. Pure overhead. Nothing about the
  donut is learned here. This space is a defect wherever it exists.

**The design test, applied to every future gap fix:** read the agent's call transcript
aloud. Every sentence should be about the mesh. "Cut a loop 4mm below the rim" passes.
"Switch to edit mode first" means the server failed to absorb (Blender space leaked).
"op=clad" means the server minted (MCP space leaked). Both are bugs — in different
spaces.

## 2. Vocabulary law

**The server may mint vocabulary only where Blender is silent.** `feel`, handles,
`on=` placement, `validate op=expect` are legitimate inventions: Blender has no words
for perception, relational addressing, or declared intent, and those are the server's
actual contribution — they are mesh-space words. But anything that *mutates a mesh*
answers to its native name: loop cut, extrude, bevel, shrink/fatten, solidify, spin,
bridge edge loops.

Why this is load-bearing, not cosmetic:

- **The agent's knowledge is indexed by native vocabulary.** Training is thousands of
  tutorials keyed to "Shift+D", "Alt+S", "Select More". A minted word (`clad`)
  disconnects a tool from everything the agent already knows about when to use it,
  what it should look like, and what usually goes wrong.
- **The human's knowledge is indexed the same way.** The partnership model (human owns
  taste, watches the viewport, speaks direction) only works if the words the human
  learned from YouTube are the words the tools answer to. If the agent speaks tutorial
  vocabulary, *every Blender tutorial ever made becomes a potential technique doc*.
- The tell was already in the README: every macro carried a "native cousin"
  annotation. If every minted word needs a translation note back to mesh space to be
  usable, the translation layer is the bug.

## 3. Verb grammar: families

A verb is a family with one shared frame, learned once:

- **WHAT** — the family member, as a *parameter*, never a new op: `brush=inflate`,
  `type=torus`, `asset="Scatter on Surface"`. New members are new enum values plus a
  small tail — never new schemas. (The `sculpt` verb already has this shape; it is the
  model.)
- **WHERE** — the scope block, *globally identical across every verb*: `target=`,
  `at=`/`handle=`/window (§6), `radius=`, the live selection. A scope is a scope
  whether it is being sculpted, moved, or selected.
- **HOW MUCH** — a magnitude in meters, plus a falloff. One name (`amount`), one unit,
  everywhere.

The disease this cures is **frame drift**, not op count: `gravity` taking
`strength`/`pin` while its siblings take `amount`; `grab` taking seven directional
params instead of a magnitude; object-mode selects returning no count while edit-mode
ones do. Every drift is one more thing the agent memorizes instead of deriving.
**Deliverable: a grammar audit across all ~15 verbs; every drift is a bug.**

Per-member tails never fully disappear (a torus needs two radii; flatten needs a
plane) — the test is that the frame carries the semantics and the tail stays small.
When a member's tail outgrows the frame (`bud`: diameter/hang/neck/direction/solver),
it is not a family member; it is a composite wearing a costume.

## 4. Macros: the category is retired

**The one-status-block test:** an operation is a legitimate tool iff one before/after
status block can verify the whole thing — however many loops run inside. If correct
execution requires a perception read *between* steps, the adaptation between those
steps is agent work, and compiling it into code produces G217: a macro whose failure
mode is "success." A composite is structurally exempt from derive-don't-divine — that
is the deep defect, worse than op proliferation.

Disposition of the six:

| Macro | Verdict |
|---|---|
| `buttons-shell-macro` (`clad`) | Passes the status-block test but fails the vocabulary law. → **technique** in native words (select region → duplicate → solidify/shrink-fatten), plus native `solidify` exposure where missing. |
| `buttons-lathe-macro` | `shape_profile` = one general operation (radial profile along an axis) → candidate primitive under a native-adjacent name; true revolves → expose native **Spin / Screw**. `taper_end`/`flute`/`scale_rings` = presets → technique parameters. |
| `buttons-blend-macro` | Native names exist: **boolean modifier**, 5.x **SDF grid** family. Expose natively; smooth-union recipes → technique. |
| `buttons-deform-macro` | Native cousins (Simple Deform, Lattice, Curve) exposed natively; formula deforms remain primitive (Blender is silent → minting allowed) if they pass the status-block test. |
| `buttons-connector-macro` | Largely native **Curve to Tube** GN modifier wearing a costume → expose natively + technique. |
| `buttons-npr-macro` | A look *setup* → **technique** over material/render ops. |
| (`bud`, already dead per G217) | **Delete.** The missing primitive is native: **Bridge Edge Loops** (weld a neck ring to a cut ring). The drip becomes a technique: clad-sequence → gravity brush → bridge loops. |

**Anchoring rationale (why deletion, not repair):** the tool list is the agent's
ontology. A `lathe` in the inventory doesn't just enable lathing — it advertises it,
and tool selection pattern-matches names before form analysis ("block out a character
→ I have lathe → cylinder + lathe"). Schemas say WHAT; only prose can say WHEN. So the
WHEN knowledge moves to the teaching layer (§5), and surviving ops are named by
*geometric condition* (surface of revolution), never by use case (flute).

## 5. The teaching layer: techniques and recipes

A recurring pattern can live in three places: code (primitives), compiled sequences
(macros — now banned), or prose. Art is the same use cases applied differently — and
"applied differently" is adaptation, which is what the agent is *for*. A macro freezes
the adaptation into code where it can't happen; prose leaves it to the agent, live,
with feel reads between steps.

Two shelves:

- **Techniques** (`guidance://techniques/…`) — named, reusable multi-step methods in
  native vocabulary: the drip, the ring-weld seam, form blockout, revolved vessels.
  A technique promises an *approach*, applied differently each time.
- **Recipes** (`recipes/`, as today) — verified end-to-end transcripts that mint a
  specific asset (the donut, the hand). A recipe promises a *result*.

**Form-analysis-first:** the guidance entry point teaches — *before choosing any tool,
classify the form; then pull the matching technique.* This breaks tool-list anchoring
upstream, at the moment it fires. Techniques must be indexed and served on demand
(not preloaded), and the entry guidance must make technique-lookup feel like the fast
path, or the efficiency gradient will skip it.

## 6. Landmark LOD windows — perception and selection as one organ

### 6.0 Root causes (from the VRoid transcript)

Three semantic selections (right index finger, nose, left nipple) cost ~25 calls and
produced one confidently-wrong diagnosis (a fingernail island misread as a tool bug —
G219). The two root causes:

1. **The attention lived in the agent, not the server.** Every verb was a stateless
   one-shot; the agent re-serialized its own focus into coordinate bands on every
   call. The agent was the RAM of the perception system.
2. **Look and select had no shared currency.** `feel` answered in prose and scalars;
   `select` listened only to numeric predicates; every noun ("the finger") existed
   only in the agent's head, compiled by hand into predicates, verified by paid calls.

The human loop this must match: **Look → Select → Modify → Repeat** (agentic ReAct),
where the human gets two primitives for free — *point at what you see* and *watch
while you hold* — plus an implicit third: persistent attention (where I'm looking, at
what scale).

**This loop is THE interface, not an addition.** Windows, landmarks, and claims are
how the agent works at all times — every modeling session runs on look → descend →
claim → modify. `feel` is demoted to a **diagnostic instrument**: precise measurement,
relational forensics (distance/gap/contacts/clearance, §6.4), fit/verify reads, and
"wtf" moments when the window view and the agent's expectation disagree. Reaching for
`feel` mid-build should be the exception that signals something is off — the way a
human drops into the N-panel or a measuring add-on only when eyeballing has failed.

### 6.1 Windows and descent

**The server can never know what the mesh is.** It reports *salience*, never
semantics: protrusions, density anomalies (concentration), boundaries, islands/shells,
symmetry pairs, edge loops. The agent brings semantics from training ("a humanoid's
two top protrusions are arms") and records them at claim time (§6.3).

- `look target=<obj>` opens the **root window**: one orientation line (extent,
  up/front, shell count, symmetry plane) + **5–9 landmarks**, salience-ranked, each
  with: a position-in-window token (`top-right`, `center-front`, `rightmost`…), its
  salience channel (protrusion / island / density / boundary / loop), scale, and face
  count. The tail is *grouped, never dropped silently*: "6 major + 59 minor shells,
  clustered by size."
- `look at=<landmark|position-token>` **descends**: the same breakdown, re-run scoped
  to that window at proportionally finer scale. Self-similar — one algorithm, one
  output shape, learned once. Zoom *is* the scale picker (a body-scale relief scan
  can't see a nose; the face-front window scans at its own scale and the nose is
  simply there).
- The server holds the **window stack** (current window = the attention state);
  `look up` pops; window/landmark ids are stable within a session. The agent
  addresses by position within the current window — the way humans talk.

Projected cost on the live tests: finger 4 calls (was 12, incl. a false diagnosis),
nose 2 (was 5), nipple 1–2 (was 5) — the valence-8 fan pole is a first-class *density
landmark*, not something excavated from a 188-vert coordinate dump. Target:
**calls ≈ decisions.**

### 6.2 Coordinate starvation — the data model

THE ONE RULE, enforced by the type system instead of by discipline:

- **Faces** are the default currency. A bottom-level window answers with faces as
  **surface areas**, ordered by connection — BFS rings out from the window's center
  ("ring 0: 1 face 2.1mm² · ring 1: 4 faces · …"), which reads the way grow walks and
  an eye scans.
- **Edges** appear as **lengths**, and are offered as *loops and rings* (how humans
  actually use edge mode), only at low LOD or when the count is small.
- **Verts** are gated behind LOD-ing into a **single face**. Only there does XYZ
  appear — and only in a **local frame** (0,0,0 at the window/face origin, axes from
  the window's principal frame). Each vert also reports **which faces it shares** —
  the incidence list; a pole announces itself as "shares 8 faces."
- **World coordinates never cross the wire.** Frame transforms are always the
  server's job ("move this vert 2mm toward the window's front" — resolved
  server-side). The coordinate-dumping reads (`select op=list` world XYZ) are
  demoted to a debug flag, off the default path: they are the escape hatch that keeps
  the agent living in coordinate space, and they fed the G219 misdiagnosis.

### 6.3 Selections offer themselves

The agent cannot click, but it is excellent at choosing from a labeled list — so the
work moves to the side of the interface that is good at it.

- **Pre-selectables:** in every window the server pre-runs the cheap segmenters —
  saturating grow per island ("autorun Ctrl+Numpad+"), crease-bounded flood regions,
  protrusion cuts, edge loops, material/vgroup patches, symmetry twins — and offers
  the results as candidates: *already handles internally, ephemeral until claimed.*
- **Claiming:** `select candidate=<id> as=<name>` mints it permanently (vgroup-backed,
  in the .blend per G218 — a scene fact). Omit `as=` to select without minting.
  Unclaimed candidates are discarded on window change — garbage-collected perception.
  The claim moment is *exactly where semantics enters the system*: the server offers
  an anonymous coherent chunk; the agent christens it `right_index_finger`; the
  handle records the interpretation the server never had to hold.
- **Region algebra:** selections/candidates are trivially added to or subtracted from
  an existing handle (`select add=<handle>` / `subtract=`), so regions can be
  assembled across windows ("rim minus drip_zone" is one call, in mesh space).
- **Mirror twins:** on a bilateral mesh every claimed candidate has a computable twin;
  claiming `left_nipple` prompts "mirror twin exists — claim as `right_nipple`?"
- **Coverage honesty (anti-anchoring):** a menu anchors, same as the macro list did.
  Every offer ends with a coverage line ("5 candidates cover 78% of this window's
  faces — 22% unoffered"), and custom predicate selection stays first-class as the
  escape hatch, not the default path.
- **`pick` — the yolo click (G221):** one arbitrary vert/edge/face within a named
  scope (window, candidate, handle, object), deterministic under a seed so
  transcripts replay. Its essence is *permission to not care which element* — paired
  with narrated grow it reproduces the human's click-and-hold-and-watch.
- **Narrated expansion (G219/G220):** every mutating select answers in feel's voice —
  count *plus* a one-line description of the grabbed region (connected patches,
  extent, position, component identity, boundary-crossing flag). Expansion ops report
  before → after and, on Δ=0, say *why* ("selection is a closed component — its own
  shell"). A count is a checksum with no reference value; component identity ("you
  grabbed exactly shell #41 of 65") is the single most decision-relevant property a
  selection has on real game meshes (nails, teeth, eyes, buttons).

### 6.4 Cross-window relations

"Is the hand clipping the hip?" spans branches. Relations between two windows are
expressed in the **nearest common ancestor's** frame. `feel`'s relational reads
(distance, gap, contacts, clearance) survive unchanged as exactly this — the
between-windows sense. The validate floor is untouched by this spec.

### 6.5 The loop is a contract (guidance requirement)

Once implemented, `GUIDANCE_FOR_LLMS.md` must call the loop out **explicitly and
first**: agents should *expect* to work as look → descend → claim → modify — it is
the normal mode of operation, not an advanced feature to discover.

And the contract cuts both ways: **if the loop is broken, the agent is exonerated.**
A window that misses a landmark, an offer list without the right candidate, a
narration that misleads, a descent that dead-ends — these are server defects, never
operator error. The guidance must say so in as many words, and prescribe the response:
log the gap (gaps.md discipline), use the declared escape hatches (custom predicates,
`feel` diagnostics), and continue — do NOT silently grind back into coordinate space,
do NOT contort to compensate, and do NOT treat the failure as your own. This is the
blind-dogfood principle with teeth: a loop the agent must work around is a defect in
the loop. (The VRoid fingernail incident is the cautionary tale — an agent hallucinated
a root cause partly because it assumed the fault was in its own usage rather than in
the tool's silence.)

### 6.6 Persistence and invalidation

The selection persists into modify (Look → Select → Modify → *more* Modify), exactly
as today's edit-mode ops act on the live selection; claimed handles persist in the
.blend. Windows are invalidated lazily by topology edits — the next `look` recomputes;
landmark ids from a stale window resolve via their backing vgroups where possible and
error legibly where not.

---

## 7. What this retires or subsumes

- The six macro tools (§4) — deleted from the surface after disposition.
- `select`'s 21 predicate ops and `feel`'s read menu — demoted from interface to
  plumbing under look/descend/claim/pick; predicates remain first-class as the custom
  escape hatch.
- `feel` as the primary perception verb — demoted to diagnostics (§6.0): measurement,
  relational forensics, verify/fit, and wtf moments. The loop's eyes are `look`.
- World-coordinate dumps — behind a debug flag.
- Gaps **G219, G220, G221** are absorbed by §6.3 (their standalone fixes remain
  worthwhile incremental steps — see §9 phase 1). **G217**'s fix direction is
  replaced by §4 (delete `bud`; expose Bridge Edge Loops; write the drip technique).
  **G218** (declarations are scene facts) is reaffirmed and extended to claimed
  handles.

## 8. Evidence

- **Donut retest (2026-07-10):** G208/G212/G213/G215 fixes hold live; `bud` failed
  both solvers on the open shell it was built for (G217) — the case study for §4.
- **VRoid test (2026-07-10):** 3 semantic selections = ~25 calls; ~8 calls were pure
  verification the select could have returned for free (§6.3 narration); a correct
  grow no-op on a fingernail island was misdiagnosed as a server bug *and committed
  to gaps.md* because "GROW x4" carries zero ground truth (G219) — while the human
  identified the nail from the viewport in one glance. Body = 65 shells; the nipple
  was found only via a valence-8 pole in a manual vert dump — a density landmark §6.1
  surfaces in one zoom.

## 9. Migration (phases, each shippable alone)

1. **Ground-truth patches to the current surface** (no redesign): narrated selects +
   Δ-reporting expansion + component identity (G219/G220); `pick` (G221); grammar
   audit fixes (§3). Immediate value regardless of the rest.
2. **`look`/descend windows, read-only**, alongside the existing surface — prove the
   breakdown quality on the VRoid + donut scenes.
3. **Offered selections + claiming** (ephemeral handles, region algebra, twins,
   coverage line).
4. **Coordinate starvation**: local-frame vert views, world-XYZ behind debug.
5. **Macro disposition + techniques shelf** (§4, §5) and the guidance rewrite:
   form-analysis-first, the loop taught explicitly as the expected way of working,
   and the exoneration clause (§6.5) in as many words.

## 10. Open questions

- ~~Is `look` a new verb or the evolution of `feel op=all`?~~ **Decided (sign-off
  session):** `look` is a new verb and owns the loop; `feel` is relegated to
  diagnostics and wtf moments (§6.0).
- BFS-ring linearization details for non-disk patches; loop detection thresholds.
  **Linearization decided (phase 4):** BFS distance is well-defined on any
  face-adjacency graph, so non-disk patches need nothing special; a multi-shell
  window restarts BFS per shell at the unvisited face nearest the window centre
  (`shell 2 · ring 0: …`). Loop thresholds stay open.
- Window invalidation policy under heavy topology edits mid-descent.
- Candidate-generator tuning (crease angle, protrusion scale) and the definition of
  the coverage metric. **Coverage decided (phase 3):** the line reports BOTH
  face-count % and area-weighted % (a flat floor and a dense detail patch weigh
  differently; anchor to neither). Generator knobs stay open for live calibration.
- Token budget per window reply (the "context-rich, not flooding" line) — likely
  needs live calibration against real meshes.
- Ephemeral-candidate lifetime rules for deterministic transcript replay.
- Sister project: ue-buttons should adopt the constitution (§1) and the offered-
  selection concept once proven here; UE's own vocabulary (not Blender's) fills the
  native-name slot there.

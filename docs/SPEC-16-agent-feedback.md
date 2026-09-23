# SPEC-16 — Agent feedback: forced perception (`feel`) + an always-on correctness floor (`validate`)

_Status: Implemented 2026-06-23. Net-new **perception/correctness** primitive. Supersedes this
spec's earlier "auto-feel" draft, whose gauge/trigger machinery dissolved once the two jobs it
conflated were split apart (see "What this supersedes")._

> **Implementation notes (2026-06-23).** The engine lives in `extension/validation.py` (a thin
> aggregator over the existing detectors in `lint.py` / `introspect.py` — no new detection
> logic), wired into the single post-op chokepoint (`extension/server.py::execute_command`) and
> rendered by `server/_core.py::_status`. The `validate` verb is `server/verbs/validate.py`;
> `feel op=all`/`exclude`/`stats` extend `server/verbs/feel.py`; the human panel is the SPEC-12
> Collab panel (`extension/ui.py`). Tests: `tests/e2e_spec16.py` (31 checks). Deliberate scoping
> choices that depart from a literal reading: (a) the always-on `validate` runs after
> **geometry/placement** ops (`VALIDATE_AFTER`), not literally every op — a material/rename
> changes no geometry, so there is nothing new to validate; (b) the declared-intent registry is
> **scene-scoped** (module-global, cleared on scene load) rather than persisted — a "Hair↔Body"
> intent is a fact about *this* scene; only the telemetry persists cross-session; (c) the ambient
> `feel` delta is a minimal counts+dims note on the touched object (honest + self-bounding, not
> yet edit-proportional); (d) the `feel op=all` bundle is the whole-mesh reads — selection-scoped
> members (`region_form`, `fit`) and their context auto-skip telemetry are a follow-on. validate's
> clipping check generalises the old G77 placement self-report, which is retired from the dispatch
> (the `auto_proximity_note` function stays for `feel op=contacts`). Post-dogfood additions: an
> epistemic-DRIFT re-ground checkpoint (G117 — the auto-feel gauge's idea recast as a re-anchor ON
> TOP of the per-op spine, triggered by weighted drift not mutation count), delta-scoped clipping
> with a TRUE recomputed penetration depth (G111), bulk/collection `expect` + `forget` + verbose
> `run` (G112), and `feel` echo gated to topology-changing ops._

---

## The problem

The agent's whole method rests on **read-then-act**, and the read is supposed to be `feel`. But
`feel` is **elective**, and the better the mutating tools get, the less the agent ever elects to
use it. When the tooling is good the agent just lets it rip — which is *correct, desirable*
behaviour — and never considers that a pile of rough edges is hiding under `feel`: z-fighting from
a coplanar placement, a shell poking through, flipped normals, non-manifold junk from a boolean.
On a simple mesh this is fine; there is little to diverge. It **gets out of control with scene
complexity**, where unverified divergence compounds and a session that made *one* `feel` call
drives the scene into a wall that costs a full rework.

The root cause is behavioural, not instrumental, and naming it dictates the whole design:

> **The model is a *reactor*, not an *inspector*.** It reacts brilliantly to information put in
> front of it; it almost never elects to go *get* information it wasn't handed. Diligence cannot
> live in the model's disposition — and shouldn't, because the disposition that skips inspection
> is the same one that makes it productive.

So every design that asks the model to *decide* to verify fails the same way — a nag or a debt
meter asks it to *consider*, which is the very act it skips in flow; mis-tuned, it goes wallpaper
and trains the reflex *down*. And the status block can't carry the missing signal no matter how
polished: it is a **single-object spotlight** (the active object) plus a couple of scene-globals,
so a relational defect (z-fight, overlap) — which needs ≥2 objects and the relation between them —
can never appear in *any* per-op block. Worse, its **silence reads as "all good,"** manufacturing
false confidence.

### Two epistemics were overloaded into one verb

`feel` today does two unrelated jobs, and the overload is the deeper bug:

- **Perception** — "here's what exists." Descriptive. **No true/false.** (`profile`, `section`,
  `silhouette`, topology structure, `region_form`, …)
- **Defect-detection** — "here's what's broken." A **predicate**, with findings and a verdict.
  (`validate`, `overlaps`, `contacts`, `clearance`, …)

These are different acts and belong in different verbs. Splitting them is what makes the rest of
this design fall out cleanly.

## The principle: feedback is a property of the system, and there are two forced senses

Stop trying to make the agent *choose* to look. **Perception is not a choice** — you can't build
with your eyes closed, so don't give the agent eyelids. There are **two senses, both forced,
neither opt-out**:

- **`feel`** — *perception*. "What exists." Feeds the agent's **intent**-check: the agent compares
  what-exists against what-it-meant-to-build. `feel` holds no verdict; it *enables* the judgement.
- **`validate`** — *correctness*. "What's broken." An always-on predicate that enforces objective
  invariants the agent can't be trusted to remember to check.

One checks intent, the other checks correctness. The agent gets both after it acts, whether it
asked or not.

---

## `feel` — forced perception

### The ambient register (forced, every op)

After each mutating op, the result carries a cheap perceptual **delta** — *"here's what you just
changed"* — proportional to the edit (a small edit → a small note; a structural change → a richer
one). It is a *description*, never a verdict, and it describes **what changed**, not a re-narration
of the whole mesh (which would be both expensive and banner-blinding). This is the floor of
perception: the agent cannot opt out of seeing its own work.

`feel` is **delta-scoped and therefore self-bounding** — it only ever perceives what the agent
*touches*. A huge untouched backdrop in the scene is never re-felt, so perception cost tracks the
agent's actual edits, not scene size.

### The deliberate register (rich, on-demand) — `op=all` by default

For looking closely, the full perceptual ops stay available — and the friction is **reversed**.
Today the agent must know which op to ask for and type it in, and *choosing the right read is
itself an inspector-move the reactor is bad at*. So:

- **`feel op=all` is the default** (a bare `feel` resolves to it): runs the full perceptual bundle,
  and the agent **opts *out*** with `exclude=` (`feel op=all exclude=silhouette,symmetry`). Breadth
  is free; trimming costs a keystroke — the reverse of today. Inverting the default removes a
  decision the agent keeps getting wrong, not just keystrokes.
- **Targeted reads still work** — `feel op=section axis=Z` is unchanged. The precise path survives;
  only *breadth* stops requiring effort.
- **Graceful auto-skip.** Perceptual ops needing context the call lacks — a live selection
  (`region_form`), minted handles — are **skipped, not errored**, and the skip is recorded as
  *context-unavailable* (distinct from an explicit `exclude`, for the telemetry below).
- **Verbosity rides the existing `lod`.** A *manual* `op=all` is a deliberate question, so it talks;
  `lod=low` pulls it back toward a summary.

The perceptual bundle: topology (structure / components / genus / boundaries / poles), `profile`,
`section`, `silhouette`, `rings`, `region_form`, `curvature`, `frame`, `fit`, the casting reads,
and `symmetry`'s *measurement* (mirror plane + error — a description, not a defect). It does **not**
contain the predicates; those are `validate`.

---

## `validate` — the always-on correctness floor

`validate` runs **after every operation**. It is the generalisation of the placement self-report
the status block already does (`"X now penetrates Y 6mm"` on every placing op) — extended to the
full defect set on the **touched delta and its relations**. Because it is a *cheap predicate*, it
needs **no schedule, no countdown, no debt meter**: it just runs. (A full-scene sweep, if ever
warranted, is a heavier variant — but the always-on common case is validating the delta.)

### Intent-free defects — unsuppressable

z-fight (coincident coplanar surfaces at the same depth — cleanly distinguishable from honest
interpenetration), non-manifold edges, flipped/inconsistent normals, degenerate faces. These are
**never wanted**, so there is **no way to suppress them.** A false fire here is *`validate`'s own
tolerance bug to fix* — not the agent's to mute. There is deliberately no "false positive" tag and
no "tolerance" tag; those would just be the easy dodge wearing a different hat.

### Intent-laden checks — governed by *declared* intent

Clipping, collision/penetration. These run always too, but intersection is **frequently
intended** — VRoid hair roots seat under the scalp; a tenon belongs in its mortise — so a raw
scanner cries wolf. The agent resolves this not by *inferring* intent (impossible) but by
**declaring** it, once.

#### Declaring intent (agent-side, narrow) — a positive assertion, not a mute

- **There is no `ignore` op.** The only affordance is `validate op=expect` (alias `intend`). The
  grammar itself sets the bar: the agent cannot reach for a mute, only *assert an expectation*.
  "ignore it, it's noisy" is a free dodge; *"I intend Hair to clip Body"* is a falsifiable design
  claim — one an LLM is far more reluctant to type falsely, and one a human spots instantly in the
  panel. The assertion carries its **reason** verbatim
  (`intended: clipping Hair↔Body — "hair roots seat under scalp"`); a fabricated reason is what
  makes a bogus claim cheap to catch on review.
- **Scoped to the *relationship*, never the mesh.** A flat `{Hair: ignore_clipping}` is not an
  intent declaration, it's a **sanctioned blind spot**: it would also hide a *new, unintended* clip
  (Hair through a Hat) later. The key is `(check, counterpart)` — *"Hair intends clipping **with
  Body**"* — so Hair↔Hat still fires. Self-checks with no counterpart key on `(mesh, check)`;
  relational checks key on the pair.
- **Suppress, don't silence.** A declared-intended finding **collapses to a count**, it never
  vanishes: `clipping: 1 intended (Hair↔Body) · 1 NEW: Hair↔Hat 8mm`. You can demote the noise, not
  destroy it — so over-tagging produces a *visible pile* of "14 intended," which is itself the
  signal that something's being plastered. Silence hides abuse; a running count exposes it.
- **The intended-set is a registry of invariants, enforced *bidirectionally*.** Not a mute list — a
  set of declared facts about the design that `validate` continuously holds true:
  - a clip that *appears* and isn't declared → finding (the classic case);
  - a clip *declared intended* that *vanishes* → finding (`Hair↔Body intended-clip is gone —
    confirm or clear`). This subsumes any "re-confirm a stale tag on geometry change" mechanism: the
    invariant breaking *is* the trigger, and it's more precise.
  - Consequently every `intended` tag is a **standing liability**, not a one-time silence — plaster
    47 of them and you've signed up for 47 tripwires that fire the moment the scene shifts. Tagging
    stops buying quiet and starts buying a thicket. (A *structural* anti-plaster force, not a
    guidance one — which is the kind that holds.)

Suppression exists **only for the intent-laden checks** plus the two intent-free checks that are also declarable: self-intersection (realized contact) and below-floor (a ground body or parked scrap). The rest of the intent-free defects have no tag at all.

### Human governance (human-side, blunt) — via the panel

The asymmetry is the principle: **blunt instruments to the human, fine instruments to the agent.**
The agent is denied a global mute *by design* (that's the plastering we prevent); the human owns
intent at the top level and owns the consequences, so the human gets the sledgehammer. All of this
extends the existing **collab panel (SPEC-12)** rather than a new surface:

- **The registry view.** The panel lists every `intended` assertion — pair, reason, status
  (holding / vanished). The human can **revoke** any (overruling the agent — "that clip's a bug,
  fix it"; revocation re-arms the finding) or **add** one.
- **Override by exclusion, scoped.** "I just imported an 80M-quad backdrop; don't validate it."
  Critically this must be **exclusion from computation**, *not* the agent's output-suppression —
  collapsing 800 messages to a count still *ran* 800 checks, and the cost on 80M quads is the
  *checking*, not the printing. So a human **per-mesh / per-collection mute** takes that object out
  of scope entirely (no work done), while validation continues on the character actually being
  built. **Global off** is the sledgehammer above that.
- **A disabled validator must announce its own absence.** This is the trap to avoid: silence
  already reads as "all good," so a *silent* override rebuilds blind-flow with the human's blessing
  — the exact failure mode this spec exists to kill. When validation is off (globally or for a
  mesh), every status block must say so out loud — `validate: OFF (human override) — floor is down`
  — so silence-because-off can never be mistaken for silence-because-clean, and the agent knows to
  compensate.

---

## Telemetry — tune the bundles from data, not taste

What each bundle *should* contain is empirical. Instrument it, persist across sessions to a small
on-disk JSON (per-session counts are too sparse), and read via `op=stats`:

- **`validate` — finding-yield per check** (the strong signal). How often a check, when it runs,
  *produces a finding* vs comes back clean. A check that has surfaced **zero** findings across
  hundreds of runs is pure cost regardless of preference — yield measures *value* directly. Plus
  **intend-rate** (how often a check needs an intent declaration) as a weaker, preference signal;
  keep explicit `intend` distinct from context auto-skip, and flag bulk declarations so they don't
  skew the ranking.
- **`feel` — exclusion-rate only.** Perception has no findings, so finding-yield is meaningless
  here; the `op=all` default membership is tuned purely by what agents trim (with the same
  bulk-exclude / auto-skip caveats).

---

## Why this preserves "let it rip"

The cost falls **entirely on the system, and entirely on the moments something is actually wrong**:
`validate` reports by exception (clean checks collapse to counts), `feel`'s ambient note is a small
proportional delta. On a clean scene nothing of substance speaks and nothing slows down — the agent
rips exactly as today. And the floor **self-scales to the danger**: divergence and per-edit defect
odds both rise with scene complexity, so the feedback bites precisely where blindness gets
expensive and stays quiet on the simple meshes where the reactor is already fine.

## What it deliberately does not do

- **No taste judgement.** `validate` reports *that* something is broken; `feel` reports *what's
  there*. Neither rules on whether a shape is *good*.
- **No auto-fix.** It surfaces; the agent (or human) decides. It never silently mutates geometry to
  "correct" a finding.
- **No agent global-mute.** The agent gets one narrow, positive affordance (`expect`); only the
  human gets blunt overrides.
- **Nothing silent that shouldn't be.** Silence-because-clean and silence-because-disabled are
  never allowed to look alike.
- **`feel` needs no override.** It is delta-scoped, so it never perceives an untouched behemoth;
  the override is purely a `validate` concern.

## What this supersedes

The earlier "auto-feel" draft scheduled an *expensive elective* check with an autocompact-style
**countdown gauge** and three **triggers** (edit-threshold, blur/flush-on-focus-loss, a Stop hook).
All of that **dissolves** once the defect-detector is split out as a *cheap always-on predicate*:
a check that runs every op has nothing to schedule, no debt to accumulate, and no abandonment to
catch. The "auto-feel" name was itself the conflation — it labelled the defect scanner as
perception. What survived: the reactor-not-inspector framing, report-by-exception, the
`op=all`/`exclude` friction inversion (now on `feel`), and the telemetry (now split — yield for
`validate`, exclusion-rate for `feel`).

## Surface

- **`feel`** (perception): bare `feel` / `feel op=all [exclude=…] [lod=…]` → full perceptual sweep;
  targeted ops (`op=section …`) still addressable; ambient delta auto-attached to every mutating
  result; `feel op=stats`.
- **`validate`** (correctness): runs after every op — block lines report by exception
  (`validate: clipping 1 intended (Hair↔Body) · 1 NEW Hair↔Hat 8mm; 4 clean`); `validate op=expect`
  / `intend` (pair, reason) to declare intent; `validate op=intended` lists the live registry;
  `validate op=stats`.
- **Panel (SPEC-12 extension):** the intended registry (revoke / add), per-mesh / per-collection
  and global validation overrides.
- **OFF banner:** `validate: OFF (human override) — floor is down`, on every block while disabled.

## Tests (sketch)

- Ambient `feel` delta attaches to every mutating result, proportional to the change, and is
  delta-scoped (an untouched mesh is never described).
- `feel op=all` (and bare `feel`) runs the full perceptual sweep; `exclude=` trims; targeted ops
  resolve to a single read; context-dependent ops auto-skip (tallied as *context-unavailable*).
- `validate` runs after every op; intent-free defects (z-fight / non-manifold / normals / degenerate)
  have **no** suppression path. `below_floor` and `self_intersection` are declarable; undeclared, they still fail.
  `below_floor` measures the evaluated shell when a modifier is viewport-enabled (B17): a Subsurf
  cage hangs outside the surface `rest_on` seats, and judging the cage reports a seated plate as
  dipped through the floor.
- `intend` is scoped to `(check, counterpart)`: declaring Hair↔Body intended collapses that finding
  to a count but a later Hair↔Hat clip still fires.
- Bidirectional enforcement: a *declared-intended* clip that disappears raises a confirm/clear
  finding.
- Human per-mesh override **excludes from computation** (the check does not run); global off raises
  the OFF banner on every block; nothing goes silently unchecked.
- `op=stats`: `validate` ranks finding-yield + intend-rate; `feel` ranks exclusion-rate; both
  persist across sessions and flag bulk declarations.

## Agent-facing copy (to land with implementation)

> **For `GUIDANCE_FOR_LLMS.md`** — new section:
>
> ### You build with two senses, and you don't get to close your eyes
>
> After every edit you get two things you did not ask for, because building blind is the most
> expensive failure here:
>
> - **`feel` (what exists)** — a short note on *what you just changed*. No verdict; it's your eyes.
>   Read it against what you *meant* to build. When you want a closer look, `feel op=all` (the
>   default — a bare `feel` resolves to it) runs the full perceptual sweep; opt out with `exclude=`
>   only when you have a reason. A lazy read is already a broad one.
> - **`validate` (what's broken)** — a correctness check that runs whether you like it or not.
>   z-fighting, non-manifold edges, flipped normals, degenerate faces are **never OK and cannot be
>   silenced** — if you see one, fix it before you build on top of it. Clipping/collision is
>   different: it's sometimes *intended* (hair through a scalp). When it genuinely is, **declare
>   it** — `validate op=expect` naming the pair and *why* ("Hair clips Body — roots seat under the
>   scalp"). There is no "ignore" — only "I intend this." That bar is on purpose: an `expect` you
>   can't honestly justify is a bug you're hiding, it stays visible to the human in the panel as a
>   count, and it becomes a tripwire that fires if the intended overlap ever *disappears*. Declare
>   the few real ones; never paper over the noisy ones — the noise is the mesh telling you it's
>   broken.
>
> If you ever see `validate: OFF (human override)`, the floor is down by the human's choice — you
> are genuinely blind, so slow down, `feel` deliberately, and ask before trusting anything.

> **For `server/_instructions.py`** — appended to THE ONE RULE bullets:
>
> • You build with two forced senses, neither optional. After each op you get a `feel` note (what
>   you just changed — your eyes, no verdict) and a `validate` result (what's broken — z-fight /
>   non-manifold / normals are never OK and unsilenceable; clipping is suppressible only by
>   *declaring intent*, `validate op=expect` with a reason, never an "ignore"). Treat a `validate`
>   finding as ground truth to act on. If you see `validate: OFF`, the human disabled the floor —
>   you are blind; `feel` deliberately and ask.

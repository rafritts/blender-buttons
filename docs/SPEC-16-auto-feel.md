# SPEC-16 — Auto-feel: a scheduled, involuntary verification floor

_Status: Proposed 2026-06-23. Net-new **perception** primitive. Makes THE ONE RULE
("favour a `feel` check over trust-me math") operational against the mutator the server
*can* observe but currently never forces to look: the agent itself, in flow._

---

## The problem

The agent's whole method rests on **read-then-act**, and `feel` is the read. But `feel` is
**elective**, and the better the mutating tools get, the less often the agent ever elects to
use it. When the tooling is good the agent just lets it rip — which is *correct, desirable*
behaviour — and never considers that a pile of rough edges is hiding under `feel`: z-fighting
from a coplanar placement, a shell poking through, flipped normals, non-manifold junk from a
boolean, near-coincident verts. On a simple mesh this is fine; there is little to diverge. It
**gets out of control with scene complexity**, where unverified divergence compounds and a
session that made *one* `feel` call drives the scene into a wall that costs a full rework.

The root cause is behavioural, not instrumental, and it is worth stating precisely:

> **The model is a *reactor*, not an *inspector*.** It reacts brilliantly to information put
> in front of it; it almost never elects to go *get* information it wasn't handed. Diligence
> cannot live in the model's disposition — and shouldn't, because the disposition that skips
> inspection is the same one that makes it productive.

Therefore every design that asks the model to *decide* to verify fails the same way:

- **Nags / a debt meter / "consider `feel`":** asking the model to *consider* is the very act
  it skips in flow. A louder nag is still a request to consider — it gets rationalised past or
  goes wallpaper, which trains the reflex *down*.
- **Conditional success / ambient lint:** better (involuntary), but still per-op and tuned
  against a happy path; mis-tuned, it fails *toward blindness* — the well-poisoning failure.

And the status block can't carry the missing signal regardless of polish: it is a
**single-object spotlight** (the active object) plus a couple of scene-global lines. A
relational defect (z-fight, overlap) needs ≥2 objects and the relation between them, so it
can never appear in *any* per-op block — not because the block lies, but because nothing in
the loop ever looks at the scene as a whole.

## The reframe that works: model it on autocompact

`feel` should run **automatically, on a schedule the agent can see coming** — the way
autocompact runs against the context window. The agent never *decides* to feel; the system
feels *for* it at predictable moments and force-feeds the result. This wins because of an
**asymmetry of failure modes**:

- Over-feel (threshold a touch too low) costs **one cheap diagnostic pass**.
- Under-feel (today's status quo) costs **the agent rebuilding a complex scene from scratch**.

One failure mode wastes a few tokens; the other poisons the well. The whole point is to take
the diligence the model doesn't have and make it a **property of the system**, while leaving
"let it rip" completely untouched on the clean path.

## The design

### The gauge

A counter accrues as edits land and is surfaced in the status block as a terse,
LLM-readable line — **no bar graph** (decoration for an eye that isn't there):

```
auto-feel in 9 edits · last: clean, 11 ago
```

- Accrue however is most accurate **underneath** (op-class weighting is fine), but **display a
  plain count/%**. Predictability is the entire value of a countdown; a number that jumps by a
  hidden risk weight breaks the "I can see it coming" property that makes autocompact legible.
  Abstract the non-uniform unit into one clean number, exactly as the context bar abstracts
  non-uniform tokens.
- The line shows the **active object's** countdown; on a focus switch it re-points to the new
  focus (per-object counters, below).

### The auto-feel pass — run wide, speak narrow

When a trigger fires, run a **fixed diagnostic bundle** (predictable, like compaction is one
defined operation) over the objects touched since the last pass **plus their relations to
neighbours**:

- **Object diagnostics:** `topology` (structure / components / genus / boundaries / poles /
  symmetry), `facing` (normals), `validate`, `audit`.
- **Relational diagnostics:** `overlaps` / `contacts` / `clearance` involving the touched
  objects (the z-fight / penetration class).

Explicitly **excluded:** the *work-tools* of `feel` — `place`, `aim`, `radial`, `anchor`,
`fit`, `handle`/`handles`, `relate`, `map`, `baseline`/`diff`/`accept`/`forget`, `verify`,
`region_form`/`protrusion`. These need a live selection, pre-minted handles, or arguments, and
several *do work* rather than *read health*; auto-running them unbidden is meaningless.

**Report by exception.** Run the full bundle but **collapse every clean check to a count and
expand only findings.** Dumping every all-clear reading buries the one real defect in pages of
"fine" and the agent banner-blinds the whole block — recreating the original problem inside the
auto-feel. Comprehensive *coverage*, exception-only *output* (also the token-cheapest way to be
thorough). When it fires:

```
auto-feel ran (12 edits) — ⚠ Body∩Hair overlap 34%; Hair: 3 non-manifold edges · 6 checks clean
```

A clean pass still emits a terse confirmation (`auto-feel ✓ clean (Body, Hair)`) — rare enough
not to be noise, and it calibrates the agent that the floor is real.

### Three triggers

1. **Threshold** — accrued edits hit the line. Catches *heavy* continuous work on one object.
2. **Blur (flush-on-focus-loss)** — a write barrier for the *abandonment* case ("20% of edits,
   `good enough`, never touched again"). **Focus-departure from A** = the next mutation targets
   an object ≠ A, *or* an explicit deselect / active-change away from A, *or* exiting edit mode
   on A. On departure, if A's pending debt clears a **low anti-thrash floor**, flush A first
   (its object diagnostics + its relations), inject the result into that next response, and
   reset A's counter. The floor stops legitimate A↔B interleaving from firing a pass on every
   hop; substantial-work-then-leave trips it, a glance doesn't. Detected server-side from the
   existing op stream (`last_focused_object` comparison) — it fires on the *next* call, which is
   exactly when the switch becomes observable.
3. **Stop hook (walk-away-entirely)** — blur fires on the *next* call; the server is purely
   reactive and **cannot** catch the pure stop (agent finishes, says "good enough," ends the
   turn — no next call). That residue is unreachable from inside the server. It needs a
   **harness-level Stop hook** that feels any objects still carrying debt when the turn ends.
   Server handles switch-away; the Stop hook handles stop-entirely.

### Debt accounting

- **Per-object debt** (drives blur-flush scoping and the active-object countdown line).
- **Scene-relation debt** (a scene-global line; accrued by transforms that move parts relative
  to each other — the z-fight generator that touches zero triangles). Flushed by the scene-level
  threshold and by any pass that runs the relational diagnostics.
- **Typed reset.** A pass clears the debt **it actually covered** — relational checks clear
  relation-debt, object diagnostics clear that object's topology-debt. (Prevents a future
  manual cheap `feel` from silencing the wrong bucket.)

### Manual `feel`: a comprehensive default, not a quantity mandate

A rejected alternative was *requiring* manual `feel` to pass ≥2 ops. It reaches for a real
thing — a single `op=topology` call gives **false breadth** ("I felt it" when only one axis was
checked) — but a mandate is the wrong tool: it is redundant with auto-feel (which already
delivers breadth involuntarily) and invites the exact cargo-cult we are killing (bolt on a
throwaway second op to satisfy the rule). Quantity is not the lever.

Instead, put the **carrot in the default**: `feel` with no / minimal args runs the comprehensive
diagnostic sweep, so a *lazy* single call is *already* broad. Make the generous thing the easy
thing; reward the one inspector-move the reactor does make. A **manual `feel` also pre-empts and
resets** the relevant counter — like `/compact` before autocompact. The careful move is rewarded
(resets the gauge); the careless default is safe (auto-feel catches it anyway). Flow is never
punished.

## Why this preserves "let it rip"

The cost of verification falls **entirely on the system, and entirely on the moments something
is actually wrong** (report-by-exception). On a clean scene nothing of substance speaks, nothing
slows down, the agent rips exactly as today. Friction appears only where there is a real defect.
And the floor **self-scales to the danger**: edits-since-feel accrues faster in complex work, and
per-edit defect odds are higher there, so the floor tightens precisely where blindness gets
expensive — and stays loose on the simple meshes where the reactor is already fine.

## What it deliberately does not do

- **No taste judgement.** It reports *that* a defect exists (overlap, non-manifold, flipped
  normal), never whether a shape is *good*.
- **No auto-fix.** It surfaces; the agent (or human) decides. It never silently mutates geometry
  to "correct" a finding.
- **No nag, no mandate.** It does not ask the agent to consider verifying and does not force a
  minimum op count. It either runs the check itself or stays silent.
- **No pure-stop catch, server-side.** The walk-away-entirely case is explicitly delegated to a
  harness Stop hook; the server does not pretend to cover it.
- **No always-on noise.** Clean checks collapse to a count; the gauge is one terse line, not a
  running readout of everything.

## Surface

- Status-block line (always): `auto-feel in N edits · last: <clean|⚠ k findings>, M ago`.
- Scene-relation line when relevant (scene-global, alongside `render`/`viewport`).
- Injected pass result on a trigger: `auto-feel ran (N edits) — <findings> · K checks clean`.
- Manual `feel` (no/min args) → comprehensive sweep + counter reset.

## Open questions / tuning

- **Threshold values.** The one knob that decides whether this works: start **conservative** and
  let it earn its way down. (Unlike a nag, mis-tuning fails benign — see the asymmetry above —
  so erring toward *more* frequent is cheap.)
- **Expensive-op tiering.** If the honest diagnostic bundle is too slow to run scene-wide on a
  large scene at every trigger, scope tighter (only object-pairs whose bboxes moved) rather than
  firing less often. Keep individual ops in their sampled/capped tiers.
- **Anti-thrash floor value** for blur — tune against interleaved relational work.

## Tests (sketch)

- Counter accrues on edits, displays in the block, resets on a manual `feel` and on each trigger.
- Threshold fires at the line; report-by-exception (clean → count only; finding → expanded).
- Blur: editing object B after substantial edits on A flushes A first (and is suppressed below
  the anti-thrash floor); A↔B interleaving under the floor does not thrash.
- Auto-feel bundle excludes the work-tool ops; covers object + relational diagnostics.
- Typed reset: a relational pass clears relation-debt but not an untouched object's topology-debt.
- Manual `feel` with no args runs the comprehensive sweep.

## Agent-facing copy (to land with implementation)

**For `GUIDANCE_FOR_LLMS.md`** — new section:

> ### Auto-feel is the floor under your flow
>
> You will see an `auto-feel` line in the status block: `auto-feel in N edits · last: …`. It is
> a countdown, like the context-window meter — it tells you how many more edits until the server
> **runs `feel` for you, automatically.** You do not have to ask. When the counter hits zero — or
> when you switch off a mesh you have been working — the server runs a diagnostic sweep over what
> you touched (and how it relates to its neighbours) and **injects the result**. A clean sweep
> says so in one line; a sweep that finds something names it (`⚠ Body∩Hair overlap 34%`). A
> finding is not noise — it is the rough edge you would not have looked for. **Stop and deal with
> it before you build further on top of it.**
>
> Why this exists: good tools tempt you to let it rip and never `feel` anything — which is fine on
> a simple mesh and disastrous on a complex scene, where unverified edits compound into a rebuild.
> Auto-feel is the guaranteed floor so that never happens. It does **not** replace your judgement:
> a manual `feel` whenever you are unsure both answers your question *and* resets the counter (and
> `feel` with no args now runs the full sweep — a lazy read is already a broad one). Reaching for
> `feel` yourself is always better than waiting for the floor.

**For `server/_instructions.py`** — appended to THE ONE RULE bullets:

> • You are not the only thing that runs `feel`. The status block carries an `auto-feel`
>   countdown; at zero, or when you switch off a mesh, the server runs a diagnostic sweep for you
>   and injects any finding. Treat an injected finding as ground truth to act on, not a footnote —
>   it is the blind spot you did not check. A manual `feel` resets the countdown; reaching for it
>   yourself beats waiting for the floor.

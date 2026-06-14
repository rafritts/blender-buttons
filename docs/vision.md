# blender-buttons: Vision

## The Idea

A model-agnostic MCP server that lets an LLM model in Blender as a **blind sculptor** —
working alongside a sighted director who owns the taste.

The LLM cannot see. It feels the model with its fingertips, more precisely than a
human eye ever could, and shapes geometry on the director's instruction. The
director looks, judges, and says "adjust this." Together they take a piece from
blockout to a WuWa/Genshin-grade finished character.

## The Division of Labor

Three parties, three jobs. A capability landing in the wrong party is a defect.

- **The human owns taste.** Vision, intent, acceptance criteria, artistic judgment —
  the *what* and the *is-this-right*. Especially appearance: texture, lighting,
  material, the final look. Only the human can say "yep, perfect" or "yikes, rework it."
- **The LLM owns precision.** It compiles the human's fuzzy, taste-laden direction
  ("bigger, more shapely") into an exact, correct, verified sequence of operations,
  and measures fidelity to the target. Not a source of taste — a precision instrument.
- **The tools own the mechanics.** Math, coordinates, state, topology, sequencing.
  None of it reaches the LLM.

**Where precision ends and taste begins, the system asks — it never guesses.** When a
genuinely aesthetic choice arises, the right behavior is to surface precise variants
("here are silhouettes at +10/+20/+30% — which reads right?") and hand the call to the
human. The design never depends on the LLM's taste; it depends on its precision to
generate exact options and its touch to tell them apart. The seam is the product.

## How the Human Drives: Four Delegation Modes

The taste/precision split isn't a fixed line — the human slides it per request, choosing
how much of the work to hand off. Between intent and geometry runs a pipeline:

```
symptom        →   diagnosis        →   fix          →   execution
"looks weird"      "normals at X,       "set them        (do it)
                    want Y"              to Y"
```

The human can enter at any point and delegate the rest. Four modes, drawn from real
harness use:

1. **Scaffold** ("go ham") — delegate the whole pipeline, broad. *"Block out an anime
   girl, pink hair, ninja outfit."* The LLM owns the full compile from intent to geometry.
2. **Diagnose** ("I can't be bothered to find it") — delegate the find-the-cause span.
   *"Her face reads wrong in this light — what is it?"* The LLM localizes the cause.
3. **Execute** ("you're faster than me") — delegate only the hands. *"Normals on the face
   are at X, the toon shader wants ~Y — fix them."* The human pre-diagnosed; the LLM is
   precise hands.
4. **Deep-dive** — co-reason about the work itself. Emergent; see below.

The same person moves fluidly across all four in one session — "pro" on the normals tweak,
"layman" on the scaffold. **Delegation span is a property of the request, not the user.**
("Design for the layman vs the pro" was therefore the wrong question — there is no fixed
user to design for.)

The load-bearing consequence: **diagnosis belongs to precision, not taste.** The human
supplies the symptom ("weird"); turning that into "it's the normals, at X, should be Y" is
a precision act the LLM owns. A pro can pre-supply the diagnosis (entering at mode 3); a
layman cannot — so the LLM must own the whole pipeline from the symptom down. Diagnosis
routes first: a *geometry-caused* symptom (a shading artifact from a topology pinch) is the
sculptor's to feel and fix; a pure *appearance* symptom (the hair color is wrong) has
nothing to touch and routes back to the human as taste.

Each near-term mode already has a home pillar:

- **Scaffold** → the generative verbs (`add_*`, build patterns).
- **Diagnose** → the introspection / touch suite (`SPEC-02`). Active stereognosis *is* the
  diagnostic instrument.
- **Execute** → the action surface, with `SPEC-01`'s refuse-with-capture as its safety net:
  mode 3 is exactly where the human asks for a specific verb the surface may not have yet,
  so it is the mode that generates the build queue.

**Deep-dive (mode 4) is deferred because it is downstream, not because it is optional.** It
isn't a feature you build — it emerges once scaffold, diagnose, and execute are each
frictionless and cheap to compose, so that dropping into any of them mid-thought costs
nothing. In the modeling context it is just a tight conversational braid of the other
three. Build the three; the fourth falls out.

## The Blind Sculptor (stereognosis)

The technical name for knowing an object's form by touch alone is **stereognosis** —
a subset of **haptic perception**. This project's "tactile introspection" is, almost
exactly, *computational stereognosis*.

This is not a degraded substitute for sight. In the **geometry** domain, touch is
**superhuman**: a proximity query feels a 0.2mm asymmetry no human eyeballing a
viewport would catch. So the boundary is clean:

- **Geometry = the sculptor's domain.** Touch. Deterministic. Sub-millimeter. The LLM's.
- **Appearance = the director's domain.** Sight *and* taste. Irreplaceably the human's.
  The sculptor may *set* a material or light (mechanical), but the *judgment* of how it
  looks always routes to the human — it literally cannot see it.

## Why Not Sight

The early design gave the LLM screenshots as its eyes. Field experience falsified it:
**LLMs gaslight themselves.** A vision-language model weights its text prior heavily,
so the model that just called `build_sword` reads the screenshot *through* that
expectation and confabulates the details that confirm it. The actor grading its own
homework is the maximum-bias configuration. The screenshot becomes anti-signal — paid
for in tokens and latency.

Touch does not gaslight. `distance_between` returns `0.30`, not "looks about right."

So sight is demoted, not deleted. It keeps exactly two jobs:
1. **The human's eyes** — real perception, real taste. Screenshots stay first-class *for the human*.
2. **An independent cold judge** — at milestones, a separate intent-blind model call for
   identity sanity ("is this a sword or a spoon?") and unknown-unknown anomalies. It
   works *because* it has no prior to bias it. This is the only LLM-vision use that
   survives the gaslighting argument.

Comparison against a reference is deterministicized where possible: extract and compare
silhouettes/profiles numerically, rather than eyeballing two images.

## The Core Iteration Loop

```
measure → decide → act → measure again
```

The LLM feels the current state, decides on the director's behalf with precision, acts
through a named operation, and feels again. *See* is reserved for the human and the cold
judge. The LLM always re-measures before acting — it never assumes the world matches
what it last did. Human interventions (the director reaching in to tweak the 5%) are
just state changes the LLM feels on the next measurement.

## Coordinates Never Cross the Boundary

LLMs are bad at carrying world-coordinates across operations. So coordinates are the
tool's internal currency and must never become the LLM's working medium. There are two
ways they leak; both are banned:

1. **Compute** — the LLM does arithmetic to derive a number. The LLM passes quantities
   it *knows* (a width it wants, the name of a part), never quantities it must *derive*.
2. **Carry** — a tool hands the LLM a coordinate so it can relay it into the next call.
   This is subtler and just as harmful: it costs working memory, risks transcription
   error, and the held number is a stale photograph — it rots the instant a part moves.

The LLM reasons over **quantities and relations** — "0.3m apart," "A is left of and
above B," "they're touching." Those are *touch*; return them freely, in scene
vocabulary. It never reasons over **coordinates**.

> **If a tool ever returns a coordinate so the LLM can pass it to another tool, that's
> the signal to collapse the two tools into one relational verb.** "Connect A and B with
> a spline, bowed out 10cm" — references in, mesh out, zero coordinates crossing the
> boundary, robust if A later moves.

**Perception is the one exception, and it isn't really an exception.** A tool may *show*
the LLM coordinates in a local frame as read-only ground truth — it helps the sculptor
build its mental picture, and being measured truth it cannot gaslight. The rule is about
*action*, not *sight*: the LLM may **perceive** position but may never **act** by
specifying or dead-reckoning a coordinate, and never carries one between tools. Perceive
in coordinates; act in labels and relational verbs.

**There is no coordinate ripcord.** The old `at=[x,y,z]` / literal-height escape hatches
are removed: dead-reckoning placement refuses with a diagnostic that captures the LLM's
intent, so every reach becomes a logged, named gap — the build queue for the missing
relational verb. Flag-gated and reversible per-capability. See `SPEC-01-strict-relational.md`.

## Stereognosis: The Design Spec

Two modes of touch, both must be effortless:

- **Proprioception (ambient, always-on, free).** You always know where your own hand is
  without looking. That's the auto status block — mode, dims, selection, where parts sit.
  Rich and ever-present, so the LLM is never lost and never has to *ask* where it is.
- **Active haptic exploration (deliberate, targeted).** The fingertip the LLM reaches out
  for one specific property. One call, high-fidelity, scene-vocabulary in return.

The active suite should cover the property taxonomy from haptics research
(Lederman & Klatzky's *exploratory procedures*). Each procedure is optimal for one
property; a gap in the table is a sense the sculptor is missing:

| Exploratory procedure | Property | Tool family |
|---|---|---|
| **Contour following** | exact shape, precise layout | `trace_profile`, `get_rings`, `get_mesh_profile` |
| Enclosure | global shape, volume | `describe` dims, bbox |
| Spatial relation | part layout | `gap_between`, `distance_between`, `is_aligned`, `check_contacts` |
| Lateral motion | surface/texture (geometry-side: density) | topology/`get_mesh_profile` |
| Part-motion test | mobility | rig / `pose_bone` checks |

**Contour following is the precision spine** — the procedure humans use for exact shape,
and exactly where the sculptor's fingertips beat the director's eyes.

The concrete representation the LLM reads — a recursive, local-frame, label-addressed
view of any selection (group → object → element) at a chosen level of detail — is
specified in `SPEC-02-introspection.md`. It is the LLM's eyes; the human never reads it.

## Effortless Is a Measurable Gate, Not a Vibe

Drive the LLM's effort to zero across all seven costs: **discovery** (how many tools
plausibly apply), **arithmetic** (must be zero), **state-carrying**, **schema-reading**,
**verification**, **recovery**, **sequencing**. Every tool, existing and future, is
graded on this rubric.

The objective metric is the **floor test**: *can the weakest model we'd ship with take a
character from blockout to finish on the tool surface alone?* The gate is fidelity, not
beauty — *"precisely execute a director's instructions and hit a supplied reference,"*
never *"make something good"* (beauty isn't measurable and isn't the LLM's job). Every
batch either moves that number or it doesn't.

There are two floor tests, nested. The **tool** floor test above is about the *driver
model*. The **product** floor test is about the *human*: can a person who supplies symptoms,
not diagnoses, direct the LLM to a WuWa-grade character? That tests the hardest span of the
pipeline — it forces the LLM to own *diagnosis*, not just execution (see "How the Human
Drives"). A request that arrives pre-diagnosed (mode 3) is the easy case; *"her face looks
weird"* (mode 1/2) is the gate. If the LLM can diagnose, it can execute for anyone.

## Model-Agnosticism Is a Law

Precision and touch are deterministic and portable across any model. Taste and sight are
contested and model-locked — taste is precisely where a model's content guardrails fire
and refuse legitimate character work. Building on touch instead of sight keeps the
foundation on the durable, portable layer.

Consequences, enforced:
- The server is a **neutral instrument** — as content-neutral as bpy itself. It moves
  geometry; it has no opinion about what the geometry depicts. No name-based refusals, no
  judgment gates.
- **No in-server LLM** (no embedded vision-summarizer). It would reintroduce both a vendor
  dependency and a censorship surface. Every verdict computed in Python instead of by a
  model is a verdict that survives a model swap.
- **Multi-driver testing is an acceptance gate**, not a nice-to-have. "Works on the
  weakest permissive driver" is a release criterion.

This is also the cleanest moat against a model-locked official connector: an artist whose
aesthetic a particular model won't engage with structurally cannot use that tool — and
can use this one.

## The North Star

Let an agent complete the Blender donut tutorial **and beyond** — culminating in modeling
a full WuWa/Genshin-quality stylized character over a multi-hour session, with a human
director who owns taste but need not know Blender at all, and a precision sculptor owning
the geometry. The donut is the
smoke test, not the destination. Every tool gap hit during real modeling is a step toward
it; default to closing the gap in the MCP rather than working around it.

## What the LLM Never Does

- Reason over raw vertex coordinates — neither computing them nor carrying them between tools
- Perform arithmetic or matrix math
- Assume scene state without feeling it first
- Judge appearance (texture, lighting, the final look) — that routes to the human
- Originate taste — where precision ends, it asks

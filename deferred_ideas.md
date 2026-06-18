# Deferred ideas

> Things that *might* make the whole system better but that we are **not** convinced are
> needed right now. This is the maybe-pile, deliberately lower-confidence than `gaps.md`.
>
> **How this differs from `gaps.md`:** a gap is *demonstrated pain* — a concrete place the
> agent was forced out of intent-space, with a general primitive that fixes it. An entry
> here is a plausible improvement whose **need is unproven** — we haven't felt the pain
> hard enough, or we've shipped something cheaper that may already cover it. No G-numbers.
>
> **Disposition:** when real, repeated pain shows up, promote an entry to `gaps.md` (or a
> SPEC) and build it. If it gets built, or proves unnecessary, **delete** it. Nothing here
> is a commitment.

---

## `workflows` verb — a pull-drawer of battle-tested tool-call plays

**The idea.** A `workflows` verb that returns named, battle-tested *plays* — multi-step
tool-call sequences for recurring intents (e.g. *localize a feature*, *build from a
primitive*, *assemble two openings*). Progressive disclosure like the rest of the surface:
`workflows` lists intents (one line each); `workflows name=<x>` returns the full play.

**Why it might help.** The recurring failure mode is the agent *inventing its own path*
to the goal and missing primitives that already exist — demonstrated live in dogfooding:
it reconstructed the stability loop by hand instead of reaching for `feel op=verify`, and
hunted with `relief` instead of `curvature`. The op list being *loaded* doesn't tell the
agent *which sequence of ops serves the intent it has*. A play encodes the sequence.

**Design constraints (if we ever build it).**
- **Generic only.** `localize-a-feature`, `build-from-primitive`, `assemble-two-openings`
  — never `find-a-nipple`. Plays are primitives, not domain shortcuts.
- **Decision trees, not scripts.** A play must carry branch logic + stop conditions ("cast
  wide → read shape → if the verdict flips when you narrow, recenter → confirm capture →
  drill only when stable → stop when growth doesn't change the verdict"). A linear recipe
  just relocates the anchoring footgun from the response into the playbook.
- **Curated from real builds, kept FEW.** A bloated drawer is as useless as no drawer.
- **One source of truth.** Derive plays from `GUIDANCE_FOR_LLMS.md`; don't hand-maintain a
  third divergent copy.

**Why it's DEFERRED (not in `gaps.md`).** We just wired the cheap version of the same goal:
the `initialize` `instructions` bootstrap (push the pointer) + the `guidance://llms`
resource (pull the depth). That already delivers "here's a drawer of battle-tested loops,
go read it" at near-zero standing cost. A dedicated verb's marginal value over a pulled doc
is **unproven** until we see two things: (1) that agents actually consult the resource
unprompted, and (2) that *structured, parameterized* plays beat a flat markdown doc enough
to justify a verb slot. The hard problem was always the **trigger/salience** — and that
lives in `instructions`, not in the verb. Build the verb only if the resource proves
consulted-but-insufficient.

**Open questions.** Verb vs. resource sufficiency. How to keep plays non-rigid in practice.
(Naming: `workflows` over `patterns` — "patterns" is too 3D-adjacent: texture/array
patterns, stencils.) This is the surviving kernel of `gaps.md` G9, minus its
push-content-into-every-response half, which we rejected as an anchoring footgun.

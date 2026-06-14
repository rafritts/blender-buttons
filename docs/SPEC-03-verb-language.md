# SPEC-03 — The Verb Language (a grammar, not a toolbox)

**Status:** proposed (design settled in dialogue; not yet built)
**Date:** 2026-06-14
**Depends on:** `vision.md`, `SPEC-01` (coordinate-free), `SPEC-02` (the noun-space / introspection)

## Goal

Stop exposing the server as a *pile of tools* and start exposing it as a *language for
talking to one workpiece*. A toolbox taxes the first of the seven costs — **discovery**
("which of N tools applies?") — on every single step, and that cost never goes to zero as
long as the surface is a flat list. A language collapses it: the LLM doesn't *discover*, it
*speaks* — it knows a small vocabulary and a few verb families, and a specific call is the
word it reaches for, not a catalog entry it hunts.

## The property that makes it a language: closure

> **Everything a sense-verb returns is a valid input to a shape-verb.**

Perceive and act speak the *same* vocabulary — named parts, features, relations, quantities
— so the output of feeling the model is directly the input to reshaping it, with nothing
translated, computed, or carried between. This is what turns a set of operations into a
composable grammar. A coordinate appearing in that stream is a foreign word (`SPEC-01`).

The three "ones":

- **One workpiece.** There is always exactly one thing under attention — scene → object →
  selection, the recursive altitude of `SPEC-02`. The LLM is never juggling contexts; it
  holds one piece and zooms. (This is proprioception — it always knows where its hands are.)
- **One vocabulary.** Every input and output speaks only: **named parts**, **features**
  (poles, boundaries, rings, regions — the touchable landmarks), **relations**
  (on / under / against / inside / through / around / between), and **quantities** (dims,
  angles, counts, gaps). Never coordinates.
- **One loop.** Every verb is either a **sense** or a **shape**; they chain because they
  share the vocabulary. `sense → shape → sense`.

## Surface shape: few families + combinators

The fork (decided): not 161 flat tools, not 2 god-tools — **a small number of verb families,
totally regular within each, over one noun vocabulary**, plus combinators that lift verbs.

- **`add(shape=…, name=…, …)`** — the *one* creation verb. The shape vocabulary lives in a
  param enum, not in 20 `add_*` tools.
- **`repeat(action=…, …)`** — a **combinator**, not a creation tool. It takes an `action`
  and applies it N times. `repeat(action="add", …)` today; `repeat(action="bevel", …)`
  tomorrow, for free. The language does the work; we don't ship a tool per case.
- **`place(target, <relation>=…, …)`** — relational placement (its own grammar below).
- **`sense` family** (`describe`, `widest`, feature queries) — returns handles + scene
  vocabulary, never coordinates.
- **`fix` family** — hygiene repair (below).

Data model: **handles are object references** — `add(name="seat")` returns the handle
`seat`; later calls pass `"seat"` / `"seat.corner.fl"` as strings. The server holds the real
state (bmesh, coordinates) keyed by the handle; the LLM only ever carries the name. This is
object-oriented in data model, functional in call syntax — and it *is* "perceive in coords,
act in labels" realized on the wire (`SPEC-01`). In the classic MCP loop the handle is a
string echoed back from each result; under a code-execution transport it is a literal
variable and chaining is free. The design is transport-independent: the LLM thinks in
handles and relations either way.

## The naming contract

**You cannot add anything without naming it.** `name` is a required parameter on every
creation and topology-changing call — no default, no auto-name. The call fails validation if
unnamed.

- The **LLM authors** the namespace; names are *intent it assigns*, never geometry the server
  infers. The namespace is the LLM's self-authored mental map.
- This includes geometry the LLM didn't place by hand — a `loop_cut`'s new verts, a
  `boolean`'s result. The causing call names what it creates. Nothing ever enters the map
  unlabeled.

### Labels for multiplicity

Naming a *kind* once ("leg") then having four collides. Resolution:

- **Spatial-semantic where roles exist** — `leg.fl / fr / bl / br` (front-left, …).
- **Positional-ordinal otherwise** — ordered by *location* (along an axis, around a ring),
  e.g. `post.1…post.12`. Never a creation-order index — labels are always spatial, never
  arbitrary.
- **Repetition groups** — the four legs are also one handle `legs`; address the group or
  drill in by member. A group is **validated by matching geometry** — it is *proven*, not
  asserted; validation rejects a leg grouped with an armrest. (This is the symmetry/
  repetition collapse of `SPEC-02`'s group view, made an authoring primitive.)

## `place` — the relational grammar

`place` was the loosest verb and needed tightening. The rule: **exactly one relation (the
mate) + a few modifiers (resolve the rest).** One primary keyword; defaults fill everything
else. A bare `place("cup", on="table")` works; modifiers override only the non-default.

The **closed relation set** — each with geometry the *tool* computes:

| Relation  | What mates |
|---|---|
| `on`      | A rests on top of B (A-bottom → B-top) |
| `under`   | A hangs beneath B |
| `against` | A's side flush to B's side (face-to-face) |
| `inside`  | A contained within B |
| `through` | A passes through B, coaxial (sword ↔ guard) |
| `around`  | A wraps B's outside (collar ↔ neck) |
| `between` | A spans / centers between two targets |

**Modifiers** (optional; defaults make the bare call work):

- `align` — how the free axes resolve: `center` (default) or a named side/edge
  (`"rear"`, `"flush:front"`).
- `gap` — distance along the mate axis: `"0"` contact (default), `"2cm"` apart, negative =
  embed / overlap.
- `anchor` — which feature of the *moved* object mates; default inferred from the relation.

**Open question — orientation.** "Stands upright," "faces forward" is rotation, not position,
and does not belong in this grammar. Either fold it into `anchor` (which face of A points at
the mate) or make it a separate `orient` verb. Undecided.

## The in-between: hygiene, normals, merging

The mid-level mesh mechanics (flipped normals, doubled verts, non-manifold edges, boolean
leftovers) mostly **disappear from the LLM's surface**:

- **The causing verb owns the cleanup.** `boolean` recalcs normals and welds its seam;
  `add` produces outward normals. Hygiene is a *postcondition*, not a step the LLM invokes.
- **When automation can't resolve it → sense + repair.** Residual defects are a *sensed
  property*, never silent state: `describe`/`check` reports "12 inward normals, 4 doubled
  verts, 2 non-manifold edges." A small `fix(target, issue="normals"|"doubles"|
  "non_manifold")` family repairs named defects. This is diagnose-mode: "looks weird" →
  feel the defect → repair. The human never sees it.
- **Two kinds of normals, kept separate.** *Hygiene normals* (just be outward/consistent) →
  automatic, tool-owned. *Intent normals* (custom split normals for shading — the toon-shader
  "X°→Y°" case) → a deliberate execute-mode verb, never auto-touched.
- **Merge is not one verb.** `assemble` = group, parts stay distinct. `join` = weld into one
  mesh, auto-merging coincident verts at the seam. `weld` (merge-by-distance) is the hygiene
  primitive `join` uses internally, also exposed for explicit seam-closing.

## Acceptance

- A sword and a chair build end-to-end using only `add` / `repeat` / `place` / `sense` /
  `assemble` (+ `taper` / `groove` / `sharpen` class shaping verbs), with **zero coordinates**
  in any arguments and **every** created element named.
- `place` accepts exactly one relation keyword; passing two is a validation error.
- A repetition group with a non-matching member is rejected by `validate="matching_geometry"`.
- Hygiene (normals/doubles) after `boolean`/`join` requires no explicit LLM call in the
  common path; residuals are reported by `describe`/`check` and fixable via `fix`.

## Open questions

- **Orientation** in `place` (see above).
- **Few-families vs uniform-many in practice** — how aggressively to collapse existing tools
  into combinator-driven families without fattening schemas past the schema-reading budget.
- **Combinator scope** — which verbs `repeat` (and future combinators like `mirror` /
  `bridge`) should legally lift, and how that composes with the naming contract (auto-deriving
  member names from one `name` + a label scheme).

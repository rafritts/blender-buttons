# SPEC-07 — Multi-feel: assembly perception + spatial handles

_Status: Proposed 2026-06-16, awaiting sign-off. Sourced from the first
torso-fabrication session — see gaps.md G10 and the "single-object horizon"
reflection._

## The problem

`feel` reads **one mesh** deeply; the status block tracks **one object's** bounds;
`edit` touches **one mesh's** selection. But character assembly is irreducibly
*relational between objects*: "fit a torso between a neck on the head, two armholes
on the arms, and a waist on the pants" is a four-object problem. To understand it
today the agent makes pairwise `feel distance/gap` calls and reassembles the picture
in its head, then re-derives the same armhole centre every time it's needed. The
whole cross-object axis — relational reads, spatial mapping, reusable anchors — is
missing. This is the constructive bridge (SPEC-06) carried up one level: from
*a point on one surface* to *the relationships between surfaces*.

## The principle

Extend `feel` from a mesh to an **assembly**, and let perception **leave durable
named anchors behind** instead of returning throwaway coordinates. Three capabilities,
all on the existing `feel` verb (keep the SPEC-05 collapsed surface — new ops, not a
new verb):

## A — `feel op=assembly` (the relational map)

One call over a set of objects (or a collection) returns the relational structure the
agent currently rebuilds by hand:
- per-object bounds + the **open boundary loops** of each (the catalog: size,
  vert count, located region — `arms`: armhole_L 17.6 cm, armhole_R 17.6 cm; `head`:
  neck 26.4 cm, …), and
- the **pairwise relations that matter**: nearest gap, flush/aligned faces, contact.

This folds the boundary-catalog half of reflection-#2 and the pairwise `gap/aligned/
contacts` ops into a single assembly read. Output is named and compact, never a
coordinate dump — same contract as `feel topology`.

## B — `feel op=map` (loose spatial mapping by raycast)

The agent's idea, verbatim: *"this opening, when raycast from its centre, hits this
other mesh around here and is 5 cm away."* From a boundary loop's centroid, cast along
the loop's average normal and report **what mesh it hits, where, and the distance** —
plus a miss when it hits nothing. This is how the agent learns, without eyes, that the
torso's top ring sits 0 cm under the neck and ~6 cm from each armhole. Spatial
adjacency as a perception primitive, not a render the agent isn't allowed to read.

## C — the handle registry (reflection-#5)

A server-held dictionary of **named spatial handles** — the agent's working symbol
table for assembly, distinct from the scene collection (the world's structure).

- **A handle stores provenance, not a frozen point.** Its derivation — `{object,
  kind: boundary-loop | aim(face,u,v) | vert-set | point, base: cage|evaluated}` — is
  the source of truth; the resolved `point + normal (+ ring verts)` is a cache.
  Resolving a handle **recomputes** from the derivation against current geometry, so
  it survives a rig pose or a mesh edit instead of going stale silently.
- **`feel` auto-creates handles** for salient features it already finds — every open
  boundary becomes a handle under a predictable name (`<object>.<region>`, e.g.
  `arms.armhole_L`), so the agent can reference one without listing first.
- **The agent can tag its own:** `feel op=handle name=l_breast_weld from=<selection |
  aim | boundary>` mints a durable named anchor at a chosen spot.
- **Listable / inspectable:** `feel op=handles` dumps the registry (name, kind,
  owning object, resolved point, base).
- **Consumable by action verbs:** anywhere a verb takes a centre/coordinate
  (`sculpt at_…`, `transform move_to`, `select in_sphere`, `add on={at:…}`), it also
  accepts `handle=<name>`, resolved (recomputed) at call time. A weld then reads
  `from=arms.armhole_L to=torso.top_ring` — names, not numbers, across two objects.

Handles are the reusable output of A and B: an assembly read and a raycast both *mint
handles* as a side effect, so the relationships the agent just learned are addressable
by name for the rest of the session.

### Creation — auto-mint only the *structural*, never the *semantic*

Two classes, kept apart on purpose — this is the legible-vs-divination line:
- **Class A — structural (safe to auto-mint).** Features `feel` already finds
  deterministically: open boundary loops, poles, shells, the symmetry plane. An open
  loop is a topological *fact* (edges with one adjacent face), not a judgment, so
  naming each one is exposing what's there, not interpreting it.
- **Class B — semantic (agent-minted only).** "Where the weld goes," "where the breast
  sits" — meaning with no topological signature. The tool must **not** guess these;
  they come only from explicit creation, and `from=aim` is their robust home (a
  normalized framing re-resolves cleanly on a smooth patch where no feature exists).

Creation needs no new primitive: a handle is **a name + any addressing mode `feel`
already has** — `from = selection | aim(face,u,v) | boundary | point`. The agent
supplies the meaning; the tool supplies the math + persistence.

### Handle state — dirty tracking, git-style

Each handle snapshots its **resolved underlying geometry** at mint (the loop's vert
positions / the aim hit / the selection centroid). On list or consume, `feel`
**recomputes from provenance and diffs** the snapshot — three states, like a working
tree:
- **clean** — recompute matches; use silently.
- **dirty (drifted)** — geometry moved under it (pose, edit, sculpt) beyond ε, but the
  feature still resolves. Don't silently trust either value: **flag it** — "⚠
  `torso.top_ring` drifted 1.8 cm since mint" — and offer **recompute** (accept the new,
  like staging it), **pin** (keep the frozen point), or **re-derive**.
- **orphaned (conflict)** — provenance won't replay (named loop gone, verts deleted).
  Can't resolve; must re-derive or discard. The merge conflict — a distinct state from
  drift.

Checks are **lazy** — the `git status` model: validate on `feel op=handles` and inline
on consume, never an eager re-validation storm after every edit. Default on a dirty
*consume*: recompute + flag (provenance is the whole point), agent can override to pin.
Honest edge: a raw `from=point` handle has no provenance to diff, so it's the one kind
that **can't self-detect staleness** — the labeled escape hatch, another reason
derivation-backed is the default. Bonus: this dirty flag is also how the agent notices
the **human** moved something under a handle between calls — free detection for the
shared-state problem (G7).

## Lifecycle / open questions (for sign-off)

- **Persistence scope.** Session-only (in-memory dict), or saved into the `.blend`
  as custom properties / empties so handles survive a reopen? Lean session-only first;
  revisit if durable anchors prove worth the file footprint.
- **Staleness signalling — RESOLVED** (see "Handle state — dirty tracking" above):
  git-style clean / dirty / orphaned, lazy checks, recompute+flag default. Remaining
  knob: the drift ε (and whether it's absolute mm or relative to handle scale).
- **Auto-handle volume.** A dense scene could mint dozens. Namespace by object and
  only auto-mint for boundaries (the assembly-relevant features), not every pole.
- **`assembly` cost.** Cracking topology on Spring's production meshes risks the
  socket-window timeout already noted (gaps.md "Open"). Cache per-object boundary
  reads; let `op=map` reuse them.

## Out of scope (named so they're not silently assumed in)

- **Live X-symmetry edit mode** — a real want, **tabled by decision** this session
  (gaps.md). Handles help (mint `…_L`, mirror to `…_R`) but the symmetry *mode* is
  separate.
- **Follow-up affordances (gaps.md G9)** — its own later spec; multi-feel's new ops
  are prime *producers* of follow-ups (`assembly → map → handle → weld`), so the two
  compose, but they ship independently.
- **`edit op=bridge` (gaps.md G10)** — the action that *consumes* two handles to weld.
  Multi-feel is the perception half; the bridge primitive is tracked separately.

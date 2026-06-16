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

**Named spatial handles backed by real Blender datablocks and visible in the Outliner**
— the human's and agent's shared working anchors for assembly. (Resolved earlier as a
server-held dict; the human's ask — "show them in the Scene Collection, right-click →
Save as Handle" — settles it better.) A handle **is** a Blender object, so it persists in
the `.blend`, shows in the Outliner, and is selectable / renamable / deletable with native
tools. The "registry" becomes a **read-model over those datablocks**, not a parallel store
— one source of truth, no server-dict↔file desync. Handles are a distinct *role* (working
anchors, not character geometry) but live *in* the scene collection, in their own group.

**Representation** — two datablocks per handle:
- **An Empty** in a dedicated `Handles` collection marks the resolved point + normal,
  named (`arms.armhole_L`); provenance (kind, base, signatures, owning object) lives in
  its **custom properties**.
- **A vertex group** (`HANDLE_<name>`) on the owning mesh stores the constituent verts —
  Blender's native "named set of verts," persisted and select-from-able. A multi-object
  handle gets one vgroup per owning mesh, tied together by the Empty (its dependency set).
- **Optional vertex-parent**: parent the Empty to ~3 representative verts and Blender's
  depsgraph rides it through pose/deform for free (see Handle state). Full vert set stays
  in the vgroup; the 3 are just the tracking anchors.

Human-made and agent-made handles are **identical citizens** — both your right-click and
the agent's `feel op=handle` hit the same operator and produce the same Empty + vgroup.

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

### `save selected to handle` — the live selection as a shared pointer

The most natural creation path, and the one that turns the **shared selection** (the
G7 liability — Blender has exactly one, written by both human and agent) into the
collaboration *medium*. The server already reads it (`select op=current`,
`get_current_selection`), so minting from it is the **cheapest** mode, not the hardest:
- **Human → handle.** The human selects geometry in the viewport and says "make this a
  handle — the stuff we need to touch." The agent snapshots it; the selected vert indices
  become provenance, and the intrinsic + extrinsic signatures and dirty/attribution model
  all apply unchanged. The addon also adds a **native `right-click → Save as Handle`**
  (viewport context menus: edit-mode for components, object-mode for whole objects → a
  name prompt), so the human can mint one without the agent in the loop at all.
- **Agent → confirm.** The agent selects a candidate region; the human *sees the
  highlight* and replies "yes / no / not that face." Selection is a two-way visual
  channel — agent proposes by selecting, human disposes by selecting. Confirmation
  returns through chat, not a callback.

Honest limits (where this *won't* behave as one might picture):
- **Pull, not push.** Blender doesn't notify the agent when the human selects — the
  human's words are the cue. Perfect for "Hey Claude, save this"; impossible as ambient
  "the agent always knows what's selected" without wasteful polling.
- **One global selection → strict ordering.** The agent must snapshot the live selection
  as its *first* action; any intervening select op / mode switch / stray click clobbers
  it. The G7 `target=` escape hatch doesn't help (we *want* the current selection).
- **Mode + sync wrinkle.** Component selection is Edit-Mode and per-active-mesh, and
  reading `v.select` reliably has the documented sync caveat G2 already hit — calibration,
  not a wall. Object-mode selection is a different beast (whole objects → a group, not a
  geometry handle); multi-object edit (Blender 5.1) → a multi-mesh dependency set, like
  `op=map`.

Synergy: once the human marks "the stuff we need to touch," the agent operating there
*should* trip **`dirty (self)`** — so the dirty flag doubles as **positive confirmation
the agent worked exactly where the human pointed.**

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

**Native tracking shortcut:** if the Empty is **vertex-parented** to its verts, Blender's
depsgraph keeps it on the surface through pose/deform — so recompute-on-read for the
common case is *free* (just read the Empty's evaluated world position), and an Empty that
visibly drifts off the surface is the dirty signal made literal in the viewport. The drift
machinery then only earns its keep on **topology** change (re-identify the feature) and the
**intrinsic-deformation** signature; rigid + deform displacement is Blender's job.

Checks are **lazy by default** — the `git status` model: validate on `feel op=handles`
and inline on consume. Default on a dirty *consume*: recompute + flag (provenance is the
whole point), agent can override to pin.

But **eager is opt-in**, flaggable at three scopes — **per-handle**, **per-mesh** (every
handle derived from it), or **store-wide** — for anchors the agent is actively building
against and wants flagged the instant they move. The re-validation-storm fear is smaller
than it sounds: a mutation is localized to specific object(s), and a handle can only
drift if a mesh in its **dependency set** was touched, so eager re-checks just the
handles on the edited mesh, not the registry — cost scales with handles-on-the-touched-
mesh, which is tiny. (Wrinkle: a `feel op=map` handle depends on *two* meshes — the loop
it casts *from* and the surface it *hits* — so its dependency set is both; re-check if
either moves.)

Honest edge — `from=point` handles have no provenance to recompute, but they're **not
fully blind**. *Fiducial check:* snapshot a point handle's distances to its *k* nearest
**provenance-backed** handles at mint; on validate, recompute those neighbors (they
self-resolve) and diff the distances — any change beyond a micro-ε means the geometry
*around* the point moved, so the frozen point is probably stale. It's a **weak** signal
(it only sees motion its fiducials sample — a bulge rising right at the point with no
nearby handle reads clean) that strengthens with handle density, but it upgrades point
handles from silently-frozen to drift-flagged-when-witnessed. Derivation-backed stays
the default; `point` stays the labeled escape hatch.

Bonus: this whole dirty machinery is also how the agent notices the **human** moved
something under a handle between calls — free detection for the shared-state problem (G7).

### Two drift signatures + attribution (custom / multi-element handles)

A `from=selection` handle over verts/edges/faces carries *internal* structure, so it
gets **two complementary signatures** — distances, not raw positions, precisely because
distances are **rigid-invariant**, which keeps the two failure modes separable:
- **Intrinsic (shape):** the distance set among its own constituent verts — full
  pairwise for a small selection (e.g. three faces), a bounded signature for large ones
  (vert-to-centroid + a few cross distances; we only need to *flag* a change, not
  reconstruct it). Catches **deformation** (the region got squished), blind to where it
  sits.
- **Extrinsic (place):** the fiducial distances to nearest provenance-backed handles
  (the `from=point` mechanism, generalized). Catches **rigid displacement** (it slid as
  a whole), which the intrinsic check can't see by construction.

Together they cover squished *and* moved. A raw-position hash would flag both but
**conflate** them; the distance form keeps deform and displacement diagnostically apart.

**Attribution — "…and the agent wasn't the one who edited it."** On detected drift, ask
*who*. The server sees its own tool calls (the G12 history/undo log is exactly this
record), so intersect the handle's **dependency meshes** with the meshes agent ops
touched since the handle minted:
- explained by an agent op → **`dirty (self)`** — low-key, "you changed your own anchor."
- nothing the agent did explains it → **`dirty (external)`** — the loud alarm: the
  *human* (or a side-effect) moved your anchor. This is what makes the G7 detection
  *actionable*, not merely present.
It still flags either way (git doesn't auto-commit your edits); attribution sets the
urgency, and the agent decides recompute vs pin.

## Lifecycle / open questions (for sign-off)

- **Persistence scope — RESOLVED.** Handles are Blender datablocks — Empties in a
  `Handles` collection + `HANDLE_<name>` vertex groups — so they persist in the `.blend`
  natively and show in the Outliner. The registry is a read-model over them, not a
  separate store; the server may cache but must rebuild by scanning the collection, never
  treat the cache as authoritative. Remaining knob: whether Empties vertex-parent (track
  deform) by default or stay put (drift becomes a visible dirty cue).
- **Staleness signalling — RESOLVED** (see "Handle state — dirty tracking" above):
  git-style clean / dirty / orphaned, lazy checks, recompute+flag default. Remaining
  knob: the drift ε (and whether it's absolute mm or relative to handle scale).
- **Auto-handle volume.** A dense scene could mint dozens. Namespace by object and
  only auto-mint for boundaries (the assembly-relevant features), not every pole.
- **`assembly` cost.** Cracking topology on Spring's production meshes risks the
  socket-window timeout already noted (gaps.md "Open"). Cache per-object boundary
  reads; let `op=map` reuse them.

## Build order — ordered by *tryability*, not the dependency chain

The first slice needs no op-log and no perception layer, so it ships first — the human +
agent can *try it* immediately. (This corrects an earlier "G12 op-log first" framing: G12
is only needed for attribution, which is Phase 3.)

**Phase 1 — mint + see (the demo, start here).** `feel op=handle from=selection name=X`
reads the current selection and builds the native substrate: an **Empty** in a `Handles`
collection + a `HANDLE_X` **vertex group** on the owning mesh. Plus `feel op=handles`
(list by scanning the collection) and the addon **right-click → Save as Handle** operator.
No drift, no recompute yet — just mint, name, show in the Outliner, delete. Smallest
tryable loop: select → save → see it. *(Substrate is all native Blender — empties, vertex
groups, custom props, collections, context-menu operators — so this is mostly gluing.)*

**Phase 2 — resolve + consume.** A handle resolves to point+normal (recompute from its
vgroup against current geometry); action verbs accept `handle=<name>` (`transform move_to`,
`select in_sphere`, `sculpt at`). Handles become *useful*, not just visible.

**Phase 3 — integrity.** Provenance snapshot at mint; git-style clean/dirty/orphaned on
list/consume; intrinsic + extrinsic signatures; vertex-parent option for free deform
tracking. Attribution (self vs external) needs the **G12 op-log** — so G12 lands here.

**Phase 4 — multi-feel.** `feel op=assembly` (relational map + boundary catalog) and
`feel op=map` (raycast adjacency), auto-minting Class-A handles.

**Phase 5 — consumers.** G9 follow-ups narrate minting; G10 `edit op=bridge` welds two
handles.

Dev loop: a new `feel` op touches the server verb (`server/verbs/feel.py` + its engine)
**and** the extension side, then reload addon + `/mcp` reconnect. Confirm the current
server⇄extension file layout before editing — don't trust a stale path.

## Out of scope (named so they're not silently assumed in)

- **Live X-symmetry edit mode** — a real want, **tabled by decision** this session
  (gaps.md). Handles help (mint `…_L`, mirror to `…_R`) but the symmetry *mode* is
  separate.
- **Follow-up affordances (gaps.md G9)** — its own later spec; multi-feel's new ops
  are prime *producers* of follow-ups (`assembly → map → handle → weld`), so the two
  compose, but they ship independently.
- **`edit op=bridge` (gaps.md G10)** — the action that *consumes* two handles to weld.
  Multi-feel is the perception half; the bridge primitive is tracked separately.

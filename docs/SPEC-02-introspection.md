# SPEC-02 — The Mental Model (introspection representation)

**Status:** proposed (core settled; LOD machinery + auto-patch are staged)
**Date:** 2026-06-14
**Depends on:** `vision.md` ("The Blind Sculptor", "Stereognosis"), `SPEC-01`

## Goal

Give the blind sculptor its eyes: a faithful, holdable textual representation of whatever
is currently selected, in a **local frame**, that the LLM can reason over and act on
without ever touching a world coordinate.

This representation is **for the LLM, never the human.** The target user is a 3D layman;
he never reads a pole count or a vertex label. This is the sculptor's sense of touch.

## Four properties (the design criteria)

- **Holdable** — fits working memory (dozens of elements, not thousands).
- **Faithful** — generated from ground truth, so it can't be gaslit (unlike a screenshot).
- **Addressable** — every element maps back to a selection / operation.
- **Stable** — the same feature keeps the same handle across edits, so an edit doesn't
  invalidate the whole mental model.

## One recursive representation, three altitudes

It is **one tool that adapts to what's selected**, not three. Same output schema at every
level — *local frame, labeled members, relational metrics, a one-line shape tag per
member, drill-down handles* — applied at whatever altitude the selection sits:

| Selection | Altitude | Returns |
|---|---|---|
| several objects | **group view** | shared local frame + member summaries + relational graph |
| one object | **object view** | object-local frame + topology at chosen LOD |
| components (verts/edges/faces) | **element view** | full detail of the selected elements |

The LLM navigates coarse-to-fine: ask at the group level, drill into one member, then into
its elements. Each summary carries the label needed for the next query down.

## Local frame

- **Origin:** default = selection centroid / bbox center. Optionally a *namable* anchor
  ("frame this on the neck joint") for cases where the natural origin isn't the geometric
  center (e.g. the center of a torus' hole).
- **Orientation:** world-aligned by default for the group view (scene parts relate along
  world up/front); a single object's view may align to the object when drilled into.
- Coordinates shown here are **perceive-only** (SPEC-01). Action goes through labels.

## Labels (stable handles)

- **Objects:** the object name *is* the label — already stable. No hashing needed.
- **Sub-object elements:** a **persistent ID stored on the vertex** (a bmesh int
  custom-data layer), assigned once and carried through edits. Not a hash of the index
  (indices renumber on `loop_cut` / `merge` / `extrude` and would break).
- **New geometry** from an edit gets fresh labels, announced in the proprioceptive delta
  ("loop_cut added `k7p2 m3x9`").
- **Topology-destroying ops** (boolean, remesh, merge-by-distance) cannot preserve IDs;
  they fire an explicit *re-labeled* event the LLM is told about. This is an accepted
  limitation, surfaced rather than hidden.

The label is a handle to "coords-and-edges the LLM never sees." It is the universal
currency of edit mode: selection, edits, and queries are all label-addressed.

## Level of detail

`detail = "cage" | "decimated" | "full"`.

- **cage** — if the object has a subsurf modifier, the base control cage *is* the modest
  labeled set; LOD = cage vs subdivision levels. (Graceful fallback: if there is no
  subsurf, return `decimated` and say so.)
- **decimated** — landmarks (poles, boundaries, high-curvature, silhouette) shown
  explicitly; flat interiors summarized ("a smooth patch of ~N quads") rather than
  enumerated.
- **full** — every element of the selection (only sane at element-view scope).

Each level has a size budget; over budget → summarize + offer drill-down, never dump.

## Group view — a relational graph, not an N² matrix

N objects have N² pairwise relations; report only the salient O(N) structure:

- **Support / contact graph** — "head rests on neck; eyes inset in head; collar wraps
  neck." Composed from existing `describe` / `check_contacts` / `is_aligned`.
- **Symmetry & repetition groups** (the big compression win) — "left_eye ↔ right_eye:
  mirror across group X, 0.1mm error"; "slat_1…slat_5: 5 identical instances, evenly
  spaced along X." Collapses many members to *one description + an arrangement*; keeps the
  block holdable for large assemblies.
- **Per-member one-liner** — "head: domed shell, ~480-vert cage, 1 boundary at neck" —
  plus its drill-down label.

## Object / element view

- Topology landmarks in scene vocabulary + region words: islands, genus (sphere vs handle),
  **poles** (valence ≠ 4) located by region + nearest named feature, **boundaries** (open
  loops), n-gons / tris, symmetry plane + error, major edge loops named by what they
  encircle.
- Per-element descriptions: "this is a 7-gon, verts `a3f9 b2k1 c8w4 …`, edges …"; "this
  strip is a spline shaped like *X*." Distances in real units (mm/cm/m), relative.
- Shape recognition is a spectrum: trivially detectable (valence, n-gon, boundary) →
  fuzzy (semantic "looks like a dome/arc"). Report the certain facts; tag the fuzzy ones
  as guesses.

## Grounding (why this shape)

Stereognosis via Lederman & Klatzky's exploratory procedures (see `vision.md`):
**contour following** = exact shape (the precision spine, → object/element view),
**enclosure** = global shape (→ group/object summary), **spatial relation** = layout
(→ the group graph). Two modes of touch: **proprioception** (ambient, always-on — the
auto status block) vs **active exploration** (this tool, deliberate).

## Open questions

- **Layman vs pro as primary target.** Recommendation: design for the layman as the floor
  (pro comes nearly free). Affects whether a "hand-tweak the 5%" path is first-class.
  Unconfirmed.
- **Auto patch-decomposition** (segmenting an organic mesh into clean grid-patches) is the
  hard, research-y part — deferred. v1 leans on rings (axis-aligned), explicit named
  regions, and the robustly-computable feature skeleton. Not full auto-gridding.
- **Sculpt regime.** This is a base-mesh / retopo-cage sense (hundreds–low-thousands of
  verts). A dense sculpt (100k+ verts) needs a *different* sense (curvature regions, not
  pole enumeration) — its own spec, not this one.
- **Per-level size budgets** — concrete numbers TBD from real sessions.
- **Relabel event UX** — how loudly a boolean/remesh re-label is surfaced so the LLM
  rebuilds its mental model without thrashing.

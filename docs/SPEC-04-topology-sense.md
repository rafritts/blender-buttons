# SPEC-04 — The Topology Sense (`get_topology`)

**Status:** v1 implemented (numpy-native methods); v2 (scipy-backed) specced, not built
**Date:** 2026-06-14
**Depends on:** `vision.md` ("The Blind Sculptor", "Stereognosis"), `SPEC-01` (coordinate-free), `SPEC-02` (the element/object view this realizes), `SPEC-03` (handles as grabbable references)

## Goal

Give the blind sculptor a real sense of a mesh's **structure** — not its bounding box. `describe`
(SPEC-02's enclosure altitude) returns placement + dims + material; it returns **zero topology**.
To cut a sleeve, graft a hood, segment a rifle, or reshape a torso, the LLM must *feel the
interior structure*: where the holes are, where tubes branch, where the hard edges and bulges
sit, how thick the wall is, what's symmetric.

This is the concrete, named tool that realizes SPEC-02's "object / element view." One verb,
many **methods**, over **one mesh**. It is a **sense**, never a mutation.

## The governing principle: landmarks as handles, never a vert dump

A topology dump (5,000 verts / 10,000 edges) is the wall-of-text that violates SPEC-02's
*holdable* property and tells the LLM nothing about **where to act**. So `get_topology` never
returns raw geometry by default. It returns **landmarks** — openings, branches, regions, poles,
symmetry, thickness — each as a **named, grabbable handle** the LLM can pass straight into a
select / cut / extrude verb (SPEC-03 closure). The LLM does not *read* topology; it *grabs* it.

Counts (verts / edges / faces) are the one exception: a handful of numbers, always cheap, always
returned.

## The vocabulary spans bodies AND machines

Reeb/SDF-style analysis understands **organic** shapes (limbs, garments, characters) but says
almost nothing about **mechanical** ones (a minivan panel, an AK's receiver). So the method set
deliberately covers both halves:

- **organic landmarks** — `skeleton` (branches/tubes), `thickness` (part diameter), `segments`.
- **mechanical landmarks** — `features` (hard dihedral edges), `curvature` (flats / ridges / bulges).
- **universal** — `components`, `genus`, `boundaries`, `poles`, `symmetry`, `frame`.

A topology sense that only understood blobs would be half an instrument.

## Signature

```
get_topology(
  target,                 # object handle; default = active object
  method = [...],         # LIST of methods; default = the cheap bundle
  lod    = "low",         # low | medium | high — OUTPUT VERBOSITY, not which mesh
  base   = "cage",        # cage | evaluated — WHICH MESH to read
  seed   = None,          # a handle/feature for seeded methods (geodesic / segments)
)
```

Three orthogonal knobs, deliberately not collapsed:

- **`method` is a list.** The LLM usually wants 2–3 facets at once; a list batches them into one
  round-trip. Default = the cheap bundle (`components, genus, boundaries, poles, symmetry, frame`).
- **`lod` scales how much is *said*, not which mesh is read.** `low` = summarized landmarks
  ("3 holes; neck ~38cm"); `high` = full enumeration (ordered boundary vert-paths, per-pole
  locations). One *global* knob — want full boundaries but summary curvature? Make two calls.
  (Simplicity-first: no per-method LOD in v1.)
- **`base` is a separate axis from `lod`** — it picks **which mesh** to analyze: the base control
  **cage** (default) vs the modifier-/particle-**evaluated** mesh. This is load-bearing: Spring's
  pullover carries subsurf + 800 hair strands; analysis on the evaluated mesh is noise. Conflating
  this into `lod` is the trap. Default `cage`.

## The method set

### v1 — numpy + bmesh + native BVH (zero extra dependencies)

| method | Question it answers | Engine |
|---|---|---|
| `components` | How many separate shells? | bmesh island BFS |
| `genus` | Sphere / tube / handled? How many holes through it? | Euler characteristic per component |
| `boundaries` | Where are the open holes, how big, where? | boundary-edge loop walk → circumference + region (+ ordered path at high LOD) |
| `poles` | Irregular verts / quad-flow breaks | valence ≠ 4 (boundary verts excluded) |
| `symmetry` | Mirror plane + error, per axis | KDTree mirror-nearest test |
| `frame` | Intrinsic principal axes + extents | PCA (numpy eigh) — so nothing assumes world-up |
| `curvature` | Flats, ridges, domes, saddles (the mechanical/organic surface sense) | angle-defect Gaussian + neighbor-centroid mean-sign |
| `features` | Hard edges (the *machine* sense) | dihedral angle threshold → sharp-edge chains |
| `thickness` | Local wall/part diameter | inward BVH ray-cast (single-ray approximation) |

### v2 — scipy-backed (needs the one bundled wheel; specced, not built)

The robust organic methods rest on a **fast sparse solve over the cotangent Laplacian** — the one
dependency that is *load-bearing for correctness*, not power. The approximations it replaces
(Dijkstra geodesics, raw angle-defect) are **tessellation-dependent** — they give a *different
answer for the same shape* when it's re-triangulated, which is disqualifying for an instrument
meant to handle arbitrary imports.

| method | Question | Engine | Why scipy |
|---|---|---|---|
| `geodesic` | Distance *along* the surface from a `seed` | heat method (Crane et al.) | one Laplacian solve; pose-invariant, mesh-independent |
| `skeleton` | Branch/tube structure (the sweater's Y, a limb count) | Reeb graph on the geodesic field; level-set component tracking | built on `geodesic`; composes with `boundaries` (known hole count = sanity check) |
| `segments` | Named auto-parts (barrel vs grip; bust/hip) | SDF (`thickness`) + concavity ("minima rule") + spectral cut | eigensolve on the Laplacian |

**The skeleton insight (validated in design):** "where does a tube branch" has a robust signal —
sweep a scalar field and watch **how many separate loops the cross-section has**: a sweater is
1 loop up the torso, then 1 → 3 at the armpits. The robust scalar is an *intrinsic geodesic field*
(pose-invariant), not world-height (axis-dependent). This is a Reeb graph; we build the
problem-sized slice of it, not a general library. It cross-checks against `boundaries`: we already
know there are exactly N holes, so we expect exactly N tube-ends.

**Ceiling we won't oversell:** even SDF+spectral segmentation is *heuristic* on genuinely novel /
fused shapes. The contract is **robust-auto + confidence-tagged + seedable/correctable** — the
tool segments automatically, says how sure it is, and the LLM (or human) can rename / merge /
override a region. Robust where it can be, never silently wrong.

## Dependencies

- **v1: none.** numpy is bundled with Blender (2.3.4 on Blender 5.1 / Python 3.13). Components/
  genus/boundaries/poles use bmesh; frame/curvature use numpy; thickness uses Blender's native
  `BVHTree`. Symmetry uses Blender's native `KDTree`.
- **v2: scipy** — a single wheel (`scipy`, cp313 / manylinux x86_64) bundled via
  `blender_manifest.toml` `wheels = [...]`. scipy also covers the graph layer
  (`scipy.sparse.csgraph.connected_components` / `dijkstra`), so it is the *only* dep needed.
  **Not igl** — its Python bindings are partial / under-maintained; depending on something
  unreliable is the wrong tool regardless of convenience. A single igl function may be revisited
  only if exact (MMP) geodesics ever prove necessary. **Not networkx** — the mesh-scale graphs
  belong in `scipy.sparse` (faster); the Reeb skeleton is a dozen-node graph done in plain Python.
  It is a cheap pure-Python add later if the skeleton bookkeeping ever wants it.
- **CGAL** is the named future frontier for the genuinely hard problem v2 still doesn't solve:
  robust booleans / exact predicates / repair of degenerate imports. Deferred until a task demands
  it, not pulled in speculatively.
- The scipy wheel is **Python-version-pinned** (cp313). A Blender upgrade that bumps Python may
  need a re-bundle.

## Acceptance

- `get_topology()` on any mesh returns vert/edge/face counts + the cheap bundle, with **no raw
  vertex coordinates** at `lod="low"`.
- `base="cage"` reads the pre-subsurf control mesh; `base="evaluated"` reads the modifier result —
  verifiably different vert counts on a subsurfed mesh.
- `boundaries` on Spring's pullover reports its open holes (neck + 2 cuffs + waist) with
  circumferences in cm; at `lod="high"` each carries an ordered vert-id path (a grabbable handle).
- `genus` reports the pullover as a genus-0 shell with its boundary count.
- Every landmark is addressable (vert-id / region) so it can feed a select / cut verb.
- v2 methods, when requested in v1, return an explicit "not yet (needs scipy — v2)" — never a
  silent empty result.

## Open questions

- **Per-method LOD** — deferred; one global knob for v1. Revisit if real sessions show a frequent
  "full X, summary Y" need that two calls handle badly.
- **Thickness fidelity** — v1 is a single inward ray per sampled face; true SDF averages a cone of
  rays. Upgrade to a cone if the single ray proves noisy on concave parts.
- **Symmetry beyond the three axis-aligned planes** — v1 tests X/Y/Z mirror; an arbitrary mirror
  plane (a tilted prop) needs the `frame` PCA axes as candidate planes. Compose later.
- **Curvature robustness** — v1's angle-defect + mean-sign is fuzzy and reported as such; the
  mesh-independent version is the Laplacian one (v2 territory).

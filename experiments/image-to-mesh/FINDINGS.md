# Image → Mesh — feasibility findings

**Idea:** instead of generating meshes with a 3D net (Meshy), have an image
model (Grok) draw multi-view *wireframes* of a head, then deterministically
**triangulate** those views into real geometry. The AI supplies 2D intent;
triangulation + repair manufacture the 3D validity. Advantage over Meshy:
clean quad topology and *derived* (legible) geometry instead of a hallucinated
tri-soup.

The whole point is testing whether this is even possible — climbing a ladder
of cheap experiments, each gating the next. Verdict so far: **every feasibility
question now answers YES.** Triangulation works (rung 0); the correspondence
solver works (rung 5); and — the keystone — **Image Edit produces metrically
coherent multi-views from a single front** (rung 6: corr +0.999, angle recovered
to within a few degrees). What remains is engineering (graph extraction +
occlusion), not open feasibility risk.

## Triangulation, in one paragraph

A 3D point is (X, Y, Z); a flat image only shows two of them. Orthographic
front = (X, Z), side = (Y, Z), top = (X, Y). Each world axis is seen by two
views, so combining views recovers all three — no perspective math, just
"grab the coordinate the other view has." Because Z appears in *both* front
and side, it's measured twice: on a real object the two agree (residual ≈ 0);
on incoherent inputs they disagree (residual spikes). That residual is our
incoherence metric.

## The ladder

| Rung | Question | Result |
|------|----------|--------|
| 0 | Does the engine rebuild a KNOWN object from perfect ortho projections? | ✅ exact (0.0 error); incoherence metric has teeth (scrambled correspondence → 25% error) |
| 1 | Is a Grok wireframe *structural* (real grid) or *decorative*? | ✅ structural — real face loops (eyes, mouth), valence-4 dominant |
| 1b | On a clean spec'd image (flat surface, black wires, red vertex dots) does detection go clean? | ✅ near-complete line capture; ~478 vertices grabbed directly by color |
| 2 | Are front + side the SAME head? (height-axis coherence) | ✅ reliable across 3 sheets: band corr 0.94–0.98, beats flipped-self null by +0.27 to +0.36, ≤0.5% span mismatch |
| 3 | Can we extract the grid GRAPH (nodes+edges) from one clean view? | 🟡 partial — regular grid extracts cleanly (dot-to-dot rebuild reads as the head, ~531 edges); dense feature regions (eyes/nose/mouth) degrade; some false-positive vertex dots. Graph saved to `graph_front.json`. |
| 4 | Can we produce an importable 3D mesh? | ✅ first mesh — `rung4_loft.py` lofts the front grid into 3D (`head.obj`, 464 verts / 184 faces / 653 edges); renders as a recognizable head with depth. Caveats: depth is GENERIC (no matching full-res side yet, so no nose/brow projection); surface holey in dense regions. 4-up quadrants are too low-res (only ~101 verts) — real reconstruction needs a full-res front+side **pair**. |
| 5 | Does the CORRESPONDENCE SOLVER work? (rung 0 was handed it) | ✅ tested on known head-like geometry (`rung5_correspondence.py`). **front + 3/4 view** reconstructs depth to **~0.8%** mean error and is robust to non-convex relief; **front + one side** only manages 6–9% and breaks on sockets/cheekbones. See the verdict below — this changes which views to generate. |
| 6 | Can **Image Edit** make COHERENT, metric multi-views from one front? | ✅ **yes — the big one.** Generate one front, edit-rotate it to 3/4 + side (PROMPTS.md §3). Across 3 separate, different-sized canvases the blue guides land at the same landmark heights to **<0.5% of head height**, and the 3/4 green seam tracks the side profile at **corr +0.999** (angle recovered 31°). The edits are true rigid rotations of one head, not redraws. `rung6_realdata.py`. Remaining: occlusion (far side hidden in 3/4 & side → fill by symmetry) and graph extraction. |
| 7 | Can we land a real derived head in Blender from the coherent set? | ✅ `rung7_reconstruct.py` → `head_v3.obj` (249v/318f), imported via `file op=import`. Faces from a density-adaptive Delaunay of the **front dots** (robust; sidesteps the fragile edge graph; long-vs-local edges dropped to keep eye/mouth holes), depth from the **real coherent side** silhouette in the shared head-height unit. Recognizable head with true forward relief. Rough: nose-region spikes, slightly deep proportion, open eye/mouth holes. Next fidelity step: 3/4-per-vertex depth (rung 5 solver) instead of the elliptical cross-section. |
| 14 | Force interior valence-4 + no triangles? | 🟡 half achievable, half impossible-on-this-graph. `rung14_force_quads.py`: de-triangulate (drop each tri's worst-on-ink edge) then force interior verts to valence-4 via nearest fill, gated by NO-shared-neighbour (forbids diagonals/tris) + no-crossing (planarity); boundary vs interior split by ink-in-the-gap. **Tris 39→0 — fully delivered, head_v9.obj is the cleanest mesh yet** (0 tris, 107 quads, 33 pent). BUT only **94/159 interior verts reach valence-4**: the rest have no legal 4th edge (any candidate either crosses or shares a neighbour). **Proof that {valence-4, no-tris, planar} are jointly unsatisfiable on a 58%-complete graph** — you get any two. Coverage stays 58%: forcing edges can't manufacture the missing *vertices*. Confirms (again) the bottleneck is base extraction density, not completion. |
| 13 | Can we MIRROR edges (one side → the other)? Is the graph too loose? | ✅ best completion yet, and NOT too loose. `rung13_mirror.py`: find the symmetry axis (minimise reflection mismatch), pair each vertex with its mirror twin (mutual nearest, residual < 0.45·spacing). **97% of vertices (302/311) pair cleanly** — the graph is highly symmetric. For each edge whose endpoints both have twins, propose the mirror if absent (gated convex/no-cross/on-ink). **25 of 44 mirrored edges (57%) ride real ink** — i.e. rung9 caught them on one side, missed the other; mirroring *recovered* them (vs kNN's 3% — symmetry is a real constraint, not a guess). Stacking close-the-quad + mirror: **94 → 110 quads** (`head_v8.obj`). The 19 off-ink mirrors are defensible by symmetry but left out to stay ink-honest. **Reality check on head_v8: kept faces cover only 59% of the head silhouette; ~30 open cells (not the ~5 intended holes) cover the rest.** So completion (close-quad, mirror) is marginal polish on a base that's only ~60% surfaced — the real ceiling is BASE EXTRACTION RECALL in the dense feature regions, which is a dot-DENSITY problem. The untested unlock is fewer dots (a ~100–150-vert base cage), where extraction should land near-complete on the first pass. |
| 12 | Can we "mandate valence-4 / close every cell"? | ❌ valence-4 mandate is topologically impossible (Euler: a quad sphere needs Σ(4−val)=8 of irregular verts; boundaries + holes + poles MUST be valence 2/3/5 — our 3.16 avg is *below 4 by design*). The right form of the wish is **close-the-quad** (`rung12_close_quads.py`): where a path a-b-c-d has 3 sides, add the 4th — gated so it (a) forms a convex quad, (b) **doesn't cross any existing edge** (the key guard — without it, "3-sided paths" are mostly diagonals of already-closed cells and adding them turns quads into tri-soup: 87→76 quads), and (c) rides a real wire. With all three gates: **+19 ink-verified closures, 87→95 quads** (`head_v6.obj`), zero diagonals. 88 more cells are convex + non-crossing but ride NO wire — pure manufacture, left off by default (`--manufacture` to force them: max closure over fidelity). So: don't mandate degree; close cells surgically, ink-gated. |
| 11 | Can we close the recall gap by STRUCTURAL assumption ("4 closest = edges")? | ❌ as a fill rule — but it paid off sideways. `rung11_complete.py` completes the grid by connecting each node to one nearest neighbour per direction (greedy angular-spread kNN, capped at local spacing so holes stay open — NOT raw 4-nearest, which grabs diagonals). Honesty instrument: every *assumed* edge is checked against the ink it never saw — 🟢 extracted, 🔵 assumed-AND-on-a-wire, 🔴 assumed-no-wire. Verdict on `v3_front`: assumed edges are **97% invention** (222/230 off-ink), and the overlay shows them as **diagonals slashing across cells** — Delaunay soup wearing a hat. BUT building it surfaced a real bug (below) that was throttling rung9, and fixing it gained +63 genuine edges for free. So: don't fill by assumption; the on-ink classifier is the right honesty gate for any future completion (e.g. close-the-quad when 3 sides exist). |
| 10 | Can we build a mesh from the AUTHORED edges (no Delaunay)? | ✅ `rung10_mesh_from_graph.py` recovers faces from the rung9 edge graph by a planar half-edge traversal (clockwise-most turn at each node; keep 3–5-gons, drop the outer face + big feature holes so eyes/mouth stay open). On `v3_front` (446-edge graph): 282 nodes → **122 faces (87 quads, 18 tris, 17 pentagons)**, `head_v5.obj`. All real authored-edge quads, **zero Delaunay** — a legible quad head with the eye/mouth/nostril openings as true holes. (Was 31 faces on the pre-fix 383-edge graph; the endpoint-void fix below tripled face closure.) Visualized in `rung10_faces.png`. |
| 9 | Can we extract the REAL quad edge graph (not Delaunay soup) from one view? | ✅ `rung9_trace.py` inverts rung3: nodes are the red dots, connectivity is LOCAL link-prediction. Per dot, ring-sample the directions ink leaves it, walk each direction's cone nearest-first, accept the first dot whose **chord validates against the ink**. Curve-tolerant: the validation tube WIDENS toward mid-span (`base + curve·L`) so Grok's bowed edges pass; and endpoints are TRIMMED because the red vertex dot blanks the wire under it (~4px ink void at every dot) — judging the interior, not the dot-void, was the key fix (recall 2.72→3.16, faces 31→122). On `v3_front`: 282 nodes, **446 edges, avg degree 3.16**, **precision ~perfect** (median chord 0px). **Succeeds in the eye/nose/mouth feature regions where rung3 skeletonize failed.** Remaining sub-degree-4 is mostly legit boundary/silhouette verts + a few dense-region ring merges. No turnkey library; built from numpy+scipy (distance transform + kdtree). |

### Anti-trick: don't paint the midline
A bright-green centerline seam (used early for coherence/profile) turned out to
ERASE the whole facial centre column — the seam covers its own vertex dots, so
red-dot detection finds **0 of ~43** midline vertices. Coherence is already
proven (rung6) and depth comes from the silhouette (rung7), so green buys
nothing now. Fix: midline vertices are ordinary RED dots (prompts updated);
for the existing green images, `rung9.detect` recovers the column by sampling
the seam, but the recovered dots aren't row-aligned (a faint centre seam
remains) — the clean fix is at the source (no green). Symmetry, not a painted
line, gives the midline axis.

### Key enabling tricks discovered
- **Control the input, not the detector.** A faint wireframe on a *shaded*
  surface is hard to detect; asking Grok for a *flat* surface with *solid
  black* wires makes detection trivial. Stop making the detector heroic.
- **Red vertex dots.** Asking Grok to dot each vertex in red lets us grab
  vertices by color instead of inferring them from line crossings.
- **Single 4-up image + shared guide lines.** Drawing all views in one pass
  (turnaround-sheet logic) keeps them mutually consistent; light-blue guide
  lines through landmarks force height alignment AND give a registration
  baseline for free. This is the poor-man's multi-view-consistent generation,
  and empirically it works.

## Correspondence — the verdict (rung 5)

The whole idea rests on matching vertices across views. Rung 0 proved
*triangulation* works when the correspondence is handed to it; rung 5 removes
that gift and tests the **solver** on known geometry (synthetic head with a
nose, eye sockets, optional cheekbones; project to views, shuffle + merge nodes
the way image extraction would, then try to recover depth). Numbers, depth span
≈ 1.14, error as % of span:

| Views | convex face | + cheekbones | why |
|-------|-------------|--------------|-----|
| front + one side | **6.0%** (worst 36%) | **8.6%** | side folds left onto right (**54% of nodes collapse**); rank-matching assumes frontmost = centerline, so any non-monotonic relief (sockets, cheekbones) is mis-assigned. Structural, not a code bug. |
| front + 3/4 (angle known) | **0.8%** | **0.7%** | the rotation breaks symmetry (**only 3–5% collapse**), so each front vertex matches exactly one 3/4 vertex by row-order. Convexity no longer assumed. |
| front + 3/4 (angle wrong by ±10°) | 10–15% | — | the win **depends on the angle**; a bad angle is as bad as the side. |
| front + side + 3/4 (angle *recovered* from data) | **1.3%** (recovered 35.5° vs true 35°) | — | side's one reliable signal (frontmost-per-row = facial profile) calibrates the 3/4 angle via the centerline; then 3/4 resolves per-vertex depth. |

**The decisive takeaway — which views to generate:** front + ONE side is *not*
the pair to ask Grok for. A true side view folds left onto right and can only
recover the centerline profile. **Generate front + side + 3/4** instead: the
side calibrates the (unknown, un-controllable) 3/4 angle, and the 3/4 view does
the actual correspondence. That recipe reconstructs a head with sockets +
cheekbones to ~1.3% depth error in the clean synthetic case.

Caveats on the synthetic: rows of unequal node count are dropped (real
extraction will leave holes there); order-matching within a row assumes the
3/4 angle is moderate (≤ ~40°) so X-order is preserved. Both are real
robustness items for the image version, not refutations of the approach.

## Open questions / what's NOT proven

1. **Image-side robustness of the graph** — rung 5 proves the *math*; it still
   needs clean per-view graphs to run on. Rung 3 extraction is *demonstrated*
   (skeleton punch + endpoint-snap; `rung3_extract_graph.py`) but NOT yet robust:
       a) **vertex-detection precision** — prune false red-dot blobs (some dots
          come back isolated because they aren't real vertices).
       b) **dense-region edges** — eyes/nose/mouth interiors drop edges because
          skeleton lines merge into multi-end blobs that the endpoint heuristic
          under-connects. A candidate-edge test (line-runs-between-dots) is the
          right idea but needs care to avoid false diagonals.
     Lesson logged: tuning the extractor against a SINGLE image is a trap —
     validate any change across multiple sheets.
2. **Top axis** — all sheets produced a *tilted* (~80°) top, not orthographic.
   Width/depth coherence is untested; a clean top must be generated separately.
3. **Orthographic-ness** — slight perspective in the views would add error.
4. **Ingest primitive** — the MCP server has NO way to ingest raw verts+faces
   (`from_pydata`). Landing a reconstructed mesh in Blender needs a generic
   "build mesh from explicit geometry" primitive. Deferred until correspondence
   proves out — no point building a landing pad for a plane that may not fly.

## Files
- `rung0_triangulate_known.py` — engine + incoherence metric on a known mesh
- `rung1_grid_coherence.py` — structural-vs-decorative via valence (shaded img)
- `rung1b_dots.py` — clean-image detector exploiting red vertex dots
- `rung2_coherence.py` — front/side same-head test (span + band cross-corr + null)
- `rung3_extract_graph.py` — per-view grid graph (red dots = nodes, lines = edges)
- `rung4_loft.py` — first 3D mesh (front grid + side-silhouette depth)
- `rung5_correspondence.py` — correspondence SOLVER tested on known geometry
  (front+side vs front+3/4 vs front+side+3/4; angle sensitivity + recovery)
- `rung6_realdata.py` — Image-Edit coherence on REAL Grok output (green-seam
  correlation between 3/4 and side; recovers the rotation angle)
- `rung7_reconstruct.py` — first real derived head from the coherent 3-view set
  (front-dot Delaunay surface + real side-profile depth) -> head_v3.obj
- `rung9_trace.py` — dot-anchored connectivity (the real quad edge graph):
  ring-sample directions off each red dot, walk each cone nearest-first, accept
  the first dot whose chord rides the ink through a curve-tolerant widening tube
- `rung10_mesh_from_graph.py` — mesh from the AUTHORED edges (no Delaunay):
  planar half-edge face traversal of the rung9 graph -> head_v5.obj (122 faces)
- `rung11_complete.py` — grid completion by structural assumption + the honesty
  instrument (classify assumed edges against unseen ink); verdict: kNN-fill is
  97% invention (diagonal soup), but it surfaced the dot-void recall bug
- `rung12_close_quads.py` — close-the-quad: add the implied 4th side of a 3-sided
  cell, gated by convexity + no-crossing + on-ink -> head_v6.obj (95 quads)
- `rung13_mirror.py` — symmetric edge completion: pair mirror twins across the
  symmetry axis (97% pair cleanly), mirror missing edges -> head_v8.obj (110 quads)
- `rung14_force_quads.py` — de-triangulate (0 tris) + force interior valence-4
  (no-shared-neighbour + no-cross gates) -> head_v9.obj; proves valence-4 + no-tris
  + planar are jointly unsatisfiable on the incomplete (58%) graph
- `*.jpg` — Grok-generated reference sheets used in the tests

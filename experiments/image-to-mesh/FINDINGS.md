# Image → Mesh — feasibility findings

**Idea:** instead of generating meshes with a 3D net (Meshy), have an image
model (Grok) draw multi-view *wireframes* of a head, then deterministically
**triangulate** those views into real geometry. The AI supplies 2D intent;
triangulation + repair manufacture the 3D validity. Advantage over Meshy:
clean quad topology and *derived* (legible) geometry instead of a hallucinated
tri-soup.

The whole point is testing whether this is even possible — climbing a ladder
of cheap experiments, each gating the next. Verdict so far: **the easy halves
all work; the hard half (correspondence) is untested.**

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

## Open questions / what's NOT proven

1. **Correspondence** — the real mountain. We've shown the *structure* aligns;
   triangulation needs per-vertex matching across views. The plan: extract the
   quad-grid *graph* in each view (red dots = nodes, black lines = edges), then
   align graphs by walking from shared anchors (centerline, silhouette). Grid
   topology turns blind point-matching into graph-alignment.
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
- `*.jpg` — Grok-generated reference sheets used in the tests

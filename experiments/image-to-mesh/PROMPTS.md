# Grok image-generation prompts (verbatim)

These are the working prompts used to generate the reference sheets in this
experiment. The reference `.jpg`s themselves are gitignored, so these prompts
ARE the reproducible artifact.

---

## 1. Multi-view 4-up sheet (the one that worked — used for rung 2)

Produced `multiview.jpg`, `mv2.jpg`, `mv3.jpg`. All three came back with a
front+side pair that was reliably height-coherent.

```
A clean orthographic model sheet of one stylized human female head, four
views of the SAME head at the SAME scale, arranged in a 2x2 grid:
top-left FRONT, top-right SIDE (profile), bottom-left TOP (looking straight
down), bottom-right 3/4 view.

Flat technical illustration, NOT a shaded render:
- Surface: single flat uniform light-grey, no shading/shadows/highlights.
- Wireframe: crisp solid even-weight pure-black lines, clean quad topology
  with loops around eyes and mouth.
- A small solid RED dot at every vertex.
- Background: flat pure white.

The front and side views are vertically aligned and share the same scale.
Draw faint LIGHT-BLUE horizontal guide lines running across both the front
and side views at: top of the skull, the eye line, the base of the nose,
and the chin — the same landmark must sit on the same guide line in both
views.
```

**What worked:** flat surface + solid black wires → trivial detection. Red
dots → vertices by color. Front+side vertically coherent across all 3 gens.
The light-blue guides came through and aligned landmarks across front/side.

**What did NOT work:** the bottom-left "TOP (looking straight down)" came back
**tilted ~80°** in every generation — not a usable orthographic top. A clean
top view will need its own dedicated generation / different phrasing.

---

## 2. Single clean front view (used for rung 1b)

Produced `clean_front.jpg`. Detection traced the entire grid; ~478 vertices
grabbed directly from the red dots.

```
A clean wireframe topology diagram of a stylized human female head, front
view, looking straight at the camera. Orthographic (no perspective
distortion), perfectly centered and symmetric, head and neck only.

Render it as a FLAT technical illustration, NOT a shaded 3D render:
- The surface is a single flat, uniform light-grey color — no shading,
  no shadows, no highlights, no gradients.
- The mesh wireframe is drawn as crisp, solid, even-weight pure-black
  lines over that flat surface.
- Clean quad topology with proper edge loops: concentric loops around
  each eye, concentric loops around the mouth, an even quad grid across
  the forehead and skull.
- Eyes, eyebrows, lips, and nostrils are drawn as wireframe loops ONLY —
  no dark fills, no shaded openings.
- A small solid RED dot at each vertex (every point where wire lines meet).
- Flat pure-white background.

High contrast, clean line art, like a retopology reference diagram.
```

---

## 3. Coherent 3-view, all-red dots

All vertex dots are pure red — no rainbow, and crucially NO colored centerline.
A painted green midline seam erases the entire centre column from red-dot
detection (measured: 0 of ~43 centre vertices survive; the seam covers its own
dots). Surface flat grey, wires black. Generate PROMPT A, then run B and C as
Image Edits off A's output. Cross-view correspondence comes from geometry /
row-order (rung5) and bilateral symmetry, not from dot color.

### PROMPT A — FRONT (generate)

Generate a clean orthographic FRONT view of a stylized human female head and
neck, dead-on and bilaterally symmetric, as a flat technical wireframe diagram —
NOT a shaded render.
- Surface: one flat uniform light-grey. No shading, shadows, highlights, or
  gradients on the surface.
- Wireframe: crisp solid even-weight pure-black lines; clean all-quad topology
  with concentric loops around each eye and the mouth, even quad grid elsewhere.
- Vertex dots: a small solid PURE-RED dot at every vertex, INCLUDING the vertices
  running down the facial midline. Do NOT draw a colored centerline seam — the
  midline is an ordinary black edge loop with red dots like everywhere else.
- Guides: four faint thin LIGHT-BLUE horizontal lines at top of skull, eye line,
  base of nose, and chin.
- Background: flat pure white. Strict orthographic, no perspective. No text.
The blue guides are perfectly horizontal, the head is bilaterally symmetric and
centered.


### PROMPT B — EDIT to 3/4 (feed it A's output)

Treat the attached image as a single rigid 3D object — this exact head, wireframe
mesh, and colored vertex dots. Do NOT redraw, re-topologize, or re-imagine it.
Re-render the SAME object from a camera rotated 35 degrees to a three-quarter view
showing the LEFT side of the face, nose pointing toward the RIGHT edge of the
image. Only the camera angle changes.
Preserve exactly:
- Every vertex keeps its PURE-RED dot; same count of dots. Rotate the mesh, do
  not redraw or re-topologize it.
- Same quad topology and edge loops.
- The four light-blue horizontal guides stay horizontal at the SAME heights as
  the source.
- Same flat light-grey surface, pure-black wires, pure-white background, same
  scale and vertical centering.
No shading, no perspective distortion, no new colors, strict orthographic.

### PROMPT C — EDIT to SIDE (feed it A's output)

Treat the attached image as a single rigid 3D object — this exact head, wireframe
mesh, and colored vertex dots. Do NOT redraw, re-topologize, or re-imagine it.
Re-render the SAME object from an exact 90-degree LEFT-side profile, nose pointing
toward the RIGHT edge of the image. Only the camera angle changes.
Preserve exactly:
- Every vertex keeps its PURE-RED dot. (Left-side dots are in front; far-side
  dots are hidden — expected.) Rotate the mesh, do not redraw it.
- Same quad topology and edge loops.
- The four light-blue horizontal guides stay horizontal at the SAME heights as
  the source.
- The facial PROFILE (forehead, nose, lips, chin) reads as the front silhouette
  edge — that profile curve is our depth source.
- Same flat light-grey surface, pure-black wires, pure-white background, same
  scale and vertical centering.
No shading, no perspective distortion, no new colors, strict orthographic.





Generate a clean orthographic FRONT view of a stylized human female head and
neck, dead-on and bilaterally symmetric, as a flat technical wireframe diagram —
NOT a shaded render.
- Surface: one flat uniform light-grey. No shading, shadows, highlights, or
 gradients on the surface.
- Wireframe: crisp solid even-weight pure-black lines; clean all-quad topology. Edge lines must be straight. 
- Vertex dots: a small solid dot at every vertex, color coded as red.
- Guides: four faint thin LIGHT-BLUE horizontal lines at top of skull, eye line,
 base of nose, and chin.
- Do not use a green center line. 
- Background: flat pure white. Strict orthographic, no perspective. No text.
The green centerline is perfectly straight and vertical, the blue guides are
perfectly horizontal, and the head is centered.
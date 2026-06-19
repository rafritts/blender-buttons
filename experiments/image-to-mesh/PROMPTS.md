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

## 3. Coherent 3-view recipe — CURRENT (front generate + two edits)

Rung 5 verdict: reconstruction wants **front + 3/4 + side**, all the SAME head at
the SAME scale with the SAME height registration. Instead of cramming them into a
low-res 4-up, generate ONE full-res front, then use Image Edit to re-render that
exact mesh from new camera angles. Coherence by construction (every view anchored
to one source) at full resolution per view.

All three prompts share one verbatim **STYLE LOCK** so the model can't drift.

### Carry-over anchors (must survive the edits — these are what the solver reads)
- **Four light-blue horizontal guide lines** at top-of-skull / eye-line /
  nose-base / chin, at the SAME image heights in every view. This is the height
  registration — rows align by these.
- **Bright-green centerline seam** (the facial midline). In front it is straight
  vertical; in 3/4 it curves around the form; in side it becomes the facial
  profile outline. The angle-recovery step keys off this.
- **Red vertex dots + quad topology** — same count, same edge loops; the edit
  must rotate the mesh, not redraw it.
- **Flat-grey surface / pure-black wires / white background / scale / vertical
  centering** — identical across all three.

### STYLE LOCK (identical in every prompt)
```
STYLE LOCK — keep all of this identical in every view:
- Subject: a single stylized human female head and neck, drawn as a clean
  quad-mesh retopology wireframe.
- Surface: one flat, uniform, light-grey fill. No shading, no shadows, no
  highlights, no gradients, no ambient occlusion, no specular — completely flat.
- Wireframe: crisp, solid, even-weight, uniform-thickness PURE-BLACK lines.
  Clean all-quad topology: concentric edge loops around each eye, concentric
  edge loops around the mouth, an even quad grid across forehead, cheeks, jaw,
  and skull.
- Vertices: one small, solid, PURE-RED dot at every vertex (every point where
  black wires cross). All dots the same size.
- Centerline: the vertical facial midline seam — top of skull, straight down the
  middle of forehead, nose, lips, chin — drawn as ONE continuous solid
  BRIGHT-GREEN line.
- Guide lines: exactly four faint, thin, LIGHT-BLUE horizontal lines spanning the
  full image width, at: (1) top of the skull, (2) the eye line (pupil height),
  (3) the base of the nose (nostrils), (4) the bottom of the chin.
- Background: flat PURE-WHITE. Nothing else in the frame.
- Projection: strict ORTHOGRAPHIC — no perspective, no lens distortion, no
  foreshortening, no depth of field.
- The ONLY colors in the image are: light-grey surface, black wires, red dots,
  green centerline, light-blue guides. No text, no labels, no axes, no extra
  objects.
```

### PROMPT A — FRONT (generate from scratch)
```
FRONT VIEW — generate from scratch.
A clean orthographic wireframe topology diagram of a stylized human female head,
dead-on FRONT view, looking straight at the face, perfectly centered and
bilaterally symmetric, head and neck only.

The bright-green centerline seam runs perfectly STRAIGHT and VERTICAL down the
exact middle of the image. The four light-blue guide lines are perfectly
HORIZONTAL. The head fills the frame vertically and is centered.

<STYLE LOCK — paste the block above verbatim>

Reminder: flat grey only, strict orthographic only, all-quad wireframe, a red dot
on every vertex, one straight vertical green centerline, four horizontal blue
guides, pure-white background. No shading. No perspective. No extra colors.
```

### PROMPT B — EDIT to 3/4 (feed it PROMPT A's output)
```
EDIT — same head, new camera angle ONLY.
Treat the attached image as a single rigid 3D object: this EXACT head, this EXACT
wireframe mesh, these EXACT red vertex dots. Do NOT redraw, re-topologize,
restyle, or re-imagine it. Re-render the SAME object from a camera rotated 35° to
a THREE-QUARTER view that reveals the LEFT side of the face — the head turns so
the nose points toward the RIGHT edge of the image and the left cheek faces the
camera. Everything else stays identical.

Carry-over anchors — preserve EXACTLY:
- Same number of red vertex dots and the same quad topology and edge loops (same
  mesh, only rotated).
- The four light-blue horizontal guide lines stay perfectly horizontal and at the
  SAME vertical heights as the source image — they are registration marks, do NOT
  move them up or down.
- The bright-green centerline seam stays ONE continuous line from skull-top over
  the nose to the chin; it curves naturally around the form but never breaks.
- Same flat light-grey surface, same pure-black even-weight wires, same pure-white
  background, same overall scale, same vertical centering.

Do NOT add or remove vertices, loops, or features. Do NOT change proportions or
identity. No shading, no shadows, no perspective distortion, no new colors. Strict
orthographic. ONLY the viewing angle changes.
```

### PROMPT C — EDIT to SIDE (feed it PROMPT A's output)
```
EDIT — same head, new camera angle ONLY.
Treat the attached image as a single rigid 3D object: this EXACT head, this EXACT
wireframe mesh, these EXACT red vertex dots. Do NOT redraw, re-topologize,
restyle, or re-imagine it. Re-render the SAME object from a camera rotated to an
exact 90° SIDE PROFILE that reveals the LEFT side of the face — full profile, the
nose pointing toward the RIGHT edge of the image. Everything else stays identical.

Carry-over anchors — preserve EXACTLY:
- Same red vertex dots and the same quad topology and edge loops (same mesh, only
  rotated).
- The four light-blue horizontal guide lines stay perfectly horizontal and at the
  SAME vertical heights as the source image — registration marks, do NOT move them.
- In this profile, the bright-green centerline seam becomes the facial PROFILE
  outline — forehead, nose bridge, nose tip, lips, chin — keep it as ONE clean,
  continuous green line along the front edge of the face.
- Same flat light-grey surface, same pure-black even-weight wires, same pure-white
  background, same overall scale, same vertical centering.

Do NOT add or remove vertices, loops, or features. Do NOT change proportions or
identity. No shading, no shadows, no perspective distortion, no new colors. Strict
orthographic. ONLY the viewing angle changes.
```

## Notes for next time
- Optional red-dot step occasionally risks the model *reimagining* topology
  instead of dotting the existing grid — eyeball the result to confirm it kept
  the same loops.
- For a real orthographic TOP, generate it separately and insist hard on
  "looking straight down, no tilt, no perspective" — the 4-up sheet won't give
  it cleanly.

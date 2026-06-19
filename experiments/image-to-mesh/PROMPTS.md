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

## Notes for next time
- Optional red-dot step occasionally risks the model *reimagining* topology
  instead of dotting the existing grid — eyeball the result to confirm it kept
  the same loops.
- For a real orthographic TOP, generate it separately and insist hard on
  "looking straight down, no tilt, no perspective" — the 4-up sheet won't give
  it cleanly.

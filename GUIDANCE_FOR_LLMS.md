# Guidance for LLMs driving blender-buttons

Field notes from real builds (chair, treasure chest, sword-in-the-stone, pocket watch).
Read this before modeling. It is the distilled version of every mistake already made.

## The one rule that explains everything else

**You cannot reason reliably about coordinates in a scene you didn't just author.**
Your coordinate math works only in the narrow regime where the pocket watch lived:
single object, centered at origin, axis-aligned, every number self-authored moments
ago, trig outsourced to a script. Outside that regime — compound rotations, curved
surfaces, scenes edited over hours — dead-reckoning fails silently (a fob bar
computed from a tangent heading landed 14cm adrift; a bow's resting tilt was
guessed and eyeballed). Therefore:

- Use the placement DSL (`on`, `between`, `left_of`, `snap_to`, `gap`) wherever its
  vocabulary covers the relationship. Absolute `at` is the ripcord, not the default.
- When you must compute positions (radial layouts have no relational vocabulary yet —
  see gaps P1/P2), do the trig in a script (`python3 -c ...`), never in your head,
  and generate all positions in one pass.
- Prefer tools that treat **the mesh itself as the coordinate system**
  (`select_ring`, `get_rings`, `band_around`, `scatter_on_surface`, `snap_to`)
  over remembered numbers.

## The status block is your instrument panel

Every mutating call returns exact world bounds. **Trust and use them.** A whole
case stack can be built as arithmetic on previous bounds without a single
screenshot — and on the pocket watch, zero placement corrections were needed in
~45 parts. Maintain a Z stack-up table as you go (caseback 0→0.035, band
0.035→0.135, ...). `get_object_info` is almost never needed; the answer was in the
last status block.

**But watch for exact equality.** Two numbers that *match* in your stack-up table
are a bug, not a coincidence: coplanar faces from different objects z-fight.


## Scene dressing

- `search_textures` / `search_hdris` → Poly Haven ids; `set_textured_material`
  needs no UVs (box projection). `dark_wood` + `brown_photostudio_02` is a proven
  warm product-shot combo.
- One soft AREA key light angled across the subject adds sparkle the HDRI alone
  doesn't give. Aim with `target=`.
- DOF: `set_camera_dof(focus_object=...)`; f/4 keeps a tabletop scene readable,
  f/2.8 for macro drama.
- AgX (default) for PBR realism; `set_color_management(view_transform="Standard")`
  for toon/NPR or saturated emission.

## Enlarging / reshaping a soft form (and editing imported meshes)

A mesh's origin doesn't matter — once imported (Maya `polySurfaceN`, a scan, etc.) its verts
are just verts; `select op=in_sphere` + a deform op work the same as on a self-built mesh.

But **do not use `edit op=inflate` (push along per-vertex normals) to grow a soft bulge on a
dense, irregular mesh.** On a hand-modelled/imported cap the per-vertex normals don't agree, so a
uniform normal-push lumps and *collapses* the form (this sank a bust on the first try). Instead:

- **`edit op=proportional_move`** — `select op=shrink` the patch to a small apex core, then move
  the core directionally (e.g. `forward=0.02`) with a `radius` that covers the whole bulge and
  `falloff=SMOOTH`. The core leads, the surroundings follow with a decaying blend → a rounded,
  seam-free enlargement. Pure directional motion, no normals involved.
- Keep the core **off the symmetry seam** if the lobes should stay separate — a core that spans
  both lobes + the cleft drags the valley forward too (merges a bust).
- **Verify with absolute / selection-independent reads**, not `region_form`: it is shape-relative
  (invariant to self-similar growth — see gaps G41) and can latch onto a stale selection (G42).
  The honest signals are the world-bbox bound delta and whole-mesh `feel … method=symmetry`.
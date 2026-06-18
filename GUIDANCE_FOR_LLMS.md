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


## How to find specific geometry (you judge *where*, the server measures it)

There is no "find me the feature" tool, and reaching for one is the most expensive
mistake in this doc. The division of labor is fixed: **your vision judges *where* a
feature roughly is; the server *measures* it precisely.** Do not ask the server to
*discover* a part/region for you — it can't, and that was never its job.

In particular, **don't reach for a salience finder to locate a broad, smooth swell**
(a belly, a calf, a bicep, a cheek, a brow, any soft mass). `feel … method=relief`
finds features with an *edge* — a local contrast: a nose, a fingertip, a ridge, an
eye-socket, a cut-line. A broad swell has *no* local contrast — every point on it is
surrounded by more of the same swell — so it never registers at any single radius, and
`method=curvature` is fuzzy and won't localize it either. You will burn a dozen calls
and conclude the mesh is featureless. It isn't; you're using an edge-detector to find a
hill.

The workflow that works is the same **feel → select → measure → act** loop the
destructive path uses (`feel structure → select limb → delete`), turned to construction:

1. **Judge the band** from a geometric read you *can* trust. `feel op=profile axis=Z`
   gives per-slice `X_width`/`Y_width`/girth up the body — a forward swell shows as the
   cross-axis width *climbing out of a landmark* (front-to-back depth growing up out of a
   waist pinch pins the chest band; girth exploding marks where the limbs enter the
   slice). `feel op=section` is the sibling read. These measure real cross-sections — no
   guessing.
2. **Select it** by composing `select` ops with **`action=INTERSECT`**. Take the band on
   one axis (`select op=between axis=Z`), then AND in each further constraint —
   `by_axis`/`between` INTERSECT keeps only verts *already selected AND* matching, so
   "band ∩ front-half ∩ one side" is three calls, not a select-deselect dance. The mesh's
   own symmetry centre (reported as `lr_balance`) splits left from right; you never type a
   centreline.
3. **Measure the selection.** `feel op=anchor` returns the selection's **surface-snapped
   apex point + outward normal + footprint radius** — the exact point and direction you
   could never dead-reckon on a curved surface. The normal is your honesty check: a real
   swell's normal points *outward along the bulge*, the way the feature actually faces; if
   it points sideways or inward, the selection is wrong, not the tool.
4. **Save it as a handle.** `feel op=handle source=selection name=<feature>` mints a
   *named* anchor from that selection — it recomputes its point+normal on every read, so
   it rides deformation and survives a stray deselect, and it lets you address the feature
   (and its mirror twin) **by name** instead of re-selecting. Prefer the named handle over
   the bare live selection for anything you'll touch more than once.
5. **Act at the handle/selection, never at a coordinate.** `sculpt at=selection` or the
   placement verbs via `handle=<name>` consume that anchor directly — no typed `at_x/y/z`.
   Then mirror to the twin.

**Confirm capture before you commit:** `feel op=verify` perturbs the selection and reports
whether it actually *caught* the feature or clipped it / bled into a neighbour. A
perfectly-measured anchor on a mis-captured region is still wrong. But note what `verify`
can and can't tell you: it certifies **capture** (did the selection cohere on a single
feature), *not* **identity** (is it the *right* feature — the brow and not the cheek). The
server cannot judge identity. So when `verify` passes but you are still genuinely unsure
you landed on the intended feature, **ask the human to eyeball the handle** before you
sculpt. Confirming identity by eye is the one judgement a human makes more reliably than
any ground-truth read — and it is far cheaper than discovering a misplaced edit afterward.

And do **not** fall back to *rendering* the mesh to hunt for the feature. LLM vision
self-confirms — you will see what you expected and report success whether or not it's
true — so a render launders the mistake instead of catching it. Locate by the
ground-truth reads above.

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
- **Be wary of `region_form` for confirming a size change**: it is shape-relative — invariant to
  self-similar growth (gaps G41) — so a cap that grows roughly self-similarly reads identically
  before/after. (It now reads the *live* selection correctly — the old stale-snapshot bug is fixed.)
  For "did it grow," the honest signals are the world-bbox bound delta and whole-mesh
  `feel … method=symmetry`; for "is it balanced," the `── edit ──` status block now reports the
  selection's centroid, bbox, and `lr_balance` on every call.
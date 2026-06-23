# Guidance for LLMs driving blender-buttons

Field notes from real builds (chair, treasure chest, sword-in-the-stone).
Read this before modeling. It is the distilled version of every mistake already made.

## The one rule

**THE ONE RULE lives in the server `instructions`** — always in your context, so it is not
restated here. In one breath: your sense of where things are is a hypothesis, coordinate
math goes stale the further you drift from authoring it, and you *read* spatial
relationships with `feel` rather than computing them. Everything below is how to **live**
that rule — the loops, the reads, and the failure modes distilled from real builds.

## The status block is your instrument panel

Every mutating call returns exact world bounds. **Trust and use them.** A whole
stacked assembly can be built as arithmetic on previous bounds without a single
screenshot — a multi-part stack with zero placement corrections is achievable when
every part seats on the last one's reported bounds. Maintain a Z stack-up table as
you go (part A 0→0.035, part B 0.035→0.135, ...). `get_object_info` is almost never
needed; the answer was in the last status block.

**But watch for exact equality.** Two numbers that *match* in your stack-up table
are a bug, not a coincidence: coplanar faces from different objects z-fight — and the
always-on `validate` floor (below) will catch it for you the moment it happens.

**The floor self-reports collisions — don't hand-check clearance.** After every geometry
op the `validate` line auto-flags any NEW penetration of the touched part into a neighbour
(`validate: clipping NEW Hair↔Hat 8mm`). So never compute whether two parts collide by
differencing their bounds — the read is done for you, unasked. A clean line = it sits
clear. When a clip is *intended* (a seated tenon, hair under a scalp), declare it with
`validate op=expect` (see "two senses" below); for a deeper read (contacts, resting,
facing, overlaps) reach for `feel`, never arithmetic.

**One dependent edit op per message.** Tool calls you batch in a single message reach
Blender over separate connections and run in ARRIVAL order, not the order you wrote
them. For object placement that's harmless (each reads the bounds it needs). But for
`edit` ops that build on each other — `loop_cut` then `taper_end`, `extrude` then
`bevel` on the new face — the second can run before the first and silently no-op
against geometry that isn't there yet. Issue chained edit ops one per message, each
seeing the prior result in its status block. Edits on *different* meshes batch fine.

## You build with two senses, and you don't get to close your eyes

After every edit you get two things you did not ask for, because building blind is the most
expensive failure here — it works on a simple mesh and quietly drives a complex scene into a
wall that costs a full rework.

- **`feel` (what exists)** — a short note on *what you just changed*. No verdict; it's your
  eyes. Read it against what you *meant* to build. When you want a closer look, `feel op=all`
  (the default — a bare `feel` resolves to it) runs the full perceptual sweep; opt out with
  `exclude=` only when you have a reason. A lazy read is already a broad one.
- **`validate` (what's broken)** — a correctness check that runs whether you like it or not.
  z-fighting, non-manifold edges, flipped normals, degenerate faces are **never OK and cannot
  be silenced** — if you see one, fix it before you build on top of it. Clipping/collision is
  different: it's sometimes *intended* (hair through a scalp, a tenon in its mortise). When it
  genuinely is, **declare it** — `validate op=expect` naming the pair and *why* ("Hair clips
  Body — roots seat under the scalp"). There is no "ignore" — only "I intend this." That bar is
  on purpose: an `expect` you can't honestly justify is a bug you're hiding, it stays visible to
  the human in the panel as a count, and it becomes a tripwire that fires if the intended
  overlap ever *disappears*. Declare the few real ones; never paper over the noisy ones — the
  noise is the mesh telling you it's broken.

If you ever see `validate: OFF (human override)`, the floor is down by the human's choice — you
are genuinely blind, so slow down, `feel` deliberately, and ask before trusting anything.


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
   centreline. And before you reason about which way is *front* or which side is *left*, run
   **`feel method=facing`** — it hands back the signed orientation frame (up / front / left /
   right world axes, each with its evidence) so you don't re-derive the handedness cross-
   product in your head and silently flip it. It abstains when the geometry is ambiguous;
   when it commits, trust it over your guess. (It can't certify *identity* — left-vs-right
   on a near-symmetric body is still worth a human eyeball before a destructive edit.)
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
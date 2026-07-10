# Guidance for LLMs driving blender-buttons

Field notes from real builds (chair, treasure chest, donut, a VRoid character).
Read this before modeling. It is the distilled version of every mistake already made.
(THE ONE RULE — derive, don't divine — lives in the server `instructions`, always in
your context; everything below is how to live it.)

## The loop: look → descend → claim → modify

**This is how you work here — the normal mode of operation at all times, not an
advanced feature.** Expect every modeling session, every "find the X", every edit
to run on it:

1. **look** — `look target=<mesh>` opens the root window: one orientation line plus
   5–9 salience-ranked landmarks (protrusions, islands, dense patches, poles, open
   rims), each with a position token and a scale. The server holds the window stack —
   your attention lives server-side, so you never re-serialize "where I was looking"
   into coordinate bands.
2. **descend** — `look at=<landmark id | position token>` re-runs the same breakdown
   scoped finer. Zoom IS the scale picker: a body-scale scan can't see a nose; the
   face window sees it natively. `look up` pops; bare `look` re-describes.
3. **claim** — every window OFFERS candidates: pre-run segmentations you choose from
   like a labeled menu instead of compiling predicates.
   `select op=claim candidate=c2 name=left_arm` selects it and mints a durable,
   vgroup-backed handle — the moment YOUR semantics ("that's the arm") enters a scene
   the server only knows as salience. Region algebra (`add=` / `subtract=`) composes
   claims; bilateral meshes offer the mirror twin.
4. **modify** — the claimed selection is live; edit/sculpt/transform act on it now,
   and the handle re-addresses it by name forever after.

The window's **coverage line** is honesty, not decoration: candidates that cover 78%
of a window leave 22% you must select by hand (`select op=between/flood/in_sphere`,
`action=INTERSECT` to compose). `select op=pick` is the yolo click — one arbitrary
element in a named scope, seeded, for when *which one* genuinely doesn't matter. Every
mutating select **narrates** what it grabbed (count, patches, extent, island identity,
open rims) — read the narration against your intent; it exists so you never pay a
separate verification call.

Faces are the working currency: bottom-level windows enumerate faces as BFS rings
(areas only), `look at=f<id>` opens the single-face vert view — the only place vert
coordinates exist, as Δs from the face centre. World XYZ never crosses the wire;
frame transforms are the server's job.

## The contract cuts both ways

**If the loop is broken, you are exonerated.** A window that misses the landmark you
can plainly infer must exist, an offer list without the right candidate, a narration
that misleads, a descent that dead-ends — these are **server defects, never operator
error**. When it happens: log the gap (gaps.md discipline), use the declared escape
hatches (predicate selects, `feel` diagnostics), and continue. Do NOT silently grind
back into coordinate space; do NOT contort your workflow to compensate; do NOT treat
the failure as your own. The cautionary tale: an agent once misdiagnosed a correct
grow no-op as its own misuse *and invented a false root cause*, because it assumed the
fault was its own rather than the tool's silence. A loop you must work around is a
defect in the loop — say so, out loud, in the gap log.

## Before any tool: classify the form

Tool lists anchor: "I have a lathe" pattern-matches before the form is even parsed.
Break that upstream — **before choosing any tool, classify the form** (revolved?
offset shell? two masses to merge? open rims to weld? flowed-and-set?), then pull the
matching technique:

- `guidance://techniques` — the index, one line per technique with its trigger
  condition. Pull the ONE that matches; they're short. Start any new asset with
  `guidance://techniques/form-blockout`.
- A **technique** promises an approach (the drip, the ring weld, the revolved
  vessel…) that you adapt with perception reads between steps. A **recipe**
  (`recipes/`) promises a result — a verified end-to-end transcript.

This lookup is the fast path, not homework: one resource read replaces the ten-call
detour of building the wrong thing with the wrong family of tools.

## `feel` is the diagnostic instrument

The loop's eyes are `look`. Reach for `feel` when you need **measurement**, not
orientation: exact distances and gaps (`distance`/`gap`/`clearance`), contact and
resting checks, `op=verify` on a selection you're about to mutate destructively,
fit reads (below), and **wtf moments** — when the window view and your expectation
disagree, `feel` is the precision forensics that settles it. Reaching for `feel`
mid-build should feel like a human dropping into the N-panel: the exception with a
reason, not the rhythm.

Diagnostics field notes that stay true:

- `feel op=profile axis=Z` (per-slice widths/girth) and `op=section` are the honest
  proportion reads; `feel method=facing` hands you the signed orientation frame
  (up/front/left/right) so you never re-derive handedness in your head.
- `feel op=anchor` on a selection → surface-snapped apex + outward normal + footprint;
  the normal is the honesty check (a swell's normal points out along the bulge — if it
  points sideways, the selection is wrong, not the tool).
  `feel op=handle source=selection name=<feature>` mints the durable named anchor.
- **Don't hunt a broad smooth swell with a salience finder.** `method=relief` finds
  features with an *edge* (a nose, a ridge); a belly/calf/brow has no local contrast
  and never registers at any radius. Judge the band from `op=profile`, then select it.
- `feel op=verify` certifies **capture** (the selection cohered on one feature), never
  **identity** (that it's the *right* feature). When verify passes but identity is
  uncertain, ask the human to eyeball the handle — cheaper than a misplaced edit.
- Do **not** render to hunt for features or to check your work. LLM vision
  self-confirms — a render launders a mistake instead of catching it. The human
  watches the live viewport in real time; locate and verify by ground-truth reads.

## The status block is your instrument panel

Every mutating call returns exact world bounds. **Trust and use them.** A whole
stacked assembly can be built as arithmetic on previous bounds — a multi-part stack
with zero placement corrections is achievable when every part seats on the last one's
reported bounds. Maintain a Z stack-up table as you go; `get_object_info` is almost
never needed — the answer was in the last status block.

**But watch for exact equality.** Two numbers that *match* in your stack-up table are
a bug, not a coincidence: coplanar faces z-fight — and the always-on `validate` floor
will catch it the moment it happens.

**The floor self-reports collisions — don't hand-check clearance.** After every
geometry op the `validate` line auto-flags any NEW penetration of the touched part
into a neighbour. A clean line = it sits clear. When a clip is *intended* (a seated
tenon, hair under a scalp), declare it with `validate op=expect`; for a deeper read
(contacts, resting, facing, overlaps) reach for `feel`, never arithmetic.

**One dependent edit op per message.** Tool calls batched in a single message reach
Blender over separate connections and run in ARRIVAL order, not the order you wrote
them. For object placement that's harmless; for `edit` ops that build on each other —
`loop_cut` then a deform, `extrude` then `bevel` on the new face — the second can run
first and silently no-op. Issue chained edit ops one per message; edits on *different*
meshes batch fine.

## You build with two senses, and you don't get to close your eyes

After every edit you get two things you did not ask for, because building blind is the
most expensive failure here:

- **`feel` (what exists)** — a short note on *what you just changed*. No verdict; read
  it against what you *meant* to build.
- **`validate` (what's broken)** — runs whether you like it or not. z-fighting,
  non-manifold edges, flipped normals, degenerate faces are **never OK and cannot be
  silenced** — fix them before building on top. Clipping is different: sometimes
  *intended* — then **declare it** (`validate op=expect` naming the pair and *why*).
  There is no "ignore" — only "I intend this." The declaration stays visible to the
  human and becomes a tripwire that fires if the intended overlap ever *disappears*.
  Declarations are scene facts: they live in the .blend and survive addon restarts.

If you ever see `validate: OFF (human override)`, the floor is down by the human's
choice — you are genuinely blind, so slow down, `feel` deliberately, and ask.

## Shaping a surface as math, not vertices (SPEC-19)

To *shape* a freeform patch — not assemble a primitive — read it as a **formula**,
edit the formula, write it back, and verify by re-reading. No vertex is ever typed:

1. **Select** a coherent region of quads (claim a candidate, or `in_sphere`/`between`/
   `flood`).
2. **`feel op=fit model=quadric`** → a height-field formula with **named knobs**
   (`a,b` = curvature/dome±, `c` = twist/saddle, `d,e` = tilt, `f` = offset), a shape
   verdict (dome/bowl/saddle), and the honesty stamp (`captured 91% · residual
   1.1mm`). It hands back a ready-to-run apply line.
3. **Edit the coefficients** in your head (steepen the dome: `a` −0.31 → −0.45).
4. **Apply**: `edit op=field axis=auto channel=axis:v field_mode=add expr="(…edited…) - y"`
   (the fit emits this `expr` in the field grammar; it round-trips byte-for-byte).
5. **Verify by re-fitting** — coefficients + residual confirm the surface matches
   intent. You never read a render to check shape.

**The residual is load-bearing.** A high residual means the basis can't describe this
region (a fold, an overhang, a ragged blob) — it **refuses honestly**. Split the
selection or pick a finer basis; don't push the bad formula through.

The rest of the menu: `model=rbf` / `progressive=true tol=<mm>` (quadric base +
localized `amp·exp(−r²/w²)` bumps — cheekbone, brow; round-trips via `edit op=field`);
`model=bspline basis_terms=N` (control-grid workhorse — mints via `as_surface=`, no
overshoot); `model=superquadric` (the gross mass of a closed blob; mints with
`as_surface=`); `as_net=<name>` (the fit as drawable iso-curves). To *merge* shaped
masses or weld patches afterwards, see `guidance://techniques/smooth-union` and
`ring-weld` — hard union + native seam work replaced the old compiled merges.

## Enlarging / reshaping a soft form (and editing imported meshes)

A mesh's origin doesn't matter — once imported (Maya `polySurfaceN`, a scan, etc.) its
verts are just verts; the loop and the deform ops work the same as on a self-built mesh.

But **do not use `edit op=inflate` (per-vertex-normal push) to grow a soft bulge on a
dense, irregular mesh.** The normals disagree, so a uniform push lumps and *collapses*
the form (this sank a bust on the first try). Instead:

- **`edit op=proportional_move`** — `select op=shrink` the patch to a small apex core,
  then move the core directionally (e.g. `forward=0.02`) with a `radius` covering the
  whole bulge and `falloff=SMOOTH`. The core leads, the surroundings follow → a
  rounded, seam-free enlargement. Pure directional motion, no normals involved.
- Keep the core **off the symmetry seam** if the lobes should stay separate — a core
  spanning both lobes + the cleft drags the valley forward too (merges a bust).
- **Be wary of `region_form` for confirming a size change**: it is shape-relative —
  invariant to self-similar growth (G41). For "did it grow," the honest signals are
  the world-bbox delta and whole-mesh `feel … method=symmetry`; for "is it balanced,"
  the `── edit ──` status block reports the selection's centroid, bbox, `lr_balance`.

## Scene dressing

- `search_textures` / `search_hdris` → Poly Haven ids; `material op=textured` needs no
  UVs (box projection). `dark_wood` + `brown_photostudio_02` is a proven warm
  product-shot combo.
- **Local texture sets on disk (Poliigon, Megascans, ambientCG) → `material op=pbr
  folder=<asset dir>`.** Auto-detects maps by filename, no UVs, no addon/login.
  `search_textures` is Poly Haven only — don't fall back to a flat tint when a real
  texture set is on disk.
- **UVs: box projection is the default and needs none.** Reach for `uv op=unwrap` +
  `material … space=uv` **only** when grain must follow a curved surface (a mug belly
  → `method=cylinder`, wood edge grain). `space=uv` with no UV layer refuses and
  points you at `uv op=unwrap`.
- One soft AREA key light angled across the subject adds sparkle the HDRI alone
  doesn't give. Aim with `target=`.
- DOF: `set_camera_dof(focus_object=...)`; f/4 keeps a tabletop scene readable, f/2.8
  for macro drama.
- AgX (default) for PBR realism; `render op=color view_transform=Standard` for
  toon/NPR or saturated emission (see `guidance://techniques/npr-look`).

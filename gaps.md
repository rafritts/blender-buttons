# MCP gaps

> **This file is a live worklist of CURRENT, OPEN gaps only.** No history lives here.
> Shipped, fixed, or retired gaps are **deleted, not archived** — use `git log -- gaps.md`
> / `git blame` to see anything past. No changelogs, no "what we shipped," no "considered
> and declined." When a gap is closed, **delete its entry**. G-numbers are **stable and
> never reused** — a missing number just means that gap was retired.

## North star

The agent's vision can **judge** but cannot **measure**; it reasons over outlines,
profiles, scalars, and named regions — never coordinate dumps. The server's job is to let
it stay in **intent-space** ("wrap the grip", "seat the bulb", "rest it on the desk") and
hand back **legible ground truth** instead of making it dead-reckon coordinates. Every gap
below is a place the agent was forced out of intent-space — into hand-trig, a self-managed
mode, or a number it couldn't trust. A gap is a general Blender primitive, never a
task-specific shortcut.

---

## G150 — `scatter` ignores the prototype's object rotation; lay-flat instances require baking orientation into mesh data

`transform op=scatter` instances share the source *mesh* but spawn with a fresh quaternion
built only from `align_normal` / `rotate_z` / `jitter_tilt` — it never copies the
prototype's `rotation_euler`. A cylinder pre-rotated 90° on X (long axis horizontal) still
scatters upright: with `align_normal=true` the default Z-long primitive aligns its long axis
to the surface normal (pegs); with `align_normal=false` the instance gets identity +
random Z spin only. The only workaround found was `rotate_to` → `transform op=apply
rotation=true` to bake lay-flat into the mesh, then scatter with `align_normal=true` so the
now-short local Z points along the normal. That sequence is nowhere in the tool schema and
contradicts the intuitive "set up the prototype, scatter it" workflow. Candidate fix: an
`inherit_orientation=` on scatter (copy the source object's rotation as a base), and/or an
`align_tangent=` mode that lays the prototype's long axis in the surface tangent plane
(sprinkles, leaves, shingles, scales) without a mesh-bake ritual.

---

## G153 — `object op=join` is the only weld primitive and it topology-nukes swept attachments; no clean handle-to-body attach

Attaching a swept tube handle to a hollow vessel has no middle path: keep separate (gap at
endpoints after any assembly rotate) or `join` (43 non-manifold edges, χ=5, 109
self-intersections on a mug+handle here). `edit op=connect`/`bridge` want boundary handles on
mesh rims, not "seat this tube endpoint on a curved wall." The spec's failure mode ("handle
join lumps / open boundaries") matched exactly; undo was the only recovery. Candidate fix: an
`attach`/`weld_endpoints` primitive that moves tube endpoints to live `feel op=aim` handles,
optionally fuses only the contact patches (or boolean-union with cleanup), and reports
remaining boundary loops — the relational version of join for two-part props.

---

## G157 — `select`/`component_mode` can leave edit-mode selection state out of sync with the agent's assumed mode

Several `select op=by_axis` / `component_mode` calls returned status in OBJECT mode while
the agent believed it was editing (no `── edit ──` block), forcing extra `object op=mode
EDIT` hops before `inset`/`extrude`. Modal Blender state leaks through the abstraction —
wastes calls and risks editing the wrong object after a stray viewport assumption. Candidate
fix: edit-mode select ops always enter edit on `target=` and echo the resulting mode in the
status block; or a hard `mode=` guard that refuses to run when the target isn't in the
expected mode with an explicit error instead of silently switching.


---

## G161 — `add type=tube` (spline_tube) self-intersects at the ends on a clean low-curvature planar path; curve+bevel→convert is clean

A C-shaped mug handle swept as `add type=tube` through 5–7 coplanar points on a smooth
half-ellipse (min bend radius ~15mm, tube radius 4.5–6mm — bend ≫ profile everywhere)
reported 11–15 self-intersections every time, and going *thinner* made it worse (15 vs 11),
which rules out bend-vs-radius. The identical points fed to `add type=curve subtype=BEZIER
bevel_depth=…` then `object op=convert` produced a clean watertight tube (0 self-intersections).
So spline_tube's end-cap/endpoint sampling looks buggy, not the geometry. Candidate fix:
either route spline_tube through the same curve-bevel path internally, or have the guidance
steer handle/cable work to curve+bevel and flag spline_tube as endpoint-fragile.

---

## G171 — no min-bend-radius / curvature read for a baked mesh tube (the `feel op=curve` bend check is curve-datablock only)

After building a handle as a tube and converting to mesh (the clean route from [G161]),
`feel op=curve profile_radius=…` refused: "Handle is a mesh, not a curve." There is then no
ground-truth way to verify a baked tube's min bend radius exceeds its profile radius — the
one read that *predicts* a swept form will self-intersect before you commit. I fell back to
`validate` self_intersection as a post-hoc proxy (it caught it, but only after the fact).
Candidate fix: let `feel op=fit model=swept_tube` (or a dedicated read) recover the
centerline + min bend radius from a baked tube mesh, so the bend-vs-profile check works on
the geometry that actually ships, not only on live curve datablocks.

---

## G173 — `scatter seat=true` on a curved/displaced surface leaves sub-mm float/sink per instance

seat should lift each copy so its lowest point rests on the surface, but across instances on
a noise-displaced icing crown some floated ~0.6mm (0 contacts) and others sank ~1.0mm — so
`feel op=resting` on an individual scatter instance reads "floating"/"sunk" rather than clean
contact. Within the donut spec's stated tolerance, but it means the acceptance check
("sprinkles on icing — genuine contacts") is technically failed for a fraction of the set.
Candidate fix: seat each instance against the surface under its *actual* footprint (not the
prototype's nominal lowest vert), so seating tracks local curvature; and/or have scatter
report the worst-case seat error so the loose ones are visible without polling each instance.

---

## G174 — generative sweeps (extrude/tube/curve) still demand absolute points; no relational vector-path language → see [docs/GAP-174-Extrude.md](docs/GAP-174-Extrude.md)

Free / generative extrudes (a handle, spout, horn, stem, wick — anything sweeping through
empty space) have no surface to address against, so `add type=tube|helix|curve` /
`edit op=extrude_along_curve` take **absolute `points=[[x,y,z],…]`** and force the agent to
*divine* coordinates — the one operation with no grounded, intent-space alternative (grounded
extrudes via `extrude until_contact`/`down=` are fine). This is the **root** that [G161]
(spline_tube self-intersects on a typed path) and [G171] (no bend read on a baked tube) are
symptoms of, and it is the caller [G153]'s weld kernel lacks. NOT net-new: `edit op=field`
already speaks vectors in a measured `tangent_normal` frame via `expr_x/y/z`; this gap is the
*uniform application* of that existing language to the sweep family — a path grown from a
handle as vectors in its measured `(n,u,v)` basis, optionally a function `f(t)`, with an
optional `to=<anchor> weld=true` terminus that unifies free and connecting extrudes into one
verb. Full design, examples, and open questions in the linked doc.

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
symptoms of, and the grounded path the old weld-kernel gap (G153, now superseded by SPEC-19
Phase 3 `edit op=graft mode=smin`) lacked. NOT net-new: `edit op=field`
already speaks vectors in a measured `tangent_normal` frame via `expr_x/y/z`; this gap is the
*uniform application* of that existing language to the sweep family — a path grown from a
handle as vectors in its measured `(n,u,v)` basis, optionally a function `f(t)`, with an
optional `to=<anchor> weld=true` terminus that unifies free and connecting extrudes into one
verb. Full design, examples, and open questions in the linked doc.

---

## G177 — straight 2-point `add type=tube` bakes self-intersecting geometry (floor flags it)

Two drawbridge chains built as `add type=tube points=[A,B] tube_radius=0.06 sides=6` — straight,
no bend — each baked with self-intersections (`self_intersection: chain_left has 8`, `chain_right
has 6`). A straight swept tube should be a clean prism; the intersections are presumably the
end-cap fill. Non-suppressible defect on an otherwise-correct prop. Workaround that was fully
clean: a plain `add type=cylinder` + `rotate_to` along the (hand-derived) tilt + `nudge` to the
midpoint — i.e. drop the tube primitive entirely and orient a cylinder, which costs the exact
no-coordinate convenience the tube `points=`/`between=` API exists to provide. Candidate fix:
clean up the tube end-cap triangulation (or n-gon cap) so a straight tube is self-intersection
free, and/or add a `tube`-family `between`/`points` that guarantees a manifold prism for the
straight case.

---

## G183 — `loop_cut` can't find a spanning ring once the topology forks; silently grabs a stub loop

On a hand cage grown from a slab (palm → 4 fingers extruded off the +Y cap, 3 webs recessed),
`edit op=loop_cut axis=Y cuts=2` — meant to ring the palm so the −X wall could be split for a
thumb base — returned "Cut 2 edges across 2 loop(s) — Y span [0.033, 0.036]": a 2-edge stub near
the knuckles, nowhere near the palm-spanning ring intended. Once the fingers and webbing broke the
clean wrist→knuckle edge flow, the loop walker hit poles and stopped, cutting a tiny local loop
instead of refusing. This kills the recipe idioms "slide loop cuts to isolate a base face" (step
5) and "add a holding loop on each side of every joint" (step 7) — both assume `loop_cut` finds
the obvious ring. Workarounds: isolate-then-`subdivide` a single quad for the thumb base; defer
the joint holding loops entirely. Two problems bundled: (a) no way to *aim* a loop cut (it picks
the ring from context/selection, and the pick is opaque), and (b) a degenerate short loop is
returned as success rather than flagged. Candidate fix: let `loop_cut` take an explicit ring
seed (an edge, a handle, or "the ring crossing plane Y=v") and **report the loop length it
found**, warning when the cut spans far fewer edges than the mesh's cross-section at that axis —
so a stub loop reads as the failure it is, not a silent no-op.

---

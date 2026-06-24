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

## G152 — no UV-unwrap verb; `material op=pbr`/`textured` assumes box projection forever

Stage 6 of the art pipeline (UV unwrap) and `project-vision.md` list UVs as in-scope, but no
verb exposes `smart_uv_project`, seam marking, island pack, or UV-space material wiring.
`material op=pbr`/`textured` explicitly use box projection ("no UV unwrap needed"), which is
fine for blockout but wrong when grain should follow a curved rim (ceramic plate lip, mug
belly, wood edge grain). The agent was asked to Smart UV Project the plate and mug and had to
say "do it by hand in Blender." Candidate fix: a `uv` verb (or `edit op=unwrap`) with
`method=SMART_PROJECT|ANGLE_BASED|…`, optional `target=`, and a follow-on `pack=` — enough
to flatten a hard-surface prop for texture painting without dropping to bpy.ops in a one-off
script.

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

## G155 — `transform op=seat` into a tilted/rotated hollow shell can fire the wrong interior floor

`seat` is supposed to lower a part into the highest interior floor under its footprint. On
a coffee disc seated into a mug that had been yawed for camera framing, `seat` drove the
liquid ~49mm — through the mug floor and below z=0 — while `rest_on` against the same target
was sane. The agent cannot tell from the schema when seat vs rest_on is safe on rotated
hollows. Candidate fix: `seat` honours the target's world orientation when casting for
interior floors (or refuses with "target transform non-axis-aligned — use rest_on"), and/or
`surface=interior|exterior` disambiguates the cavity read that G145 improved for axis-aligned
cups.

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

## G159 — `transform op=seat` mis-fires when the source starts overlapping/below the target (axis-aligned, not just rotated)

Distinct trigger from [G155]: seating a torus into an axis-aligned plate well, the donut
began straddling the plate (spawned at origin, lower half below z=0). `seat` drove it
*down* 2.9mm — to rest below the table — instead of lifting it onto the well floor. The fix
that worked for both the donut and (pre-emptively) the coffee was the same: `nudge` the
source entirely clear above the cavity first, then `seat` (which then dropped a sane
18.9mm / 67mm onto the real floor). So seat's interior-floor raycast is only trustworthy
when the source already sits fully above the cavity mouth. Candidate fix: seat should lift
the source clear of the target's bbox before casting (or detect initial interpenetration and
auto-lift), so a part that spawns inside/below its destination doesn't seat *through* it.

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

## G163 — `transform op=scatter` yields a few corrupt instances (inverted normals, wild misplacement) needing manual cull

Scattering 80 capsule sprinkles onto a curved icing crown left 2 instances with inverted
normals (mirrored alignment frames → would render dark) and 2 placed 30–45mm into the
surface (clip depth larger than the whole donut — almost certainly seated onto a wrong/inner
face near the hole boundary). ~5% defect rate, each a hard `validate` defect with no
suppression path, fixable only by deleting the offending instances by name. Candidate fix:
scatter should reject negative-determinant (mirrored) placement frames and discard
instances whose seat lands deeper than the prototype's own height, reporting the count it
dropped rather than emitting broken geometry.

---

## G165 — `feel op=resting` reports nonsense when an object contains another (vessel + liquid)

`feel op=resting targets=Mug` returned "on Coffee, 0 contacts, sunk 62.8mm" — the mug rests
on the *table*, but the read latched onto the Coffee disc sitting *inside* it and reported a
62mm sink. `feel op=contacts` on the same pair was correct ("Mug connected to Table,
Coffee"). So resting picks the nearest surface beneath the part without excluding geometry
the part encloses. Candidate fix: resting should ignore targets fully contained within the
queried object's footprint+height (or prefer the lowest external support), so a filled
vessel still reads as resting on the table.

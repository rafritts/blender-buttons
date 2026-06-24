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


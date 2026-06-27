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
symptoms of, and the grounded path the old weld-kernel gap (G153, now superseded by SPEC-19
Phase 3 `edit op=graft mode=smin`) lacked. NOT net-new: `edit op=field`
already speaks vectors in a measured `tangent_normal` frame via `expr_x/y/z`; this gap is the
*uniform application* of that existing language to the sweep family — a path grown from a
handle as vectors in its measured `(n,u,v)` basis, optionally a function `f(t)`, with an
optional `to=<anchor> weld=true` terminus that unifies free and connecting extrudes into one
verb. Full design, examples, and open questions in the linked doc.

---

## G175 — a second sequential `edit op=boolean` (EXACT) on the same mesh inverts that mesh's normals

Cutting a gate through a curtain wall as two chained `DIFFERENCE` booleans (a box, then an
arch cylinder) on the *same* target: the first applied clean, the second flipped the whole
wall — `inverted_normals: wall_front normals appear inverted (most face inward)`. Not the new
recess faces — the *entire* shell. A single boolean (one combined cutter) on the same wall is
always clean; arrow-loop strips (one arrayed cutter → one boolean per wall) and the moat
ring/trench (one boolean each) never inverted. So the trigger is specifically **applying a
second EXACT boolean to a mesh that is already a boolean result**. The floor correctly flags
it, but it's non-suppressible (rightly), and there is **no in-place fix** (see [[G176]]) —
the only recovery was `history op=undo_to` back past both booleans and rebuilding the gate as
a single combined cut. Candidate fix: recompute/repair output normals after every applied
boolean (recalc-outside on the result), or at least detect+auto-correct a fully-inverted
result; failing that, document that multi-cut features must be one unioned cutter.

---

## G176 — no `recalc_normals` / `flip` primitive: a flipped-normal mesh has no recovery path short of undo

When G175 inverted the wall, the floor named the defect but nothing in the schema fixes it.
`material shade_smooth/flat` is shading, not winding; `object remesh` rebuilds topology
(destroys crisp boolean edges); `edit` has no `recalc_normals`/`flip`/`make_consistent`.
Blender's everyday "Mesh ▸ Normals ▸ Recalculate Outside" (Shift-N) — the standard one-keystroke
fix for exactly this — is simply not exposed. The floor declares flipped normals "never OK and
cannot be silenced," which is right, but pairing an unsuppressible defect with **no repair op**
forces a full undo+rebuild for what is a one-operator fix in the UI. Candidate fix: add
`edit op=recalc_normals` (outside/inside) and `edit op=flip` over the current selection (default
whole mesh), so a flipped boolean result — or an imported mesh with bad winding — is recoverable
in place. Pairs with [[G175]].

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

## G179 — no material-slot removal: a mesh can be consolidated *to* the right faces but not *trimmed* to the right slot count

Prepping a frankenstein character (two skeletal meshes `object op=join`ed into one — 7 material
slots, but the target game asset declares 4) for an in-game-compatible slot layout. `material
op=assign` cleanly moved the surplus faces onto the correct slots, leaving three slots at **0
faces** — but nothing in the schema can then *remove* them. Neither `material` (set/assign/
toon/…) nor `object` (info/join/split/rename/…) exposes slot removal, and Blender's one-click
**Material Properties ▸ ⌄ ▸ "Remove Unused Slots"** is unreachable. So a mesh that must match an
external asset's exact slot list (game-mod round-trip, FBX hand-off) can be reassigned correctly
yet never brought to the right slot *count* from the server — the work has to finish in the UI.
Candidate fix: `material op=remove_slot slot=N` + `op=remove_unused_slots` (drop every zero-face
slot), and/or a `consolidate` that reassigns-then-trims in one call. Pairs with the export-prep
naming need (slot names must match the target asset).

---

## G180 — no `.blend` append: combining two existing scenes forces an out-of-band `bpy` script

Building a two-character workbench by bringing a fully-textured rig+mesh out of one saved
`.blend` into another (the everyday **File ▸ Append**). `file op=import` covers mesh interchange
formats (obj/stl/ply/glb/gltf/fbx) but **not** appending objects/collections from a `.blend`.
With the donor already a packed `.blend`, re-importing its source GLB throws away the assemble
step's wired+packed materials, so the only route was a headless `bpy.data.libraries.load` script
run *outside* the server (plus a manual parent-aware translate, since nudging a parented mesh
*and* its armature double-moves the mesh — see the shift gotcha). A user who "doesn't know how to
import a .blend" cannot be helped by the toolkit at all here. Candidate fix: `file op=append
path=<blend> [name=<object/collection substr>] [link=false]`, linking the appended roots into the
scene — the in-server equivalent of Append.

---

## G181 — a selection's spatial extent isn't readable without a manual edit-mode hop

Verifying *where* a material/vgroup selection sits — does CyberBunny's skin reach down the
forearm, or stop at the shoulder (i.e. is there arm skin under the sleeves)? After `select
op=material` / `op=group` in Object Mode, the status block's `bounds` report the whole **object**
bbox, not the selection's, and `select op=current` errors `Must be in edit mode`. Getting
`sel_bounds`/`sel_z` meant an explicit `object op=mode mode=EDIT` first, then re-running the read
— a forced mode toggle mid-derivation just to answer "how far does this selection span," which is
exactly the kind of grounded read THE ONE RULE wants cheap. Candidate fix: have `select
op=current` report the live selection bbox/centroid regardless of mode (or surface `sel_bounds`
in the status block whenever a non-empty component selection exists), so a selection's extent is
one read, not a mode dance.

---

## G182 — `taper_end` / `taper_section` ignore the live vertex selection and operate on GLOBAL axis rings

Tapering one finger of a hand (the finger's 4 rings selected, 16 verts) with `edit op=taper_end
axis=Y end=MAX scale=0.55` scaled only the single end ring of the *whole mesh*; `edit
op=taper_section axis=Y from_ring=0 to_ring=-1 …` then reported "tapered rings 0..6 of 7 (44
verts)" — i.e. it binned **every vert in the object** into rings along Y and tapered the lot,
squeezing the palm, not the selected finger. There's no way to scope either op to the selection,
so per-feature tapering (one finger, one phalange band, one limb of many) is impossible with the
named taper primitives. The reliable fallback was hand-rolling the taper: select each ring by a
thin `between axis=Y` band and `transform op=scale_verts sx/sz` it individually — N selects + N
scales where one op should do. The schema reads as selection-aware (it sits in `edit`, which
"operates on the current selection"), so the global behaviour is a silent contract break.
Candidate fix: have `taper_end`/`taper_section` parameterize over the **selected** rings only
(fall back to global when nothing is selected), matching every other `edit` op; or document the
global scope loudly and add a `selection_only=true`.

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

## G184 — fraction-band selection (`select op=between` lo/hi 0..1) restales every time the bbox grows mid-build

Throughout the hand build, isolating a face/ring meant `select op=between axis=X lo hi` with
lo/hi as 0..1 fractions of the **current** bbox extent. But the bbox keeps growing as you model:
the moment the middle finger reached Y=0.125, every Y fraction I'd been using shifted (the +Y cap
row that was fraction 0.57–0.60 became 0.0519–0.057 → selected 0 verts), and an X `hi` that
landed exactly on a vert row clipped it (x=0.021 verts dropped at `hi=0.742`, a boundary
inclusivity surprise). So a band that selected the right thing five edits ago is a stale guess
now — the same perishability THE ONE RULE warns about, but injected by the *addressing scheme*
itself, forcing a recompute-from-status-bbox before every single selection. It's workable (read
bounds, redo the arithmetic) but it's the dominant friction tax of detailed component work, and
the failure is quiet: a wrong fraction just selects fewer/other verts, no error. Candidate fix:
accept **world-space** lo/hi on `between`/`by_axis` (e.g. `axis=Y world_lo=0.043 world_hi=0.046`)
so a band addresses a fixed location that doesn't drift as the mesh grows, and/or make `hi`
inclusive of verts within epsilon of the bound. A world-space band is to fraction-bands what the
status bbox is to a guessed coordinate — the ground-truth version of the same address.

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

### G188 — Poliigon addon is installed, but only Poly Haven has a search→download→apply path

`material op=search_textures` / `op=search_hdris` query Poly Haven, and `op=textured` then
fetches and wires the chosen id in one call — a full *find-by-intent → download → apply*
pipeline for one library. For **Poliigon there is no equivalent**, even though the Poliigon
addon is installed in the build. The guidance tells the agent to "download via its own addon,
then apply with `material op=pbr folder=`" — i.e. drop out of the server entirely, drive the
Poliigon addon by hand in Blender's UI, and only rejoin once the maps are sitting on disk.
`op=pbr folder=` is the *apply* half only; the *find* and *fetch* halves are a manual,
out-of-band detour.

The cost is intent-space: a recipe that says "marble PBR from Poliigon / ceramic / icing /
pottery" (donut2.md does, four times) can't be satisfied by naming the look. The agent either
asks the human to hand-download four sets, or silently substitutes Poly Haven / procedural and
quietly changes what was asked for. The library the artist actually licensed is the one the
server can't reach by name.

The missing primitive: a Poliigon search/fetch path that mirrors the Poly Haven one — e.g.
`material op=search_textures source=poliigon query="marble"` returning asset ids, and
`op=textured source=poliigon asset_id=...` driving the installed addon to download + apply
(falling back to the existing `folder=` apply once local). Same find→fetch→apply shape, just
pointed at the second library that's already authenticated in the build. Until then, "from
Poliigon" in a brief is an instruction the server can read but not honor.

### G189 — no way to create a Lattice (or any deform-cage) object → cage-deform intents are unreachable

`add` mints meshes, curves, lights, cameras — but there is **no Lattice primitive**, and no
empty/cage either. The deform modifiers that need a partner cage (`modifier op=add type=LATTICE`,
and likewise MESH_DEFORM) name a `host`/cage object that must already exist — but nothing in the
verb set can bring that cage into being. So the entire **lattice / cage free-form deformation**
workflow is dead on arrival: the artist can't drop a 4×4×4 lattice over a form, parent the mesh to
it, and push lattice points to warp the whole thing (the donut2 recipe asks for exactly this — "add
a 4×4 lattice … deform the icing and sprinkles").

The cost is a whole *class* of edit: a low-res cage that warps a dense mesh (and any instances on it)
as one smooth gesture, non-destructively, is the standard way to give a stiff form organic life. The
only workarounds are destructive direct-mesh deforms (`proportional_move`, sculpt) on the base mesh —
which work, but lose the non-destructive cage and can't be re-grabbed later.

The missing primitive: `add type=lattice` (resolution u,v,w, sized to enclose a target) that mints a
real Lattice object, plus a `transform` path to move its points by intent — then `modifier op=add
type=LATTICE host=<mesh> target=<lattice>` finally has a cage to bind to. Pairs with the existing
LATTICE/MESH_DEFORM modifier support, which today points at an object the toolset can't produce.

### G190 — `edit op=bridge` can't make the canonical two-hole handle: non-manifold + inconsistent topology

The textbook way to model a mug/jug handle is "cut two holes in the wall, select both rims, **Bridge
Edge Loops**" — and donut2 names it directly ("Bridge Edge Loop Gaps"). Driving exactly that through
`edit op=bridge a=<hole-A> b=<hole-B>` (two clean 6-vert boundary handles minted by `feel op=assembly`)
produced a tangled result every time: `+52 faces … 18 non-manifold edge(s) … 3 self-intersection(s) …
impossible topology (χ=0, 3 boundary loops)`. Lowering `bridge_cuts`/`smoothness`/`profile` reduced
the mess but never reached a clean manifold tube; the two source boundaries were never consumed (the
hole count stayed at 3). The validator's own verdict: "the op likely did the opposite of its intent."

So the one operation the docs point at for a tunnel-between-two-holes can't deliver it. The fallback
that *did* work was sweeping a `add type=tube` through the two measured attach points and seating its
ends into the wall — clean, but it's a separate object lapping the wall (a declared clip), not the
welded single-shell handle the bridge was supposed to give.

The fix is in the bridge itself: when `a` and `b` are two boundary loops on the **same** shell, weld
rim-to-rim into a manifold tunnel (consuming both boundaries, genus +1) instead of fanning faces that
self-cross. Until then, `feel op=assembly` happily mints the two handles, and the very next suggested
step (`edit op=bridge a=… b=…`) can't honor them.

### G191 — Geometry-Nodes modifier inputs are write-once: no socket edit after `add_asset`

`modifier op=add_asset` sets GN sockets fine at creation (`Density`, `Seed`, `Collection`, `Realize
Instances`, …). But there is **no way to change one afterward**: `modifier op=modify … inputs={…}`
returns an empty set and mutates nothing — the `inputs` dict is honored only on `add_asset`. So
flipping a single dial on a live scatter/array (raise the density, toggle Realize Instances, switch
Distribution Method to Amount) forces a full **remove + re-add** of the modifier, re-specifying every
socket from scratch and losing stack position. That's the opposite of how a node modifier is meant to
be lived with — its whole value is tweakable dials.

The missing primitive: let `modifier op=modify` accept the same `inputs={socket: value}` map as
`add_asset`, validated against the live modifier's socket list (it already knows the names — it prints
them). One dial in, one dial changed, stack untouched.

### G192 — no ground-truth read of a Geometry-Nodes instance COUNT (scatter density is unverifiable)

A scatter brief is a number — "about 500 sprinkles." But nothing reports how many instances a GN
modifier actually emits. `feel op=audit` and `object op=describe` both read the **base** mesh
(the icing shell's 10368 tris), not the evaluated instance stream; `describe posed=True` says nothing
about instances. The only way I found to even estimate was to duplicate the host, `modifier op=apply`
to realize, and read the tri/loose-vert delta — and even that was noisy (realize-on welds, realize-off
on apply drops them). So "set density to ~500" can't be confirmed against ground truth; the agent is
left guessing whether Density is per-m² or absolute, with the render (which it's told not to read) the
only real feedback.

The missing read: an instance-aware count on the evaluated geometry — e.g. `feel op=audit` reporting
`instances: N (from 'Scatter on Surface')` alongside base tris, so a density/amount can be dialed to a
target the way every other quantity in this server is measured rather than eyeballed.

### G193 — `graft` (smooth-min SDF) cracks open on a tall-thin organic assembly; voxel-remesh is the working substitute

Building a ~1.55m female blockout, the recipe's core merge step — `buttons-blend-macro op=graft` of the
torso + a leg (each a clean closed genus-0 shell, verified) — returned a **non-watertight, fragmented**
result every time: "⚠ has open edges at the seam", and `feel op=topology` showed **31 shells / 31 open
boundary loops (χ=−129)** at resolution 96, and the same open-seam warning at resolution 64. Two very
different resolutions failing identically rules out simple voxel noise. The likely cause is the cubic
`N³` grid stretched over a non-cube bbox: the body is ~1.44m tall but ~0.25–0.45m in X/Y, so the Z cells
are 3–5× the X/Y cells, and the marching-tetrahedra surface cracks along the anisotropic blend seam. So
graft — sold as THE clean watertight mass-to-mass weld — fails on exactly the elongated organic
assembly (a limbed body) it's most wanted for, and there is no `voxel_x/y/z` or "uniform cell size"
control to fix the anisotropy.

What worked instead: `object op=join` the five primitives (join honors each part's *live* world
rotation — see G194) then `object op=remesh mode=voxel voxel_size=0.012` → a single **closed genus-0
shell**, X-symmetric to 0.001mm, watertight by construction, with naturally rounded hip/shoulder joins.
Native voxel-remesh delivered the graft's stated goal that graft itself couldn't. The missing piece in
graft: either uniform-cell-size voxelization (cell metres, not a per-axis count) so a tall bbox doesn't
crack, or an internal fallback to the native voxel path when the bbox aspect ratio is extreme.

### G194 — `duplicate_mirrored` and `apply rotation` silently STRIP a live axis tilt (a splayed limb comes back upright)

A leg given a 4° outward splay (`transform op=rotate axis=Y angle=4`) reads correctly while live —
`object info` shows `rotation_deg [0,4,0]`, `tilt_off_vertical_deg 4.0`, rotation-aware bbox width 0.245.
But the moment you try to *commit* or *mirror* that tilt, it vanishes:
  • `object op=duplicate_mirrored axis=X` produced a twin with `rotation_deg [0,0,0]`, `tilt_off_vertical
    0.0`, and width **0.190 = the UN-rotated width** — i.e. an upright leg, not the −4° mirror image.
  • `transform op=apply rotation=True` on the original did the same thing: world bbox collapsed from
    width 0.245 (tilted) to 0.190 (upright), foot X jumped from −0.213 to −0.157. Applying the rotation
    *removed* it instead of baking it into the mesh.

So you cannot mirror a splayed limb, and you cannot bake its rotation — both paths quietly discard the
Y-tilt and leave geometry that's wrong in a way the status block's own numbers contradict. The reflection
of `Ry(θ)` across the YZ plane should be `Ry(−θ)` (same bbox); apply should leave world geometry
invariant. Both are broken for an off-axis object rotation.

Workaround used: build each side independently with explicit mirror-image live rotations (`+40°` / `−40°`
for the arms), never apply/mirror, and let `object op=join` bake the world transforms at merge time —
join *does* honor live rotation correctly (arm tips landed at ±0.51 as authored). But that only works
because a later join consumes them; anything that needs a baked-or-mirrored single tilted part is stuck.

### G195 — draping a grid with ONE function makes a ribbon; the loft path has no per-line function array and no ribbon warning

The grid + field-deform path is, conceptually, **vacuum forming**: the `add type=grid` sheet is the hot
plastic, a function is the mould, `buttons-deform-macro op=field` is the vacuum that pulls each vert onto
the form. That framing is sound — and it exposes the gap. A loft/drape is properly an **array of
functions, one per grid line**; the *variation across that array* is what gives the sheet its second
curvature (a true double-curved shell). The field deformer applies exactly **one** function (preset |
points | expr) uniformly across the whole selection — it has no notion of a per-line array — so the only
shape it can produce in the un-varied direction is an **extrusion**: a single-curvature **ribbon**.

Concrete: built `body_card` (grid 14×80) and ran `field channel=axis:Z add` with a 16-point silhouette
curve along the height axis. `feel op=profile axis=Z` then showed `Y_width = 0.3000` at **every** height
band — dead flat across the depth, i.e. the silhouette bent down the length but never across the width.
Developable ribbon, not a body shell. The mould was a 1-parameter function `w(z)`; a 1-D mould can only
bend the sheet one way.

Two missing pieces, both intent-level (NOT a return to `surface_patch`'s typed P(u,v) coordinate math,
which was cut as off-thesis):
  • a **drape/loft op that takes a per-line function array** (or, equivalently, interpolates between a
    handful of named cross-section profiles down the grid) so the sheet picks up curvature in both u and
    v — the actual vacuum-form-onto-a-solid, vs. extrude-a-profile.
  • a **teaching warning** when the per-line functions are uniform — identical, or differing only by a
    rigid offset (still developable): `⚠ uniform functions → this drapes as a ribbon (single curvature),
    not a shell`. A *warn*, never a block — a ribbon is sometimes the intent (a strap, belt, flat curved
    panel), same spirit as the existing validate ⚠ lines.

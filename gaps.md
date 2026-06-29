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

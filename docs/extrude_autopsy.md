# Extrude autopsy — mug handle session

Field notes from a live dogfood session (donut scene → mug handle rebuilds →
mug-only extrude focus). Not a changelog. The mesh was never the product; this is
where freeform extrude forced the agent out of intent-space.

---

## What made it hard

A mug handle is a **freeform path through empty space** that must:

- start on measured wall geometry
- travel through air as a thin solid bar
- land cleanly on another patch of wall
- look continuous under Subsurf + Solidify

That is one of the few modeling jobs where **intent-space almost runs out**.
Placement tools (`on=`, `between`, `rest_on`) and grounded extrudes (`out=`,
`until_contact`) work when there is a surface to talk about. A handle’s mid-arc
has **no surface to address**. So every attempt collapsed into one of two awkward
recipes:

1. **Delete two wall patches → bridge** → hollow *pipe* topology
2. **Multi-extrude a solid finger → try to land** → self-intersections, zero-area
   faces, merge chaos

Neither is the human gesture “draw a sleek C with the mouse.”

---

## Why it got messy (mechanics)

| Layer | What went wrong |
|--------|------------------|
| **Topology choice** | Bridge-of-holes makes a **tube**. Ceramic handles are usually a **solid rod** (or a nearly filled tube). Solidify then either bloats the bar or collapses the “finger hole” (which was never the right hole — humans put fingers in the *C opening*, not the pipe interior). |
| **Bridge dials** | `profile` / `smoothness` / `cuts` are real Blender knobs, but they don’t read as “make it look like the reference photo.” Effect size is opaque; same dials produced ~5 cm vs ~8 cm stick-out without legible feedback. |
| **Multi-extrude chain** | Each step only moves the **end cap**. Pure `up=` created degenerate faces; landing by extruding *into* the wall caused self-intersections; merge-by-distance papered over bad topology and then reported χ-impossible. |
| **Selection** | “Those two faces on the right, mid-low” became a **predicate dance** (X ∩ Y ∩ Z bands). Wrong band → whole vertical strip → wrong tube diameter. Humans just click. |
| **Solidify as a global modifier** | Wall thickness and handle thickness are the **same dial**. A thickness that reads right for the cup can destroy the handle cross-section. |
| **No mid-build shape read for “does this look like a handle?”** | `feel` gave clearance, genus, bounds. It did **not** give “tube diameter along arc,” “C opening size,” “thickness variation,” or “matches reference silhouette.” |

Messiness was not random — it was **compounded topology + opaque dials + weak
selection + one thickness for two jobs**.

---

## Missing from Blender’s standard tool set? Mostly no

Blender already has what a human uses for this:

- Extrude region (repeated)
- Bridge Edge Loops
- Proportional edit / smooth
- Solidify + Subsurf
- Optionally: curve + bevel, spin, etc.

**The engine is not missing the operators.** What’s missing is a **composition of
them that stays in intent-space** for free sweeps.

There is an in-repo gap for exactly this: **GAP-174** (`docs/GAP-174-Extrude.md`) —
free/connecting sweeps from measured frames, not inventing midpoints. There is
also an older `extrude_along_curve` helper, but it still wants a curve of points
and isn’t a first-class “from wall A to wall B as a thin C” path on the collapsed
verb surface.

So: not “Blender can’t extrude.” It’s “the server never productized the *handle
gesture* as a legible primitive.”

---

## Missing from eyes / hands / mouse / keyboard sense

This is the bigger half.

### Eyes (perception)

Humans continuously see:

- silhouette of the C
- thickness along the bar
- whether the join is smooth or pinched
- proportion vs the body

The agent got:

- bbox dims
- validate (self-intersect, degenerate)
- status after each op

Those catch **broken mesh**, not **ugly handle**. No “section radius along path,”
no “opening height of the C,” no cheap silhouette check for the handle alone. So
we optimized for *validate: fewer red lines*, not *reads like the reference
photo*.

### Hands (action granularity)

A human with a mouse:

1. Click two faces
2. Extrude, drag, rotate view, extrude again
3. Nudge the mid-span with proportional edit
4. Eyeball until it feels right

The agent:

1. Compiles face clicks into axis predicates (error-prone)
2. Issues **one discrete extrude vector per message** (no continuous drag)
3. Cannot “pull the middle of the handle out a bit” without re-selecting a band of
   verts by coordinates/predicates
4. Dependent edits must be sequential; no sculpt-like continuous correction loop
   on the arc

So the **hand** is a series of rigid transforms, not a continuous stroke.

### Mouse / keyboard (control affordances)

Missing “soft” controls that humans use constantly:

- drag extrude with live feedback
- middle-mouse orbit while extruding
- scale the *profile* while the path stays put
- soft select the mid-handle and drag along the outward normal

We had meters and axis words — good for precision blocks, **bad for freeform
taste**.

### The dual-sense contract broke for *form*, not *defect*

`feel` + `validate` answer “is geometry broken?”  
They barely answer “is this *shaped* right?” for an organic C.

That’s why multiple rebuilds still felt like wrestling: each rebuild fixed a
*defect class* (flush torus, fat pipe, self-intersect) and reopened a *shape
class* (sleekness).

---

## One-line root cause

**Grounded extrude is strong; freeform extrude-through-air is not an intent-space
verb yet** — so the agent fell back to Blender primitives that produce the wrong
topology (pipe vs rod) and corrected with dials it couldn’t see.

---

## If we fix the server (general, not “mug handle”)

1. **Relational sweep** — `from` / `to` handles, path as arc/C in a measured
   frame, profile radius as a dimension (GAP-174)
2. **Section as a first-class quantity** — “bar Ø 10 mm,” report achieved Ø after
   solidify
3. **Solid vs shell handle modes** — don’t silently produce pipes
4. **Selection that isn’t coordinate bands** — claim/offer “side faces at height
   band” from look
5. **Shape reads** — path length, min bend radius, C opening, thickness variation

Until that exists, a sleek mug handle will keep being hard for *any* blind agent
— not because Blender lacks Extrude, but because **extrude-as-intent for
empty-space curves was never finished**.

---

## Related

- `docs/GAP-174-Extrude.md` — relational sweeps; measured frames; proposed
  `edit op=sweep`
- Session context: donut tutorial dogfood → mug handle rebuilds against a photo
  reference (sleek solid C-rod) vs server results (fat pipe / self-intersecting
  multi-extrude)

# Curves Feedback — Connecting Shapes with Curves

Findings from the first dogfooding pass at connecting two shapes (two offset, differently-oriented
tubes) with organic curved connectors instead of straight shortest-path bridges. This is a net-new
capability area. Gaps are framed as **general Blender primitives**, not task-specific.

The gaps fall into six layers — from the surface primitive down to the thing that's really missing.

## 1. The connection primitive itself
- **`bridge` is straight-only.** It welds two loops with single-segment shortest-path quads — no
  curvature. Native Blender Bridge Edge Loops already exposes the dials that fix this:
  **Number of Cuts, Smoothness, Profile Factor, Twist, Merge**. None are surfaced. With
  cuts+smoothness a bridge bulges into an S that leaves each loop along its normal.
  *Smallest change with the biggest payoff.*
- **No twist/alignment control on the weld.** When the two loops face different directions (e.g. a
  +Z opening and a tilted one), vert *i* of loop A should map to the nearest vert of loop B. There's
  no twist parameter, so the band spirals.

## 2. Sweeping a hollow tube along a path
- **`extrude_along_curve` sweeps the *filled* face → a solid, non-manifold rod** (read back as
  *genus -24, chi=50* — broken). No "sweep the rim only / hollow" mode, and no auto-strip of
  start+end caps.
- **It ignores the curve's world placement.** It re-launches the curve as a *relative* shape along
  the face normal, so you cannot pin the far end to a target. The only way to land on the target tube
  was reverse-engineering the rule (force start-tangent = face normal so no reorientation happens).
  Needs an explicit **sweep-to-handle / sweep-along-curve-in-world** mode.
- **No roll control on the swept cross-section**, so even a successful hollow sweep arrives at the
  target loop mis-rotated and unweldable.

## 3. Authoring the curve in intent-space (the deepest gap)
- **There is no relational way to author the connecting curve.** Every Bezier control point was
  placed by typed coordinates plus trig in a Python script — exactly the dead-reckoning the whole
  system is built to forbid. Needs a primitive like **"curve from handle A to handle B, leaving each
  along its surface normal, with bulge/slack N."**
- **No concept of tangent/normal continuity.** "Organic" *means* the connector exits each opening
  along that opening's normal. Nothing in the toolset can express "leave the tube the way the tube is
  pointing." Today that's left to guesswork on control points.
- **No feasibility awareness.** Tube radius vs. bend radius vs. tube spacing is a hard constraint
  (fat tubes sitting close *cannot* be joined by a smooth fat curve). `extrude_along_curve` reports it
  *after* you try; nothing derives the feasible curve, or offers to auto-taper/thin the connector to
  fit.

## 4. Surgery & selection to set up / clean up a connection
- **No select-by-shell / select-linked.** To open one capped tip required `split` by loose parts just
  to isolate a connected piece.
- **No select-by-face-type** (n-gons / non-quads), so a cap can't be picked out by what it *is*.
- **No "open/close end" (uncap) primitive.** `delete ONLY_FACE` silently no-op'd because the cap
  wasn't the single face assumed — guessing topology by hand.
- **No "select the boundary loop / Nth ring nearest a handle."** Isolating a 16-vert rim came down to
  hand-tuning an `in_sphere` radius to 0.305 m. Brittle.

## 5. State & workflow friction
- **Inconsistent edit-mode entry.** `select`/`grid_fill` auto-enter edit mode; `extrude_along_curve`
  does not, and then reports the *wrong* error ("must be in edit mode with a face selected") when the
  real problem is mode, not selection.
- **Selection/mode resets to OBJECT between calls**, so multi-step edit sequences are fragile and need
  re-selection each time.

## 6. Verification & hygiene
- **No "is this connection good" check.** `feel` lints topology and self-intersection, but nothing
  evaluates the connector *as a connector*: continuity, flow, pinching, normal match at the seams.
- **Generalize the one great diagnostic.** `extrude_along_curve`'s bend-radius-vs-profile-radius
  preflight is the best feedback in the toolchain — `bridge` and the tube primitives have nothing
  equivalent.
- **`feel op=assembly` collides with orphaned handles** from deleted owners (minted 2 of 4 until
  pruned). Handles whose owner is gone should auto-prune or be namespaced.
- **`add type=tube` (SPLINE_TUBE) is unreliable for welding:** `sides=` is ignored (always 36), it
  fragments into multiple shells on tight curves with no warning, and reports doubled boundary loops —
  so its output can't bridge 1:1 to a real cylinder.

## Priority
- **#3 is the real prize** — relational, normal-continuous curve authoring.
- **#1 is the cheapest win** — curved bridge via the native Bridge Edge Loops dials.
- **#2 unblocks the hollow-sweep path.**
- The rest is the support tooling that makes those usable.

---

## Appendix: reproduction notes & hard-won specifics

These took many calls to discover. Preserve them so the findings are reproducible.

### Test fixture (the two tubes)
- `tubeA`: cylinder r=0.3, h=2, segments=16, `cap_fill=NOTHING`, at origin → vertical, open both ends.
  Openings: **A-top (0,0,1)**, **A-bottom (0,0,-1)**.
- `tubeB`: same cylinder but `rot_y=25`, then `move_to (1.3, 0.4, 0.2)`.
  Openings: **B-top (1.72262, 0.4, 1.10631)**, **B-bottom (0.87738, 0.4, -0.70631)**.
  Tube B's local +Z axis in world = `(sin25, 0, cos25) = (0.4226, 0, 0.9063)`.
- Gap between the two tube walls in X ≈ 0.3 m ("somewhat close").

### Known-good baseline: clean closed loop via straight bridges (round 1)
1. Add the two open cylinders (above). `object join [tubeA, tubeB]` → one object (join does **not** weld verts; shells stay separate).
2. `feel op=assembly targets=<obj>` → mints 4 named boundary handles, one per opening.
3. `edit op=bridge a=<handle> b=<handle>` for the top pair, then the bottom pair.
4. Result: **closed genus-1 surface, 1 shell, 0 holes.** Verified clean topology.
5. **But** straight bridges between the misaligned openings produce **26 self-intersections, thinnest
   wall 0.88 mm**, on the *insides* of the bends. Subsurf (levels 3) smooths the cage but does **not**
   resolve the self-intersections — they become smooth self-intersections. This is the "decorated
   workaround," not a real curved connector.

### `extrude_along_curve` — the reverse-engineered placement rule
- The curve is applied as a **relative shape launched along the selected face's normal**, NOT in world
  coordinates. The curve's start tangent is mapped onto the face normal, rotating the whole curve.
- **Recipe to make it land where you want:** author the curve so its **first segment is exactly along
  the face normal** (e.g. for a +Z-facing cap, make control point 1 directly above point 0 → pure +Z
  start tangent). Then no reorientation happens and the sweep follows world coordinates; the far end
  lands at the curve's actual last point. A tilted first segment sends the endpoint somewhere
  unpredictable (observed: far end at z≈2.5 instead of on the target).
- It **sweeps the filled face** → solid, non-manifold result (`genus -24, chi=50`). Caps are NOT
  auto-removed. So even with correct placement, the output is a solid rod, not a weldable hollow tube.
- **Self-intersection preflight (the good part):** it refuses and reports *tightest bend radius vs
  profile radius*. For profile r=0.3: top connector succeeded at bend 0.5699 then 0.3667 (barely);
  bottom failed at 0.214 and 0.264 (narrow/shallow dips) and only passed at **0.3079** once made wide
  AND deep. **Rule of thumb: bend radius must exceed the tube radius**, and close fat tubes leave little
  room — the U-turn out of a down-facing cap is the worst offender.

### Cap-and-sweep selection sequence (that actually fired)
`extrude_along_curve` needs a FACE selected AND the object in EDIT mode (it does not auto-enter edit):
1. `select in_sphere` at the opening center, r=0.4 → the 16 rim verts.
2. `edit grid_fill` → caps the rim (+16 faces, adds **9 interior verts** → 25-vert grid cap).
3. `select in_sphere` r=0.45 → 25 verts (16 rim + 9 interior).
4. `select component_mode FACE`.
5. `object mode EDIT` (explicit — this is the step that was missing when it errored).
6. `edit extrude_along_curve`.

### Isolating a boundary rim near other geometry
- After `join`, shells stay separate; use `object split` (by loose parts) to get them as separate
  objects so `in_sphere` won't grab the neighbor's verts.
- For a 16-seg tube of r=0.3: `in_sphere` r=**0.305** grabbed exactly the 16 rim verts; r=0.32 grabbed
  24 (16 rim + 8 of the next ring). `delete ONLY_FACE` on the 16 rim **no-op'd** — the swept tip was
  not a single n-gon, so the assumed cap topology was wrong.

### Renders produced this session (for the human, not to be read back)
- `~/two_tubes_linked.png` — round-1 straight bridges.
- `~/two_tubes_curved.png` — same loop with subsurf levels 3 (the smoothed workaround).

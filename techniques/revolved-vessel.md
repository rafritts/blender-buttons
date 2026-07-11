# Revolved vessel — anything whose silhouette sweeps around an axis

**When the form is:** a *surface of revolution* — goblet, vase, bottle, plate, bowl,
baluster, chess pawn, lamp base, wheel. The tell: one silhouette curve + one axis
describes the whole thing.

## Trace the silhouette, spin it

1. Author the **profile** as an open edge run in a plane through the axis — e.g.
   `add type=plane`, delete down to a vertex strip, or extrude a chain of verts whose
   radii/heights you type as *authored dimensions* (that's legitimate provenance).
2. `edit op=spin axis=Z angle=360 sections=<steps>` — revolves the selected profile
   about the axis through the object's origin; a full turn welds the seam and recalcs
   normals for you.
3. **Verify:** the status block's dims match the intended max radius ×2 and height;
   `feel op=topology` for watertightness where the profile allows it.

Helical variants (threads, springs) are the **SCREW modifier**
(`modifier op=add type=SCREW`).

## Reshaping the silhouette afterward

The profile IS the design — to re-shape it, select the rings whose radius should change
and `edit op=scale` them (per-ring, about the axis), then re-read with `edit op=trace`
(the measured cross-section) against the numbers you intended. Re-read rather than
eyeballing.

## Failure modes

- Spin revolves around the **object origin's** axis line — author the profile with the
  origin ON the intended axis (radius = distance from origin); a profile whose whole
  strip sits away from the axis spins into a torus-like shell, which is sometimes the
  point (a rim) and usually not.
- On a solid blob there's no ring structure to grip — spin a fresh profile instead.

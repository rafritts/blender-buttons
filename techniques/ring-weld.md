# Ring weld — joining two open rims into one continuous surface

**When the form is:** two openings that must become one continuous skin — a neck onto
a head, a spout onto a teapot body, a limb into a socket, a pipe tee. The tell: two
open boundary loops, roughly facing each other.

The native primitive is **Bridge Edge Loops** — `edit op=bridge`.

## The sequence

1. **Open the rims** (if they aren't): select the cap faces at each joint site,
   `edit op=delete mode=FACE`. Similar vert counts across the two rims bridge
   cleanest — `edit op=subdivide` the coarser rim's neighbourhood to close the gap.
2. **Name them**: `feel op=assembly` reports and mints boundary handles
   (`torso.neck`, `head.base`) — address rims by name from here on.
3. **One object**: `edit op=bridge` is same-object only — `object op=join` the parts
   first (join *into* the part whose materials should win).
4. **Bridge**: `edit op=bridge a=torso.neck b=head.base`. Default is a straight strut;
   for a curved span raise `bridge_cuts` (intermediate loops) with `smoothness` for the
   tangent bow, `profile` to bulge the throat outward, and `twist` to kill the spiral
   when the rims' vert orders start misaligned.
5. **Settle the span**: `sculpt brush=smooth` across the new band evens the quads;
   `material op=shade_smooth` if the joint should read organic.

**Verify:** the bridge's status block + `feel op=topology` — the two open rims are
gone, no non-manifold edges. Then `feel op=clearance` against neighbours if the new
span swings near other parts.

## Tubes along a path (the span is long or must follow a curve)

Author the centreline as a curve (`add type=curve` through relational anchors), then
`modifier op=add_asset asset="Curve to Tube"` — the native GN tube. Weld its end rings
to the openings with the bridge sequence above. Several strands = several curves
sharing endpoints, tubed individually.

## Failure modes

- Bridging in separate objects: refused — join first (step 3).
- Keyed/rigged meshes: bridge refuses (topology change corrupts keys) — bake keys
  first or bridge before rigging.
- A spiral in the span: `twist=<±n>` rotates the rim-to-rim vertex mapping; step by 1
  and re-read.
- Rims facing the same way (not toward each other) bow the span through the body —
  check `feel op=facing` on the two openings before bridging.

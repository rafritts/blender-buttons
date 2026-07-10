# The drip — gravity-formed hangs off a rim

**When the form is:** matter that *flowed and set* — icing drips off a donut rim, wax
runs down a candle, paint sags, honey strings. The geometry signature: a rim or edge
zone that swells, narrows into tongues, and hangs bulbs below the source surface.

This was once a macro (`bud`, G217 — it failed both boolean solvers on the open shell
it was built for and reported success anyway). It is a technique now because every
drip is *adapted*: where the tongues fall, how far each hangs, how bulbous the tips go
— decisions made by reading the mesh between steps, which is exactly what a compiled
sequence cannot do.

## The sequence

1. **Pick the drip zone** on the shell's rim: `look` at the source object, descend to
   the rim window, claim the boundary/rim candidate as `drip_zone` (or select the rim
   band by hand). Densify if the band is coarse — `edit op=subdivide` on the selection;
   drips need resolution to curve.
2. **Drape it**: `sculpt brush=gravity` scoped to the zone (radius covers the band) —
   real sag, not hand-placed verts. Alternate with reads: the status block's z-min
   tells you how far the longest tongue now hangs.
3. **Shape the tongues**: select individual tongue tips (`select op=pick
   within=drip_zone` then `op=grow`, or `select op=in_sphere` at a tip), pull down with
   `edit op=proportional_move down=<m>` (falloff SMOOTH, radius spanning the tongue),
   and **narrow them as they fall** — `edit op=proportional_scale factor=<0.9…0.7>`; a
   drip narrows toward its tip, that's a scale, not a translate.
4. **Bulb the tips**: select just the tip verts, `edit op=inflate amount=0.002…0.004`
   — teardrop bulbs instead of pointy tongues.

## A discrete bead that must WELD onto the surface (the old `bud` case)

No boolean. A local bridge is clean where the boolean was not:

1. Cut the socket: select a small face patch at the fuse point, `edit op=delete
   mode=FACE` — an open ring on the host.
2. Author the bead: `add type=sphere` sized to the drop, placed at the socket
   (`on=`/handle placement); delete its top cap the same way — an open neck ring.
3. Make them one object (`object op=join`), mint the two rims as handles
   (`feel op=assembly`), then `edit op=bridge a=<neck> b=<socket>` — Bridge Edge Loops
   welds the neck to the cut ring, watertight, no membranes.

**Verify:** `feel op=topology` after the bridge (no new non-manifold edges, no
pinholes); hang distance = status-block z-min against the rim's z you read in step 1.

## Failure modes

- Gravity on the whole mesh instead of the zone sags the body too — scope the brush.
- Bridging rims with wildly different vert counts makes spiral quads — `twist` and
  `bridge_cuts` dials help; matched-ish counts (subdivide the coarser rim) help more.
- A drip band that includes the rim's underside self-intersects when it sags —
  `validate` will flag it; shrink the zone off the underside first.

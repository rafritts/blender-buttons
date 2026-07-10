# Shell — an offset skin over a region, or a solid carved into a vessel

**When the form is:** a surface that *follows another surface at a distance* — clothing,
armor plates, icing on a donut, a phone case, bark, a rind — or a solid that should be a
*walled container* — cup, bowl, vase, pot.

The thickness engine is native **Solidify**; everything around it is selection and
cleanup work you adapt to the mesh at hand.

## Offset shell over a region (the "clad" sequence)

1. **Claim the region** the shell should follow — `look` at the host, claim the offered
   candidate (`select op=claim candidate=<id> name=shell_zone`) or select it by hand
   (`select op=between` / `flood`, `action=INTERSECT` to compose constraints).
2. **Copy the host**: `object op=duplicate name=<host> new_name=<shell>`.
3. **Keep only the region on the copy**: reselect the zone on the duplicate
   (`select op=group name=shell_zone target=<shell>` — the claimed vgroup rode along),
   then `select op=all action=INVERT` and `edit op=delete mode=FACE`.
4. **Stand it off the host**: `edit op=inflate amount=<clearance>` pushes the copy out
   along its normals (a few mm). On a dense, irregular mesh normals disagree — if the
   inflate lumps, use `modifier op=add type=SHRINKWRAP` with an `offset` instead.
5. **Give it walls**: `modifier op=add type=SOLIDIFY thickness=<m>` (add SUBSURF after
   it for a soft rim).

**Verify:** `feel op=clearance` between shell and host (the standoff is real, not
assumed); the `validate` line stays clean or the shell↔host contact gets declared
(`validate op=expect` — roots seat under a scalp). Measure the wall with `feel`
rather than trusting the modifier number.

## Vessel from a solid (the "hollow" sequence)

1. Select the end cap to open (e.g. `look` at the top window → claim the cap face
   region, or `select op=by_axis axis=Z factor=0.9 comparison=GREATER` on a cylinder).
2. `edit op=delete mode=FACE` — the vessel is now an open surface.
3. `modifier op=add type=SOLIDIFY thickness=<m> offset=-1` — walls grow inward, the rim
   stays put; the result is a manifold cup. (Inset→extrude seals the wrong end — don't.)

**Verify:** `feel op=topology` — one open rim, no non-manifold edges; declare the open
rim intended if the floor asks (`validate op=expect check=open_boundary`).

## Failure modes

- Deleting the interior with mode=VERT can take boundary verts the region shares with
  its rim — use mode=FACE and re-read the count the select narrates.
- Solidify on a shell whose normals are mixed makes crossing walls — `edit
  op=recalc_normals` first if `validate` reports flipped normals.
- A shell over a *moving* host should be a SHRINKWRAP + vgroup, not a baked copy.

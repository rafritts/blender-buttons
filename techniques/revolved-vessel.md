# Revolved vessel — anything whose silhouette sweeps around an axis

**When the form is:** a *surface of revolution* — goblet, vase, bottle, plate, bowl,
baluster, chess pawn, lamp base, wheel. The tell: one silhouette curve + one axis
describes the whole thing.

Two native authors, by starting point:

## From nothing: trace the silhouette, spin it

1. Author the **profile** as an open edge run in a plane through the axis — e.g.
   `add type=plane`, delete down to a vertex strip, or extrude a chain of verts whose
   radii/heights you type as *authored dimensions* (that's legitimate provenance).
2. `edit op=spin axis=Z angle=360 sections=<steps>` — revolves the selected profile
   about the axis through the object's origin; a full turn welds the seam and recalcs
   normals for you.
3. **Verify:** the status block's dims match the intended max radius ×2 and height;
   `feel op=topology` for watertightness where the profile allows it.

Helical variants (threads, springs) are the **SCREW modifier**
(`modifier op=add type=SCREW`), or `add type=helix` for wire forms.

## From an existing revolve: author the silhouette directly

`edit op=shape_profile axis=Z points=[[ring, radius_m], …]` sets ring radii in
**absolute meters**, interpolating between control points — seam-safe and idempotent.
Read ring indices first (`select op=ring` / the `edit op=trace` cross-sections), then
type the silhouette as numbers. A goblet from a cylinder is one call:
`points=[[0,0.05],[11,0.009],[22,0.06]]`.

- **Taper / flare**: a 2-point profile (or `edit op=field channel=radial
  field_mode=multiply preset=taper preset_a=1 preset_b=<end scale>` for a relative
  scale — preset_b 0 collapses to a point, >1 flares a bell lip).
- **Flutes / gadroons** (radius vs *azimuth*, not height): `edit op=field
  channel=radial preset=lobes freq=<count> amp=<depth>` — negative-feel grooves =
  concave flutes, outward lobes = gadroons. Scope it to a band first (select the rings)
  for band-local fluting.
- **One ring**: shape_profile with a single-ring pair, or select the ring and scale.

**Verify after each shaping pass:** `edit op=trace` (the measured cross-section
silhouette) against the numbers you authored — the profile IS the design, so re-read
it rather than eyeballing.

## Failure modes

- Spin revolves around the **object origin's** axis line — author the profile with the
  origin ON the intended axis (radius = distance from origin); a profile whose whole
  strip sits away from the axis spins into a torus-like shell, which is sometimes the
  point (a rim) and usually not.
- shape_profile wants an actual ring structure (a lathe-like mesh); on a blob it has
  nothing to grip — spin a fresh profile instead.

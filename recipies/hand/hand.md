# Building a Hand in Blender — Step-by-Step Geometry Guide

On-geometry box modeling, grown from the palm out. Axes: **X** = thumb-to-pinky,
**Y** = wrist-to-fingertip, **Z** = thickness (back of hand +Z). One right hand.

## 1. Palm base
- Add a cube. Scale to a flat slab: X ≈ Y, Z ≈ ¼ width. +Y is the knuckle edge, −Y the wrist, −X the thumb side.

## 2. Knuckle columns
- 6 loop cuts along Y → 7 columns, slid to alternate **wide, narrow ×3, wide** (4 finger roots, 3 gaps).

## 3. Fingers
- Extrude each finger root (+Y) three times — three phalanges. Lengths: middle > index ≈ ring > pinky; drop the pinky root back toward −Y.
- Scale each new tip ring down for taper.
- Rotate each finger a few degrees off-Y so they **fan** outward, not parallel.

## 4. Webbing
- Select the 3 gap top faces; push them −Y and −Z so each web sits below the finger roots. Smooth-falloff proportional drag to soften the V.

## 5. Thumb (opposed — comes off the bottom, not the side)
- Root it **low on the palm side**, not the flat edge: the lower palm-side corner near the wrist — the thenar mass at the −X / −Y / −Z corner. Use 2 loop cuts to isolate one base face there.
- Before extruding, rotate that base about Y by ~a quarter-turn so the thumb's flat plane leaves the palm plane: the thumbnail should end up facing the **side** (−X), not the back (+Z). This rotation is what makes the thumb *oppose* the fingers instead of lying coplanar with them.
- Extrude twice. Segment 1 reaches forward (+Y) and in toward the palm (−Z); segment 2 continues the **hook**, curling further toward the palm so a relaxed thumb could wrap around a pipe. Scale the tip ring down.
- Test: sighting down the wrist (−Y → +Y), the thumb tip points **inward toward the fingers/palm**, ready to hook around a cylinder — not jutting straight out to the side (the "knife hand" to avoid).

## 6. Tips
- Per digit: inset the end cap, pull it in, scale/bevel the last ring so the tip domes.

## 7. Joint loops
- Add a holding loop on **each side** of every joint ring (finger joints + bases) so folds don't pinch under subdivision.

## 8. Organic shaping — Proportional Editing (Connected, Smooth falloff)
- **Curl:** grab each fingertip and pull toward the palm; falloff arcs the whole finger into a relaxed bend. Vary the curl slightly per finger.
- **Palm dome:** grab center-back verts +Z for a soft dome; keep the palm side flatter.
- **Pads:** grab the thumb-base vert (+Z) for the thenar bulge, and a smaller one under the pinky.
- **Knuckles:** small +Z nudge at each base knuckle for the row of bumps.

## 9. Nails
- On each finger's last segment (+Z face): inset a small rectangle, push it down (nail bed), extrude up slightly (nail).

## 10. Round it out — Sculpt pass
The box base still reads blocky under subdivision because every cross-section is a rounded square. Sculpt to give it volume and an organic silhouette. Goal: a good-looking hand, not a lifelike one — stop once the facets are gone and the silhouette reads right.
- Add a Subdivision Surface modifier with holding loops at knuckles, bases, and nails; apply it (or switch to Multires) so there's enough resolution to sculpt into.
- **Inflate:** add volume to the palm body, the finger pads (palm side of each segment), and the thenar (thumb-base) mass so flat faces become rounded flesh.
- **Grab:** ease each finger's cross-section from square toward oval; round the outer silhouette of the hand and the thumb's curl; soften the knuckle and web transitions.
- **Smooth:** pass over the whole surface to melt the blocky facets — heavier on the back of the hand, lighter across the knuckles so they keep definition.
- **Pinch/Crease (light, optional):** only to re-sharpen nail edges or web valleys if smoothing flattened them.

## 11. Finalize
- Merge by distance; recalculate normals outside.

## Invariants
- All quads; loops run **along** each finger.
- Every bending joint has a loop on each side.
- Fingers and thumb are separate extrusions, joined only at palm + webbing.

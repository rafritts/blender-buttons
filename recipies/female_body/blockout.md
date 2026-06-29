# Female body blockout (headless, A-pose)

A game-ready BLOCKOUT of a female torso + limbs — no head, no hands/feet detail.
Method follows the server guidance: **block the masses → merge as algebra (`graft`)
→ refine the soft swells last with the measured `feel → select → anchor → sculpt`
loop** (broad swells are sculpted, never found with a salience finder or grown with
`inflate`). Built directly in A-pose (geometry, not a rig) since it's a static blockout.

Coordinate convention: feet on the floor (z=0), figure faces −Y (front), centred on x=0
so a single `duplicate_mirrored` across X gives perfectly symmetric pairs.

Rough Z stack-up (m), female ~1.55m headless:
  ankle 0.08 · knee 0.45 · crotch 0.80 · hip-widest 0.88 · waist 1.06 ·
  underbust 1.16 · bust apex 1.24 · shoulder 1.40 · neck-base 1.43 · neck-top 1.52

Rigging is not necessary at this time.

## 1. Torso mass (the hourglass)
1. Add a cylinder along Z spanning crotch→neck, ~24 segments, capped.
2. Loop-cut it into many Z rings (≥12) so the lathe has control rings at each landmark.
3. `feel op=profile axis=Z` to map ring index → world Z (don't trust the index math).
4. `buttons-lathe-macro op=shape_profile axis=Z` — set ring radii in absolute metres to
   carve the silhouette: shoulders wide, bust, waist pinch, hip flare, taper to crotch,
   narrow neck stub at the very top.
5. Squash the whole torso in Y (`transform op=scale_verts sy≈0.72`) → elliptical
   cross-section (a body is shallower front-to-back than it is wide). Verify symmetry.

## 2. Legs (A-pose: near vertical, slight stance)
6. Add a frustum (cone with both radii) for the LEFT leg: thigh-radius at top → ankle
   at bottom, top poking up into the pelvis so the graft has overlap to blend.
7. Place it under the left hip; a few degrees of outward splay is fine.
8. `object op=duplicate_mirrored axis=X` → the right leg, perfectly mirrored.

## 3. Arms (A-pose: ~40° from vertical, down-and-out)
9. Add a frustum for the LEFT arm: shoulder-radius at top → wrist at bottom.
10. Rotate ~40° about Y so it swings down-and-out; seat the top inside the shoulder.
11. `object op=duplicate_mirrored axis=X` → the right arm.

## 4. Merge as algebra
12. `buttons-blend-macro op=graft` the legs, then the arms, onto the torso with a small
    `blend` fillet radius → watertight body with organic hip/shoulder blends. Higher
    `resolution` so the limbs survive the voxelisation. Verify: one component, genus 0,
    clean symmetry.

## 5. Sculpt the soft female forms (LAST — graft would re-voxelise sculpt away)
For each swell: judge the band from `feel op=profile`, `select` it by INTERSECTing a
band ∩ side ∩ front/back, `feel op=anchor` to measure the apex+normal, save a `handle`,
then `sculpt`/`proportional_move` at the handle. Mirror to the twin. Verify with `feel`.
13. **Breasts** — two forward-and-up swells on the chest band, off the centre seam so
    the cleavage valley stays. Soften the under-curve; a touch of `gravity` for drape.
14. **Glutes** — two rounded swells on the buttocks (back of the pelvis), with the seam
    between them preserved.
15. **Belly** — a gentle forward swell below the navel; soft.
16. **Lumbar / waist** — deepen the small-of-the-back curve; sharpen the waist pinch.
17. **Collarbone / shoulder** — a faint deltoid + clavicle hint at the shoulder.
18. Light `smooth` pass to relax graft seams. `validate`. Render for the human.

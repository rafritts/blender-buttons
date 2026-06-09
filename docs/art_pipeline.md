# 3D Art Pipeline — Stage Reference

A checklist for identifying which stage of the standard hard-surface / prop pipeline
a model is currently in. Read the **TELLS** to diagnose the current stage, then the
**DONE WHEN** of that stage to know what finishes it.

For a **portfolio beauty render** (no game engine target), skip stages 5–7 and go
straight from high-poly → materials → lighting → render.

---

## Stage 1 — Reference / Concept
- **GOAL:** Decide what's being built before building it.
- **ARTIFACTS:** Reference board (PureRef), orthographic views, real photos, concept sketches.
- **TELLS:** No 3D geometry yet, or only a scratch scene.
- **DONE WHEN:** Proportions, silhouette, and key features are locked from reference.

## Stage 2 — Blockout
- **GOAL:** Establish correct proportions and silhouette with primitives.
- **TELLS:**
  - Built from raw cubes / cylinders / spheres.
  - Hard 90° edges everywhere; no bevels.
  - Parts may be floating, intersecting, or visibly detached.
  - Single flat material or default gray.
  - Recognizable as the subject but obviously "blocky."
- **DONE WHEN:** Silhouette reads correctly from hero angles; proportions match reference.

## Stage 3 — Mid-poly / Refinement
- **GOAL:** Refine forms; fix proportions; commit to the major shapes.
- **TELLS:**
  - Floating parts are now joined or properly seated.
  - Major cuts and contours are present (ejection ports, panel seams, grip curves).
  - Still mostly hard edges, but topology is intentional.
  - Parts are correctly named and organized in collections.
- **DONE WHEN:** Every major shape is in place; nothing is floating or visibly wrong.

## Stage 4 — High-poly
- **GOAL:** The "hero" mesh. Heavy, beautiful, unoptimized.
- **TELLS:**
  - Every hard edge has a bevel/chamfer that catches light.
  - Small details present: screws, pins, rivets, seams, engraving, checkering.
  - Subdivision surface or dense geometry; poly count is high.
  - Booleans / sculpt detail baked into the form.
- **DONE WHEN:** Close-up renders hold up; no edge looks mathematically sharp.

## Stage 5 — Retopology *(skip for portfolio renders)*
- **GOAL:** Clean low-poly mesh rebuilt over the high-poly for game engines.
- **TELLS:** A second, much lighter mesh exists alongside the high-poly; quads with deliberate edge flow.
- **DONE WHEN:** Low-poly silhouette matches high-poly; topology supports deformation/UVs.

## Stage 6 — UV Unwrap *(skip for portfolio renders)*
- **GOAL:** Flatten the low-poly into 2D islands for texturing.
- **TELLS:** UV seams marked; UV editor shows packed islands.
- **DONE WHEN:** No stretching; texel density is uniform; islands pack efficiently.

## Stage 7 — Bake *(skip for portfolio renders)*
- **GOAL:** Project high-poly detail onto low-poly UVs.
- **TELLS:** Normal / AO / curvature / position maps exist as image textures.
- **DONE WHEN:** Low-poly with baked maps looks indistinguishable from high-poly at intended viewing distance.

## Stage 8 — Texture / Material
- **GOAL:** Surface appearance — color, roughness, metalness, wear.
- **TELLS:**
  - Materials beyond flat gray; PBR shader networks.
  - Base color, roughness, metallic, normal inputs wired up.
  - Edge wear, grunge, fingerprints, dust where appropriate.
- **DONE WHEN:** Material reads correctly under multiple lighting conditions.

## Stage 9 — Rig *(only if animated)*
- **GOAL:** Bones, constraints, weight painting for deformation.
- **TELLS:** Armature present; vertex groups assigned; controls/IK set up.
- **DONE WHEN:** Mesh deforms cleanly across the full range of motion.

## Stage 10 — Lighting + Render / Engine Integration
- **GOAL:** Final presentation.
- **TELLS:**
  - Three-point lighting or HDRI; camera with intentional framing and DoF.
  - World background set; render engine configured (Cycles/Eevee).
  - Post-processing: color grade, bloom, vignette.
- **DONE WHEN:** The render sells the asset.

---

## Quick Diagnosis Cheatsheet

| If you see…                                              | Stage just completed |
|----------------------------------------------------------|----------------------|
| Only reference images, no mesh                           | 1                    |
| Blocky primitives, hard edges, floating parts, gray mat  | 2                    |
| Joined parts, major cuts in, still hard-edged            | 3                    |
| Bevels everywhere, screws/seams, dense mesh              | 4                    |
| A second clean low-poly mesh next to a heavy one         | 5                    |
| UV islands packed in the UV editor                       | 6                    |
| Normal/AO/curvature image textures present               | 7                    |
| PBR materials with wear and grunge                       | 8                    |
| Armature with weighted vertex groups                     | 9                    |
| Camera, lights, world, post-fx all configured            | 10                   |

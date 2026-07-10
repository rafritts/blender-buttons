# NPR look — cel/anime shading and outlines

**When the target is:** a stylized look — anime/cel bands, flat colors, dark contour
lines — rather than PBR realism. This is a *look setup* over material and render ops,
not a modeling operation; assemble it near the end, after forms are signed off.

## The cel material

`material op=toon target=<obj|group> hex=#RRGGBB bands=2 shadow_color=[…]` — assembles
the native **Shader-to-RGB → ColorRamp** band graph (EEVEE only; Cycles has no
Shader-to-RGB). `rim_color`/`rim_width` add the anime rim light;
`gradient_top`/`gradient_bottom` give the vertical color drift anime skin/hair uses.

Known 5.x quirk: the Shader-to-RGB chain ignores object emission (blender #119828) —
glow via a separate emissive object, not the toon material.

## The outline

`material op=outline target=<obj> thickness=0.01 color=[0,0,0]` — the inverted-hull
trick (flipped-normal Solidify shell, baked). Thickness is world meters: scale it to
the asset (a 2 m character wants ~5–15 mm; a 6 cm donut wants ~0.5 mm). Strip with
`op=remove_outline`.

For *true line rendering* (crease lines, intersection lines, stroke control) the
native tool is **Line Art** (Grease Pencil) — heavier setup, real strokes; reach for
it when the hull outline's silhouette-only lines aren't enough. (Freestyle exists but
is render-only and unmaintained.)

## The render side

Flat colors die under filmic tone mapping: `render op=color view_transform=Standard`
(AgX, the default, muddies saturated cel fills). One hard key light reads more
"anime" than an HDRI wash; keep the world dim and let the bands do the shading work.

## Verify

The human's eye is the ground truth for a look — they watch the viewport live, so ask
for taste sign-off on band count / outline weight rather than rendering to check.
Geometry-side: the outline shell intentionally wraps the object — declare the overlap
if `validate` flags it, and re-check silhouettes after any later mesh edit (the baked
hull does not follow deformation; re-run outline after reshaping).

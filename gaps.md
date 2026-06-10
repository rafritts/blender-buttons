# MCP gaps surfaced by the donut tutorial

A live attempt at the Blender Guru donut tutorial via the MCP server.
Each entry: what the tutorial calls for, the closest tool we have, and what's missing.

## 1. Organic deformation — IMPLEMENTED

Two complementary tools:

- `jitter_vertices(amount, axis=NORMAL|X|Y|Z|XYZ, seed, only_positive)` —
  random per-vertex displacement. Covers "lumpy dough".
- `proportional_move(x, y, z, radius, falloff=SMOOTH|LINEAR|SPHERE|SHARP|ROOT|CONSTANT)` —
  move selected verts with a falloff that drags nearby verts along. The
  donut-tutorial proportional-editing equivalent — gives bulbous icing drips
  when applied to sparse boundary handles.

## 2. Sculpt-mode brushes

**Tutorial step:** alternative path to organic deform — use Sculpt mode with Grab/Inflate/Smooth brushes.

**What we have:** `set_mode SCULPT` enters the mode; no brush dispatch.

**Why deferred:** sculpt brushes work on screen-space strokes — they take a list of (x, y, pressure) viewport samples. Driving them from MCP means either (a) scripting `bpy.ops.sculpt.brush_stroke` with a synthesized stroke list (works but coordinate space is gnarly — viewport vs. world) or (b) skipping brushes entirely and exposing direct mesh deformations like "inflate this vertex set by N along normals". (b) is the saner MCP shape but it's a real design exercise.

## 3. Delete in edit mode (verts / edges / faces) — IMPLEMENTED

`delete_geometry(mode: VERT | EDGE | FACE | ONLY_FACE | EDGE_FACE)` —
`extension/editmode.py:delete_geometry`, MCP wrapper in `server/main.py:delete_geometry`.

## 4. Separate by selection (P key) — IMPLEMENTED

`separate_selection(new_name?)` — `extension/editmode.py:separate_selection`,
MCP wrapper in `server/main.py:separate_selection`. Returns the new object's name.

## 5. Shrinkwrap modifier — IMPLEMENTED

`add_modifier(type='SHRINKWRAP', target=..., offset=..., wrap_method=...)` —
extended in `extension/finishes.py:add_modifier`. `wrap_method` defaults to
`NEAREST_SURFACEPOINT`; pass `target` (object to wrap onto), optional `offset` (skin distance).

## 6. Sprinkles / surface scatter — IMPLEMENTED

`scatter_on_surface(target, source, count, scale_min, scale_max, align_normal,
rotate_z, parent_to_target, seed, name_prefix)` — new module
`extension/scatter.py`, MCP wrapper in `server/main.py:scatter_on_surface`.

Area-weighted triangle sampling on the target's *evaluated* mesh (so sprinkles
land on the visible post-subsurf/shrinkwrap surface). All instances share the
source's mesh data so memory stays cheap. Capped at 5000 per call.

**Small remaining quirks** (left as polish, not gaps):
- Source object's origin must be set so the source sits "on top" of its base — otherwise instances get half-embedded in the target surface. We don't have an origin-set tool yet (`bpy.ops.object.origin_set`).
- No way to filter by normal direction (e.g. "scatter only on upward-facing faces"). Sprinkles can land inside the donut hole.

## 7. Render (image output)

**Tutorial step:** F12 to render the final frame.

**What we have:** nothing. `get_viewport_screenshot` is a viewport grab, not a render.

**Why deferred:** `bpy.ops.render.render(write_still=True)` blocks the main thread for the full render duration. Our socket handler has `result_event.wait(timeout=30)` — anything > 30s silently times out and leaves Blender mid-render. Needs either async dispatch (fire-and-forget + a poll tool for "is the render done?") or a per-call timeout override. Same shape would help any other long-running op (heavy remesh, heavy subsurf bake, etc.).

## 8. Viewport shading mode (see your materials) — IMPLEMENTED

`set_viewport_shading(mode: WIREFRAME | SOLID | MATERIAL | RENDERED)` —
`extension/viewport.py:set_viewport_shading`, MCP wrapper in
`server/main.py:set_viewport_shading`. Call before `get_viewport_screenshot`
to see materials/lighting in the captured image.

## 9. Curve objects (Bézier / NURBS) — PARTIALLY IMPLEMENTED

**Tutorial step:** Andrew uses a Bézier circle as a particle distribution control / for camera dolly paths.

**What we have now:** `spline_tube` (`extension/curves.py`) — interpolating
(Catmull-Rom) curve through 2–32 points, swept as a tube with per-point radius,
converted to mesh in one call. Deliberately NOT Bezier-handle-based: through-points
are verifiable claims for an LLM; tangent handles are invisible state. Curve
datablocks as live scene objects (camera paths, particle controls) remain unbuilt.

---

# MCP gaps surfaced by the anime base-character build

Live attempt at a 7-heads-tall T-pose nude base mesh. Each entry describes the friction in concrete terms, the proposed tool/fix, where in code to make the change, and an effort estimate.

**Implementation priority for next session** (top 6, ordered by how much they hurt this build):

1. Symmetry — `mirror_of` in placement DSL **+** wrap MIRROR modifier in `add_modifier`
2. `taper_section` rotation bug (real bug, not missing feature)
3. Edge crease / mark sharp (so SubSurf preserves hand/foot silhouettes)
4. `merge_by_distance` (post `join_objects`, eliminates seam shading artifacts)
5. Placement DSL: absolute `x` / `y` overrides (kills the placement→nudge round trip)
6. `frame_scene(targets=...)` (current `frame_scene` includes lights, useless)

## C1. No symmetry — every left-side limb was a hand-copied right-side op

**What hurt:** built `thigh_R` → had to manually build `thigh_L`. Did the same for calf, upper_arm, forearm, hand, foot. Worse, every edit-mode taper had to be done twice with ring indices flipped (right side ring 0=top, left side ring 0=bottom because `_compute_rings` sorts ascending by world coord). ~50% of build calls were just mirrored duplicates.

**Fix A — placement DSL `mirror_of`:** in `extension/placement.py:resolve_placement`, add a spec form:
```
{"mirror_of": "thigh_R", "axis": "X"}  # → centers at (-cx_of_thigh_R, cy, cz)
```
Effort: ~20 lines. Trivial.

**Fix B — `add_modifier(type='MIRROR', axis='X', merge_threshold=0.001)`:** wrap Blender's mirror modifier in `extension/finishes.py:add_modifier`. Then build only the right side; modifier produces the left automatically AND edits propagate. Effort: ~30 lines. Easy.

**Fix C — `duplicate_mirrored(name, axis='X', new_name)`:** for static (non-modifier) mirroring after the fact. `bpy.ops.object.duplicate` + apply transform with flipped axis scale + recalc normals. Effort: ~40 lines. Easy.

All three would coexist; A is for first-placement, B for live editing, C for one-shot mirror.

## C2. `taper_section` ignores object rotation (real bug)

**What hurt:** arms rotated 90° around Y came out **oval**, not round, because cross-section scaling only affected one of the two non-axis world directions.

**Root cause:** `extension/rings.py` — `_compute_rings` groups by **world** coord (correct), but `taper_section` then scales `v.co[ax]` in **local** coords. For a rotated cylinder, scaling local Y affects world Y, but scaling local Z (which equals world X for an arm) has no effect because all verts in a ring share the same local Z (it's the length axis post-rotation).

**Fix:** convert centroid + verts to world via `mat = obj.matrix_world`, scale in world, convert back via `mat.inverted()`. ~10 line change in `taper_section` (and analogously in `taper_end`). Easy.

**File:** `extension/rings.py`, `taper_section` ~line 260, `taper_end` similar.

## C3. SubSurf had no crease control — hand/foot boxes became blobs

**What hurt:** added SubSurf to the joined body for smoothing; the rectangular hand and foot boxes melted into rounded pebbles because no edges were marked sharp.

**Fix:** new edit-mode tool `mark_sharp(angle_threshold=30)` and `set_edge_crease(weight=1.0)`. Both operate on selected edges. `mark_sharp` toggles `edge.smooth = False`; `set_edge_crease` uses `bm.edges.layers.crease.verify()` then `edge[crease_layer] = weight`.

**File:** new functions in `extension/editmode.py`. Effort: ~30 lines each. Trivial.

## C4. `join_objects` doesn't merge seam vertices — body stays segmented

**What hurt:** joined torso+pelvis+limbs into one mesh; surface still reads as 16 disconnected pieces because object boundaries had coincident-but-separate verts. SubSurf then smoothed each piece independently → mannequin look, not continuous skin.

**Fix:** `merge_by_distance(threshold=0.001, targets='')` — edit-mode op wrapping `bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=threshold)`. Or extend `join_objects` with `merge_threshold` param that auto-welds after joining.

**File:** new function in `extension/editmode.py`, plus optional param in `extension/objects.py:join_objects`. Effort: ~15 lines. Trivial.

## C5. Placement DSL: no absolute `x` / `y`, no `mirror_of`

**What hurt:** `raise_to: 0.4` always puts (X, Y) at (0, 0). Every limb wanted a side-offset, so I had to `add_*` then `nudge`. Doubled the call count.

**Fix:** in `extension/placement.py:resolve_placement`, allow `x`, `y`, `z` overrides at the top level of the spec, applied AFTER relational resolution. Example: `{"raise_to": 0.4, "x": 0.085}` → bottom at z=0.4, centered at x=0.085, y=0.

**File:** `extension/placement.py`. Effort: ~10 lines. Trivial.

Pair with `mirror_of` from C1 for the cleanest API.

## C6. `frame_scene` includes lights — useless framing

**What hurt:** called `frame_scene()`; viewport zoomed out to fit the lights at z=3, leaving the character tiny. Had to manually `orbit_viewport` with eyeballed distance.

**Fix:** `frame_scene(targets='')` — if targets given, fit only those objects; otherwise current behavior. Or skip lights/cameras by default and add an `include_lights=False` flag.

**File:** `extension/viewport.py`. Effort: ~15 lines. Trivial.

## C7. `taper_section` only does linear interpolation

**What hurt:** sculpting a calf bulge (wider at mid, narrow at ankle) needed **two** taper_section calls with a hard inflection at the bulge ring. Same for chest swell. A curve param would do it in one.

**Fix:** add `curve: 'linear' | 'ease_in_out' | 'smoothstep' | 'bezier'` param. Replace `t = (ring_i - from_idx) / span` with a curve eval.

**File:** `extension/rings.py:taper_section`. Effort: ~20 lines. Easy.

## C8. No localized region-editing on a joined mesh

**What hurt:** after joining the body, couldn't say "inflate this chest region" or "push out the bust" — `taper_section` only operates on whole-axis rings of an isolated object.

**Fix path:** `select_in_sphere(center=[x,y,z], radius)` for spatial selection, then existing `proportional_move` or new `inflate_selection(amount)` along normals.

**File:** new function in `extension/editmode.py`. Effort: 1 day. Medium — design-y.

## C9. No bulk primitive add

**What hurt:** 16 body parts = 16 separate `add_box`/`add_cylinder` calls. Each round-trips through the MCP socket queue.

**Fix:** either `add_primitives(specs=[{type,name,...}, ...])` batched, or accept `parts=[...]` on existing tools. Trade-off: simpler API vs. fewer round trips.

**File:** new function in `extension/primitives.py`. Effort: ~40 lines. Easy.

## C10. `join_objects` is one-way — no `split_by_part`

**What hurt:** after joining, can no longer say "re-taper thigh_R's knee." Lost per-part addressability.

**Fix:** `split_by_part()` — wraps `bpy.ops.mesh.separate(type='LOOSE')`. Splits the active mesh into separate objects, one per connected component. Names become `<base>.001`, `.002`, etc. Auto-name from per-island bbox if possible.

**File:** new function in `extension/editmode.py`. Effort: ~20 lines. Easy.

## C11. No hide-overlay screenshot mode

**What hurt:** every screenshot showed the orange selection outline of whatever was last selected, including the entire joined body. No clean hero shot.

**Fix:** `get_viewport_screenshot(hide_overlays=False)` — toggle `space.overlay.show_overlays` around the screenshot capture.

**File:** `extension/viewport.py:get_viewport_screenshot`. Effort: ~10 lines. Trivial.

## C12. No `add_floor` / ground reference

**What hurt:** "feet on z=0" was eyeball-checked. A 2m × 2m ground plane would make floor reference obvious and give shadow catching for hero shots.

**Fix:** could be done with `add_plane`, but a `add_floor(size=10, material='matte_gray')` helper would set up the standard char-modeling ground in one call.

**File:** new function in `extension/primitives.py`. Effort: ~15 lines. Trivial. Lowest priority.

---

# Long-term gaps (character quality finish line — NOT for next session)

These are the road from a base mesh to Wuthering-Waves-quality. Listed for the north star, not for now:

- Sculpt brushes (semantic, not gesture-based — e.g. `inflate_region(center, radius, amount)`)
- Multires + dyntopo wrappers
- Retopology — auto-retopo or guided
- Armature creation + auto-weight (rigify is the target)
- Pose mode — `pose_bone(name, rot=[x,y,z])`
- UV unwrap with seam control
- Material node graph beyond Principled BSDF
- Hair card system
- Face topology: eyes/nose/mouth loops with subsurf-correct flow
- Curve objects (carry-over from donut gaps #9)
- Render to file (carry-over from donut gaps #7)

---

# MCP gaps surfaced by the primitive-assembly anime girl build (2026-06-09)

A 36-part character (head, hair, dress, limbs from shaped primitives) built
entirely through the placement → resize → mirror → material → screenshot loop.
All items below are IMPLEMENTED as of this session; details for the record.

## D1. Placement DSL silently ignored unknown keys — IMPLEMENTED

`on={"at": [0, 0, 1.48]}` did nothing: the object landed at the origin with no
error, and the build fell back to add-then-nudge for all ~25 parts (doubled the
call count). Two fixes in `extension/placement.py`:
- `{"at": [x, y, z]}` is now a real key — literal world-coordinate center (ripcord).
- `resolve_placement` validates against `VALID_SPEC_KEYS` and rejects unknown
  keys with the full valid vocabulary in the error.

## D2. add_primitives dropped rot_x/y/z in bulk specs — IMPLEMENTED

Single-primitive tools map `rot_x/y/z` → `rotation_deg`; the bulk path passed
specs through raw, so `{"type": "cylinder", ..., "rot_y": 14}` created an
UNROTATED cylinder silently (the character's A-pose arms came out vertical).
`extension/primitives.py:add_primitives` now does the same mapping.

## D3. Stale viewport screenshots — IMPLEMENTED

After `set_material`/`resize` edits, `get_viewport_screenshot` returned
byte-identical stale frames (several iterations were spent "re-fixing" shoes
that were already fixed; diagnosed with a glowing red debug material). Root
cause: socket-driven edits generate no UI events, so the depsgraph/viewport
never refreshed before capture. `_capture_viewport` now forces
`view_layer.update()` + `evaluated_depsgraph_get().update()` + a real
`wm.redraw_timer` cycle first.

## D4. Setters without getters: no material introspection — IMPLEMENTED

`set_material` existed but nothing reported what was assigned.
`common.material_summary()` reads back slot names + Principled values
(base_color, roughness, metallic, alpha, emission); `describe()` includes a
material clause, `get_object_info()` gains `materials` + `modifiers`.

## D5. resize on rotated objects shears silently — IMPLEMENTED (warning)

`resize` works in world axes; on a rotated cylinder it shears the geometry and
the bbox math is rotation-inflated. Now warns per rotated target and suggests
recreating at size or `apply_transform(rotation=True)` first.

## D6. No group scale about a shared pivot — IMPLEMENTED

Wanted "make head+hair 8% bigger" (12 objects); `resize` can't (it sets each
member to identical absolute dims). `scale_group(targets, factor, pivot)`
scales locations + local scales about a shared pivot (`center`,
`bottom_center`, `origin`, object name, or literal point), then bakes scale.

## D7. mirror_across name pollution — IMPLEMENTED

Suffix appending produced `eye_R_L`-style names. `replace=["_R", "_L"]` swaps
the token instead; names without the token fall back to the suffix.

## D8. No curving primitives at all — IMPLEMENTED (bend + spline_tube)

Everything buildable was straight or linearly tapered; hair locks and curved
strands had no path. Two new verbs:
- `bend(targets, angle, axis, apply=True)` — SimpleDeform BEND wrapper
  (`extension/finishes.py`). One-call arc on existing geometry.
- `spline_tube(name, points, radius, resolution, sides)` — new module
  `extension/curves.py`. Interpolating Catmull-Rom curve THROUGH 2–32 control
  points ([x,y,z] or {"near": obj, "offset": [...]}), swept with per-point
  radius, capped, converted to mesh in one call. Through-points are stored on
  the object and reported by describe().

Verified by `bb_e2e_test.py`-style headless run (flatpak Blender 5.1,
38 assertions) + pure-math tests for the Catmull-Rom sampler.

---

# MCP gaps surfaced by the anime treasure chest build (2026-06-10)

A Genshin-style treasure chest: box body, half-barrel lid, gold straps wrapping
body+lid, corner feet, lock plate/tongue/knob. 15 parts. The build worked, but
one gap destroyed the entire scene mid-session and forced a full rebuild.

## E1. undo() rolled back the whole session and the history log didn't notice — CRITICAL

**What hurt:** called `undo(steps=2)` to revert one bad `resize` + one
`set_material` (27 ops into the build). The scene reset to the Blender startup
state: every chest part gone, the default Cube resurrected. `get_history` still
listed all 27 ops as "remaining" — the MCP history log and Blender's real undo
stack are completely desynced. There is no redo tool, so the only recovery was
rebuilding all 15 parts from scratch (~25 calls).

**Root cause hypothesis:** MCP tool calls arrive over the socket without UI
events, so Blender doesn't push an undo step per tool — `steps=2` therefore
walked back through whatever sparse undo points existed, landing at file-open.

**Fix:** each mutating tool should push exactly one named undo point
(`bpy.ops.ed.undo_push(message=op_id)`); `undo(steps=N)` then maps 1:1 to tool
calls. After undoing, verify the scene matches the history entry's recorded
post-state (object names at minimum) and report what was actually reverted.
Add `redo()`. Until then `undo` is more dangerous than helpful — a destructive
tool masquerading as a safety net.

**File:** `extension/` op dispatch + history module. Effort: medium, but top priority.

## E2. Placement DSL resolves before rotation — every rotated primitive lands wrong

**What hurt:** the lid is a cylinder with `rot_y=90` placed `on={"on": "lid_rim"}`.
Placement used the UNROTATED bbox (tall thin cylinder), then rotation spun it
around its center — the barrel floated 0.2m above the rim. Same story for the
`rot_x=90` lock plate and knob (`in_front_of` left them floating 2–7cm off the
surface). Every rotated part in the build (4 of 15) needed a follow-up `snap_to`
to land where the placement spec already said it should be.

**Fix:** in `resolve_placement`, apply `rotation_deg` to the primitive's bbox
FIRST, then resolve `on`/`in_front_of`/etc. against the rotated extents. The
docstring's "rotation applied after placement" ordering is exactly backwards
from what relational placement means.

**File:** `extension/placement.py` + primitive creation path. Effort: ~30 lines.

## E3. resize on rotated objects: warns AFTER mutating, and maps axes wrong (follow-up to D5)

**What hurt:** `resize("lid", width=0.98)` on the rot_y=90 barrel. Requested
world width 1.06→0.98; instead world HEIGHT went 0.66→0.61 (squashed
cross-section) and width stayed 1.06 — the scale factor was computed from world
dims but applied to local axes. The D5 warning printed, but only after the
geometry was already wrong, which is what triggered the E1 undo disaster.

**Fix:** resolve the world→local axis mapping through the rotation matrix (for
axis-aligned rotations this is exact), or refuse to touch rotated objects and
suggest `apply_transform(rotation=True)` BEFORE mutating. A warning attached to
a wrong result is the worst of both.

**File:** `extension/objects.py:resize`. Effort: ~20 lines.

## E4. No arch/half-cylinder primitive and no boolean cut

**What hurt:** the classic chest lid is a half-barrel. Closest path: full
cylinder sunk halfway into the body so the lower half hides inside. Works for a
closed silhouette, but the hidden half is wasted geometry, the trick collapses
the moment the chest needs to open (interior shows the buried barrel), and
nothing similar exists for any shape whose cut face is visible.

**Fix options:** (a) profile primitives — `add_arch`/`add_wedge`/`add_half_cylinder`
(general: a 2D profile swept along an axis); (b) a `cut_with(target, cutter,
keep='ABOVE')` boolean wrapper. (b) is more general — it also covers keyholes,
mortises, and split-lid chests.

**File:** `extension/primitives.py` or BOOLEAN in `extension/finishes.py:add_modifier`.

## E5. No "band around a composite silhouette"

**What hurt:** each gold strap wrapping body+lid had to be hand-assembled from
a box (body section) and an oversized short cylinder (lid section), with proud
offsets matched by eye (box sits 0.02 proud, ring 0.015 — there's a visible
2cm step where they meet at the seam). Two parts + one snap per strap, twice.

**Fix:** `band_around(targets, axis='X', at=0.27, width=0.09, thickness=0.02)` —
take the combined cross-section silhouette of `targets` at the given axis
position, offset it outward by `thickness`, sweep it `width` wide. Covers chest
straps, barrel hoops, belts, pipe clamps — a general primitive, not a chest tool.

**File:** new module. Effort: medium (silhouette extraction is the design work).

## E6. set_material colors are linear floats — "dark chocolate" renders pastel

**What hurt:** `base_color=[0.22, 0.1, 0.045]` (dark brown as picked from any
color reference) displayed as pale tan: Blender treats the floats as scene-linear,
and linear→sRGB lifts 0.22 to ~0.5. Took two material rounds to get actual brown
(the working value was `[0.09, 0.04, 0.018]` — numbers no human associates with
mid-brown).

**Fix:** accept `hex="#5C3317"` (sRGB) and convert to linear internally; state
the color space explicitly in the docstring either way.

**File:** `server/finishes.py` + `extension/finishes.py:set_material`. Effort: ~15 lines.

## E7. No 3/4 viewport preset (minor)

`set_viewport_angle` has only axis-aligned views; judging a build wants the 3/4
hero angle, which means `orbit_viewport` with magic numbers (azimuth -30,
elevation 18, distance ≈ 2.5× subject size...). A `THREE_QUARTER` preset that
auto-frames the targets — or `orbit_viewport(distance='AUTO')` — would remove
the eyeballing. The collage's PERSP panel proves the framing math already exists.

## E8. Deform-after-bevel ordering trap (minor, not hit — avoided)

Wanted a slight anime flare (body wider at top) AFTER `smooth_edges` had baked
its bevel. `taper_end` operates on the extreme ring along the axis — which, post
bevel, is the 6mm bottom sliver of the bevel itself, so it would pinch the bevel
instead of tapering the wall. Skipped the flare rather than risk it (this was
the same session as E1, with no undo to lean on). A guard would help: if the
extreme ring spans <2% of the axis extent, suggest `taper_section` over the full
range instead.

# Follow-up from shopping-list verification (2026-06-10, post T1–T7)

## E1-residual. Live-session undo is a no-op; verification correctly catches it

T3 fixed the bookkeeping and added post-step verification — and that part works:
`undo(1)` after an `add_box` in a LIVE interactive session left the box in the
scene, and the tool reported `POST-UNDO MISMATCH` loudly instead of claiming
success. `redo(1)` then re-synced the log to the scene (`verified ✓`). The spec's
fallback ("a lying undo is worse than no undo") is satisfied.

But the underlying `bpy.ops.ed.undo` does nothing in the live socket→timer
context, even with the `temp_override(window=...)`. The headless e2e passes the
same sequence, so this is interactive-session-specific — likely the undo steps
pushed from a timer aren't registered against the window's undo stack the
override points at. Needs investigation in a live session specifically; the
headless harness can't reproduce it. Until then the practical guidance stands:
checkpoint with `save_design`, recover with `open_design` — but undo is now
fail-loud instead of scene-destroying, so it's safe to *attempt*.

## E9 (minor). `add_box` docstring still says rotation "applied after placement"

T4 made placement resolve against the rotated bbox (verified live: a
`rot_y=90` box placed `on` the lid landed exactly on the lid's top). But the
per-tool doc lines in `server/primitives.py` still read "applied after
placement", which now under-describes the behavior. One-line doc fix per
primitive that takes `rot_*` + `on`.

## E10. Color management is not exposed — AgX silently mutes every render

Surfaced by the PBR re-skin of the chest (2026-06-10). `dark_wooden_planks`'s
diffuse map is genuinely dark brown on disk, the node wiring is correct
(sRGB diffuse → Base Color, Non-Color roughness/normal), yet the render reads
pale warm gray. Lighting-ratio changes barely moved it. The same muting hit the
toon build: pure-emission gold `[0.85, 0.58, 0.2]` displayed as flat tan, and
emission bypasses lighting entirely — so the common factor is the VIEW
TRANSFORM. Blender 4.x defaults to AgX, which lifts and desaturates midtones.

No tool can see or change `scene.view_settings` (view transform, look,
exposure, gamma), so an agent can't even diagnose this without guessing — and
NPR/toon work actively wants Standard (no tone mapping of emission), while PBR
work wants AgX/Filmic highlight rolloff. The two styles need different
transforms and the agent controls neither.

Want: `set_color_management(view_transform, look='', exposure=0, gamma=1)` +
current values in `get_blender_status` (or screenshot metadata, next to the
shading mode that's already reported there). `set_toon_material`'s docs should
then recommend Standard. **File:** `server/scene.py` + `extension/lighting.py`
(or a new `extension/color.py`). Effort: small, low risk — four scene fields.

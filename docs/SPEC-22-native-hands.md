# SPEC-22 — Native Hands: strip all judgment sugar, complete the native operator basis

**Status:** APPROVED DIRECTION (2026-07-10). Written for an executor agent with no
conversation context. Phases run in order. **Where any prior spec conflicts with this
one, this one wins.** No overrides, no special cases, no grandfathering.

**The law:** **high-level eyes, low-level hands.** The server invents only in the
substrate — the mouse and eyes the agent lacks. Everything that *mutates* is a native
Blender operator, under its native name, with its hotkey and menu path as retrieval
keys. There is no third category.

**Why (short form).** The agent's Blender knowledge is deep but it is *indexed by native
vocabulary* — hotkeys, menu paths, tutorial phrasing. An agent asked cold can recite the
donut tutorial flawlessly, procedure-perfect, in that vocabulary. The same agent driving
this server maps narrative steps onto minted outcome-verbs and stops early — no LLM
session has ever attempted the long icing drip, despite provably knowing it. Minted
mutation verbs strand the training corpus, act as semantic checkboxes ("`noise_displace`
≈ lumpy: done"), and set the expected effort ceiling at one call per narrative step. The
fix is not better sugar; it is no sugar. This spec exists to **validate that thesis on a
clean baseline** — strip everything first, measure, and only then consider adding
anything back. Do not taint the experiment.

---

## 1. The criterion (binary, total)

Applied to **every op that mutates** geometry, materials, objects, or scene state.

**KEEP — substrate.** An op survives as a server invention only if it substitutes for
hardware the agent lacks (the mouse, the eyes, the viewport). This was never the
problem:

- selection & addressing: all of `select`, handles, `claim`, `look` windows
- perception & verification: `feel`, `validate`, `view op=check_*`, status/no-op detection
- relational placement: the `on=` DSL, `rest_on`, `seat`, `snap`, `place`, `move_to`,
  `aim_axis` — placement is mouse work
- invisible plumbing *inside* native ops: auto mode switching, selection guards, unit
  discipline, auto-status. Absorbed, never exposed as a named op.

**KEEP — native.** The op resolves to a **single native Blender operator, modifier, or
shipped feature** (SPEC-20's litmus: "one operator, or several?"). It keeps — or is
renamed to — the native name. A native op wearing a minted name gets its native name;
that is part of this rule, not an exception to it.

**DELETE — everything else.** Any mutating op that is not a single native operation is
judgment sugar and is deleted. Composites, outcome-named verbs, preset/expression-driven
deformers, construction macros — all of it. No usefulness test, no "but it passes
verification," no borderline queue, no user sign-off gate. If it mutates and it isn't
native, it goes.

**Classification is derived, never recalled** (SPEC-20 R3): read each op's
implementation (what `bpy.ops`/bmesh/modifier calls it makes) and check native claims
against the live 5.x build — not model memory, which is version-stale.

## 2. Phase 1 — audit for judgment sugar

Walk every mutating op on the surface (verb definitions in `server/`, implementations in
`extension/`). For each, one row: **op → NATIVE-KEEP | NATIVE-RENAME (to what) |
SUBSTRATE-KEEP | DELETE**, with the implementation evidence (the native call it wraps,
or the composite it compiles).

**Deliverable:** the table, appended to this spec as Part II.
**Verification:** every registered mutating op appears in exactly one row.

## 3. Phase 2 — remove judgment sugar

Delete every DELETE-row op: server verb entry, extension implementation, flat-tool
registration, validation entries, schema text. Apply every NATIVE-RENAME. Purge
references (`recipes/`, `GUIDANCE_FOR_LLMS.md`, guidance resources, tests).

**Do not write replacement technique docs, wrappers, or migration shims.** The
experiment is whether native vocabulary unlocks the agent's trained procedural
knowledge; pre-authored recipes for the deleted verbs' jobs would confound the result.
Git history is the archive if anything is ever wanted back.

**Verification:** server registers cleanly; tests pass; `grep -r` finds no dangling
references to deleted op names.

## 4. Phase 3 — audit missing native actions

Enumerate the native operator basis **from the live build**: the edit-mode **Mesh /
Vertex / Edge / Face** menus, the Select menu, and the daily hotkey set; cross-check
each against the surface. Seed list from the donut-procedure mapping (verify and extend
against the build — this list is observations, not rulings):

| native action | hotkey / menu | observed status |
|---|---|---|
| Duplicate selection (in-mesh) | Shift+D | missing (`separate` rips, it doesn't copy) |
| Shrink/Fatten (per-vert normals) | Alt+S | `move_verts` out/in exists — verify semantics match |
| Rotate selection (with pivot) | R | missing |
| Merge at Center/First/Last/Cursor | M | only merge-by-distance exists |
| Rip / Rip-Fill | V / Alt+V | missing |
| Split | Y | missing |
| Bisect | Mesh ▸ Bisect | missing |
| Shear | Shift+Ctrl+Alt+S | missing |
| To Sphere | Shift+Alt+S | missing |
| Smooth Vertices | Vertex ▸ Smooth | `relax` exists — verify vs native |
| Randomize | Mesh ▸ Transform ▸ Randomize | `jitter` exists — rename candidate |
| Dissolve Verts/Edges/Faces | Ctrl+X | missing (delete ≠ dissolve) |
| Hide / Reveal (edit mode) | H / Alt+H | missing |
| Fill / Beautify | F | grid_fill exists; plain fill unverified |
| Triangulate / Tris-to-Quads | Ctrl+T / Alt+J | missing |
| Snap-to-face-projected vert dragging | Snapping: Face + Project | missing — native Snapping as a flag on vert moves |

**Deliverable:** the gap table appended to Part II, prioritized daily-driver-first (ops
that appear in every tutorial outrank menu completeness).
**Verification:** every item in the live build's edit-mode menus has a row (present /
missing / deliberately-skipped-with-reason).

## 5. Phase 4 — implement missing native actions

For every new op, and retrofitted onto every surviving native op:

1. **Native name, native semantics, native defaults.** The op does what the tutorial
   says it does. Robustness is absorbed invisibly (§1), never a named variant.
2. **Hotkey + menu path as retrieval keys — mandatory.** The schema description opens
   with the native anchor:
   `duplicate — Shift+D · Mesh ▸ Duplicate: copy the selected geometry in-mesh; the
   copy is selected and unmoved.`
   The hotkey is the index the agent's training uses; it is not decoration.
3. **Family grammar** per SPEC-21 §3: shared WHERE scope block (`target=`, selection,
   `at=`/`handle=`), one magnitude word (`amount`, meters), member as parameter.
4. **Live-verify each op** on a real scene per the `gaps.md` discipline.

## 6. Validation — the experiment this spec exists for

Re-run the donut, blind (standing dogfood discipline: server instructions +
`guidance://llms` only; no repo docs, no recipes). Grade the **transcript**, not the
mesh: does the agent work in native vocabulary from its own knowledge — the top-half
duplicate for the icing, rim verts pulled into drips of varied depth with snapping,
inflate strokes on drip tips, stroke→look cycles in the double digits on craft steps?
That transcript is the measurement of the core thesis. Only after this baseline is read
does any conversation about adding higher-level anything begin.

---

# PART II — PHASE 1 AUDIT (2026-07-10)

**Method (R3).** Every op's verdict was derived by reading its implementation in
`extension/*.py` (the `bpy.ops`/`bmesh.ops`/`modifiers.new`/property call it actually
makes) — never model memory. Every native claim was checked against the **live Blender
5.1.2 build**: a headless introspection confirmed all wrapped operators and modifier
types exist (`mesh.extrude_region_move`, `mesh.spin`, `mesh.symmetrize`, `mesh.fill_grid`,
`transform.shrink_fatten`, `transform.vertex_random`, `mesh.vertices_smooth`,
`transform.vert_slide`, `transform.edge_crease`, `SIMPLE_DEFORM`/`BOOLEAN`/`DISPLACE`/…).
Op sets were enumerated programmatically from each verb's `Literal[...]` enum in
`server/verbs/*.py` (grep, not recall).

**Scope.** Rows cover **every mutating op**. Pure perception/read ops (`look`, `feel`,
`validate`, `collab`, and the read-only ops *inside* mutating verbs — `edit op=trace`,
`object op=info/describe/parts/props`, `material op=search_*`, `modifier op=list`,
`scene op=tree`, `render op=settings`, `history op=log/mark/diff/acknowledge/changes`,
`file op=list`, `pose op=bone_tree/describe_bone/constraints/shape_keys`, `view op=check_*`)
carry no row. `connect` (attach/detach/launch) and `addon` (list/inspect/run — a generic
native-operator passthrough) are connection/escape-hatch plumbing, not scene mutations.

## II.0 Counts

| verdict | count |
|---|---|
| **NATIVE-KEEP** | 91 |
| **NATIVE-RENAME** | 9 |
| **SUBSTRATE-KEEP** | 49 |
| **DELETE** | 24 |
| **total mutating-op rows** | **173** |

**Verification:** enumerated op counts per verb — add 17, object 21, edit 31, transform 22,
modifier 7, material 13, sculpt 8, pose 15, scene 6, render 6, history 9, file 4, uv 1,
view 15, select 23. Every mutating op appears in exactly one row below; the remainder are
the reads/plumbing listed under Scope.

## II.1 DELETE list (24) — the judgment sugar

| op | why (implementation) |
|---|---|
| `edit op=noise_displace` | Clouds-texture + Displace-modifier + apply — preset-driven deformer composite |
| `edit op=round` | named-corner select + `mesh.bevel` + shade_smooth — construction composite |
| `edit op=smooth_edges` | Bevel-modifier + shade_smooth + auto_smooth + apply — composite |
| `edit op=shape_profile` | bespoke per-ring radius interpolation (`rings.py`, no native call) |
| `edit op=field` | explicit per-vertex formula deformer (`fields.py`, no native call) |
| `edit op=loft` | vacuum-form onto authored moulds (`fields.py`, no native call) |
| `edit op=relax` | `bmesh.smooth_vert` + BVH-reproject loop — LoopTools-style composite |
| `edit op=slide` | direction-word move + BVH-reproject — bespoke composite |
| `transform op=mirror` | `object.duplicate` + reflect + `transform_apply` — dup-and-place composite |
| `transform op=array_corners` | `object.duplicate`×4 + place — composite (native = Array modifier) |
| `transform op=array_along` | `object.duplicate`×N + place — composite (native = Array modifier) |
| `object op=duplicate_mirrored` | duplicate + per-vert reflect + recalc + origin_set — composite |
| `add type=tube` | fully bespoke swept ring mesh via `from_pydata` (no native sweep / no Curve-to-Tube) |
| `add type=helix` | parametric samples → poly-curve bevel → convert → shade_smooth (not a Screw modifier) |
| `material op=textured` | multi-node PBR graph builder (≈ Node-Wrangler) |
| `material op=pbr` | same multi-node PBR graph handler as `textured` |
| `material op=toon` | Shader-to-RGB → ColorRamp cel-band graph builder |
| `material op=outline` | Emission slot + inverted-hull Solidify modifier — composite |
| `material op=remove_outline` | inverse of `outline` (remove modifier + slot) — composite |
| `sculpt brush=gravity` | region-parametric sag — no native "Gravity" brush; invented effect |
| `pose op=create_armature` | armature + per-bone `edit_bones.new` loop — construction composite |
| `pose op=weight_to_bone` | vgroup-at-1.0 + Armature modifier — composite |
| `pose op=bind` | MESH_DEFORM modifier create + `meshdeform_bind` — composite (pure bind survives as `rebind`) |
| `pose op=shape_key_bake` | shape_key_add(from_mix) + read + clear + write co — bespoke bake sequence |

## II.2 NATIVE-RENAME list (9) — native op wearing a minted name

| op | → native name | native op (5.1-verified) |
|---|---|---|
| `edit op=inflate` | **shrink_fatten** | `transform.shrink_fatten` (Alt+S) — push verts along per-vert normals |
| `edit op=jitter` | **randomize** | `transform.vertex_random` (Mesh ▸ Transform ▸ Randomize) |
| `edit op=proportional_move` | **grab** | `transform.translate` w/ proportional editing (G, O); falloffs = native enum |
| `edit op=proportional_scale` | **resize** | `transform.resize` w/ proportional editing (S, O) |
| `transform op=move_verts` | **grab** | edit-mode `transform.translate` of the selection (G) |
| `transform op=scale_verts` | **scale** | edit-mode `transform.resize` about pivot (S) |
| `transform op=lattice` | **grab** | Grab/Scale of lattice control points (slab-picker = addressing) |
| `object op=split` | **separate** | `mesh.separate(type='LOOSE')` — Separate ▸ By Loose Parts (P) |
| `add type=floor` | **plane** | `mesh.primitive_plane_add` seated on the floor |

## II.3 Per-verb tables

### edit (30 mutating; `trace` = read)
| op | verdict | evidence |
|---|---|---|
| extrude | NATIVE-KEEP | `mesh.extrude_region_move` |
| bevel | NATIVE-KEEP | `mesh.bevel` |
| loop_cut | NATIVE-KEEP | `bmesh.ops.subdivide_edges` on a ring = Loop Cut (Ctrl+R) |
| subdivide | NATIVE-KEEP | `bmesh.ops.subdivide_edges` |
| merge | NATIVE-KEEP | `bmesh.ops.remove_doubles` = Merge by Distance |
| symmetrize | NATIVE-KEEP | `mesh.symmetrize` |
| delete | NATIVE-KEEP | `mesh.delete` |
| separate | NATIVE-KEEP | `mesh.separate(type='SELECTED')` |
| mark_sharp | NATIVE-KEEP | `e.smooth=False` = Mark Sharp |
| crease | NATIVE-KEEP | crease layer = Edge Crease (Shift+E) |
| recalc_normals | NATIVE-KEEP | `mesh.normals_make_consistent` (+ optional `flip_normals`) |
| boolean | NATIVE-KEEP | `BOOLEAN` modifier (+ apply) |
| bridge | NATIVE-KEEP | `bmesh.ops.bridge_loops` = Bridge Edge Loops (handles = addressing) |
| spin | NATIVE-KEEP | `mesh.spin` |
| poke | NATIVE-KEEP | `bmesh.ops.poke` |
| inset | NATIVE-KEEP | `bmesh.ops.inset_individual`/`inset_region` |
| grid_fill | NATIVE-KEEP | `mesh.fill_grid` |
| bend | NATIVE-KEEP | `SIMPLE_DEFORM` modifier (BEND) + bake |
| inflate | NATIVE-RENAME → shrink_fatten | hand-rolled per-vert normal push = `transform.shrink_fatten` |
| jitter | NATIVE-RENAME → randomize | hand-rolled white noise = `transform.vertex_random` |
| proportional_move | NATIVE-RENAME → grab | hand-rolled falloff translate = proportional-edit Move |
| proportional_scale | NATIVE-RENAME → resize | hand-rolled falloff scale = proportional-edit Resize |
| noise_displace | DELETE | Clouds texture + Displace modifier + apply (preset composite) |
| round | DELETE | corner-select + bevel + shade_smooth composite |
| smooth_edges | DELETE | Bevel modifier + shade_smooth + auto_smooth composite |
| shape_profile | DELETE | bespoke ring-radius interpolation |
| field | DELETE | bespoke per-vertex formula deformer |
| loft | DELETE | bespoke mould-array deformer |
| relax | DELETE | smooth_vert + BVH reproject composite |
| slide | DELETE | direction move + BVH reproject composite |

### transform (22)
| op | verdict | evidence |
|---|---|---|
| nudge | SUBSTRATE-KEEP | relational object move (`obj.location`) |
| place | SUBSTRATE-KEEP | the `on=` placement DSL |
| move_to | SUBSTRATE-KEEP | absolute placement |
| rotate_to | SUBSTRATE-KEEP | absolute orientation placement |
| aim_axis | SUBSTRATE-KEEP | orientation placement |
| rest_on | SUBSTRATE-KEEP | BVH-raycast seating |
| seat | SUBSTRATE-KEEP | BVH-raycast seating |
| snap | SUBSTRATE-KEEP | bbox-face snapping |
| snap_grid | SUBSTRATE-KEEP | grid snapping |
| rotate | SUBSTRATE-KEEP | object rotate about pivot (the mouse's R) |
| resize | SUBSTRATE-KEEP | dimensions-over-coordinates sizing (+ apply-scale) |
| scale | SUBSTRATE-KEEP | relational group scale about a shared pivot |
| match_dim | SUBSTRATE-KEEP | relational sizing to a reference extent |
| distribute | SUBSTRATE-KEEP | relational even-spacing between anchors |
| snap_loop | SUBSTRATE-KEEP | fit a loop onto a named opening (assembly snap) |
| apply | NATIVE-KEEP | `object.transform_apply` (Ctrl+A) |
| move_verts | NATIVE-RENAME → grab | edit-mode vert translate |
| scale_verts | NATIVE-RENAME → scale | edit-mode vert scale about pivot |
| lattice | NATIVE-RENAME → grab | move/scale lattice control points |
| mirror | DELETE | duplicate + reflect + apply (native = Mirror modifier) |
| array_corners | DELETE | duplicate×4 + place (native = Array modifier) |
| array_along | DELETE | duplicate×N + place (native = Array modifier) |

### object (17 mutating; info/describe/parts/props = reads)
| op | verdict | evidence |
|---|---|---|
| rename | NATIVE-KEEP | `obj.name`/`obj.data.name` (F2) |
| delete | NATIVE-KEEP | `bpy.data.objects.remove` = Delete |
| duplicate | NATIVE-KEEP | `object.duplicate` (Shift+D) |
| join | NATIVE-KEEP | `object.join` (Ctrl+J) |
| convert | NATIVE-KEEP | `object.convert(target='MESH')` |
| visibility | NATIVE-KEEP | `hide_set`/`hide_viewport`/`hide_render` (H) |
| particle_visibility | NATIVE-KEEP | particle-modifier `show_viewport` |
| set_prop | NATIVE-KEEP | custom-property write |
| light | NATIVE-KEEP | light-datablock props |
| mode | NATIVE-KEEP | `object.mode_set` (Tab) |
| remesh | NATIVE-KEEP | `object.voxel_remesh` / `object.quadriflow_remesh` |
| split | NATIVE-RENAME → separate | `mesh.separate(type='LOOSE')` |
| group | SUBSTRATE-KEEP | object addressing via native Collections (object-level `claim`) |
| ungroup | SUBSTRATE-KEEP | Collection API |
| add_to_group | SUBSTRATE-KEEP | Collection API |
| aim | SUBSTRATE-KEEP | relational aim (`to_track_quat`) |
| duplicate_mirrored | DELETE | duplicate + reflect + recalc + origin_set composite |

### add (17)
| op | verdict | evidence |
|---|---|---|
| box | NATIVE-KEEP | `mesh.primitive_cube_add` |
| plane | NATIVE-KEEP | `mesh.primitive_plane_add` |
| cylinder | NATIVE-KEEP | `mesh.primitive_cylinder_add` |
| sphere | NATIVE-KEEP | `mesh.primitive_uv_sphere_add` |
| cone | NATIVE-KEEP | `mesh.primitive_cone_add` |
| torus | NATIVE-KEEP | `mesh.primitive_torus_add` |
| icosphere | NATIVE-KEEP | `mesh.primitive_ico_sphere_add` |
| circle | NATIVE-KEEP | `mesh.primitive_circle_add` |
| grid | NATIVE-KEEP | `mesh.primitive_grid_add` |
| curve | NATIVE-KEEP | native Curve datablock (+ per-anchor Hook = plumbing) |
| text | NATIVE-KEEP | Add Text (Font object) + mesh-convert tail absorbed |
| lattice | NATIVE-KEEP | `bpy.data.lattices.new` cage |
| light | NATIVE-KEEP | `bpy.data.lights.new` + link |
| camera | NATIVE-KEEP | `bpy.data.cameras.new` + link |
| floor | NATIVE-RENAME → plane | `mesh.primitive_plane_add` seated at z=0 |
| tube | DELETE | bespoke swept mesh (`from_pydata`) |
| helix | DELETE | bespoke poly-curve bevel + convert |

### material (11 mutating; search_* = reads)
| op | verdict | evidence |
|---|---|---|
| set | NATIVE-KEEP | Principled BSDF input writes + slot assign |
| assign | NATIVE-KEEP | `face.material_index` on the selection |
| remove_slot | NATIVE-KEEP | `object.material_slot_remove` |
| remove_unused_slots | NATIVE-KEEP | `object.material_slot_remove_unused` |
| shade_smooth | NATIVE-KEEP | `object.shade_smooth` |
| shade_flat | NATIVE-KEEP | `object.shade_flat` |
| textured | DELETE | multi-node PBR graph builder |
| pbr | DELETE | same multi-node PBR graph handler |
| toon | DELETE | Shader-to-RGB cel graph builder |
| outline | DELETE | Emission slot + inverted-hull Solidify |
| remove_outline | DELETE | remove modifier + slot (inverse composite) |

### modifier (6 mutating; list = read)
| op | verdict | evidence |
|---|---|---|
| add | NATIVE-KEEP | `obj.modifiers.new(type=…)` |
| add_asset | NATIVE-KEEP | `NODES` modifier + bundled GN Essentials asset |
| modify | NATIVE-KEEP | modifier prop / GN-socket writes |
| move | NATIVE-KEEP | `object.modifier_move_to_index` |
| remove | NATIVE-KEEP | `obj.modifiers.remove` |
| apply | NATIVE-KEEP | `object.modifier_apply` |

### sculpt (8) — see II.4 judgment note
| op | verdict | evidence |
|---|---|---|
| grab | NATIVE-KEEP | shipped Grab brush (bmesh-driven — native stroke needs a mouse) |
| draw | NATIVE-KEEP | shipped Draw brush (bmesh-driven) |
| inflate | NATIVE-KEEP | shipped Inflate brush (bmesh-driven) |
| smooth | NATIVE-KEEP | shipped Smooth brush (bmesh-driven) |
| crease | NATIVE-KEEP | shipped Crease brush (bmesh-driven) |
| pinch | NATIVE-KEEP | shipped Pinch brush (bmesh-driven) |
| flatten | NATIVE-KEEP | shipped Flatten brush (bmesh-driven) |
| gravity | DELETE | no native "Gravity" brush — invented sag effect |

### pose (11 mutating; bone_tree/describe_bone/constraints/shape_keys = reads)
| op | verdict | evidence |
|---|---|---|
| auto_weight | NATIVE-KEEP | `object.parent_set(type='ARMATURE_AUTO')` |
| assign_weight | NATIVE-KEEP | bmesh deform-layer write = `object.vertex_group_assign` |
| pose_bone | NATIVE-KEEP | pose-bone `rotation_euler`/`location` |
| rebind | NATIVE-KEEP | `meshdeform_bind`/`surfacedeform_bind`/`correctivesmooth_bind` |
| shape_key_set | NATIVE-KEEP | `key_block.value` |
| shape_key_active | NATIVE-KEEP | `active_shape_key_index` |
| shape_key_delete | NATIVE-KEEP | `shape_key_remove`/`clear` |
| create_armature | DELETE | armature + per-bone edit-bone loop |
| weight_to_bone | DELETE | vgroup-at-1.0 + Armature modifier |
| bind | DELETE | MESH_DEFORM create + bind (pure bind = `rebind`) |
| shape_key_bake | DELETE | from_mix add + read + clear + write co |

### scene (5 mutating; tree = read)
| op | verdict | evidence |
|---|---|---|
| world | NATIVE-KEEP | world Background node (color/strength/HDRI) |
| atmosphere | NATIVE-KEEP | native World Volume Scatter/Absorption shader |
| new | NATIVE-KEEP | `wm.read_homefile` (New File) |
| frame | NATIVE-KEEP | `scene.frame_set` + start/end |
| bake_physics | NATIVE-KEEP | `ptcache.bake_all` (free-first = plumbing) |

### render (5 mutating; settings = read)
| op | verdict | evidence |
|---|---|---|
| image | NATIVE-KEEP | `render.render(write_still=True)` (F12) |
| engine | NATIVE-KEEP | `scene.render.engine` |
| quality | NATIVE-KEEP | EEVEE raytracing/gtao/shadows/samples props |
| cycles | NATIVE-KEEP | Cycles device/denoise/samples props |
| color | NATIVE-KEEP | Color-Management view_settings |

### history (4 mutating; log/mark/diff/acknowledge/changes = reads)
| op | verdict | evidence |
|---|---|---|
| undo | NATIVE-KEEP | `ed.undo` (Ctrl+Z) |
| redo | NATIVE-KEEP | `ed.redo` |
| undo_to | NATIVE-KEEP | computed step count → `ed.undo` |
| restore | NATIVE-KEEP | `ed.undo` to a marked op_id |

### file (3 mutating; list = read)
| op | verdict | evidence |
|---|---|---|
| save | NATIVE-KEEP | `wm.save_as_mainfile` |
| open | NATIVE-KEEP | `wm.open_mainfile` |
| import | NATIVE-KEEP | native importer per type (`wm.stl_import`/`fbx_import`/`obj_import`/`import_scene.gltf`) |

### uv (1)
| op | verdict | evidence |
|---|---|---|
| unwrap | NATIVE-KEEP | `uv.smart_project` (+ cube/cylinder/sphere_project by method) |

### view (10 mutating; check_* = reads)
| op | verdict | evidence |
|---|---|---|
| camera_dof | NATIVE-KEEP | camera DoF props (focus_distance/aperture) |
| camera_lens | NATIVE-KEEP | camera `lens` prop |
| active_camera | NATIVE-KEEP | `scene.camera` (Set Active Camera) |
| shading | SUBSTRATE-KEEP | viewport shading mode (the eyes) |
| angle | SUBSTRATE-KEEP | standard-view snap (the eyes) |
| overlays | SUBSTRATE-KEEP | overlay toggles (the eyes) |
| orbit | SUBSTRATE-KEEP | viewport orbit (the eyes) |
| zoom | SUBSTRATE-KEEP | zoom-to-selection (the eyes) |
| frame | SUBSTRATE-KEEP | frame-objects-in-view (the eyes) |
| rig | SUBSTRATE-KEEP | relational camera/light placement + aim |

### select (23) — SUBSTRATE-KEEP, wholesale (§1: "all of `select`")
`all · none · object · by_axis · between · list · by_index · group · material ·
boundary · limb · grow · shrink · flood · pick · claim · random · in_sphere ·
by_radius · ring · rings · component_mode · current` — every op is selection &
addressing (the eyes/hands the agent lacks); none mutates geometry. `claim` mints a
vgroup-backed handle (a scene fact, G218), still addressing. No native/delete cut applies.

## II.4 Judgment calls (where the criterion took real work)

- **sculpt `grab/draw/inflate/smooth/crease/pinch/flatten` → NATIVE-KEEP; `gravity` → DELETE.**
  All eight are hand-rolled bmesh math calling zero `bpy.ops.sculpt` (native brushes need
  interactive mouse strokes, undrivable headless). Seven wear *exact native brush names* and
  reproduce a shipped brush's effect — §1's "single … shipped feature," with the bmesh
  reimplementation being the mouse-substitute the server exists to provide. `gravity` is not
  a native brush (Blender has a gravity *setting*, not brush) → invented effect → DELETE.
- **`inflate`/`jitter`/`proportional_move`/`proportional_scale` → NATIVE-RENAME (not DELETE).**
  Each is hand-rolled yet reproduces *exactly one* native operator (all four confirmed present
  in 5.1: `shrink_fatten`, `vertex_random`, proportional `translate`, proportional `resize`).
  A from-scratch reimplementation of one native op is still that op (cf. §1 NATIVE).
- **`relax`/`slide` → DELETE (not NATIVE).** `vertices_smooth` and `vert_slide` both exist in
  5.1, but neither op *wraps* them: each is a smooth/move pass **plus** a BVH reproject-onto-
  surface pass — a two-step LoopTools-style composite whose outcome no single core op yields.
- **Object-mode transforms → SUBSTRATE; edit-mode vert transforms → NATIVE.** §1 declares
  relational placement "mouse work," so whole-object move/rotate/resize/snap/aim (`nudge`,
  `rotate`, `resize`, `scale`, `snap*`, `match_dim`, `distribute`, `aim`, …) are SUBSTRATE.
  `move_verts`/`scale_verts`/`lattice` mutate *geometry* (verts/lattice points) → native hands
  (Grab/Scale). The dividing line is object-placement=mouse vs geometry-mutation=native.
  `transform op=apply` is the exception among object-transforms: it's a real native operator
  (`transform_apply`, Ctrl+A), not placement → NATIVE-KEEP.
- **`mirror`/`array_corners`/`array_along`/`duplicate_mirrored` → DELETE.** All are duplicate-
  and-place composites; the native single-operation equivalents are the Mirror and Array
  *modifiers* (already reachable via `modifier op=add`), not these baked multi-object macros.
- **pose `create_armature`/`weight_to_bone`/`bind`/`shape_key_bake` → DELETE.** Rigging
  *construction* composites. The native operators they bundle survive individually
  (`auto_weight`=parent_set, `rebind`=the bind operator, the shape-key set/active/delete ops).
- **`group`/`ungroup`/`add_to_group` → SUBSTRATE (not NATIVE).** Backed by native Collections,
  but their role is object-level *addressing* — the object analog of vert `claim` — so they
  belong with the addressing substrate, not the native-hands basis.
- **`text` → NATIVE-KEEP; `tube`/`helix` → DELETE.** `text` bottoms out on Add-Text (a native
  Font object) with the mesh-convert tail absorbed as Blender-space plumbing. `tube` is a fully
  bespoke `from_pydata` sweep (does **not** use the native Curve-to-Tube GN modifier) and
  `helix` is a bespoke poly-curve bevel (not a Screw modifier) → neither is a single native op.
- **`noise_displace` → DELETE though Displace is native.** The op authors a Clouds texture,
  wires a Displace modifier, and applies — a preset-driven deformer composite, which §"DELETE"
  names explicitly; the bare Displace modifier remains reachable via `modifier op=add`.
- **`material set/assign/shade_*` → NATIVE; `textured/pbr/toon/outline` → DELETE.** The kept
  four are single native operations (Principled input writes, `material_index`, shade ops);
  the deleted four are multi-node shader-graph builders (Node-Wrangler / NPR composites).

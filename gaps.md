# MCP gaps

## Remaining from the X-series live pass (X3B, X7), 2026-06-11

X1–X6 are closed (see Batch 9 below). Two deferred items remain open — both are
selection/edit verbs that ignore an existing selection; filed together because
they live in the same neighborhood and the authoring session hit both in one
rim-edit attempt:

- **X3B — no primitive selects an OPEN BOUNDARY loop (a mesh rim).** Batch 9's
  selection-flush fix (X3A) turned "catastrophic whole-mesh duplicate" into
  "merely wrong for rim work" — but it did NOT unblock the actual task. A tilted
  rim ring can't be isolated by axis bands (a 24-vert band always drags in ~10
  adjacent faces), which is what pushed the authoring session off `extrude`
  entirely. Wants a `select_boundary` / open-edge-loop verb: select the edges
  that border a hole (edges with exactly one face), optionally grown from a seed
  region. The real unblock for rim insets, collar re-shaping, sleeve hems.

- **X7 — `loop_cut` ignores the selection and answers in coordinates.** With 154
  verts selected (one shoulder segment) it cut 2302 edges across the ENTIRE mesh
  — both arms, all fingers — doubling a production mesh (3288→8100). It also
  returned the full list of ~2000 cut X-positions: a raw coordinate dump, the
  exact anti-pattern the tactile-introspection principle bars. Wants: respect the
  current selection when one exists (whole mesh only as the no-selection
  fallback), and report "Cut N edges across M loops in [region words]" instead of
  the dump. (The global cut happened to suit Spring's arms — density was needed
  there — but that was luck, not intent.)

_New gaps from future builds go above this line._

## Tactile introspection — the design principle

The guiding principle for P4–P12, kept here because it governs all future
introspection work: the agent's vision can *judge* but cannot *measure*. These
tools convert geometry into short semantic verdicts in scene vocabulary (object
names, mm/deg deltas, frame %) — never coordinate dumps, which the agent cannot
reason over. Region words ("top-left-front") locate things without leaking
coordinates. BVHTree makes the proximity queries milliseconds-cheap at hobby poly counts.

---

# Recently closed

## Batch 9 — X-series live regressions (X1, X2, X4, X5, X6; X3A), 2026-06-11

Closes everything the live re-stage of the tank-top edit exposed except the two
deferred selection primitives (X3B, X7, still open above). e2e in
`tests/e2e_batch9.py` (25 checks); all 12 prior suites still green. X1/X6/X2 are
socket / live-depsgraph / viewport phenomena the headless harness can't fully
reproduce — X1's null-on-timeout guard is tested at the socket level (undrained
queue = a too-slow op), the rest verified by reasoning + the live diagnosis the
authoring session recorded.

- **X1 — the bind family's `'NoneType' object has no attribute 'get'` was a
  timeout, not a logic bug.** `handle_client` runs the tool on the main thread and
  `result_event.wait(timeout=30)`; a mesh-deform bind on a production cage takes
  ~35–40s, so the wait expired with `result_box[0]` still `None`, the server sent
  `json.dumps(None)` = `"null"`, and every MCP wrapper's `result.get(...)` threw
  that error. Live-only because headless calls `execute_command` directly (no
  socket). Fix: (a) `handle_client` NEVER serializes `None` — on timeout it returns
  an honest error that says the op was NOT cancelled, may still complete and log
  itself as a success, and to check `get_history` before retrying (a blind retry
  stacks a second bind behind the first); (b) `bind_mesh_deform` / `rebind_deform`
  default to a 120s timeout (plumbed like `render_to_file`) so the bind actually
  finishes. The original 5-call crash was a pile-up: call #1 hogged the main
  thread, #2–5 (incl. a trivial introspection) timed out queued behind it.
- **X2 — `frame_scene` failed in POSE mode** (production files open posed):
  `select_all.poll()` fails in any non-OBJECT mode. It already dropped EDIT→OBJECT
  for framing; generalized to save ANY non-OBJECT mode (POSE included), frame in
  OBJECT, then restore the user's mode — framing is no longer a silent mode switch.
- **X3A — selectors now flush the vert selection up to the active edge/face
  domains.** In EDGE/FACE component mode, `select_flush_mode` re-derived verts FROM
  a stale higher selection and clobbered the just-set verts — so a 24-vert band
  left all 6554 edges + 3268 faces lit and the next region-`extrude` cloned the
  whole mesh. New `_flush_vert_selection` (used by select_by_axis / select_between /
  random_select / select_in_sphere): capture the wanted verts, clear every domain,
  re-set the verts, `select_flush(True)` to promote — so an edge/face is selected
  iff all its verts are. (Capture-first matters: `edge.select=False` flushes DOWN
  and would deselect the verts.) Flushes up to the current mode; doesn't force VERT.
  NB: this turns "catastrophic" into "merely wrong for rim work" — the real rim
  unblock is the X3B boundary selector, still open.
- **X4 — a VALID deform bind silently shadows a rest-shape edit, and now warns.**
  MESH_DEFORM / SURFACE_DEFORM / CS(BIND) reconstruct bound-vert positions from
  their driver, so a position-only base-mesh edit (no vert-count change → topology
  guard silent) is invisible until rebind. The edit guard now also fires on
  position-only edits when a reconstruct-bind is present AND still VALID, emitting
  `bind_shadowed` + a rebind prescription. Validity is gated on a `bb_bind_vcount`
  custom prop (seeded on first observation, set on every bind/rebind): a DEAD bind
  (count mismatch from an earlier topology edit) is inert and shows edits 1:1, so
  it correctly stays silent — the false-positive the authoring session warned
  about. Known limit: a file imported with an already-dead bind we never observed
  valid gets one false "rebind to show" once (harmless advice). Both the manual
  (`check_edit_binds`) and request-scoped (`execute_command`) paths covered.
- **X5 — `modify_modifier` can now neutralize a modifier without removing it.**
  Added `factor` (CORRECTIVE_SMOOTH / SMOOTH strength), `strength` (DISPLACE),
  `iterations`, and the universal `show_viewport` / `show_render` enable-disable
  toggles. The escape hatch when a modifier is fighting an edit (X4's shadowing
  bind), short of `remove_modifier` throwing away production-tuned settings.
- **X6 — an orphan-completed op no longer poisons introspection.** A timed-out op
  (X1) keeps running and on completion can wedge the touched object's evaluated
  mesh, after which `describe(posed)` / status bounds report the stale ghost as
  truth. Fix: (a) on timeout, `handle_client` records the touched object as
  eval-dirty (`state.mark_eval_dirty`) and the next command force-retags it
  (`flush_eval_dirty` at the top of `execute_command`); (b) `eval_world_bbox`
  force-retags + updates the depsgraph before reading, so the evaluated measuring
  tools can't be served a stale cache. (X6c — the bbox-vs-sel_z self-contradiction
  flag — left as a nice-to-have.)

## Batch 8 — deform-stack aftermath (W1, W2, W3), 2026-06-11

Closes the W-series — the layer exposed by cage-rebinding Spring's tank top: once
a deform bind is recoverable (V1/V2), the stack AROUND it (order, the bind guard's
blind spots, the other bind types) becomes the gap. e2e in `tests/e2e_batch8.py`
(42 checks). Verified headless only — the live Blender went unreachable mid-session
(see re-stage recipe below); W2's manual-path repro and the MESH_DEFORM +
CORRECTIVE_SMOOTH rebinds are the production-equivalent cases under headless cover.

- **W1 — modifier stack ORDER is addressable.** New `move_modifier(target,
  modifier, index=|before=|after=)` (wraps `modifier_move_to_index`) — `index` is
  absolute, `before`/`after` place relative to a named modifier (the vacated-slot
  shift is handled so "after Subsurf" always lands directly below it). Chose the
  explicit primitive over any auto-placement heuristic ("deform modifiers above
  generators") — that's the bespoke magic the project bars; the agent places
  legibly. **The trap:** a bind is computed against the modifier's evaluated INPUT,
  so moving a bound deform modifier silently kills the bind — and WITHOUT a
  vert-count change, so the V2/W2 guard is blind to it. `move_modifier` therefore
  returns its own `bind_invalidated` + `bind_warning` (cause=`stackmove`) whenever
  it moves a bound MESH_DEFORM/SURFACE_DEFORM/CORRECTIVE_SMOOTH; the recipe is
  move → `rebind_deform`. Also added **CORRECTIVE_SMOOTH** to `add_modifier`
  (rest_source BIND default / ORCO, factor, iterations) — the stack staple it
  couldn't recreate before. DISPLACE deferred: it's inert without a texture
  datablock and there's no texture-creation verb yet — half-shipping a dead
  modifier with our name on it isn't worth it.
- **W2 — the bind-invalidation guard is no longer bypassed by the manual edit
  path.** The V2 snapshot was request-scoped (`server.execute_command`, one
  `target=` verb), so the four-command manual path (`set_mode(EDIT)` → `select_…`
  → `delete_geometry` no-target → `set_mode(OBJECT)`) slipped through. The snapshot
  is now **edit-session-scoped** (`state.snapshot_edit_binds` / `check_edit_binds`):
  taken when EDIT is entered (in `objects.set_mode`), compared when EDIT is exited
  — one warning per session, on the `set_mode(OBJECT)` that ends it. The
  request-scoped `target=` path still warns immediately (unchanged; verified no
  regression), and `_enter_edit_for_target` drops any pending manual snapshot so
  the two paths don't cross-contaminate. A position-only manual edit (no
  vert-count delta) and an unbound mesh both stay silent. Accepted limit: exiting
  EDIT via the Blender UI bypasses the compare; the next MCP edit-enter reconciles
  the stale snapshot by replacing it (S1b: a guard on one path is a guard on none).
- **W3 — every bind type has a rebind verb.** New umbrella `rebind_deform(mesh,
  modifier=)` dispatches by type to `meshdeform_bind` / `surfacedeform_bind` /
  `correctivesmooth_bind` — one concept ("this bind is stale"), one verb, so the
  invalidation warning prescribes a single cure regardless of which patient is
  dying. Default rebinds every bound deform modifier on the mesh; `modifier=` names
  one. RE-BINDS existing modifiers only (never creates — `bind_mesh_deform` stays
  the MESH_DEFORM cage-setup verb). A CORRECTIVE_SMOOTH at rest_source=ORCO has no
  stored bind, so it's reported as skipped, not toggled blind. `deform_bind_warning`
  now points every diagnosis at `rebind_deform`.

_Re-stage the W1/W3 live repro (Spring): delete the jacket, remove the pullover's
Mask, cut verts, `bind_mesh_deform` to `BlenRig_mdef_cage_sweater`; or just verify
on a synthetic cage stack headless (what `e2e_batch8.py` does). Side note logged by
the authoring session: `check_contacts` timed out on Spring's heavy evaluated
meshes right before the server dropped — worth a look as its own gap._

## Batch 7 — deform-bind recovery (V1, V2), 2026-06-11

Closes the V-series — re-dressing Spring exposed that a production deform stack
was unrecoverable after a destructive edit. e2e in `tests/e2e_batch7.py` (28 checks).

- **V1 — the mesh-deform bind is reachable: add, bind, rebind, unbind.**
  `add_modifier` now opens the deform-modifier door it was missing —
  `MESH_DEFORM` / `ARMATURE` / `LATTICE`, each wired to its driving object via a
  required `target` (cage mesh / armature / lattice; wrong-type targets fail
  loudly). `bind_mesh_deform(mesh, cage, action=bind|unbind|rebind)` wraps
  `bpy.ops.object.meshdeform_bind` (the operator nothing reached before): it
  creates the MESH_DEFORM modifier when only a `cage` is given, drives the
  bind/unbind toggle deterministically per `action`, and runs through
  `state.ui_override()` so it works live, not just headless. A bind that comes
  back unbound is reported as an error, not a false success. This is the
  cage-deformation recovery path — higher cloth/skin quality than the
  `auto_weight`-straight-to-armature downgrade the edit session fell back to.
- **V2 — topology edits no longer silently kill deform binds.** The dispatch
  hook every edit verb routes through (`_enter_edit_for_target`, U10's hook
  point) now snapshots a target's vert-count-dependent bound modifiers
  (MESH_DEFORM / SURFACE_DEFORM / CORRECTIVE_SMOOTH — `common.deform_binds`)
  before the edit and, if the edit actually changed the vertex count, injects a
  loud `bind_invalidated` + `bind_warning` onto the result ("DEFORM BIND
  INVALIDATED … rebind required"). Surfaced generically in `server/_core._status`
  so it rides every edit verb's output. Keyed on the real cause — a vert-count
  delta — so a position-only edit (`move_vertices`, which leaves a MESH_DEFORM
  bind valid) stays silent and an unbound mesh-deform mesh never warns.

## Batch 6 — presentation pass (T1, T5), 2026-06-11

Closes the T-series. e2e in `tests/e2e_batch6.py` (21 checks).

- **T1 — materials addressable beyond slot 0.** `set_material(material="iron_mat",
  …)` edits an EXISTING material datablock by name with no target — restyle a
  shared material everywhere it's used in one call. `set_material(target=…,
  slot=N)` operates on a specific slot: without `material_name` it edits the
  material already in that slot in place (a multi-slot mesh's secondary material);
  with one, it assigns there. `set_textured_material` gained the same `slot`.
  Out-of-range slots fail loudly.
- **T5 — the user's live viewport is configurable.** `set_viewport_overlays(
  relationship_lines=, floor=, cursor=, wireframes=, text_info=, axes=, overlays=)`
  toggles the overlays the PERSON sees (not just the agent's screenshot);
  `set_object_visibility(name, viewport=, render=)` hides an object — e.g. an
  armature, so its bones stop drawing over the meshes — while the Armature modifier
  keeps deforming the bound mesh. (set_viewport_overlays is NON_UNDOABLE like
  set_viewport_shading.)

## Batch 5 — production-asset access (U4, U7, U8, U10), 2026-06-11

Closes the U-series. e2e in `tests/e2e_batch5.py` (23 checks, incl. a real
library-link round-trip).

- **U4 — `get_scene_tree` scales.** New `filter` (name substring), `type`
  (MESH/ARMATURE/…), `max_depth`, and `summarize` (collapse any collection over N
  objects to per-type counts; default 20, 0 = full). Filtering disables
  summarization so matches are listed. A ~400-object rig reads as a handful of
  lines; drill in with filter/type.
- **U7 — particle systems workable.** `set_particle_visibility(name, show)`
  toggles show_viewport on every particle-system modifier (hair buries the mesh);
  `describe` gains a `N particle system(s): name(hair, 500)` line.
- **U8 — shape keys exist.** `list_shape_keys(name)` (names + values + ranges) and
  `set_shape_key(name, key, value)` to drive morphs/correctives.
- **U10 — linked library data is defined.** `common.linked_status` /
  `is_linked_data` / `linked_guard`; `describe` and `get_scene_tree` tag objects
  `[lib:File.blend]` / `[override:File.blend]`; and geometry edits (via the shared
  `_enter_edit_for_target` hook — covers the whole edit-mode family) and the three
  material setters fail loudly on read-only linked data instead of opaque
  no-ops/errors. Local overrides stay editable; local objects are unaffected.

## Batch 4 — rig + metadata introspection (U1, U2, U3, U6, U9), 2026-06-11

The read-side of rigging: operate on a rig someone else built, not just one we
authored. e2e in `tests/e2e_batch4.py` (35 checks).

- **U1 — armature discovery.** `get_bone_tree(armature, filter=, deform_only=,
  max_depth=)` prints the bone hierarchy (control bones marked, ancestors kept
  for filter context — handles hundred-bone rigs); `describe_bone(armature, bone)`
  gives parent/children, head & tail region words, length, deform flag, pose
  locks, constraints (type→target), and custom props. The read complement of
  `create_armature`.
- **U2 — custom-property access.** `get_custom_properties(name, bone=)` /
  `set_custom_property(name, key, value, bone=)` on objects or pose bones (where
  IK/FK switches live). General Blender metadata; bb_*/_RNA_UI internals excluded.
- **U3 — `pose_bone` translates + accumulates.** `loc` alongside `rot` (both now
  optional; ≥1 required) to drive IK controls, and `additive=True` to nudge one
  axis without re-deriving the pose. Rotation-only callers unchanged.
- **U6 — non-mesh `describe` vocabulary.** Armatures report a bone summary + what
  they deform; empties report their display type + what references them; lattices
  report what they deform — instead of the useless "no material".
- **U9 — constraints/drivers visible.** `list_constraints(name, bone=)` lists
  constraints (type + target/subtarget + influence + mute) on an object or pose
  bone, plus object-level drivers — the BlenRig control graph `pose_bone` could
  otherwise silently fight. (All four read tools are NON_UNDOABLE; get_bone_tree
  is NO_STATUS like get_scene_tree.)

## Batch 3 — evaluated/posed-bounds primitive (T6, T2), 2026-06-11

New `common.eval_world_bbox` / `eval_world_center` — evaluated (modifier- AND
pose-aware) bounds computed from the evaluated mesh verts, so they're reliable
even when `obj.bound_box` lags (its display bounds are pose-aware in 5.1 but only
after a depsgraph update — which is what made describe look "rest" live). e2e in
`tests/e2e_batch3.py` (12 checks).

- **T6 — `describe(name, posed=True)`** reports the evaluated geometry's
  bounds/dimensions plus `posed_center_offset_mm` = how far the deformed geometry
  center sits from the UNDEFORMED base-mesh center (the dead-reckoning the
  GUIDANCE warns about, in one call). `posed=False` is unchanged.
- **T2 — `set_camera_dof(focus_object=…)`** now focuses on the evaluated-geometry
  center, not Blender's focus-object tracking (which follows the rest origin — a
  posed part rides ~1m off it). It projects the evaluated center onto the camera's
  view axis to set `focus_distance` and clears `dof.focus_object`, so the focal
  plane sits on the posed geometry at call time.

## Batch 2 — material introspection (U5, T3), 2026-06-11

Both live in `common.material_summary` (read by `describe`/`get_object_info`) +
`describe`'s formatting. e2e in `tests/e2e_batch2.py` (17 checks).

- **U5 — node-graph materials no longer summarized as their stale defaults.**
  `material_summary` now checks each Principled socket's `is_linked`: a
  link-driven Base Color/Roughness/Metallic is reported as `*_driven: nodegraph`
  (describe prints `color=nodegraph-driven (summary unreliable)` / `rough=
  nodegraph`) instead of the meaningless default — so Spring's node-graph skin no
  longer reads "black". Emission is only reported when strength>0 AND the
  emission color is non-black, killing the false "glow=1.0" off the Principled
  default (black emission renders nothing).
- **T3 — tint is read back from the live node, not echoed from a stored dict.**
  When Base Color is driven by `set_textured_material`'s diffuse→MULTIPLY(B=tint)
  graph, `material_summary` reads the mix node's B socket and reports
  `base_color_tint`; describe renders `texture(cotton_jersey@1k
  tint=[0.45,0.33,0.2])`. Reading the socket (not the `bb_texture` write-time
  record) means a later hand-edit of the tint is reflected — the honest
  instrument the authoring session asked for. `base_color` overrides already set
  the BSDF socket directly, so they were and remain reported verbatim.

## Batch 1 — independent quick wins (T4, T7, T8, U11, S1b), 2026-06-11

Five self-contained gaps with no shared dependencies. e2e in
`tests/e2e_batch1.py` (24 checks); existing `tests/e2e_headless.py` still green.

- **T4 — viewport shading in the status block.** `get_blender_status` now reports
  `viewport: SOLID|MATERIAL|RENDERED|WIREFRAME` (first 3D viewport found via the
  window-manager; omitted in true headless), and `server/_core._status` prints a
  `viewport:` line. The agent can now catch "texturing while the user stares at
  gray SOLID blockout" at the first material call.
- **T7 — delete frees a hidden object's name.** Root cause confirmed: the old
  `bpy.ops.object.delete()` path only acts on selected objects, and a hidden
  cutter can't be selected — so it silently deleted nothing while reporting
  success. `delete_object` now removes via `bpy.data.objects.remove(obj,
  do_unlink=True)` (ignores visibility/selection) and asserts the name is gone,
  failing loudly otherwise. `_delete_collection` hardened the same way (hidden
  group members were the same latent bug).
- **T8 — boolean refuses to bake an empty result.** Before applying, the
  evaluated modifier mesh is vert-counted; a 0-vert result is refused — the
  modifier is left live and unapplied (base mesh intact), with a loud
  `empty_result`/`warning`, mirroring the existing apply-failure contract.
  Normal booleans (incl. interior-cutter cavities) apply unchanged.
- **U11 — history reset on manual file open.** New `state.reset_history_state()`
  (the four clears `new_scene` does inline), driven by a `@persistent`
  `load_post` handler registered in `extension/__init__`. A hand-opened file no
  longer leaves history/diff/undo bookkeeping describing a dead scene.
- **S1b — group expansion reports non-mesh members.** `resolve_targets` gained an
  opt-in `include_non_mesh` flag (default keeps mesh-only behaviour for the many
  transform/shading callers); `validate_scene` and `audit_asset` pass it so a
  group's curves/empties reach the `excluded_non_mesh` accounting instead of
  being dropped at expansion.

## Live-curve delivery gaps (S1–S2) — finishing the catapult rope, 2026-06-11

R4 made the beveled live curve a first-class deliverable (the rig-following
rope); these two close the gap between "the curve follows the rig" and "the
curve is a textured, exportable deliverable". e2e in `tests/e2e_curve_delivery.py`
(19 checks).

- **S1 — material tools accept any material-slot object, not just meshes.**
  `set_material`, `set_textured_material`, and `set_toon_material` now filter on
  `has_material_slots(obj)` (new `common.py` helper: `obj.data` carries a
  `materials` collection — MESH, CURVE, SURFACE, FONT, META) instead of
  `type == 'MESH'`. A beveled curve renders as a solid tube with ordinary slots,
  so it materializes directly — no more baking throwaway `spline_tube` stand-ins
  per pose to texture a rope. Extended to `set_toon_material` too (same
  assign-to-slots family; leaving it mesh-only would just be the same gap one
  tool over). `add_outline`/`remove_outline` stay mesh-only — they build an
  inverted-hull solidify shell, which is genuine mesh geometry, not a slot
  assignment. **S1b:** `audit_asset` and `validate_scene` genuinely can't lint a
  curve (no faces), but they no longer *silently* drop them — both return
  `excluded_non_mesh` and the server prints "(skipped N non-mesh: …)", per the
  no-silent-caps principle.
- **S2 — `convert_to_mesh(name)` bakes a live curve into a real mesh.** New
  general verb (Object > Convert > Mesh) in `finishes.py`. `bpy.ops.object.convert(target='MESH')`
  evaluates the FULL result — modifiers, the curve's bevel, AND the hooks — in
  one call, so the R4 following-rope delivery is now a single
  `convert_to_mesh("rope")` after posing (not apply-then-convert). Chose a
  dedicated verb over auto-converting inside `apply_modifiers`: silently changing
  an object's type would surprise callers and break "apply a hook but keep
  editing the spline". Verified headless: a posed, hooked, beveled POLY curve
  converts to a MESH whose baked verts keep the hook-deformed shape and then
  takes `set_textured_material` with no complaint. R4 delivery docstrings
  (server `add_curve`, extension `add_curve`) updated to point at it.

## Siege-catapult rigging gaps (R1–R5) — mechanical-prop rigging, 2026-06-11

Rigid-assembly rigging + set-dressing. Armature work in `extension/armature.py`,
the following rope on `add_curve` (`extension/curves.py`), exclusion zone on
`scatter_on_surface` (`extension/scatter.py`); all mirrored server-side. e2e in
`tests/e2e_rigging.py` (25 checks).

- **R1 — `weight_to_bone(mesh, armature, bone)`** — rigid bind: 100% weight on
  every vertex to ONE bone, strips this armature's other deform groups so the
  bone is the sole influence, creates/reuses the Armature modifier. The
  deterministic alternative to `auto_weight`'s heat solve for hard-surface parts
  (wheels, doors, levers, throwing arms). Added an `armature` param the gap's
  `(mesh, bone)` shorthand omitted — a bone name alone can't say which armature
  owns the modifier. Verified headless: posing the bone deforms the bound mesh.
- **R2 — `auto_weight` coverage verdict** — now reports `weighted/total` and
  clusters orphaned (unweighted) verts into connected islands by mesh edges,
  located by region word: `96/128 weighted — 32 orphaned in 2 islands: 18 verts
  top-front, 14 verts bottom-back`. WARNs like the zero-weight case and points at
  `weight_to_bone` for rigid parts. (`_orphan_islands` unit-tested directly,
  since the heat solve won't deterministically orphan a simple test mesh.)
- **R3 — `deform: false` bone flag** — `create_armature` bone spec accepts
  `"deform": false` → `edit_bone.use_deform`, excluding root/control bones from
  the heat solve. Replaces the bury-the-bone-below-the-floor hack. Result lists
  `non_deform_bones`.
- **R4 — anchored following curve** — landed on `add_curve` (not `spline_tube`):
  a baked mesh can only drag its endpoint vertex rings (shear/tear), so the tube
  must stay a LIVE curve whose spline re-solves between hooked control points.
  Any control point can carry `"anchor": {"object": "winch_drum"}` or
  `{"bone": "rig/arm_swing"}` → a Hook modifier; the curve follows when the
  target moves/poses (rope, cable, hose, chain). Per-point (not endpoint-only) so
  a sag midpoint can stay in world space. `spline_tube` keeps its pure
  bake-to-mesh contract. Traps handled: hook captures the point in the bone's
  REST space (anchor in rest pose), and add_curve's identity object transform
  makes `matrix_inverse = target_world⁻¹` the correct no-jump bind. Delivery:
  pose the rig, then `apply_modifiers` to bake the curve to a game-ready mesh.
- **R5 — `scatter_on_surface` exclusion zone** — `avoid` (object/collection) +
  `avoid_margin` rejection-samples instances out of the avoid's world XY
  footprint; instances that can't clear it after 20 tries are dropped and
  reported. Set-dressing around a hero asset in one call.

## Pocket-watch gaps + tactile introspection (P1–P12)

Manipulation (`relational.py`, `transforms.py`) and two new analysis modules
(`extension/lint.py`, `extension/introspect.py`, mirrored server-side). All
read-only tools are in `NON_UNDOABLE_TOOLS`; e2e in `tests/e2e_introspect.py`.

- **P1 — `array_radial`** — circular/arc duplication around a center (point or object), optional `align_to_tangent`. Full 360 span = no overlapping seam (`step=span/count`); any other span = arc, inclusive of both ends. Built with `matrix_world` composition so orientation rides the orbit only when tangent-aligned. Clock markers, bolt circles, gear teeth, chain links on an arc.
- **P2 — `rotate_object(pivot=…)`** — optional `pivot=[x,y,z]` / `pivot="<object>"`. Rigid `T(pivot)·R·T(−pivot)·matrix_world` swing (position + orientation) for clock hands about the dial, a door about its hinge. No pivot → unchanged own-origin spin.
- **P3 — `find_coplanar_overlaps(targets?, epsilon)`** — collapses each object's axis-aligned faces into merged "panels" (axis, outward-sign, plane-coord) and reports cross-object coplanar panels overlapping in-plane, with overlap size in mm. Same-sign requirement avoids flagging legitimate flush stacking. Also reused inside P5.
- **P4 — `check_contacts(targets?)`** — per part: connected / floating(gap mm) / penetrating(depth mm) vs its nearest neighbour. Gap from BVH nearest-vert; penetration from all-axis bbox overlap (robust for matched footprints where vertex-inside tests fail). Reports facts, no judgement.
- **P5 — `validate_scene(targets?)`** — compiler-style lint: cross-object z-fights (P3), likely-inverted normals (centroid-facing heuristic), zero-area faces, objects below the floor. "PASS" or one finding per line. (Authoring-time lint-on-write left for later; standalone tool shipped.)
- **P6 — `check_mesh(target)`** — non-manifold edges, self-intersections (BVH self-overlap minus shared-vert adjacency), zero-area faces, thinnest wall (inward ray "pinch test"). **Deviation from the original note:** Blender 5.1 does *not* bundle the 3D-Print Toolbox (it moved to the extensions platform in 4.2+ and isn't installed), so the metrics are computed directly with bmesh+BVH — no add-on dependency, more robust.
- **P7 — `trace_profile(target, axis, sections)`** — per-section radius + centre drift, plus a feature narrative (rise / taper / flat / crease / bulge with mm-over-trend). Object-mode, evaluated geometry. Needs ≥3 populated sections (cones with only base+apex verts are correctly rejected).
- **P8 — `check_symmetry`** now dual-level + server-exposed. Single mesh → mesh-level BVH mirror-deviation (max/mean mm + worst region); multiple/collection → the existing object-pairing logic. Defaults: 0.5mm mesh, 10mm object.
- **P9 — `check_framing(targets?, camera?)`** — frame coverage %, clipped edges (+ overflow %), behind-camera, and % occluded by other objects (scene ray casts from the camera). Pure matrix math + raycasts; the deterministic answer to "is it still cropped?".
- **P10 — `check_resting(targets?)`** — support (floor or object below), contact-point count, float/sink mm, and whether the COM sits over the contact footprint (else tip direction).
- **P11 — `diff_since(checkpoint?)`** — narrates added/deleted and per-object moved(mm)/rotated(deg)/scaled/deformed(max mm + where). Backed by a cheap per-op geometry snapshot in `state.log_operation` (loc/rot/scale + a capped *local* vertex sample, so rigid motion and real deformation are told apart). Defaults to the first recorded op.
- **P12 — `audit_asset(group, tri_budget)`** — missing material slots, tri counts (with on-screen coverage % when a camera exists, to flag overbuilt parts), unapplied scale/rotation, loose verts.


- **Live-session undo (E1-residual)** — `bpy.ops.ed.undo` was a no-op in the live socket→timer context. Root cause: `temp_override(window=wins[0])` REPLACES the context with only the window, dropping the screen/area the global-undo operator resolves against, so it ran as a silent no-op. (Headless passed because with no windows it took the bare `bpy.ops.ed.undo()` path.) Fix: `state.ui_override()` builds a full VIEW_3D context (window + screen + area + region), used by both `_step_op` (history.py) and `push_undo_step` (state.py); returns None in headless so that path is unchanged. Verified live: `undo(2)` / `redo(2)` actually revert/replay with `✓ scene verified against history snapshot` and no POST-UNDO MISMATCH. Headless e2e still green (no regression).
- **`new_scene(empty=False)`** — File → New → General in one call. Wraps `bpy.ops.wm.read_homefile(app_template="")` (resets world / color-management / render settings with it), clears the history bookkeeping, and re-registers the persistent queue timer defensively. `empty=True` additionally wipes the startup cube/camera/light for a bare modelling slate. The daemon socket thread + `persistent=True` timer both survive the reload, so no full re-arm was needed. Replaces the `open_design("_empty_general")` workaround. Verified live + e2e.

- **E4** — `boolean(target, cutter, op, solver, apply, hide_cutter)` MCP wrapper. Keyholes, mortises, split-lid chests, half-barrels.
- **E5** — `band_around(name, targets, axis, at, width, thickness)`: a strap/hoop/belt following the convex-hull silhouette of the combined targets (bridges gaps between parts).
- **E6** — `set_material(hex="#RRGGBB")`: sRGB → scene-linear so reference colors render true.
- **E7** — `orbit_viewport(auto_frame=True)`: aim at the selection/scene bbox and pull back to fit — one-call three-quarter hero shot.
- **E8** — `taper_end` warns when the extreme ring is a bevel sliver (< 2% of the axis extent) and points at `taper_section`.
- **E9** — primitive `rot_*` docstrings corrected: placement resolves against the post-rotation bounding box.
- **E10** — `set_color_management(view_transform, look, exposure, gamma)`; current values in `get_blender_status` under `render:`. `set_toon_material` recommends `Standard`.
- **E11** — `set_render_quality(raytracing, ao, shadows, samples)` toggles the Eevee features off by default (metals reflect instead of looking plastic).
- **duplicate_mirrored** — bake a static mirrored copy across a world axis (normals recalculated, transform applied).
- **Render to file** — `render_to_file(filepath, resolution, samples, engine, format, transparent)`; per-call `timeout` threaded through the socket protocol so long renders aren't cut at 30s. (Synchronous — the viewport freezes during the render.)
- **Curve datablocks** — `add_curve(name, points, type, cyclic, resolution, bevel_depth)`: live Bézier/NURBS/POLY curve objects (dolly paths, bevel profiles).
- **Sculpt brushes** — semantic sculpt verbs (`sculpt_draw/inflate/grab/smooth/pinch/flatten/crease`) already shipped.
- **Armature + rigging (Tier C beachhead)** — `create_armature(name, bones)` builds a skeleton from named head/tail joints + parenting; `auto_weight(mesh, armature)` binds with automatic weights (warns if weighting comes back empty); `pose_bone(armature, bone, rot)` articulates a joint. End-to-end deform verified.

---

# Long-term (character quality finish line)

- Rigify control-rig generation (the generic armature layer is in; this adds IK/FK controls on top)
- Multires + dyntopo wrappers
- Retopology — auto-retopo or guided
- UV unwrap with seam control
- Material node graph beyond Principled BSDF
- Hair card system
- Face topology: eyes/nose/mouth loops with subsurf-correct flow
- Camera path animation (Follow Path constraint + keyframed eval over `add_curve` paths)

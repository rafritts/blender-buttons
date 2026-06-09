# Tools Notes — caveats, gotchas, known-shaky tools

Companion to the tool docstrings. Tools listed here have non-obvious failure
modes that the inline help can't fully convey. Read before reaching for them.

---

## `boolean` — SHAKY ⚠

Boolean ops (DIFFERENCE / UNION / INTERSECT) wrap Blender's Boolean modifier.
Conceptually simple, but they sit on top of a CSG solver that is famously
sensitive to mesh quality.

### Failure modes you will hit

- **Non-manifold geometry** — any open edge, T-junction, or interior face on
  either mesh can cause the EXACT solver to either error out on apply, or
  produce visually-fine geometry that has holes / inverted normals / duplicate
  faces. Common with hand-built blockout meshes.
- **Overlapping coplanar faces** — if `target` and `cutter` share a face exactly
  flush, the solver has to decide which side wins. EXACT usually handles it;
  FAST often produces z-fighting artefacts.
- **Un-applied non-uniform scale** — a cutter scaled to `(1, 0.5, 1)` in object
  mode behaves differently than one whose scale has been baked into mesh data.
  Always `apply_transform(scale=True)` on both meshes before booleans.
- **Tiny / coincident vertices** — verts within ~1e-5 of each other can crash
  the solver. Run `merge_by_distance(threshold=1e-4)` on both meshes first.

### How to use it safely

1. `apply_transform(targets="target,cutter", scale=True)` — bake scale.
2. `merge_by_distance(threshold=1e-4)` on both meshes — kill duplicate verts.
3. `boolean(target, cutter, op="DIFFERENCE", apply=False)` — keep modifier live first.
4. Visually inspect (`get_viewport_screenshot`, `get_viewport_collage`).
5. If it looks right, re-run with `apply=True` to bake.

If apply fails, the tool leaves the modifier on the target and returns an
`apply_error` field. Inspect with `list_modifiers`, fix the input meshes,
`remove_modifier`, and retry.

### EXACT vs FAST

- **EXACT** (default): correct on tricky topology, slower. Use it.
- **FAST**: legacy solver. Faster on simple meshes but produces bad output on
  anything with coincident geometry. Only fall back to it if EXACT errors out
  on apply and you're sure the geometry is clean.

---

## `check_symmetry` — object-level only

This is **object-level** symmetry, not mesh-level. It pairs whole objects whose
bbox centres mirror across the plane and whose dimensions match. It will NOT
catch:

- A single mesh whose vertices are not symmetric (use Blender's built-in
  `mesh.symmetry_snap` or visual inspection for that).
- Asymmetry within a paired object (e.g. a slide with serrations on one face
  only is a single mesh — check_symmetry sees it as "the slide pairs with
  itself if it spans the plane").
- Material / shading asymmetry.

Good for: "are all the matching parts present and roughly positioned right?"
Bad for: "is this mesh truly mirror-symmetric down to the vertex?"

The default tolerance (0.01 m) is forgiving. Tighten it (`tolerance=0.001`) when
you want to catch sub-centimetre placement drift.

---

## `set_origin` — applies operator `origin_set`

The operator runs on each target sequentially. It briefly mutates the 3D
cursor for the face-centre modes (`bottom`, `top`, `front`, `back`, `left`,
`right`) and restores it after. If the call is interrupted mid-loop, the
cursor may be left at the last computed face centre. Not destructive.

Geometry does not move in world space — only the local-space pivot does.
After this, `obj.location` will change to reflect the new origin position;
this is expected, not a bug.

---

## `get_object_info` — `tilt_off_vertical_deg` & `yaw_deg`

- `tilt_off_vertical_deg` is the angle between the object's local +Z and world
  +Z. 0° = upright, 90° = on its side, 180° = upside-down.
- `yaw_deg` is the rotation of local +X projected onto world XY, measured CCW
  from world +X. `null` when the object's local +X is (near) vertical — yaw is
  geometrically undefined in that pose.
- `orientation` is a human-readable summary derived from both. Read this first;
  drop to the numbers when you need precision.

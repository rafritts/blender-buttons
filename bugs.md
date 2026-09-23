# bugs.md — repo defects & open-source readiness

Unlike `gaps.md` (tool-surface friction found while modeling), this file tracks defects
in the repo itself — docs, packaging, tests, hygiene, and implementation that violates
an existing contract. Numbered **B#**, stable, delete when fixed.

_Seeded 2026-07-09 by an open-source-readiness audit. Shipped, fixed, or retired bugs
are deleted, not archived — use `git log -- bugs.md` / `git blame` to see anything
past. B-numbers are stable and never reused._

---

## B14 — `modifier op=modify` writes Subsurf `levels` as a float

`_MODIFIER_PROPS` maps `levels` to `float` and `render_levels` to `int`. Blender 5's `SubsurfModifier.levels` is an int. `setattr(mod, "levels", float(val))` raises `TypeError: expected an int type, not float`. The add path assigns the value it was given, so `modifier op=add type=SUBSURF levels=2` works when the number arrives as an int; `modify` cannot change it afterward.

**Friction (donut v5, 2026-09-23):** `modifier op=modify target=Mug modifier_name=Subsurf levels=1 render_levels=1` failed with that TypeError. Workaround: remove the modifier and `add` it again.

Fix: coerce `levels` with `int`, same as `render_levels`.

## B15 — `camera_dof focus_object=` stores a distance and says it bound the object

`set_camera_dof` projects the evaluated center onto the lens axis, sets `dof.focus_distance`, and sets `dof.focus_object = None` (deliberate: Blender's tracker follows the rest origin, gaps.md T2). The receipt still reports `focus_object=Donut`. `view op=rig` moves the camera and does not recompute the distance. Nothing in the status block says the focal plane is stale.

**Friction (donut v5, 2026-09-23):** DOF was set on Donut at distance 0.4605, then the camera was rigged out to 0.66 m. The next render was sharp on empty air in front of the subject. Calling `camera_dof` again updated the distance to 0.6956. The agent had treated `focus_object=Donut` as a live binding.

Fix: either recompute that distance inside `view op=rig` when a focus target was named, or stop reporting `focus_object` once the implementation has cleared it — report the frozen distance and the target name as a snapshot ("focused on Donut at 0.4605 m at this camera; not tracking").

## B16 — `select_ring` then `edit op=grab` in script moved every vertex

`select_ring` assigns the ring, then calls `bm.select_flush_mode()`, and returns `verts_in_ring` from the ring bucket — not the selection count after the flush. A following `edit op=grab` moves whatever is selected.

**Friction (donut v5, 2026-09-23):** an exec on the spun plate did `call("select_ring", index=6)` then `edit(op="grab", up=0.0055)`, and the same for two more rings. The plate's world bbox translated rigidly by the sum of those deltas (z `[0.0002, 0.016]` → `[0.0108, 0.0266]`, height unchanged) and the clip into the donut climbed 4.7 → 9.7 mm while each step reported ok. Undo of the grabs restored the foot. The same select-then-grab pattern earlier in the session, on the mug cage before Solidify, moved only the named rings. The plate had just been spun (`spin` ends in `mesh.select_all`) and was carrying Solidify + Subsurf.

Fix: after `select_flush_mode()`, return the selection count that the next op will actually move, and fail the grab (or the select) when that count is the whole mesh and the request was one ring. `select_flush_mode` in face mode re-derives verts from faces and can put the pre-flush ring selection back to "everything that was selected before."

## B17 — `rest_on` seated the plate 1.2 mm through the table

`rest_on` casts from the source's full evaluated verts onto the target BVH and moves by the minimum signed clearance (G108, G123). Offset was 0. The table top was at z=0.

**Friction (donut v5, 2026-09-23):** `transform op=rest_on targets=Plate target=Table offset=0` reported `Plate↓1.6mm`. Bounds went from z `[0.0004, 0.0162]` to `[-0.0012, 0.0146]`, and the floor said the plate dips 1.2 mm below z=0. The lowest point of a mesh dropped onto a surface at z=0 should land on z=0. Workaround: nudge back up by the penetration the floor reported.

Fix: the clearance that wins must be the source's lowest vert that actually hits the surface, and the post-move evaluated `zmin` along the axis should be checked against the hit. A seat that finishes below the surface is a failed `rest_on`, not a success with a later floor warning.


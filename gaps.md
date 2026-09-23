# MCP gaps

> **This file is a live worklist of CURRENT, OPEN gaps only.** No history lives here.
> Shipped, fixed, or retired gaps are **deleted, not archived** — use `git log -- gaps.md`
> / `git blame` to see anything past. No changelogs, no "what we shipped," no "considered
> and declined." When a gap is closed, **delete its entry**. G-numbers are **stable and
> never reused** — a missing number just means that gap was retired.

## North star

The agent's vision can **judge** but cannot **measure**; it reasons over outlines,
profiles, scalars, and named regions — never coordinate dumps. The server's job is to let
it stay in **intent-space** ("wrap the grip", "seat the bulb", "rest it on the desk") and
hand back **legible ground truth** instead of making it dead-reckon coordinates. Every gap
below is a place the agent was forced out of intent-space — into hand-trig, a self-managed
mode, or a number it couldn't trust. A gap is a general Blender primitive, never a
task-specific shortcut.

---

## G236 — `below_floor` is "any geometry under z=0", and it cannot be declared

**Verb:** the validate floor (`below_floor`), intent-free.

**Friction (donut v5 live session, 2026-09-23):** a table whose *top* sits on z=0 is 22 mm thick, so its body is under the plane. From that op on, every receipt opened with `Table dips 22.0mm below z=0`. Parked prototypes (moved out of frame, under the floor) joined the list. `validate op=expect` has `clipping`, `open_boundary`, and `self_intersection` — not `below_floor`. New clips had to be read out of the tail of a line the agent had learned to skim. A script that `add`s a centered primitive also dies on the add step (`Sprinkle_r dips 4.1mm below z=0`) before the next line can move it, so add-then-place is not a legal exec.

**Why it's a gap:** a ground body has to occupy z<0. The check conflates "this object fell through the world" with "this mesh has thickness under the plane." There is no intent to declare, so the finding is permanent and the floor stops being a signal.

**Fix direction:** either treat below-floor as declareable (`expect check=below_floor` for a named ground / scrap), or flag an object only when its *seat* is unsupported — not whenever `zmin<0`. A centered primitive's add must not be an intent-free abort if the next step in the same script places it.

## G237 — the status block never shows the modifier stack, or which mesh the dims are

**Verb:** the status block on every op.

**Friction (donut v5, 2026-09-23):** dims jumped when Solidify or Subsurf was added, so they were the evaluated mesh, but the block never said so and never listed the stack. Cage vs evaluated is the state that actually bites (`rest_on` and `feel` disagree about which surface you just measured; a self-intersection can exist only on the evaluated result). Reading it took `modifier op=list`, a second call, every time the stack changed. The block also returns `mode: OBJECT` and `selected: ['Name']` after an edit-mode op whose real selection was the `sel:` line above it — that component selection is not repeated on the next call.

**Why it's a gap:** the block is the paragraph the agent is supposed to carry instead of Blender's state machine. The stack and the selection domain are the two facts that change what the numbers mean, and both are left for the agent to remember.

**Fix direction:** one line on the block: modifier stack in evaluation order, and whether `dims`/`bounds` are evaluated. When an edit-mode selection is live on the mesh, repeat its `sel:` summary even though the mode left behind is OBJECT.

## G238 — `material op=set` stops before subsurface and coat

**Verb:** `material op=set`.

**Friction (donut v5, 2026-09-23):** dough subsurface weight/radius/scale and a glaze coat are ordinary Principled sockets. `set` exposes base color, metallic, roughness, ior, alpha, transmission, emission. The rest was a `bpy` node walk (`via_bpy: yes` on the receipt). The render was the only check that the sockets landed.

**Why it's a gap:** "this clay transmits, this glaze has a coat" is intent. The verb already writes Principled inputs; the missing ones are the ones a shaded still actually needs, so the agent leaves the surface for the node tree.

**Fix direction:** add `subsurface_weight`, `subsurface_radius`, `subsurface_scale`, `coat_weight`, `coat_roughness` to `set`, written to whichever Principled socket name the attached Blender has. Skip silently-missing sockets only with a reported skip, not a success that didn't set them.

## G239 — a searched Poly Haven texture cannot be applied

**Verb:** `material op=search_textures` / `op=image`.

**Friction (donut v5, 2026-09-23):** `search_textures` returned `wood_table_worn`. The download helper exists in `server/polyhaven.py` (`ensure_texture_maps` → diffuse, roughness, normal). No verb takes that id. `op=image` binds one file to Base Color or Emission. Wiring roughness and normal was a hand-built node graph in `bpy`.

**Why it's a gap:** the search advertises a library the agent cannot use. "This object wears that texture" is one intent; the agent currently does the node graph, which is the coordinate-authoring of shading.

**Fix direction:** `material op=texture id=wood_table_worn` (or `image` growing a `maps=` form) downloads via the existing helper and wires diffuse, roughness, and normal with box projection. One call, one material. Resolution and a scale dial are enough.


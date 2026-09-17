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

## G232 — boolean UNION reports success when the operands never fused

**Verb:** `edit op=boolean bool_op=UNION`.

**Friction (Strat live session, 2026-09-17):** a closed cutter whose bbox overlapped the host but whose volume sat in a cutaway void "UNION"ed successfully. The host bbox grew (the cutter's extent was absorbed into the object) and validate was clean. `feel topology` then said **2 shells**. The agent built on a merge that had not merged.

**Why it's a gap:** "fuse these two masses" is the intent. A success receipt whose only check is "the op ran" lets a non-intersecting UNION look like a one-body result — the agent leaves intent-space to run a topology read it shouldn't need. T8 already refuses a 0-vert bake; the cousin is a *non-empty* bake that did not fuse.

**Fix direction:** after an applied UNION, narrate shell count (and bbox-vs-operand). If the result still has N>1 shells, flag it — `success` with `unfused: 2 shells` (or refuse). Same class as T8: the receipt has to say whether the boolean *did the thing*.

## G233 — applied boolean hides the cutter instead of consuming it

**Verb:** `edit op=boolean` (baked). `hide_cutter=True` by default.

**Friction (Strat live session, 2026-09-17):** every UNION/DIFFERENCE baked (`apply` on the edit verb defaults True — the param is shared with `bend`) and hid the cutter. Hidden objects stay in the name namespace: `scene op=tree` lists them, `rename` to the cutter's old name mints `.001`, a later `object op=delete` without `name=` hits the viewport-active host. Delete-by-name works (T7 — `objects.remove` ignores hide), but the agent has to know the ghosts exist and sweep them.

**Why it's a gap:** a *live* boolean modifier needs the cutter. A *baked* boolean has consumed it. Hide is Blender's modifier convention; for an agent, hidden ≠ gone — it is a claimed name that validate/tree/`parts_only` still have to reason about. The agent drops into outliner hygiene instead of the next part.

**Fix direction:** on successful apply, delete the cutter (or move it to a scrap collection that `scene op=tree parts_only` and name-lookup ignore). Keep hide for `apply=False` (live modifier). Do not leave a baked operand in the part namespace.

## G234 — silhouette `#` is edge occupancy, not a filled projection

**Verb:** `feel op=silhouette`.

**Friction (Strat live session, 2026-09-17):** a closed 45 mm slab (two unioned cylinders) rasterized as a hollow outline with interior `.` cells. The agent read cavities and spent the next cuts trying to "fix" holes that were never volumes. The docstring says edges are walked onto a grid of `'#' (filled) / '.' (empty)` — "filled" here means "an edge hit this cell," not "the projection covers this cell."

**Why it's a gap:** silhouette is the 2D shape read. A thin closed solid's *shape* is a disc; an edge-only raster is a ring. The map uses the same `#`/`.` alphabet as a filled occupancy, so the agent cannot tell "outline of a solid" from "there is a hole." Forced out of intent-space into a render to see the real silhouette.

**Fix direction:** flood-fill the projected outline (or rasterize faces, not just edges) so a closed slab reads as a filled disc; or label the map honestly as edge occupancy and keep a filled mode. The legend must not say "filled" for an edge hit.

## G235 — script exec has no `object` verb (`object` is the Python builtin)

**Verb:** `script op=exec` / the `buttons` DSL.

**Friction (Strat live session, 2026-09-17):** a 6-string duplicate loop called `object(op="duplicate", …)` and died `TypeError: object() takes no arguments` — Python's builtin, not the verb. The `Buttons` class binds `add`/`transform`/`edit`/`material`/`validate`/`feel`/`call`; it does not bind the object verb. Workaround: `call("duplicate_object", name=…, new_name=…)`. SPEC-23 says the runner speaks the same verb surface.

**Why it's a gap:** loops over duplicate/join/delete/rename are exactly the exec gear (frets, strings, pole copies). Forcing `call("duplicate_object")` is a second grammar the field manual said the runner would not invent. The agent either memorizes tool names or writes the loop in REPL.

**Fix direction:** inject the object verb under a name that isn't the builtin (`obj`, or a `Buttons.object` method). `object()` in exec should never mean `builtins.object`.

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

## G226 — Collection-instancing scatter: per-point variety is invisible until you know the magic input

**Verb:** `modifier op=add_asset asset="Scatter on Surface"` (and any GN instancer) fed a multi-prototype collection.

**Friction (blind donut run, 2026-07-11):** Scattering a 5-color sprinkle collection stacks **all five prototypes on every point** until the non-obvious `Pick Instance` input is flipped — the agent only found it by reading the input dump and guessing. The existing density-floor warning (1/m² floors to 0 emits on a 0.009 m² icing) fired and was genuinely helpful; instance-semantics gets no equivalent teaching.

**Why it's a gap:** the modifier's effective behavior (N overlapping copies per point) is visually wrong but numerically plausible; nothing on the surface says "collection sources need Pick Instance for one-random-per-point." Same class as the density warning the server already ships — the input dump knows the source is a collection and could say so.

**Fix direction:** when a GN instancer's source input is a collection and `Pick Instance` is off, attach the same style of advisory the density floor gets ("all K prototypes will stack per point; Pick Instance=True draws one at random").

## G227 — `validate` can't bless intended contact: self_intersection has no expect path

**Verb:** `validate` / `validate op=expect`.

**Friction (blind donut run, 2026-07-11):** Realized scatter instances seated *into* the icing (correct, intended nesting) tripped 2678 `self_intersection` findings. `expect` has declaration paths for open boundaries etc., but none for self-intersection, so a legitimately-overlapping assembly can't be declared and the floor stays noisy. The agent's workaround (un-realize the instances) happened to be right for other reasons, but the check drove it, not intent.

**Why it's a gap:** intended overlap is a normal end-state (parts pressed into parts, scattered instances bedded into a substrate). A verification floor that can't record "this contact is by design" forces either noise-blindness or geometry contortions — both exits from intent-space.

**Fix direction:** give `validate op=expect` a `check=self_intersection` declaration scoped like the others (object/pair/region + optional depth bound), mirroring how the icing↔donut contact is already declared and quieted.

## G228 — The teaching layer has a single point of failure: agents without resource readers never see guidance

**Verb:** the `guidance://llms` MCP resource (and `guidance://techniques/*`).

**Friction (blind donut run, 2026-07-11):** the modeling agent's harness exposed the blender-buttons *tools* but no MCP resource-read tool, so `guidance://llms` was unreachable; the whole run went in on schemas + training alone. It succeeded anyway — but the server's one deliberate teaching channel silently didn't exist for that client.

**Why it's a gap:** resources are optional in MCP clients; tools are the only surface every agent reliably gets. A guidance layer that only ships over resources reaches some agents and silently skips others — worse than a uniform surface either way.

**Fix direction:** expose the same guidance text through a read-only tool op (SENSE-class, substrate: it mutates nothing) — e.g. a `guide` op on an existing verb — with the resource kept as the secondary route. Verify a resource-less client can pull it.

## G229 — `add type=text` at small scale mints intent-free degenerates

**Verb:** `add type=text` (converted mesh).

**Friction (14" MBP live session, 2026-08-12):** keycap legends at ~2 mm cap height (`shft`, `caps`, `tab`, `;`, `,`, `.`, `F2`, `F12`) validated as zero-area faces (font counters collapsing). Those are intent-free — no `expect` path — and they rendered fine. Remesh made self-intersections. The only moves that unblocked later work were delete-the-labels or leave them and abandon `script` for REPL.

**Why it's a gap:** extruded type is a normal hard-surface primitive (legends, dials, maker's marks). At the scale those things actually live, the convert produces a mesh the floor will never accept. The agent is forced out of the verb (delete, bpy cleanup, or skip bulk) to letter a part.

**Fix direction:** make the converted mesh validate — dissolve/fill degenerate counters at convert time, or refuse/repair rather than emit a mesh that trips the floor. Do not add an `expect` for degenerates; the mesh has to be clean.

## G230 — no verb to put an image on a mesh

**Verb:** `material` (after SPEC-22 stripped `op=textured` / `op=pbr`). `uv op=unwrap` exists; nothing consumes the UV layer.

**Friction (14" MBP live session, 2026-08-12):** a display panel needs a packed image on emission (and usually UV, not box). The live `material` ops are PBR scalars only. The desktop landed via `script` + `bpy.data.images.load` + Principled `Emission Color`/`Base Color`, then a second bpy pass to set UVs from the panel's measured world X/Z because smart-unwrap on a tilted plane mapped the menu bar onto the hinge. The first apply vanished under the next script's undo. SPEC-15 then locked the world until `acknowledge`.

**Why it's a gap:** "this face is a screen / decal / label" is intent, not a node graph. UV unwrap without a material that reads UVs is inert (SPEC-18 already said so). Forcing bpy is the dump SPEC-23 exists to kill, and it is undo-fragile.

**Fix direction:** a thin `material` op that binds a packed image to a mesh (emission and/or base color; `space=uv|box`) without bringing back the retired PBR node-graph sugar. Pair with the existing unwrap. Provenance is a path or a packed image name, not a hand-wired tree.

## G231 — `script` abort treats pre-existing scene intent-free defects as introduced-by-step

**Verb:** `script` (`batch` / `exec`), `on_error=abort` (default).

**Friction (14" MBP live session, 2026-08-12):** after G229 legends existed, `script` phases that only touched `Key_*` (`select_by_axis` + `inset_faces`) aborted on `Lbl_lshift` / impossible topology and restored the whole phase. REPL on the same ops warned and continued. `validate=` was `touched`. SPEC-23 §5.6 says abort on intent-free defects **introduced by a step**; the runner fired on leftovers elsewhere in the scene.

**Why it's a gap:** progressive bulk is the gear for "I already know the next 12 insets." One earlier degenerate object (or a leftover z-fight) makes that gear unusable — every later phase transactional-restores — so the agent drops to one-op REPL or deletes the offending parts. The floor is right that degenerates are never OK; it is wrong to attribute a pre-existing one to the current step.

**Fix direction:** abort only on intent-free findings on the step's touched set, or on findings new versus the pre-script baseline — the §5.6 "introduced by a step" rule, implemented. Pre-existing scene defects stay in the final validate line (and the REPL warning) so they remain visible, not fatal to an unrelated batch.

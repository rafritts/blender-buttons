# SPEC-05 — The Verb Collapse (Blender-native verbs)

**Status:** v1 implemented — the 15-verb layer is built (`server/verbs/`) and the
137 flat tools are pruned from the MCP surface (one cutover, `main.py`). Verified
live: reads, a full add→transform→delete round-trip, relational placement, the
status block on every act-verb, and error paths. The four status-block
*improvements* below (declared mutation bit, verb-aware foregrounding, before/after
delta, generalized warning channel) are addon-side and **not yet built**.
**Date:** 2026-06-15
**Depends on:** `SPEC-04` (the topology sense — the already-built realization of `feel`)
**Supersedes:** `SPEC-01`, `SPEC-02`, `SPEC-03` — set aside. This spec replaces the
"few families + combinators + self-authored namespace" approach with a simpler, more
direct one: **one verb per Blender menu.**

## Goal

Collapse the **157 flat tools** into **~15 verbs, each one a Blender menu**. The current
surface is a landfill: every turn the model reloads ~157 schemas into context and must pick
one by matching intent against a flat list. Only the largest models reason around that. A
small Blender-native verb set removes the artificial bottleneck — not by making the model
smarter, but by leaning on Blender knowledge it already has from training, and by making
organization *mandatory* so the server can't sprawl again.

## The problem, precisely

A flat tool list taxes **selection** ("which of N tools applies?") on every single step, and
that cost never goes to zero while the surface is flat. 157 tools also means 157 schemas in
every `tools/list` payload — a per-turn context tax the model pays whether or not it acts.
The capability underneath is small: `bpy` is a handful of orthogonal concepts (create,
select, transform, modify, query) wearing 157 costumes. The count reflects *packaging*, not
irreducible capability.

## The principle: one verb per Blender menu

Each verb maps **1-to-1 to a Blender menu or mode**, using Blender's own verbage. The shape,
the operation, the option — all become **params**, never separate tools. `add(mesh="plane")`
and `add(image="reference")` are the same verb dispatching on Blender's own Add-menu taxonomy.

This is **not greenfield**. `add`, `extrude`, `bevel`, `loop_cut`, `select`, `modifier` are
terms the model already knows from Blender's docs and tutorials in its training. Leaning on
native verbage means the schema doesn't have to *teach* the concept — only specify the args.
The "schema bloat" the collapse trades for is mostly **recognition**, not net-new learning.

The taxonomy is **self-closing**: when the verb set is "the Blender menus," it can't drift
back up to 157 without Blender itself growing a new menu. `add` can never re-split into
`add_box` / `add_sphere`; the shape is a param. Organization stops being a discipline we have
to enforce and becomes a property of the structure.

## Two families

- **act** — the right-hand-menu world: create, select, transform, and modify scene / assets /
  meshes. The majority of Blender work. Each act-verb is a free-standing Blender menu.
- **feel** — *understanding* a mesh: its structure, not its bounding box. This is `SPEC-04`'s
  `get_topology` family, read-only. The blind sculptor touches the mesh through `feel`.

There is **no `inspect`**. An earlier draft had a second perception verb for "params, values,
option menus." It's dropped: reads are **verb-owned** (below), and scene-level state belongs
to `scene`. The only two perception concepts are *feel the shape* and *read a verb's own
state*.

## The verb set

≈ **15 verbs**, every one a Blender menu except `feel`.

| Verb | Blender menu / mode | Collapses (representative) |
|---|---|---|
| **add** | Add menu | `add_*` primitives, light, camera, curve |
| **object** | Object mode / menu | delete, duplicate, rename, join, group/ungroup, visibility, split, convert, custom props |
| **edit** | Edit mode / Mesh menu | extrude*, bevel, loop_cut, merge, delete_geom, mark_sharp, crease, boolean, bend, taper*, round, separate, trace/spline/band |
| **select** | Select menu | `select_*`, grow_selection, random_select |
| **transform** | transform (mode-agnostic) | nudge, resize, rotate, scale_*, snap_*, mirror, align, distribute, match_dim, move/scale_vertices |
| **modifier** | Modifier properties | add/apply/modify/move/remove/list modifier, convert_to_mesh |
| **material** | Material properties / shading | set_material / textured / toon, shade_flat/smooth, outline, hdri+texture search |
| **sculpt** | Sculpt mode | all `sculpt_*` brushes |
| **pose** | Pose mode / armature | create_armature, pose, weights, bind/rebind, shape_keys, bone reads |
| **scene** | Outliner + scene-level Properties | scene collection (tree), render settings, output, world, view layer |
| **view** | 3D Viewport View menu | orbit, viewport shading/angle/overlays, zoom, frame, camera-as-viewpoint, check_framing |
| **render** | Render menu | render_to_file, render/cycles/color quality |
| **history** | top **Edit** menu (Undo/Redo) | undo, redo, undo_to, get_history, diff_since |
| **file** | File menu | save/open/list design (`.blend` persistence) |
| **feel** | — (the sense; `SPEC-04`) | get_topology + measurements (distance/gap/align), symmetry, lint/check |

When the verb set closed, it closed on Blender's own menu bar — File, Edit, Add, Object, View,
Render — which is the strongest evidence the set is right, not invented.

## Surface shape: binary with subcommands

Not one god-tool, not 157 flat tools. Each verb is a **free-standing MCP tool** that dispatches
internally on a subcommand / option param — the **`docker <command> <subcommand> [flags]`**
shape. `docker` is one *binary*; its subcommands each carry their own flags. So here: ~15 MCP
tools, each with a real, readable schema the model sees up front, dispatching to the right
operation by argument.

**Discipline (the one real cost).** The collapse doesn't shrink complexity, it *relocates* it:
157 schemas become ~15 fat schemas with subcommand enums and conditional params. The win is
real (the model learns 15 verbs, not 157; `tools/list` shrinks ~10×), but each verb's schema
now carries what ~10 tools used to. The rule that keeps this from becoming a different landfill:
**keep each verb's args regular** — shared options across subcommands (like `docker`'s
`--format` / `--filter`), not a union of ten unrelated signatures. Lean on Blender training so
the schema specifies args, never re-teaches concepts.

## Auto mode-switching

Each verb **declares the Blender mode its operations require**, and the dispatcher enters that
mode automatically before running. The model never issues a mode switch and never fails for
forgetting one — **the verb *is* the mode context**.

| Verb | Enters |
|---|---|
| add, object, transform | Object Mode |
| edit, select (component) | Edit Mode |
| sculpt | Sculpt Mode |
| pose | Pose Mode |

## Reads are verb-owned

With no `inspect`, a read is a subcommand of the verb that owns the thing — `modifier list`,
`object info`, `scene` reads the collection tree. This is **more Blender-true**, not less: you
read a modifier in the same Properties tab where you edit it. `feel` is the one exception — it
owns mesh-structure perception across any object, because structure isn't owned by a single
act-verb.

## Boundaries (the rulings)

These were the only real forks; they are decided:

- **`scene` is scene-level only.** Blender's right side is two editors: the Outliner (scene
  tree) and the Properties editor. The Properties tabs split into **scene-level** (Render,
  Output, View Layer, World, Scene) and **per-object** (Modifier, Material, Constraints, Object
  Data). `scene` takes only the scene-level ones. Per-object tabs stay with `modifier` /
  `material` / `object` — otherwise `scene` swallows the verbs we just freed.
- **`transform` is free-standing**, not folded into `object` / `edit`. It works in both modes
  and is high-frequency; making it its own verb stops `object` and `edit` each duplicating
  move / rotate / scale.
- **`render` is free-standing**, not folded into `scene`. Blender has a top-level Render menu;
  "produce the image" is too central to bury under scene settings.
- **lint / check folds into `feel`.** `validate_scene`, `audit_asset`, `check_mesh / contacts /
  resting`, `find_coplanar_overlaps` don't match a Blender menu because they're ours. They're
  perception-of-correctness — feeling for defects — so they live in `feel`, keeping the rest of
  the set Blender-true.
- **measurements + symmetry fold into `feel`.** `distance_between`, `gap_between`, `is_aligned`,
  `check_symmetry` are geometric truth about the mesh, not reported metadata.

## The status block is a hard invariant

The block appended after every mutating call is **sacred**. It is the perception-after-action
loop — the blind sculptor feeling the result of every move, faithful ground truth
(depsgraph-updated, can't be gaslit) it can't get from a screenshot.

It is built addon-side in `extension/status.py:get_blender_status`, injected generically at
`extension/server.py` onto every mutating result (minus the `NO_STATUS_TOOLS` opt-out), and
formatted in `server/_core.py:_status`. It carries: mode; active object / type; selection;
**rotation-aware world dims + bounds**; rotation; `last_action` + history depth; render /
color-management settings; the user's **live viewport shading mode**; and in edit mode the
component mode, selected / total counts, selection z-range, and the **non-Basis shape-key
landmine** warning — plus the bind-invalidation warning channel.

> **Invariant: every act-verb call returns the status block, and the collapse drops not one
> field.** This is non-negotiable. `feel` and read-subcommands don't carry it — they *are*
> perception.

### Improvements the collapse unlocks (do these)

The collapse doesn't just preserve the block — it makes it better, because a ~15-verb
dispatcher knows more about what just ran than 157 anonymous tools did:

1. **Replace the name-blocklist with a declared mutation bit.** `NO_STATUS_TOOLS` is today a
   hand-maintained set of tool *names* — pure landfill risk (add a read tool, forget the set,
   get noise). Mutation is now structural: act-verbs emit, `feel` / reads don't. The opt-out
   becomes **one declared bit per verb** that can't drift as subcommands land.
2. **Verb-aware foregrounding.** The dispatcher knows which verb ran, so the block leads with
   the relevant facet: `edit` → the edit sub-block, `render` / `material` → the render line,
   `scene` → collection counts, `transform` → dims / bounds. Same data, surfaced by relevance
   instead of one fixed wall.
3. **Free before/after delta.** The dispatcher already wraps every act — snapshot pre + post
   and report *what changed* (`dims 0.5→0.7`, `+120 verts`). `diff_since` logic riding every
   act for free; an absolute snapshot becomes a change report, which is better feedback for a
   smaller model.
4. **Generalize the warning channel.** `bind_warning` / `shape_key_warning` are hand-injected
   today; give them a real home — a postcondition-warnings list any verb contributes to.

## What does NOT change

The collapse is almost entirely a **`server/`-side** change. The addon (`extension/`,
~11.8k lines vs the proxy's ~4.8k) dispatches **by tool name** into a handler dict; the real
`bmesh` / `bpy` work stays put. The new ~15 verbs route to the *same* `add_box` / `extrude` /
`loop_cut` handlers that exist today. **We collapse the interface, not the engine.**

## Open questions

- **Subcommand schema ergonomics** — how to express conditional params (the args valid for
  `add(mesh=…)` differ from `add(image=…)`) without a schema the model can't read. Per-verb
  discipline (regular shared options) is the lever; the exact JSON-Schema shape is unsettled.
- **Staging** — order of collapse. `feel` is effectively done (`SPEC-04`). The act-verbs can
  land one menu at a time behind the existing tools, then the flat tools retire per verb.
- **`asset` search placement** — `search_hdris` / `search_textures` sit under `material` here;
  if asset browsing grows (models, node groups) it may deserve its own File-menu-adjacent verb.

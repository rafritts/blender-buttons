# SPEC-09 — Selection as the construction anchor: no divined coordinates

_Status: Proposed 2026-06-17. Sourced from the navel place-by-hand exercise on Body —
and the divined-vs-measured thread that fell out of it (see gaps.md G47, G43, G38, and
the "dead-reckoning a feel probe" reflection). Builds directly on the existing handle
system (`extension/handles.py`, `feel op=handle`)._

## The problem

The **destructive** half of this MCP never dead-reckons: `feel structure` finds a
protrusion → `select op=limb` anchors to its base ring → `edit delete`. Zero coordinates;
the target is a real topological feature.

The **constructive** half still does. `sculpt(brush, at_x/y/z)` and the seed of a dimple
(`select op=in_sphere center_x/y/z`) take a raw world point on a smooth patch — the exact
thing an LLM cannot dead-reckon. This session proved it twice over:

- Placing a navel, I typed `z=1.02`, then "up 10cm" → `z=1.11`. Both wrong. The *measured*
  center of the abdomen region we shaped together was `z=1.063` — and the real navel sat
  there.
- Worse, **"feeling" itself degraded into dead reckoning** when the probe *location* was
  divined: I hunted the navel by typing guessed Z heights (0.93, 0.95, 1.0, 1.02), probing
  a small sphere at each, and walked straight past the real dimple at z≈1.06. Feel graded a
  guess instead of deriving an answer.

The maddening part: **the measured path already exists and I routed around it.** `feel
op=handle source=selection` mints a named anchor at the live selection's **centroid**, with
its surface **normal**, an intrinsic shape signature and extrinsic fiducials (so it
recomputes and rides deformation); and `sculpt`, `select op=in_sphere`, and `transform
op=move_to` all already accept `handle=`. I reached for the raw-coordinate params anyway —
because they sit at equal billing and are the path of least resistance. Guidance in
docstrings can't fix this (that's G9 — docstrings aren't reliably in context under deferred
loading); **only tool shape can.**

## The principle

> Every spatial parameter a construction verb takes — center, direction, radius, depth,
> axis, plane — must descend from a **selection or a handle**, never from a typed
> coordinate. A selection is not just a set of verts; it is a **bundle of measured
> affordances**, and the verbs should source from that bundle.

A selection (or the handle minted from it) is already measured — anchored to real
geometry, and (we proved) **robust**: the navel centroid landed on the feature whether the
region was trimmed precisely or not, where a divined coordinate missed entirely. A measured
anchor degrades gracefully; a guess is brittle.

## Phase 1 — target = selection | handle, never a raw coordinate

Point-addressed construction ops (`sculpt` brushes; any seed that today takes a center)
must take a **selection or a handle**. Demote `at_x/y/z` and `select`'s `center_x/y/z` to a
clearly-marked **ripcord** — present, awkwardly named, docstring leading with the anchor
alternative — exactly the demotion `move_to(x,y,z)` got versus `nudge`. Note the scope:
this is *only* point-seeded ops. Selection-operand ops (`extrude`, `bevel`, `inflate`,
`delete`, `subdivide`, `proportional_move`, `scale_verts`) already act on the selection and
are already non-divined — leave them.

## Phase 2 — the live selection IS an implicit, ephemeral handle

To stop Phase 1's requirement from becoming a tax that pushes me back to the ripcord, make
the **correct path the cheapest path**: if a selection is live, a point-op uses its
centroid + normal directly — no named object minted, no lifecycle, no cleanup (it lives
exactly as long as the selection, which Blender already manages). The selection + its
`sel_center` are already computed every call; this just *uses* what's there.

**One concept, two lifetimes:**
- **live-and-ephemeral** — the zero-ceremony default for one-shot acts.
- **named-and-persistent** — the reuse / deform-stable upgrade (`feel op=handle name=…`);
  also the recovery from a stray deselect (`select handle=abdomen` → back instantly).

Raw coordinates fall out of both.

**Required for both:** a patch centroid sits slightly *inside* the surface (a curved patch
bows inward; a loop's centroid is fully interior), so the anchor must carry **centroid +
normal + ray-snap-to-surface** — otherwise "sculpt at the selection" pokes from a point
floating behind the skin. This is the G47 ray-snap, needed on the implicit and named paths
alike.

## Phase 3 — selection-sourced parameters (close the re-typing leak)

Nearly every derived affordance already computes as a *read* — but a read that I must
copy out of a status block and re-type into the next call is where a measured value
degrades back into a hand-entered one (transcription, staleness; the G9 dead-end shape).
Wire verbs to **source a parameter directly from the selection**, from a **closed
vocabulary** of derived affordances:

| Affordance | Today's read | Replaces the divined… |
|---|---|---|
| **centroid** | `sel_center` | brush center |
| **apex / deepest vert** | `feel protrusion → apex_world` | "the tip / the pit" center |
| **normal** | handle avg normal | push/extrude direction (no more "is +Y inward?") |
| **frame** (principal axes) | `feel … method=frame` | orient axis (long/short axis of the feature) |
| **extent** (bbox w/h/d) | `sel_bounds` | brush **radius** ("over *this* footprint") |
| **boundary ring** | `select op=boundary` / `mint_boundary_handle` | bridge/snap/extrude target |

So `sculpt radius=from_selection`, `extrude direction=selection_normal`, etc. **Discipline:
keep it a closed set (~six things), not "derive any stat, pipe it anywhere"** — infinite
knobs are just a new way to get lost.

## Relationship to other gaps

- **Closes G47** — surface-relative placement *is* anchor (selection/handle) + offset +
  ray-snap-to-surface, returning the world point + normal.
- **Composes with G43** (region-coherent feature selection): a better region → a better
  anchor. Selecting the navel *as its rim-bounded feature* makes its centroid/normal
  truer than a coordinate sphere that cuts across the rings.
- **Composes with G38** (feature discovery): so the seed selection isn't itself guessed.
- **Gated by G48** (selection certifies localization, not capture): a measured anchor on a
  *mis-captured* region is still wrong — the centroid is robust enough to look right while the
  selection has clipped the feature (a thumb) or swept in its neighbour (a tricep) or taken the
  wrong *form* (a vertical "collarbone"). The bridge is only as good as the selection feeding it,
  so the anchor must carry a **capture verdict** (G48's perturbation-convergence + shape-vs-form
  checks), not just a point. Especially for the named/persistent path, where the handle's vgroup
  *is* the deform region — there, extent errors are not cosmetic.
- **Built on** the existing handle infra — this is largely *surfacing and defaulting* what
  `extension/handles.py` already does, plus the ray-snap and the parameter-sourcing wiring.

## The frame

This is the **constructive twin of the destructive bridge.** Destruction: `feel structure
→ select limb → delete`. Construction, after this SPEC: `feel/select region → (implicit or
named) anchor → sculpt/edit at the anchor, with parameters sourced from the selection`.
Same spirit — intent-space, measured, zero divined coordinates — finally extended to the
half of the tool that builds.

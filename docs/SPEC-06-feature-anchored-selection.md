# SPEC-06 — Feature-anchored selection (the mesh as coordinate system)

**Status:** DRAFT / exploration. Nothing built. This is the deferred **#5** from
`SPEC-05` Addendum C, written up precisely so it survives. One design fork is still
open (bottom of file) and needs a decision before any code.
**Date opened:** 2026-06-15
**Depends on:** `SPEC-04` (the `feel` topology sense), `SPEC-05` (the verb collapse),
`GUIDANCE_FOR_LLMS.md` §"The one rule that explains everything else".

---

## The symptom that started it

Driving the live verb set to cut Spring's pullover sleeves off (tank-top task), the
sleeve was selected with `select(op="by_axis", axis="X", factor=0.683, comparison="GREATER")`
to grab everything past x≈0.16 (the armhole). After deleting the first sleeve, the
mesh's X-bounds shrank, so the **same intent** ("cut at the armhole, x≈0.16") now
required a **different** factor — `0.535`, not `0.683` — because `by_axis` normalizes
`factor` (0..1) against the mesh's **current** bounding box on that axis, and that
box changed under the edit.

Reuse the number, cut the wrong place. That instability is the surface defect.

## Why the obvious fix is WRONG

The tempting fix is "let me pass an absolute world coordinate instead of a 0..1
factor" — e.g. `by_axis(axis="X", at_world=0.16)`. **Rejected.** That is dead
reckoning wearing a different hat.

Per `GUIDANCE_FOR_LLMS.md` §the one rule: *coordinate math only survives in the
narrow regime where it was authored* — single object, centered at origin,
axis-aligned, every number self-authored moments ago. `x=0.16` is meaningful for a
2k-vert Spring pullover sitting at the origin. Drop the same cut into a hero asset
with the garment offset 400m out in a city scene, or a 2M-vert mesh, and `0.16` is
noise. Absolute-coordinate input is **stable the way a stopped clock is** — it gives
the same answer regardless of whether that answer is still right.

Both the shifting `factor` AND the proposed `at_world` are the same mistake: the
agent holding the coordinate system in its head. Wrong layer.

## The reframe (DECIDED): the mesh is the coordinate system

A sleeve is **not** a coordinate range. It is a **topological protrusion** — a tube
that branches off the torso and terminates in a boundary loop (the cuff). Stated
without any number:

> the sleeve = the region reachable from the **cuff boundary loop**, walking inward,
> stopping at the **armhole** (where the tube meets the body — a pinch / branch).

That sentence contains no coordinate. It means the same thing on a 2k-vert or
2M-vert mesh, at the origin or 400m out, before or after an edit. **That** is the
effortless, scale-free solution — not a better number.

Crucially, `feel` **already sees both anchors** and the agent threw them away:
- `feel(op="topology", method="boundaries")` enumerates the cuff as an open loop
  (6cm around, region "left"/"right"; grabbable vert path at high lod).
- `feel(op="profile")` (post-Addendum-C, aggregated) reports the **pinch** — the
  girth-minimum band between cuff and torso = the armhole.

The read already produces the structure. The gap is that `select` can only consume a
coordinate, so the structure gets flattened to a number on the way in. Close that:
let `select` consume the structure directly.

## Proposed primitives (NOT yet built)

Two layers, smallest first:

### 1. Separating-loop select (the core primitive)
`feel` returns a **grabbable loop handle** for the pinch (the same way
`topology boundaries` already returns vert-id paths). `select` consumes a loop and
takes one side:

```
select(op="across", loop=<handle>, side=SMALLER | LARGER | "+X" | …)
```

Partition the mesh by the loop into two connected regions; select the named side
(`SMALLER` = the protrusion, in the sleeve case). Pure topology — no coordinate.

### 2. `limb` (the sugar / one-shot)
```
select(op="limb", from=<cuff boundary handle>)
```
Flood-fill inward from a boundary loop, **auto-stop** at the first pinch/branch.
"Select the limb ending at the left cuff" → exactly the sleeve. This is the
effortless top-level call; it composes #1 internally.

### The intended read→act loop (no number anywhere)
```
feel topology boundaries     → cuff loops enumerated (left, right)
feel profile                 → pinch (armhole) located as a loop handle
select op=limb from=<left cuff>   (or: select op=across loop=<pinch> side=SMALLER)
edit delete                  → sleeve gone
```
The loop closes entirely in the mesh's own terms. The handle passes feel→select as a
structural reference (vert-id path / named landmark), never a world coordinate.

## What this is NOT

- Not "add `at_world` to `by_axis`." That's the rejected dead-reckoning fix.
- `by_axis` `factor` can stay as a quick relative convenience, but must be
  **documented honestly** as relative-to-live-bounds (it re-anchors as you edit), and
  de-emphasized for any multi-step edit sequence in favor of feature selection.
- Existing mesh-relative primitives (`select ring`/`rings`/`boundary`/`grow`/`shrink`)
  already lean this way; #5's gap is specifically "select a *region/limb* bounded by a
  feature loop," which none of them express.

## OPEN FORK — needs a decision before any code

**Where does the "stop" (the pinch/armhole) come from?**

- **(a) Geometric pinch** — the girth local-minimum along the flood-fill distance
  (built on Addendum-C profile aggregation). Dead general: works on organic meshes
  with no clean edge loops. But **fuzzy** — a baggy/folded sleeve can pinch in more
  than one place, and the minimum may not sit on a real edge loop.
- **(b) Topological branch** — detect where the tube's ring stops being a single
  clean loop (valence pattern / ring split where tube meets body). **Crisp and exact**
  on quad-flow garments, but **brittle** on messy/triangulated/non-manifold meshes.

**My lean (Claude, not yet ratified):** geometric-primary, topological-confirm — find
the pinch by girth, then snap it to the nearest real edge loop if one exists. Robust
default, exact when the topology cooperates.

**Decision owner:** Ryan. This choice drives the whole primitive (how `feel` reports
the handle, how `select op=limb` terminates). Waiting on the geometric-vs-topological
call before sketching an implementation.

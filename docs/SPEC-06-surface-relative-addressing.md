# SPEC-06 — Surface-relative addressing (gaps.md G1)

_Status: Phase 1 implemented 2026-06-16 (`feel op=aim`). Phases 2–3 proposed,
awaiting sign-off._

## The problem

The **destructive** half of this MCP has a clean perception→action bridge:
`feel structure` finds a protrusion → `select op=limb` anchors to it → `edit
delete`. **Zero coordinates** — the target is a real topological feature.

The **constructive / sculpt** half has none. `sculpt(brush, at_x/y/z, radius)`
demands a raw world point on a smooth, featureless patch — the exact thing an LLM
cannot dead-reckon. "Where a breast goes" has no loop, pole, or boundary to grab.

## The principle

Mirror the destructive bridge. Give construction a **perception primitive** that
turns an aim the agent _can_ reason about — *a framing in fractions of the form* —
into the world point + surface normal the action verbs need, **and hands that
coordinate back** so the agent learns it instead of inventing it.

No anatomy is baked in. "Cast onto the surface behind a normalized framing
coordinate" is a general operation on any mesh.

## The addressing model

A surface aim is **a face of the target's local bounding box + two normalized
coordinates on that face + a cast inward to the first surface hit.**

- `face` — which local bbox face to cast from, written as a signed axis:
  `-Y +Y -X +X -Z +Z`. `-Y` = stand on the −Y side, ray travels **+Y** into the
  volume. (Per-object semantics like "front" are the agent's to map — front was
  −Y for Spring; the tool stays axis-pure.)
- `u, v` — position on that face, each `0..1` over the **other two** local axes
  in ascending index order (X<Y<Z). For `face=-Y`: `u`→X, `v`→Z. For `face=-Z`:
  `u`→X, `v`→Y. 0 = min corner, 0.5 = centre, 1 = max corner.
- The cast: origin just outside the face at `(u,v)`, ray inward along the face
  axis, first hit on the **evaluated** (modifier/subsurf) surface = the answer.

Returns: **world hit point**, **world surface normal**, the cast axis, and the
push hint ("to pull OUT, move along +normal"). A miss is reported plainly (the
surface isn't behind that framing — try other `u/v` or face).

## Phases

### Phase 1 — `feel op=aim` (the resolver) — IMPLEMENTED
Read-only. `feel op=aim target=<mesh> face=-Y u=0.25 v=0.65` → world point +
normal. The agent then feeds the point to the existing coordinate verbs:
`sculpt … at_x/y/z=<point> radius=…` (push along the returned normal), or
`select op=in_sphere center=<point>`, or `add … on={"at":<point>}`.

Two calls, but the seam is the same as `feel structure` → `select`: perception
then action, with the coordinate surfaced in between. This is the keystone; it
makes every coordinate-hungry constructive verb reachable without dead-reckoning.

### Phase 2 — one-call convenience on `sculpt` (proposed)
Let `sculpt` accept `face/u/v` directly (in place of `at_x/y/z`), resolve
internally via the Phase 1 cast, and default the push direction to the surface
normal. Collapses the common case to one call. Same for a future `add … at_surface`.

### Phase 3 — normalized placement everywhere (proposed)
Extend the normalized frame to `move_verts`, drop-primitive placement, and an
absolute "set position/rotation to" (gaps.md G8 — `transform` is relative-only
today). The G1 frame and the G8 placement story are the same fix from two ends.

## Why a separate resolver, not baked into every verb (Phase 1 choice)

- It returns the coordinate — the agent _learns_ the point and can reason about /
  reuse / mirror it (matters for L/R symmetry work).
- It's one general primitive instead of N verb-signature changes.
- It's read-only and dogfoodable immediately; the verb integrations (Phase 2/3)
  layer on top without re-deriving the cast.

## To verify live (written without a running Blender)

`Object.ray_cast(origin, direction, distance)` returns `(hit, location, normal,
index)` in **object space** against the **evaluated** mesh. Confirm: it hits the
subsurfed surface (not the cage); normal points outward; the outside-the-face
origin + inward ray finds the near wall (not the far one). Tune the margin.

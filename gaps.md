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

## G84 — `material op=set` has no transmission; glass/gem/liquid is unreachable

`set` exposes `base_color, metallic, roughness, ior, alpha, emission`. There is no
**transmission** (nor transmission-roughness) control. `alpha` only drives blend-mode
see-through — a flat transparent *surface*, not a refractive *solid*. So any clear solid
(a watch crystal, a gemstone, a bottle, a lens, water) cannot be expressed: it will read
as a ghosted decal, never as glass that bends and catches light. `ior` is already there
and is meaningless without transmission to pair it with. This is the one material the
intent "make it glass" maps to, and the verb can't say it.
**Want:** `transmission` (0..1) + optional `transmission_roughness` on `material op=set`,
wired to the Principled BSDF transmission inputs (and auto-set the blend/refraction flags
the active engine needs so it actually refracts).

## G85 — edit-mode `sel_bounds` is wrong right after `extrude` (ground truth lies)

Inset a cap face (status correctly reports the inner face: `faces:1`, `sel_bounds` at the
inset radius). Then `edit op=extrude down=` that same face. The post-op edit status now
reports `faces:1` but `verts:192` (a single N-gon has N verts, not 2N) and `sel_bounds`
spanning the **full outer radius of the object**, not the extruded face's radius. The
whole method rests on "trust the status block over what you remember" — but here the very
next call's selection ground-truth is untrustworthy, and I only caught it by spending a
`feel op=section` to confirm the real form. A misreport in the instrument panel is worse
than no report.
**Want:** after `extrude`, `sel_bounds`/`sel_center`/vert count must describe exactly the
resulting selection (the moved face ring), the same way `inset` already does.

## G86 — no focal-length control on an existing camera

`view` can move (`camera_position`), focus (`camera_dof`), frame, and activate a camera,
but nothing sets its **lens/focal length** after creation. `add type=camera` takes `lens=`,
so the only way to get an 85 mm hero lens onto the scene's camera is to throw it away and
add a new one (then re-activate, re-DOF, re-frame). Focal length is the primary
storytelling dial of a shot (wide vs. compressed) and it's write-once-at-birth.
**Want:** a `view op=camera_lens` (or a `lens=` on `camera_position`) to retune focal
length on an existing camera.

## G87 — selection not reliably preserved across `transform op=move_verts` → `edit` (intermittent)

`select op=all` → `transform op=move_verts` → `edit op=taper_end`, issued one-per-message
(per the chaining rule). On one mesh the taper landed; on an identical sequence on the next
mesh the taper **no-op'd** (the no-op guard correctly flagged byte-identical geometry), and
re-issuing `select op=all` immediately before the taper fixed it. So the live edit-mode
selection appears not to survive a `move_verts` reliably — `move_verts` lives under the
`transform` verb but mutates verts in edit mode, and the following `edit` op sometimes sees
an empty/stale selection. The no-op detector is doing its job; the underlying
non-determinism is the gap — it forces a defensive re-select before every edit op that
follows a `move_verts`.
**Want:** edit-mode selection state to persist deterministically across consecutive
edit-mode mutations regardless of which verb (`transform` vs `edit`) issues them.


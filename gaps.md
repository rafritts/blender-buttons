# MCP gaps

_Rewritten 2026-06-16, from the first real body-sculpting session (building a
female torso onto the Spring rig — breasts from scratch, by feel + partnership).
The old contents (J-hatchets, I1 consolidation, H1/H2, F/G closed items) are in
git history if needed._

---

## The headline: the **constructive** half has no perception→action bridge

This is the one that matters; everything below is a facet of it.

The **destructive / structural** half of this MCP grew a clean perception→action
bridge and it works beautifully:

> `feel structure` finds a protrusion → `select op=limb` anchors to that
> topology → `edit delete`. **Zero coordinates.** It works because the target
> *is* a real topological feature (an open loop, a tube).

The **constructive / sculpt** half never grew that bridge. "Where a breast goes"
is a smooth, blank, featureless patch — no loop, no pole, no boundary to anchor
to. So `sculpt` falls back to raw world coordinates (`at_x/y/z`), which is the
**exact thing `feel` exists to cure** (LLMs cannot dead-reckon points in open 3D
space). `select op=limb` has no sculpt counterpart.

We *routed around* this in the session — and the workaround is the spec for the
fix (see "What worked"). But the gap itself is the project's next frontier.

---

## G1 — surface-relative / local-frame brush addressing  ⭐ the big one

`sculpt(brush, at_x/y/z, radius)` demands a world point on a featureless
surface. Make the brush (and every constructive verb) addressable in a
**normalized local frame** instead:

> "Cast from the **front** (−Y), at **65% up** the torso, **25% left** of
> center, radius **5cm**, pull out **2.5cm**."

Spec:
- A normalized addressing layer (`0..1` or `−1..1` per **local** axis, origin at
  the object) that any constructive verb accepts — sculpt brush, drop-primitive,
  `move_verts`, `in_sphere`.
- Optional **"cast to surface along an axis"**: the server raycasts the
  normalized aim onto the actual skin, applies the op at the hit point, **and
  returns the world point + surface normal it used** (so push direction is
  automatically correct, and the agent *learns* the coordinate instead of
  inventing it).
- Fully general — "hit the surface behind a normalized framing coordinate" works
  on any mesh. **No anatomy baked in** (per the general-tools rule).

This is the sculpt analog of `select op=limb` and the direct sibling of the
dimensions-over-coordinates thesis. Build it once → every constructive verb
stops demanding meters.

## G2 — `feel` cannot read **form** back, only the bounding box

After a form sculpt the agent is blind: a concave slope, a teardrop, a dome, a
splay are all invisible to an axis-aligned bbox. Today the **only** form-feedback
channel is the human pasting a screenshot.

- Proof it bites: I called a correct `duplicate_mirrored` "upright/reset" purely
  from its bbox dims, and was wrong — the mirror was fine (user confirmed by
  eye). I cannot read shape from a box.
- `feel op=profile` exists but dumps ~200 lines of near-zero per-ring deltas —
  noise, not a verdict.

Fix: `feel` should emit **short scalar form-verdicts** in the tactile-
introspection style — e.g. "upper slope: concave, 4mm deep", "projects 2.3cm
over a 5cm radius", "L/R symmetric to 0.1mm", local curvature sign. Closes the
agent's feedback loop *between strokes* so it isn't narrating by the user's eyes.

## G3 — no clean path to **sculptable resolution** in a region

The body cage has ~**12 verts / 5 faces** across a whole breast-sized patch —
far too coarse for a dome *and* a crisp root. Every good densification path is
blocked or unexposed:
- **Apply-Subsurf** (→ dense clay) and **dyntopo** (`subdivide=True`) are both
  blocked by the mere presence of shape keys (see G4).
- **Multires** isn't exposed as a modifier/sculpt target.
- `loop_cut` adds full torso loops, not *local* resolution.

Need a reliable "add sculptable resolution here" affordance: a multires wrapper,
or local subdivide-of-selection, or simply unblocking the above once G4 lands.

## G4 — no `delete` / `bake-to-basis` for shape keys

`pose` has `shape_keys` / `shape_key_set` / `shape_key_active` — but no
**delete**, and no **"flatten current mix into Basis."** A mesh derived from a
rigged source inherits its shape keys, which (a) silently capture edits into the
active non-basis key, and (b) block apply-Subsurf and dyntopo (G3). Today the
only fix is a manual hand-off to the human. Need both verbs server-side.

## G5 — no `shade_smooth` on the verb surface

Turning faceted shading to smooth is a one-click human op (`Object → Shade
Smooth`) with no reachable MCP equivalent — `edit smooth_edges` also bevels, so
it's not the same primitive. Want plain `object op=shade_smooth | shade_flat |
shade_auto_smooth` (a flat `shade_smooth` may still exist pre-collapse but isn't
surfaced through the `object`/`view` verbs).

## G6 — schema↔engine mismatches (small, but they cost a round trip each)

- `edit taper_section curve_shape`: docstring says `linear|smooth`; engine
  rejects `smooth` and wants `ease_in | ease_in_out | ease_out | linear |
  smoothstep`.
- `transform rotate pivot`: docstring lists `center|cursor|..`, but passing
  `pivot="center"` errors with `pivot object 'center' not found` — the string is
  treated as a `pivot_object` name. The pivot-**mode** path is unreachable; only
  the default works. (Blocked an in-place rotate mid-session.)

## G7 — shared selection / active-object / mode collides with the human

Blender has exactly **one** active object, **one** selection, **one** mode,
globally — and both the human's clicks and the MCP write them. This bit us three
times (a deleted selection, a cleared selection, an "enter Edit mode" landing on
the wrong object after a stray click).

- **Coexistence model worth documenting for drivers:** the **camera is
  conflict-free** (orbit/pan/zoom/shading never touch MCP state); **only
  selection + active + mode collide.**
- Server fix: ops that run on the *active* object implicitly (`object op=mode`,
  edit-mode selections) should accept an explicit `target`, so a click can't
  hijack them.
- Driver discipline (already adopted): address by name and **re-assert the
  target immediately before each step**; announce "hands-off the selection"
  during multi-step Edit-mode sequences.

## G8 — no absolute "move/rotate to", and the local-frame placement story

`add` is relational-first (`on: seat/between/on_floor`) — good philosophy — but
dropping a marker at a *computed* point needs the obscure `on={"at":[x,y,z]}`,
and `transform` offers only **relative** `nudge` — no absolute set-position or
set-rotation. The G1 local-frame layer should also serve placement (the same
fix from the other end).

---

## What worked — formalize this, don't fight it

The breast volume was placed, sized, projected, teardropped, splayed, spaced,
and given a concave slope — **with zero new code**, by improvising the missing
bridge out of four ingredients. This is the template the server should lean into
instead of trying to make the agent a freehand sculptor:

1. **Parametric proxies, not freehand.** A guide sphere is four legible dials
   (center, radius) the agent *can* reason about; a brushstroke at a guessed
   point is not.
2. **The status block as a closed coordinate loop.** Every nudge returned exact
   new bounds — the agent navigates by instrument without "seeing."
3. **Human eyes as a first-class pipeline stage.** Every judgment the agent
   structurally can't make ("too wide", "generous isn't on-model") came from the
   user. Precision from the agent, taste from the human — a permanent division,
   not a phase.
4. **Deltas, not absolutes.** Start close, correct in small safe steps that
   converge.

**Partnership feedback channel worth making first-class:** the human hand-edits
*one* side; the agent reads the **transform delta** (`object info`) and
propagates it to the mirror twin. ("You rotated the left breast +25° yaw — let
me mirror that onto the right.") A "match/mirror this object's edit to its twin"
affordance would make this a one-call move.

---

## Corrections (things wrongly flagged this session)

- **`duplicate_mirrored` is fine.** It does *not* drop a rotated source's
  orientation — that read came from the bbox and was wrong. Logged here only as
  evidence for G2.

---

## Carried over (still relevant, bears directly on G3)

- **Multires + dyntopo wrappers** — the proper resolution story for organic
  sculpt.
- **Retopology** (auto or guided) — once the form is sculpted, deformation-grade
  edge flow.
- **UV unwrap, material node graph, hair cards, face-loop topology** — further
  out, on the road to a finished character.

## Open (older, unverified against current build)

- `check_contacts` / contact queries timing out on dense evaluated meshes
  (Spring's production geometry) vs the socket window.
- bbox-vs-`sel_z` self-contradiction flag (the stale-eval-cache symptom).

---

## The thesis these all serve

The agent's vision can **judge** but cannot **measure**; it reasons over
outlines, profiles, scalars, and named regions — never coordinate dumps. The
destructive half already honors this (`feel` → named handles → anchored verbs).
**The work now is to extend that same contract to construction:** aim in
fractions-of-the-form, get form-verdicts back, keep the human's eyes in the loop.

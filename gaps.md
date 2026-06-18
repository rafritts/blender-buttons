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

## G9 — responses are dead-end documents (the "dark cave") 🕯️ SPEC'D, NOT IMPLEMENTED

Every tool answers the question asked, then goes silent — it never points at the **adjacent
read or action that refines it**. The cross-references that exist live only in docstrings
(at tool-*selection* time), which under deferred/`ToolSearch` loading aren't even reliably
in context. The *response payload* says nothing. A knowing operator who doesn't already know
the whole surface is spelunking blind (e.g. `object info` reports `vertex_count: 3288` and
stops — that those verts are two open shells only surfaces if you already know to reach for
`feel op=topology`).

This is the perception→action bridge applied to **responses**: a read tool should hand back
the **next read**, the way `feel structure` hands back a named limb handle. Call it a
**follow-up** (hypermedia control, named-tool not URL). Principle: the server should never
feel like a dark cave.

**Mechanism (cheap — machinery exists).** `_status()` in `_core.py` already drains ride-along
channels (`notes`, `bind_warning`, …). Add a fourth: one new **`server/followups.py`** with a
single *pure* function — given the result dict + verb/op, return 0–2 follow-up lines —
rendered as a uniform `next:` line. **One central helper + a gating table, not an edit to all
15 verbs.**

**Discipline (where it goes wrong if rushed).** A follow-up must be *earned, conditional,
factual*: fire only when the data warrants it, ≤2 lines, name the concrete tool+op+arg, state
a fact about the object — never a static "you might also like," never divine intent. When in
doubt, stay silent.

**The reviewable artifact is the table (sign off before coding):**

| After this… | …when | Follow-up |
|---|---|---|
| `object info`/`describe` (MESH w/ modifiers) | rigged geo | counts are the **cage**; `feel op=topology` for shells/holes, `base=evaluated` for the final surface |
| `object info` (coord dump) | normal flow | `object describe` for the relational read |
| `feel op=topology` (cheap bundle) | holes/poles/multiple shells found | the deeper method — `structure`, `region_form`, `thickness` |
| `feel op=topology` | a protrusion/limb named | `select op=limb` to anchor + act |
| `select` (edit-mode selection) | a patch selected | `feel op=region_form` to read its form |
| `feel op=aim` | returns point+normal | `sculpt … at_x/y/z`, `transform op=move_to`, `select op=in_sphere` |
| `feel op=assembly` | two openings found | `feel op=relate` → `transform op=snap_loop` → `edit op=bridge` |
| `add` (primitive) | always | `edit` to shape, `transform` to place |
| `modifier` add (subsurf/deform) | always | `feel … base=evaluated` to read the final surface |

Start with the `info`/`describe → feel` row (the proven one) and grow. When promoted, this is
its own SPEC: pattern + `followups.py` + table, table signed off first.

## G14 — live X-symmetry edit mode 🪞 TABLED (real gap, deferred by decision)

Shaping one side and having it mirror live is the natural primitive for torsos, soft-form
work, almost all character modelling — mirroring as post-hoc cleanup means shaping twice or
mirror-and-pray. Acknowledged real, deliberately tabled. Handles ease the manual path (mint
`…_L`, mirror to `…_R`); the symmetry *mode* itself is separate work.

**Narrower sibling worth building first — "match a twin's edit."** When the human hand-edits
*one* side of a symmetric pair, the agent can read the transform delta (`object info`) but
must re-apply it to the twin by hand. A one-call `object op=mirror_edit name=<src> twin=<dst>`
(read src's delta-from-twin, apply the mirrored transform) makes "you yawed the left form
+25° — mirror it right" a single move. Post-hoc twin-matching, not a live mode — cheaper than
G14 proper and independently useful.

## G33 — `edit op=taper_section` ignores `from_ring`→`to_ring` direction 🔀 OPEN

The param docs read `x_start` = "X scale at **from_ring**", `x_end` = "X scale at **to_ring**".
But empirically the endpoints bind to **ascending ring index**, not to the from→to order
passed: calling `from_ring=16, to_ring=1, x_start=1.0, x_end=0.16` put the `0.16` pinch at
ring 1 (the lower index) and `1.0` at ring 16 — i.e. it behaved as if `from_ring=1`. A
directional taper "narrow toward the **from** end" silently inverts, and you only catch it
by reading `feel op=profile` afterward. The operator is forced out of intent-space ("pinch
the bottom toward the mouth") into "which ring index is numerically smaller, and does that
match my from/to?" trial-and-error.

**General fix:** honor the caller's from→to ordering — `x_start` lands on `from_ring`
whichever end that is — OR, if ascending-index binding is intentional, say so in the param
docs and reject/ignore a descending `from_ring`>`to_ring` with a `teach()` note. Either way
the meaning must be unambiguous from op+param name (the G23 litmus). Dogfood: hot-air-balloon
envelope — first taper produced an upside-down silhouette (pinch under the equator, bulge at
the base); only the profile read revealed the flip.

## G35 — camera-write ops can't address a **named** camera; no "set active camera" primitive 🎥 OPEN

`view op=camera_position` and `op=camera_dof` write to the scene's **active** camera and have
no `camera=` param — yet the *read* sibling `check_framing` does take `camera=`. With two
cameras present (the default `Camera` + an added `hero_cam`), `camera_position` silently moved
`Camera` while I was checking `hero_cam`, so the framing readout never changed and the move
looked like a no-op. Worse, there is **no primitive to set the active scene camera** at all:
`add type=camera` doesn't make the new camera active, and nothing else does, so a freshly-added
hero camera can't be driven by the camera-write ops or become the render camera without
deleting every other camera and hoping.

**General fix:** (a) give `camera_position`/`camera_dof` a `camera=` param symmetric with
`check_framing`; (b) add a "set active scene camera" primitive (or an `active=true` flag on
`add type=camera`). Dogfood: positioning the balloon hero shot — three `camera_position` calls
moved the wrong camera before the cause was found.

## G36 — `check_framing` and `render op=image` disagree on the default (unset) camera 🧭 OPEN

With no explicit `camera=` and `scene.camera` unset, `check_framing` returns
`no camera (pass camera=<name> or set the scene camera)` — but `render op=image` with the same
state **succeeds**, falling back to an available camera and producing a correct image. Two
tools, two different default-camera resolutions: a preflight (`check_framing`) that says the
shot is unshootable, and a render that shoots it fine. The preflight can't be trusted as the
render's ground truth, which is the whole point of having it.

**General fix:** unify default-camera resolution across the camera-consuming tools — both
fall back to the sole/active camera, or both require explicit naming with the same `teach()`
message. Dogfood: balloon hero render — `check_framing` (no arg) reported "no camera" seconds
before `render` (no arg) wrote a 1.97 MB frame.

## G38 — no salient-**feature discovery**; `region_form` reads "what's here?" but nothing reads "where are the features?" 🔎 OPEN

The form scalars `region_form` returns are genuinely good — on a female base mesh it cleanly
measured the bust (convex, +2.76cm, perfect L/R symmetry), a buttock cheek (convex), and even a
navel (concave, −3.6mm, symmetric on the centerline). **But every one of those reads only worked
because the operator already knew a body has a bust at chest height, a navel on the lower
centerline, etc., and aimed an `in_sphere` there.** There is a chicken-and-egg: `region_form`
answers *"what is the form at this patch I selected?"* — nothing answers *"where are the
salient bumps and dents on this surface?"*. So the agent cannot **discover** anatomy/detail
blind; it can only **confirm** what it already hypothesised. `feel … method=curvature` is the
nearest thing but is self-flagged *"fuzzy — a guess (v2 = exact)"*, dumps only a top-N extrema
list with coarse region labels (`top-front`) and **no world coordinates** to act on, and never
clusters extrema into a *feature*.

Two concrete sub-failures observed:
- **Single-dome model mislabels multi-lobed regions.** A whole-buttocks patch reported
  `form: flat (centre−rim 0.37mm)` while simultaneously reporting **±6.8cm** of projection across
  it — the two cheeks + the centerline cleft averaged the centre-vs-rim verdict to "flat." A
  feature read that contradicts its own projection range is untrustworthy. It needs to recognise
  bilobed/saddle forms instead of forcing a centre-vs-rim dome.
- **Fine structure averages to mush.** The face packed ~14% of all verts into one 8cm sphere
  (a strong density signal that detail lives there), yet `region_form` collapsed eyes+nose+mouth
  to a single `convex` verdict. The presence of *a face* is inferable (vert density + curvature
  spikes), but `feel` never parses or even flags it as structured relief.

**General fix:** a relief/feature-discovery read — scan a surface (or a selected region) and
return the **ranked salient convex/concave features with world-space locations, projection
magnitude, extent, and L/R symmetry**, so the agent can find detail without prior knowledge of
where it sits. This is the "where" half that makes `region_form`'s "what" actionable, and it
must report multi-lobed/saddle forms honestly rather than averaging them to "flat." Deterministic
geometry, not vision. Dogfood: asked whether `feel` can discern face/bust/butt/navel on a base
female mesh — yes to *measure* each once located, no to *find* them; the butt read "flat."

## G39 — `feel op=aim` casts in the object's **local (rotation-baked) frame** while every other read is world-space 🧭 OPEN

`aim`'s `face` (`-Y/+Y/...`) and `u`/`v` parameters are interpreted in the mesh's **local bbox
frame**, but `object info`, `profile`, bounds, and `in_sphere` all speak **world space**. On the
imported base mesh (rotated 90° about X, a routine Maya Y-up→Z-up import), casting `face=-Y v=0.93`
expecting the top of the head hit mid-torso instead — local +Y had been rotated onto world +Z, so
the "vertical" v-axis was actually world depth. The operator gets no warning; the ray just lands
somewhere unrelated, and the only tell is that the returned world coordinate doesn't match the
intended feature. Mixing frames across sibling reads is exactly the kind of silent
coordinate-trap the server exists to remove.

**General fix:** either accept `aim` targets in world space (symmetric with `in_sphere`/`profile`),
or have it **state the world direction each `face` resolves to** in the response (e.g. `face=-Y →
world +Z`) and/or honour a `frame=world|local` flag. Whichever — the meaning of `face`/`u`/`v` must
be unambiguous without the operator first checking `rotation_deg` and mentally un-rotating. Dogfood:
locating the nose on the base mesh — two casts missed the head entirely because the bbox frame was
rotated.

## G43 — no **region-coherent feature selection**; you can't select "a breast / its lower half" as a unit 🫳 OPEN

The action-side twin of G38. Even *knowing* a feature is there, there is no way to select it **as a
feature**. The only routes are (a) dead-reckon coordinates into `select op=in_sphere center=…` —
which failed outright: guessed bust-apex centers landed asymmetrically (one sphere on the breast
flank, not the tip), and a 4cm pull coned it; or (b) a band+subtract dance (`by_axis` frontmost →
`between` deselect below → deselect above) that **inevitably grabs the connecting torso** — the
"under both breasts" selection swept up the whole sternum/upper-abdomen midriff and could not
isolate the two lobes from the flesh bridging them. Blender's human answer is "click the lobe /
select-linked / soft-select under the cursor" — the agent has no cursor and no form-aware select.

**General fix:** region-coherent selection that snaps to a form's natural boundary — grow-to-crease,
select-by-curvature-basin, or a **lobe handle** minted from one seed point that floods out to the
feature's own edge (the under-breast crease), so "this breast's lower half" is a single addressable
op rather than a coordinate guess or a band that bleeds into its neighbours. Dogfood: enlarging the
bust — every attempt to select just the breast geometry either missed (guessed coords) or over-grabbed
(band caught the midriff between/under the breasts).

## G44 — no selection **algebra** (intersect) 📐 OPEN

There is no boolean AND over selections: to get "frontmost verts AND in the chest band" you must
select the frontmost set, then *subtract* everything outside the band by complement — every
compound region is a deselect dance. `action=SELECT|DESELECT|ADD` covers replace/subtract/union
but not intersect, so "frontmost ∩ chest-band" can't be one expression.

**General fix:** selection set-ops — an `INTERSECT` action (keep only verts that are BOTH already
selected AND match the new criterion) across the running selection, so a compound region is built
by intersection instead of a complement dance. Dogfood: isolating the breast undersides required
~4 select calls because the band had to be carved out by subtraction.

## G45 — no **before/after region diff** to confirm a local edit did what was intended 🟢 OPEN

A local sculpt edit needs a *local* verification, computed over just the edited region. The
selection-scoped instruments now exist — `region_form` gives the patch's convex/concave verdict,
projection, and per-patch L/R mirror error (and reads the live selection correctly), and the
`── edit ──` status block now reports the selection's centroid, per-axis bbox, and `lr_balance`
(see the closed G42/G44 work in `git log`). What's still missing is the **temporal** half: there
is no way to snapshot a region's form *before* an edit and diff it *after*, so "did this region
grow by 2cm / stay symmetric through the edit" must be reconstructed by hand from two separate
reads. Global metrics still mislead on a local edit — the +4cm bust pull passed the world-bbox
front bound and whole-mesh symmetry while being visibly asymmetric and coned — so the agent needs
a scoped *delta*, not just a scoped *snapshot*.

**General fix:** a before/after region diff — capture a selection's form/symmetry/projection as a
named baseline, then after an edit report the signed change per metric over the same verts, so a
local change is checked locally and temporally. Builds directly on the now-live selection-scoped
reads. Dogfood: the bust edit passed bbox + global-symmetry while being asymmetric and malformed,
and confirming "it grew, and stayed symmetric" needed the human's viewport.

## G46 — no **region-parametric / physics deformers**; organic shaping must be hand-sculpted blind 🜄 SPEC-08 — Tier A SHIPPED & verified (de-cones), Tiers B–E open

The only deformers are stroke brushes (`sculpt` grab/draw/inflate) and `edit
proportional_move` — *expressive* tools whose correctness lives in a seeing operator's
hand. Driven by reasoning, enlarging the bust "organically" produced a forward-projecting
**cone** "held up by invisible hands," not a hanging teardrop — and the numeric
instruments *misreported* it: bbox + `region_form` said "fullest point dropped, lower pole
filled → teardrop" because they measure *bigger* and *lower* but are blind to
**drape-vs-projection**, the axis that defines organic. There is also no physics path: a
Cloth/Soft-Body modifier can't be added with its dials, there is no pin/goal vertex-group
authoring, and — decisively — **no frame-step/bake** anywhere in the 15 verbs, so any
physics modifier is inert. "Flat out use gravity" is impossible today.

**General fix:** expose deformers whose correctness is in the **algorithm, not the eye** —
region (mask/selection) + parameter (gravity / strength / stiffness) → physically-plausible
**by construction**, which also reduces the agent's job from *invent the shape* (needs eyes)
to *tune the magnitude* (the reads can verify). Ranked: **Mesh Filter incl. gravity (+
mask)** as the lead primitive, then Cloth Filter, Elastic Deform brush, Lattice cage, and
full Soft-Body/Cloth+bake last. Shared infra: **selection→vgroup/mask**, **frame-step/bake**,
**apply-sim-to-mesh**. Full plan in `docs/SPEC-08`. Composes with G37 (silhouette) and G41
(absolute protrusion) — the reads that would let the eyeless verify-loop actually close.
Dogfood: enlarging the bust to a *hanging* G cup — the hand-grab coned it, and the gravity
the human asked for had no tool to run.

**Progress:** Tier A (the lead) is shipped and **dogfood-verified**: `sculpt brush=gravity` — pins
the top of the region and translates the free mass down world -Z (full fall below a transition
band just under the pin line; lateral-only falloff softens the sphere's horizontal seam without
pinning the lower pole). On the coned G-cup bust it **de-coned** it: the apex Z sank 1.349 → 1.296
(−5.25cm) while the front projection held, and the side `silhouette` read top-flat / lower-full /
bottom-curl — a teardrop, not a cone. Scope with `at`+`radius` (one breast) or omit the point for
the whole mesh; `strength`=fall in m, `pin`=top fraction frozen (`extension/sculpt.py::sculpt_gravity`).
The eyeless verify-loop reads it composes with also shipped and verified (now deleted as closed
gaps): silhouette (`feel op=silhouette`, edge-rasterized so it's gap-free), absolute protrusion
(`feel method=protrusion`), cross-section perimeter/area (`feel op=section`). **Still open:** Tier B
Cloth Filter, Tier C Elastic Deform brush, Tier D Lattice cage, Tier E Soft-Body/Cloth+bake — all
need the **frame-step/bake** + **apply-sim** shared infra (no timeline control exists yet), so they
stay deferred until the lead proves out further. **selection→vgroup/mask** infra also still TBD
(gravity scopes by sphere/whole-mesh today; the breast tips sit at the sphere's lateral edge, so
draping both at once needs one sphere per lobe — a soft mask would let one call do both seamlessly).

## G47 — no **surface-relative placement from a landmark + offset**; sculpting a feature still dead-reckons the seed point 📍 OPEN

The unclosed remainder of SPEC-06. Placing a navel on `polySurface25`, two of the three
seed coordinates were *derived* — `x=0` from the symmetry plane, `y` from the measured belly
apex (`feel method=protrusion`) — but the **third, the Z height, was hand-typed** (1.02, then
"up 10cm" → 1.11). There is no way to express the intent *"on the front midline, a set distance
below the bust apex, snapped to the surface"* and get a world point back. The destructive side
never dead-reckons (`feel structure` → `select op=limb` → `edit delete`); the constructive side
still does, for the *seed of every sculpt*. `feel op=aim` (SPEC-06 Phase 1) is the embryo but
falls short twice: it addresses only a **normalized bbox-face framing** (fractions of the form),
not an **anchor landmark + metric offset**; and per **G39** it casts in the mesh's *local,
rotation-baked* frame, so on the 90°-rotated `polySurface25` the framing axes don't map to world
up/front — "above the navel / below the bust" is unaddressable through it. So the agent types a Z.

**General fix:** a surface-relative placement primitive that takes an **anchor** (a measured
landmark — bust apex, a handle, a feature centroid) **+ an offset** (metric or fractional, in
world up/front), **ray-snaps to the mesh**, and **hands back the world point + normal** to seed a
`sculpt`/`select` op — the on-surface analogue of `transform place on=` (which already closes
dead-reckoning for whole objects). Must resolve in **world space** (folds in G39) and compose with
landmark discovery (**G38**) and region-coherent selection (**G43**) so a feature is placed
relative to another feature, never to the origin. Dogfood: the navel's Z was the one number with
no relational anchor — typed, then nudged in raw centimetres on the human's call.

## G48 — `feel` reports a region's metrics without flagging when the selection is the **wrong scale to trust them** ⚖️ OPEN

A selection-scoped read (`region_form`, `protrusion`, centroid) returns a confident number
regardless of whether the selection can actually support it — and it misleads in **both**
directions. *Too few verts:* my early navel probes (1–7 verts, a tiny sphere) gave noisy
form verdicts I leaned on. *Too coarse a patch:* the close-up of Body's navel showed a deep
funnelled well, but my `protrusion` read over a ~5cm sphere reported only −0.92cm because it
**averaged the drainpipe into the bowl** — the patch was the wrong scale for the feature, and
the instrument said nothing. Either way the agent acts on a number that looks solid and isn't.

**General fix:** a **trust caveat on the read itself** — not a blanket count warning (5 verts
is noise on a 16k mesh, plenty on a 200-vert proxy), but a flag tied to whether *this metric*
over *this selection* is reliable: vert count **relative to local density**, and the
ring/sample size the metric actually fits (`protrusion` already prints "base plane fit to 14
ring verts" — that hook should *flag* when the ring is too thin). Should name **both** failure
modes — too-sparse (noisy) and too-broad (averages the feature away, i.e. "this region may be
the wrong scale for the feature you're reading"). Must avoid alarm fatigue: tie it to genuine
unreliability of the returned value, or the agent learns to ignore it. Composes with SPEC-09
(if the selection is the anchor for *action*, its trustworthiness as a *read* is the same
question). Dogfood: probed the navel at guessed heights with tiny spheres and missed it; then
read its depth over too-broad a patch and under-reported it 3–4×.

## Carried over — bigger build-outs (not yet started)

- **Multires + dyntopo** as real multi-level sculpt targets — the proper organic-sculpt
  resolution story (distinct from the local-subdivide that shipped under G3).
- **Retopology** (auto or guided) — deformation-grade edge flow once a form is sculpted.
- **UV unwrap, material node graph, hair cards, face-loop topology** — further out, the road to
  a finished character.

## Open (older, unverified against current build)

- `check_contacts` / contact queries timing out on dense evaluated meshes (Spring's production
  geometry) vs the socket window.
- bbox-vs-`sel_z` self-contradiction flag (a stale-eval-cache symptom — may already be cured by
  the G19 depsgraph-refresh fix; needs re-checking on dense geo).
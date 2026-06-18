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
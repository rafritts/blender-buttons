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

## G208 — `file op=import` is a stranger to its own interlock

`file op=import` mutates the world (adds objects) but does not stamp that mutation into
the SPEC-15 clean baseline the way every other mutating verb does. Result: the very next
mutating op trips the external-mutation lock on the object the server itself just
imported — "added: rung1_recovered" reported as if a human or script had done it. In an
import-heavy session (lining up 10 OBJ exports) the lock fired on effectively every
import→place pair, costing an `history op=acknowledge` round-trip each time and training
the agent to reflex-acknowledge — which dulls the one alarm that must stay sharp (it
ALSO fired correctly mid-session when the human really did move the character; that
catch is the feature working). The general primitive: any mutation routed through the
bridge is FIRST-PARTY — every world-mutating verb, `file` included, must update the
baseline it will later be diffed against. An interlock that cries wolf on the server's
own actions erodes exactly the trust it exists to protect.

## G204 — GN menu sockets: illegible options, unsettable by name

Essentials GN modifiers gate their behavior behind **menu sockets** (Scatter on
Surface: `Input Type`, `Instance Type`, `Density Method`, `Distribution Method`,
`Alignment Axis`). The `inputs=` surface fails on them twice over: (a) passing the
display name errors — "Cannot assign a 'str' value to the existing Int IDProperty" —
only a raw int lands; (b) nothing anywhere reports what the ints MEAN. The mapping is
not display order (`Instance Type`: UI shows Object, Collection but Object=1,
Collection=0), the enum items live on Menu Switch nodes inside the group whose
`NodeEnumItem` doesn't even expose its int identifier, and `inputs_available` lists
bare names with no type/options/current-value. The agent is forced to sweep magic
ints blind against evaluated geometry to reverse-engineer a dropdown. The general
primitive: every settable input must be legible (type, options by NAME, current
value) and settable by the same name a human sees in the modifier panel — the server
should resolve name→int itself (empirically if the API hides it: probe the interface
item's `default_value` string against a scratch modifier's idprop int).

## G205 — add_asset `collection=` assigns a socket its gate ignores

`modifier op=add_asset asset="Scatter on Surface" collection=Sprinkles` reports
success with `set: {'Collection': 'Sprinkles'}` — and does nothing: the group only
reads its Collection socket when the `Instance Type` menu is 'Collection', and the
default is 'Object' (with Object unset, each point instances an invisible 8-loose-vert
placeholder — zero faces, invisible in solid shading). The convenience arg's whole
INTENT is "instance from this collection"; it must also flip the menu that gates the
socket it just set, or refuse loudly. General form: assigning a value to a gated
input while its gate points elsewhere is a silent no-op the agent cannot see — the
server must either honor the intent (set value + gate together) or surface the gate.

## G206 — GN modifier ops succeed while emitting zero instances

Scatter on Surface defaults to Density=1/m². At real-world tutorial scale (a 0.15m
donut ≈ 0.05 m² of surface) that floors to **0 points** — modifier added, success
reported, viewport empty, no signal. Compounded by `Viewport Visibility` (a 0..1
fraction that can hide everything) and G205's invisible placeholder. The agent had no
read that says "this modifier currently emits N instances"; ground truth had to be
extracted by duplicate→realize→apply→count. The general primitive: any op that adds
or modifies an instance-emitting modifier should report the **evaluated instance
count** in its result (and warn at 0) — that one number makes every configuration
mistake in this family legible instantly.

## G207 — `op=apply` silently discards unrealized instances

Applying a NODES modifier whose output is instances-on-points (Realize
Instances=False, the default) drops them: the mesh comes back byte-identical
(caught only by the no-op interlock — the right alarm for the wrong reason) or, on
a host with other changes, would silently lose the scatter. Worse, the add_asset
result note actively claims the opposite: "add `modifier op=apply` (Realize
Instances) if you need editable geometry." Fix: `op=apply` must detect an
instance-emitting NODES modifier and set its Realize Instances socket (or append a
realize step) before applying, and the add_asset note must stop promising apply
realizes when it doesn't.

## G208 — two `inflate`s, two secret unit systems, one balloon

`edit op=inflate amount=` is meters. `sculpt brush=inflate amount=` is a raw brush
strength where 0.5 threw a vert 0.455m — 91× the brush radius — across a 15cm scene
(the over-large-displacement warning fired only AFTER the mutation; an undo repaired
it). The working value turned out to be ~0.001, i.e. meters-ish after all, just
attenuated by falloff. Same verb name, same argument name, incompatible scales, and
nothing in the schema says which system a given brush speaks. The general primitive:
every displacement dial on the surface should be denominated in METERS (the unit the
whole rest of the surface speaks), and a stroke that would move any vert further than
~2× the brush radius should refuse BEFORE mutating, not warn after.

## G209 — the select verbs strand their own selection for `feel op=handle`

Every select op stores the selection and drops back to OBJECT mode; `feel op=handle
source=selection` then refuses with "must be in edit mode with a vertex selection."
The escape hatch (object op=mode mode=EDIT, then mint) works because the selection
survived all along — the refusal is about MODE, not about missing data. A verb that
consumes "the live selection" should re-enter edit mode on the selection's owner
itself, exactly like every edit verb's target= does. One-line fix, one fewer
mode-dance every time a handle is minted from a measured selection.

## G210 — handles die on any topology change, even far from their verts

`sculpt subdivide=true` under a drip stroke orphaned the very handle the stroke was
aimed at ("vert count changed 5→14 — re-derive or discard"), forcing a re-derivation
dance (boundary ∩ in_sphere ∩ z-band) for every subsequent touch of the same feature.
Blender vertex groups already survive subdivision — new verts inherit membership —
so the tracked verts still existed; only the handle's vert-count checksum invalidated
them. The general primitive: a handle should survive topology edits that don't delete
its tracked verts, and an op that subdivides at a handle should re-mint that handle
as part of its own contract.

## G211 — `edit op=bend` bends around the long axis by default, warns after

Bending a cylinder sprinkle bent around its own length ("barely changes shape — a
perpendicular axis usually wants this") and still mutated, costing an undo; the axis=
dial that fixes it isn't documented for bend (schema tags it loop_cut/trace only) and
was found by guessing. If the op can already DETECT the degenerate long-axis case well
enough to warn, it should refuse before mutating (or default to a perpendicular axis),
and the schema should admit bend takes axis=.

## G212 — no way to address "the rim at angle θ" in one read

`feel op=radial` casts at bbox-centre HEIGHT, so on a dome-with-rim it lands mid-wall
(z=0.040) when the target was the boundary edge below (z=0.025); brushing there bulged
the wall and left the rim unmoved (bbox floor never dropped — caught by reading bounds,
not by any warning). The working address took three composed calls per spot: select
op=boundary ∩ in_sphere(cast) ∩ z-band. That composition is the system working, but
the read "the OPENING'S edge at clock angle θ" is a first-class question on any rimmed
form (cup lips, sleeve cuffs, icing edges) — radial wants a crossing=rim/boundary mode
that lands ON the nearest boundary loop instead of the wall above it.

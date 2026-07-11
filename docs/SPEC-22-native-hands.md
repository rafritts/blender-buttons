# SPEC-22 — Native Hands: strip all judgment sugar, complete the native operator basis

**Status:** APPROVED DIRECTION (2026-07-10). Written for an executor agent with no
conversation context. Phases run in order. **Where any prior spec conflicts with this
one, this one wins.** No overrides, no special cases, no grandfathering.

**The law:** **high-level eyes, low-level hands.** The server invents only in the
substrate — the mouse and eyes the agent lacks. Everything that *mutates* is a native
Blender operator, under its native name, with its hotkey and menu path as retrieval
keys. There is no third category.

**Why (short form).** The agent's Blender knowledge is deep but it is *indexed by native
vocabulary* — hotkeys, menu paths, tutorial phrasing. An agent asked cold can recite the
donut tutorial flawlessly, procedure-perfect, in that vocabulary. The same agent driving
this server maps narrative steps onto minted outcome-verbs and stops early — no LLM
session has ever attempted the long icing drip, despite provably knowing it. Minted
mutation verbs strand the training corpus, act as semantic checkboxes ("`noise_displace`
≈ lumpy: done"), and set the expected effort ceiling at one call per narrative step. The
fix is not better sugar; it is no sugar. This spec exists to **validate that thesis on a
clean baseline** — strip everything first, measure, and only then consider adding
anything back. Do not taint the experiment.

---

## 1. The criterion (binary, total)

Applied to **every op that mutates** geometry, materials, objects, or scene state.

**KEEP — substrate.** An op survives as a server invention only if it substitutes for
hardware the agent lacks (the mouse, the eyes, the viewport). This was never the
problem:

- selection & addressing: all of `select`, handles, `claim`, `look` windows
- perception & verification: `feel`, `validate`, `view op=check_*`, status/no-op detection
- relational placement: the `on=` DSL, `rest_on`, `seat`, `snap`, `place`, `move_to`,
  `aim_axis` — placement is mouse work
- invisible plumbing *inside* native ops: auto mode switching, selection guards, unit
  discipline, auto-status. Absorbed, never exposed as a named op.

**KEEP — native.** The op resolves to a **single native Blender operator, modifier, or
shipped feature** (SPEC-20's litmus: "one operator, or several?"). It keeps — or is
renamed to — the native name. A native op wearing a minted name gets its native name;
that is part of this rule, not an exception to it.

**DELETE — everything else.** Any mutating op that is not a single native operation is
judgment sugar and is deleted. Composites, outcome-named verbs, preset/expression-driven
deformers, construction macros — all of it. No usefulness test, no "but it passes
verification," no borderline queue, no user sign-off gate. If it mutates and it isn't
native, it goes.

**Classification is derived, never recalled** (SPEC-20 R3): read each op's
implementation (what `bpy.ops`/bmesh/modifier calls it makes) and check native claims
against the live 5.x build — not model memory, which is version-stale.

## 2. Phase 1 — audit for judgment sugar

Walk every mutating op on the surface (verb definitions in `server/`, implementations in
`extension/`). For each, one row: **op → NATIVE-KEEP | NATIVE-RENAME (to what) |
SUBSTRATE-KEEP | DELETE**, with the implementation evidence (the native call it wraps,
or the composite it compiles).

**Deliverable:** the table, appended to this spec as Part II.
**Verification:** every registered mutating op appears in exactly one row.

## 3. Phase 2 — remove judgment sugar

Delete every DELETE-row op: server verb entry, extension implementation, flat-tool
registration, validation entries, schema text. Apply every NATIVE-RENAME. Purge
references (`recipes/`, `GUIDANCE_FOR_LLMS.md`, guidance resources, tests).

**Do not write replacement technique docs, wrappers, or migration shims.** The
experiment is whether native vocabulary unlocks the agent's trained procedural
knowledge; pre-authored recipes for the deleted verbs' jobs would confound the result.
Git history is the archive if anything is ever wanted back.

**Verification:** server registers cleanly; tests pass; `grep -r` finds no dangling
references to deleted op names.

## 4. Phase 3 — audit missing native actions

Enumerate the native operator basis **from the live build**: the edit-mode **Mesh /
Vertex / Edge / Face** menus, the Select menu, and the daily hotkey set; cross-check
each against the surface. Seed list from the donut-procedure mapping (verify and extend
against the build — this list is observations, not rulings):

| native action | hotkey / menu | observed status |
|---|---|---|
| Duplicate selection (in-mesh) | Shift+D | missing (`separate` rips, it doesn't copy) |
| Shrink/Fatten (per-vert normals) | Alt+S | `move_verts` out/in exists — verify semantics match |
| Rotate selection (with pivot) | R | missing |
| Merge at Center/First/Last/Cursor | M | only merge-by-distance exists |
| Rip / Rip-Fill | V / Alt+V | missing |
| Split | Y | missing |
| Bisect | Mesh ▸ Bisect | missing |
| Shear | Shift+Ctrl+Alt+S | missing |
| To Sphere | Shift+Alt+S | missing |
| Smooth Vertices | Vertex ▸ Smooth | `relax` exists — verify vs native |
| Randomize | Mesh ▸ Transform ▸ Randomize | `jitter` exists — rename candidate |
| Dissolve Verts/Edges/Faces | Ctrl+X | missing (delete ≠ dissolve) |
| Hide / Reveal (edit mode) | H / Alt+H | missing |
| Fill / Beautify | F | grid_fill exists; plain fill unverified |
| Triangulate / Tris-to-Quads | Ctrl+T / Alt+J | missing |
| Snap-to-face-projected vert dragging | Snapping: Face + Project | missing — native Snapping as a flag on vert moves |

**Deliverable:** the gap table appended to Part II, prioritized daily-driver-first (ops
that appear in every tutorial outrank menu completeness).
**Verification:** every item in the live build's edit-mode menus has a row (present /
missing / deliberately-skipped-with-reason).

## 5. Phase 4 — implement missing native actions

For every new op, and retrofitted onto every surviving native op:

1. **Native name, native semantics, native defaults.** The op does what the tutorial
   says it does. Robustness is absorbed invisibly (§1), never a named variant.
2. **Hotkey + menu path as retrieval keys — mandatory.** The schema description opens
   with the native anchor:
   `duplicate — Shift+D · Mesh ▸ Duplicate: copy the selected geometry in-mesh; the
   copy is selected and unmoved.`
   The hotkey is the index the agent's training uses; it is not decoration.
3. **Family grammar** per SPEC-21 §3: shared WHERE scope block (`target=`, selection,
   `at=`/`handle=`), one magnitude word (`amount`, meters), member as parameter.
4. **Live-verify each op** on a real scene per the `gaps.md` discipline.

## 6. Validation — the experiment this spec exists for

Re-run the donut, blind (standing dogfood discipline: server instructions +
`guidance://llms` only; no repo docs, no recipes). Grade the **transcript**, not the
mesh: does the agent work in native vocabulary from its own knowledge — the top-half
duplicate for the icing, rim verts pulled into drips of varied depth with snapping,
inflate strokes on drip tips, stroke→look cycles in the double digits on craft steps?
That transcript is the measurement of the core thesis. Only after this baseline is read
does any conversation about adding higher-level anything begin.

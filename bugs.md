# bugs.md — repo defects & open-source readiness

Unlike `gaps.md` (tool-surface friction found while modeling), this file tracks defects
in the repo itself — docs, packaging, tests, hygiene, and implementation that violates
an existing contract. Numbered **B#**, stable, delete when fixed.

_Seeded 2026-07-09 by an open-source-readiness audit. Shipped, fixed, or retired bugs
are deleted, not archived — use `git log -- bugs.md` / `git blame` to see anything
past. B-numbers are stable and never reused._

---

## B11 — `transform op=snap` ignores `targets=`; always the viewport-active

**Defect, not friction.** The verb schema and the teach example (`transform op=snap targets=lid target=jar side=Z_MAX`) take `targets=`. Dispatch is `transforms.snap_to(target, side, source_side, offset)` — no `targets`. The extension reads `bpy.context.active_object`. `snap_grid` is the same (active only).

**Repro (Strat live session, 2026-09-17):** `transform op=snap targets=Nut target=Fretboard side=Y_MAX` snapped `KnobT2` (viewport-active). The nut did not move. Status bounds were the knob's. Workaround: select-then-snap, or `nudge` by a measured delta.

Nudge/place/rest_on honor `targets=` via `resolve_targets`. Snap is the odd one out on the same verb. Fix: pass `targets` through, snap each named object (or refuse with "snap needs targets= / active is X").

## B12 — script runner skips `_targets()`; comma-list `target=` 404s and abort undoes the phase

**Defect, not friction.** Server verbs expand `"a,b,c"` in `_targets()` before the extension sees a list. `script` batch/exec maps `material`/`transform` to the extension tool with params as written. `resolve_targets` does `if isinstance(targets, str): targets = [targets]` — no comma split — and 404s `Target 'String1,String2,…' not found`.

**Repro (Strat live session, 2026-09-17):** an exec that duplicated five strings then `material(op="set", target="String1,String2,String3,String4,String5,String6", …)` failed on that last step. Default `on_error=abort` transactionally restored the eleven successful steps. REPL `material op=set target=a,b,c` on the same objects works (G27). Workaround: set the material on the prototype *before* duplicating, or one `material` call per name.

Fix: run script params through the same `_targets()` parser the verbs use (or split commas in `resolve_targets` so both paths match). A late 404 must not be the first moment the agent learns the list was one name.

## B13 — script exec has no `object` verb (`object` is the Python builtin)

**Defect, not friction.** SPEC-23's v0 thin-map covers add/transform/edit/material/validate/feel/**object**, and `resolve_step` already maps `object op=duplicate|rename|delete|join`. Exec injects those verbs as top-level names on `Buttons` — except `object`, because it is Python's builtin. `object(op="duplicate", …)` is `TypeError: object() takes no arguments`. Batch can say `verb=object`; exec cannot.

**Repro (Strat live session, 2026-09-17):** a 6-string duplicate loop called `object(op="duplicate", …)` and died on that TypeError. Workaround: `call("duplicate_object", name=…, new_name=…)`. Loops over duplicate/join/delete/rename are exactly the exec gear.

Fix: bind the object verb under a name that isn't the builtin (`obj`, or a `Buttons.object` method) and inject it into exec globals so `object()` in a script never means `builtins.object`.

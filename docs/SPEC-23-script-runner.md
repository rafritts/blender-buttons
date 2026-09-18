# SPEC-23 — Script Runner: DSL scripts with a validation receipt

_Status: Experimental v0 shipped 2026-07-15 (rev 4 — usage centered on known
countable repetition, not the default loop; transport unchanged from rev 3).
Transport primitive — `script` verb (`batch` | `exec` | `dry_run`), hard cap 25,
compact receipt, transactional abort restore via history undo. Nested
`execute_command` (placement DSL, auto-`feel`, auto-`validate`). Verb thin-map
covers add/transform/edit/material/validate/feel/object; full surface via
`tool=<name>`. Known v0 gaps: undo is N Blender steps (not one collapsed unit on
success); some transform ops need `tool=`; not every feel/edit op is aliased.
See `extension/script_api.py`, `server/verbs/script.py`, `tests/e2e_spec23_script_runner.py`._

**Depends on:** SPEC-05 (verb surface / `op=` grammar), SPEC-15 (external-mutation
interlock at the socket boundary), SPEC-16 (forced `feel` + always-on `validate`),
SPEC-01 / THE ONE RULE (dimensions and measured provenance over divined coordinates).

**Out of scope:** ue-buttons (separate project; no shared schedule or receipt shape
required here).

---

## 1. The problem

The MCP verb REPL is the product: the next move depends on a read the agent has not
taken yet — localize a feature, claim a region, measure a gap, then act once. That
loop is the **default**. A unique 12-step assembly, even one the agent has already
planned, still belongs there.

The REPL is the wrong tool for **known, highly repetitive, obviously quantifiable
work** — the same primitive N times, where N and the pattern are already in hand.
Speaker holes in a MacBook chassis. Frets on a neck. A ring of identical bolts. You
could write `for i in range(n)` without another `look`. There the pain is transport,
not judgment:

1. **Round-trips.** One MCP call per verb. Latency and context cost scale with
   repetition count, not with difficulty.
2. **Ordering.** Tool calls batched in one message can arrive out of order
   (`GUIDANCE_FOR_LLMS.md`: dependent `edit` ops must be one-per-message). Scripts are
   sequential by definition.
3. **Status flood.** Every mutating call returns a full status block. Twenty identical
   holes dump twenty near-identical panels; the agent either drowns or stops reading
   them — which is how the floor fails.
4. **The raw-`bpy` escape.** Agents already write one-shot scripts (`tmp/*.py`) and
   run them outside the verb surface. That buys speed and loses everything that makes
   blender-buttons trustworthy: relational placement, named handles, auto-`feel`,
   auto-`validate`, THE ONE RULE, and the interlock's notion of "server-known" state.

So the gap is not "can the agent execute Python in Blender?" (it can, badly). The gap
is:

> **Run a known, countable repetition that speaks the blender-buttons language, in
> order, as one turn, and return a receipt the agent can trust the same way it trusts
> a single-op status block.**

---

## 2. What this is / is not

| This is | This is not |
|---------|-------------|
| **Transports** over the existing verb/tool surface (`batch` + `exec`) | A new modeling domain or macro library |
| The same primitive, **N times**, N and the pattern already known | The default modeling loop; a dump of a unique 12-step plan |
| Ordered runs that call the **same** `execute_command` path as MCP | A parallel mutation path that bypasses validate/status |
| One MCP turn → many ordered ops → one **receipt** | A replacement for the REPL's perception loop |
| A way to keep THE ONE RULE via measured returns (exec) or prior-receipt bounds (batch) | Permission to dump free `(x,y,z)` and call it progress |
| A **progressive** repetition path (chunk → receipt → next chunk) | A license to author a 2000-line program and hope |

Techniques (`guidance://techniques/…`) stay **method docs**. Recipes stay **verified
transcripts**. The runner is **execution**. Macros (`buttons-*-macro`) stay **named
composites with fixed semantics**. Session-local programs are not shipped primitives.

---

## 3. Three gears (when to use which)

The failure mode this section exists to kill:

> Agent treats `script` as the default multi-step path — either a unique 12-step
> assembly dumped as a batch, or a triumphant 2000-line Python scene, fired once,
> receipt unreadable, no cheap way to localize *which* assumption was wrong.

Repetition is useful. **Unverified bulk is how you lose an hour.** So even countable
repetition is progressive, and the server enforces budgets that make the mega-dump
awkward.

| Gear | What it is | Use when | Between turns |
|------|------------|----------|---------------|
| **REPL** | One MCP verb call — **the default** | Shape unknown; localization; taste; unique steps (even if planned); anything that needs a fresh still or a decision the agent can't pre-encode | Agent judgment on each status / look / feel |
| **Exec** | Python + `buttons` DSL — **the usual repetition form** | Same primitive, count already known: `for i in range(n_holes)`, computed names, a mid-phase `feel` branch | Short body, one phase; read the receipt; next chunk or back to REPL |
| **Batch** | Ordered list of ~N verb steps, **no Python** | Short enumerated repetition you can name without a loop (six identical feet, a named bolt set) | Read the receipt; fix or continue with the next chunk of the same repetition |

**Litmus:**

- Next step needs a `look` / human render / a *different* judgment → **REPL**
- Same primitive, `for i in range(n)` / computed names, n already known → **exec**,
  still a **small** body (one phase), not the whole build
- Same primitive, short list you can enumerate without a loop → **batch**
- "I planned 15 different ops" → still **REPL**

**Composition (the house style):**

```
REPL until the pattern is known and counted
  → exec (or a short batch) for one repetition phase, ≤25
  → read receipt → fix if dirty
  → next chunk of the same repetition, or back to REPL
```

REPL remains the eyes. Exec is the power tool for quantified repetition. Batch is the
no-Python form of a short enumerated list — not a lesser sibling of exec, and not a
dumping ground for a unique assembly.

### 3.1 Why even repetition is phased (and why a short batch beats a novel exec)

1. **Bounded blast radius.** A 25-step hole grid that fails is a 25-step problem. A
   400-step exec that fails is an archaeology problem — even with a good journal.
2. **Forced re-ground.** Returning to the agent between chunks re-attaches THE ONE RULE
   to *measured* receipt bounds before the next chunk is authored. Mega-scripts author
   far ahead of any ground truth the server has returned *in this turn*.
3. **No control-flow fantasy.** A counted loop is honest about what the agent actually
   knows. Python still invites writing the whole cathedral before the foundation
   validates — don't.
4. **Same receipt.** Batch and exec share one receipt shape — progressive chunks stay
   legible the same way.

### 3.2 The mega-script failure mode (normative)

**Rejected as the working style:** one `exec` that builds an entire multi-object scene
from a blank mental model, with validation only at the end (or as a wall of per-step
findings the agent cannot act on). Also rejected: using `batch`/`exec` because the
agent has more than one step.

**Required style:** REPL until the repetition is known and counted; then phases. Each
phase is one short exec (usual) or one short batch (enumerated list), sized so a human
or agent can read the receipt and answer "is this phase good?" before the next phase
depends on it.

Server-side step cap (§6.4) makes the rejected style impossible past 25 steps; guidance
makes mega-phases wrong even under the cap; first-failure receipt focus (§5.9) makes
partial disasters diagnosable when they still happen.

---

## 4. Surface shape

### 4.1 Verb

One new MCP verb: **`script`**.

| `op` | Role |
|------|------|
| `exec` | Run a Python body with the `buttons` DSL in scope. **Usual repetition path** (a short counted loop). |
| `batch` | Run an ordered list of verb/tool steps (no Python). Short enumerated repetition. |
| `dry_run` | Parse / bind only: syntax, unknown tools, missing required params, budget check — no mutation |

Parameters (sketch):

- `steps` — JSON list of `{verb, op?, params}` (`batch` only)
- `code` — inline Python (`exec`)
- `path` — absolute path to a `.py` file (optional alternate to `code`; still subject to
  **step** budget once expanded, not a loophole for megascripts)
- `on_error` — `abort` (default) | `continue` *(continue is for diagnosis, not for
  "push through 800 errors")*
- `validate` — `touched` (default final scope) | `scene`
- `verbose` — include full per-step status blobs (default false)
- `label` — short name for undo / history (`batch:legs`, `exec:spoke-ring`)
- `strict` — if true, undeclared clipping aborts like intent-free defects (default false;
  use for recipe CI)

### 4.2 The `buttons` DSL (script namespace)

Scripts do **not** invent a second API. They call thin wrappers that map to the same
flat tools the MCP verbs already dispatch — **full surface in v1**, no subset. This is
**not** a reimplementation of modeling ops. Each DSL call (and each batch step) is a
small map into the existing verb/`execute_command` path: same tools, same placement DSL,
same auto-`feel` / auto-`validate`. The only new code is transport (batch/exec loop,
journal, receipt, budgets, Handle returns).

```python
# Injected into exec globals — not a separate installable package for v1.
import buttons   # or: from buttons import add, transform, edit, object, …

stem = add(type="cylinder", name="stem", radius=0.01, height=0.08)
# stem is a Handle: .name, .bounds, .dims, .result (raw dict)

bulb = add(type="sphere", name="bulb", radius=0.03,
           on={"on": "stem", "align": "top"})

# Mid-script perception for branches the agent planned
r = feel(op="resting", a="bulb", b="stem")
if not r.get("resting"):
    raise buttons.Abort("bulb not seated on stem")

validate(op="expect", a="tenon", b="mortise", reason="seated joint")
```

Design rules for the DSL:

1. **Full surface, thin map.** Every MCP verb/op reachable from the agent REPL is
   reachable from `buttons` / batch steps. Call shape mirrors the verb surface
   (`add(type=…)`, `transform(op="snap", …)`, `edit(op="bevel", …)`,
   `object(op="duplicate", …)`). Binding is a
   dispatch table + structured return adapter — not a second implementation of any op.
   The agent should not learn two grammars.
2. **Returns are structured**, never the MCP pretty-print string. Every mutating call
   returns a small object with at least: `ok`, `name` / `names`, `bounds`, `dims`,
   `validate` (the per-op floor result), `warnings`, `raw` (full `execute_command`
   dict when needed).
3. **Handles are names.** `stem.name == "stem"`. Chaining is free because Python has
   variables — this is SPEC-03's transport remark made real.
4. **`import bpy` is allowed but discouraged.** Escape hatch for rare ops not yet on
   the verb surface. Raw `bpy` mutations still dirty the scene; they **do** run inside
   the script's undo unit, but they **do not** get per-op validate unless the script
   calls `validate` / a DSL mutator afterward. The receipt marks any step that used
   raw `bpy` as `via=bpy` so provenance is honest.
5. **No silent coordinate laundry.** The DSL does not ban `on={"at":[…]}` (the
   underlying tools may still accept measured points), but the receipt **tags** steps
   that used absolute placement so the agent and human can see drift toward divination.

### 4.3 Batch form (short enumerated repetition)

```json
{
  "op": "batch",
  "label": "batch:lamp-stack",
  "steps": [
    {"verb": "add", "params": {"type": "box", "name": "a", "width": 0.1, "depth": 0.1, "height": 0.1}},
    {"verb": "add", "params": {"type": "box", "name": "b", "width": 0.1, "depth": 0.1, "height": 0.05, "on": {"on": "a"}}}
  ]
}
```

Same receipt shape as `exec`. No loops, no branches — and that is a feature. Ideal for
a short enumerated repetition (six identical feet, a named bolt set) and for tests
that prove transport. Not a dump of a unique assembly.

**Authoring from a prior receipt:** the agent copies measured bounds / names from the
last receipt's journal into the next batch's params (relational `on=` preferred). That
is progressive THE ONE RULE without Python.

**Chunk size habit:** aim for one *repetition phase* per run — e.g. "≤25 speaker
holes," not "entire laptop + materials + UVs + render setup." Hard step cap is **25**
— you cannot author past that in one run (§6.4).

### 4.4 Exec form (usual repetition path)

Use `exec` when the repetition is quantified:

- a computed count (`for i in range(n_holes)` — speaker grille, frets, spokes),
- branch on a mid-phase measure (`if feel(...): …`),
- name generation or math that is uglier as 25 nearly-duplicate JSON steps.

Do **not** use `exec` to smuggle a whole-build novel, or a unique assembly, past the
REPL. An exec body should still be one repetition phase: short enough that the journal
is skimmable and a single undo unit is emotionally cheap to throw away.

---

## 5. The central design question — receipt ergonomics

### 5.1 The tension

In the REPL, **the status block is the instrument panel**. Placement arithmetic
("next part seats on last Z-max") is done by the agent reading bounds and typing the
next call. Validate and feel ride that same block (SPEC-16). Silence means clean.

A script that returns *N full status blocks* destroys context. A script that returns
*only `"success": true`* destroys the instrument panel — the agent cannot verify
placement, cannot stack the next REPL move on measured numbers, and cannot see which
step introduced a non-manifold edge.

So the receipt must be **as trustworthy as N status blocks and as cheap as one**.

### 5.2 Split: in-script instruments vs out-of-script receipt

This is the key ergonomic cut:

| Audience | What it needs | Mechanism |
|----------|---------------|-----------|
| **The running script** | Live bounds / validate for THE ONE RULE arithmetic and branches | **Structured return values** on every DSL call (full fidelity, stays in Blender process memory, never hits MCP context unless the script chooses to print) |
| **The agent after the script** (MCP return) | Proof of what ran, what failed, where things landed, whether the floor is clean, enough bounds to continue in the REPL | **The receipt** — compact journal + required finals + selective detail |

Arithmetic and mid-sequence decisions happen **inside** the script against return
values. The receipt is the **handoff and audit trail**, not a replay of every panel.

That inverts the bad pattern of "dump everything into the chat so the model can
pretend it watched." The model authors the script with the numbers it already has
(authored dims + prior REPL measures); the script measures as it goes; the receipt
proves the outcome.

### 5.3 What the receipt always contains

A fixed skeleton — never optional, never silent when the floor is down:

```
── script receipt · <label> · batch|exec ─────
  result:    ok | aborted | completed_with_warnings | rejected_budget
  steps:     N  (ok=…  warn=…  fail=…)
  created:   name, name, …
  touched:   name, …          # created ∪ modified ∪ deleted-from
  deleted:   …
  via_bpy:   yes|no           # any raw bpy mutation?
  on_error:  abort|continue
  duration:  …

  ── first failure (if any) ──
  <step i, focus, full error / validate line — the one place to look first>

  ── journal ──
  <one compact line per step — see §5.4; on abort may elide clean tail — §5.9>

  ── findings (rolled up) ──
  <counts by class; list capped — full list in structured JSON>
  <or: (none)>

  ── final validate · scope=touched|scene ──
  validate: <SPEC-16 line — clean or listed findings>
  intended: <registry count / holding / vanished if any>

  ── final focus ──
  <status for the last acted-on object, or an explicit buttons.focus() target>
  bounds / dims / mode / selection summary — same fields as a REPL status block

  ── checkpoints ──
  <only if the script called buttons.checkpoint — see §5.5>
──────────────────────────────────────────────
```

**Hard rules (receipt integrity):**

1. **Final validate always runs** (unless the human already has the global floor OFF —
   then the receipt must say `validate: OFF` exactly as SPEC-16 requires; silence is
   never clean).
2. **Intent-free defects never collapse out of the findings rollup.** A non-manifold
   introduced on step 7 and "fixed" on step 12 still appears as a historical finding
   unless the final validate is clean *and* we choose to show only final (see §5.6
   policy: show both "introduced" and "final" for intent-free defects).
3. **Created / touched sets are first-class.** The next REPL move should be able to
   `look target=<one of created>` without re-deriving the name list from prose.
4. **One undo unit + transactional abort.** The whole script is one history entry
   (`script:<label>`). On success, `history op=undo` reverts the whole run. On
   `on_error=abort`, restore to the pre-script snapshot (transactional) so partial
   geometry does not remain as a trap; receipt still journals what ran before the
   failure for diagnosis. Document `undo.policy: transactional` in the structured
   receipt.

### 5.4 Journal line format (the placement ergonomics)

Default journal lines are **one line per step**, dense, fixed columns:

```
  #  verb/op            focus        flag   dims                     note
  1  add/cylinder       stem         ok     [0.020, 0.020, 0.080]
  2  add/sphere         bulb         ok     [0.060, 0.060, 0.060]   on=stem align=top
  3  transform/snap     shade        ok     z=[0.080, 0.140]        on=bulb
  4  edit/boolean       body         WARN   non-manifold×2          ⟵ validate
  5  material/assign    bulb         ok     —
 12  (bpy)              —            ok     via=bpy
 13  feel/resting       bulb         ok     resting=true
```

**What appears on a default line (by op class):**

| Op class | Always on the line | Why |
|----------|--------------------|-----|
| **Create** (`add`, duplicate, …) | name, dims, placement relation if any (`on=…`) | Stack-up and identity |
| **Place / transform** (snap, rest_on, move relational, resize, …) | focus name, **world bounds or the axis that changed**, relation | Placement is the hard problem — bounds are the receipt's job |
| **Edit / topology** | focus name, flag, validate summary if not clean, optional vert/face delta | Correctness > exact bounds mid-edit |
| **Material / rename / non-geo** | name, ok | Cheap; no bounds noise |
| **Sense** (`feel`, `look`, `validate` called explicitly) | short result predicate or one-line measure | Branch evidence |
| **Fail** | full error string (may wrap to a second line) | Actionable |

**What does *not* appear by default:** full multi-line status panels, full feel
bundles, per-step scene trees, render settings. Those stay in `raw` on the structured
API and appear in the MCP receipt only with `verbose=true` or on failure.

**Bounds policy for placement (the sharp edge):**

- Every successful **create** and **placement/transform** step must include enough
  numeric footprint for the agent to continue in the REPL without re-measuring:
  preferably `dims` + the Z (or primary) world range, or full `bounds` when the
  line budget allows (implementation may always attach full bounds to the
  *structured* receipt JSON even when the pretty-print line is abbreviated).
- The pretty-print line may abbreviate (`z=[…]` when only vertical stack-up matters);
  the machine-readable receipt (`result["journal"][i]["bounds"]`) always carries
  full world bounds for create/place steps when the underlying status had them.
- If a place step's validate reports a **new undeclared clip** or **z-fight**, the
  line flag is `WARN` (or `FAIL` if `on_error` treats floor failures as fatal — §5.6)
  and the finding is copied into the rollup. Placement without a clean floor is
  never a quiet `ok`.

### 5.5 Checkpoints — agent-authored density

Long scripts need a middle ground between "every step" and "only the end":

```python
buttons.checkpoint("base seated", focus="base")
# forces into the receipt:
#   - a full status block for focus (or active)
#   - a validate run scoped to touched-so-far (or scene if asked)
#   - an optional feel delta on focus
```

Checkpoints are **explicit**. The runner does not invent them. Guidance teaches:
checkpoint after each major seat/join, before a boolean, and at the end of a phase
you might hand back to the REPL.

This is how multi-phase builds stay legible without default verbosity.

### 5.6 When does the floor abort the script?

| Finding class | Default (`on_error=abort`) | Rationale |
|---------------|----------------------------|-----------|
| Tool / DSL error (`success: false`) | **Abort** | Hard failure |
| Intent-free defect (non-manifold, flipped normals, degenerate, z-fight) introduced by a step | **Abort** | SPEC-16: never OK; building on top is the expensive failure |
| Undeclared clipping | **Warn + continue** (default) | **The whole point of progressive bulk:** mid-phase clips are often about to be fixed or declared; aborting every near-miss kills the assembly loop. Final validate (and the next phase's authoring) still surfaces them. |
| Declared clip vanished (tripwire) | **Warn** | Same as REPL — visible, not always fatal mid-script |
| `buttons.Abort(msg)` | **Abort** | Script-authored stop |

`strict=true` promotes undeclared clipping to abort — for recipe CI and any run where
"warn and finish the phase" is the wrong contract. Default stays warn-and-continue.

Intent declarations inside the script (`validate op=expect`) work exactly as in the
REPL and affect subsequent auto-validate on later steps.

### 5.7 Machine-readable receipt (API)

Pretty-print is for the agent in chat. The structured payload (also returned / logged)
is the source of truth:

```json
{
  "success": true,
  "result": "ok",
  "label": "desk-blockout",
  "steps": {"total": 18, "ok": 17, "warn": 1, "fail": 0},
  "created": ["stem", "bulb", "shade"],
  "touched": ["stem", "bulb", "shade", "desk"],
  "deleted": [],
  "via_bpy": false,
  "journal": [
    {
      "i": 1,
      "tool": "add_cylinder",
      "verb": "add",
      "op": "cylinder",
      "focus": "stem",
      "flag": "ok",
      "dims": [0.02, 0.02, 0.08],
      "bounds": {"x": [-0.01, 0.01], "y": [-0.01, 0.01], "z": [0.0, 0.08]},
      "placement": {"on": "desk", "align": "top"},
      "validate": {"passed": true, "line": "validate: clean …"},
      "absolute_placement": false
    }
  ],
  "findings": [],
  "final_validate": { "passed": true, "line": "…", "scope": "touched" },
  "final_status": { },
  "checkpoints": [],
  "undo": { "unit": "script:desk-blockout", "policy": "transactional" }
}
```

Agents that need stack-up after the fact read `journal[i].bounds`, not the prose.

### 5.8 What the agent should do with a receipt (guidance contract)

Ship this in `GUIDANCE_FOR_LLMS.md` when implemented:

1. **Read `result`, then `first failure` (if any), then `final_validate`.** Do not
   scroll a long findings list hoping insight appears — fix the first failure, re-run
   the phase (or undo + re-batch).
2. **If the phase is dirty, do not author the next phase.** Progressive bulk only works
   if each chunk is trusted before the next depends on it.
3. **Use `created` / `touched` for the next `look` / `feel` / next batch.** Don't
   re-list from memory.
4. **Use journal bounds for the next batch or REPL placements** the same way you'd use
   a status block — they are measured, not divined.
5. **Don't re-run a huge body to "see more"** — use `verbose=true`, add a checkpoint,
   shrink the phase, or drop into the REPL on a named focus.
6. **Undo is one shot** for the whole batch/exec unit; prefer re-batching a fixed phase
   over editing a 400-step program in place.

### 5.9 First failure, not 860 errors

When many steps fail or warn, the pretty-print receipt **leads with diagnosis**, not a
wall:

1. **`first_failure` block** — step index, focus name, verb/op, full error or validate
   line, and (for place/create) bounds if any. This is the primary agent-facing signal.
2. **Findings rollup as counts** — e.g. `non-manifold×4 · undeclared_clip×12 ·
   z_fight×2`, then at most a small sample (e.g. 5 detail lines). Full list lives in
   structured JSON for tools, not for chat wallpaper.
3. **On `abort`:** journal prints all steps up through the failure in full compact
   form; **successful steps after a failure do not exist** (abort stops work). On
   `on_error=continue` (discouraged for normal builds): journal may compact clean
   runs to a count line (`… 40 ok …`) and only expand warn/fail lines, so continue
   mode cannot be used to launder a disaster into an unreadable receipt.
4. **`on_error=continue` is a diagnostic mode**, not a build mode. Guidance: if you
   needed continue to "get through it," the phase was too large or the plan was wrong
   — undo, shrink, fix the first failure, re-batch.

The triumph response we refuse to reward: dump megascript → drown in findings →
shrug. The response we engineer: small batch → first failure is obvious → fix → next
batch.

---

## 6. Execution model

### 6.1 Where it runs

- MCP `script` verb → socket command → Blender main thread (same queue as every other
  tool). No background threads mutating bpy.
- Body runs **inside** the extension process with `buttons` bound to wrappers over
  `execute_command`.
- SPEC-15 interlock: the **whole script is one client turn**. External mutations
  before the turn still lock; mutations *caused by the script* are server-known and
  must not trip the interlock mid-script. Implementation: either nest
  `execute_command` without re-entering `handle_client`'s lock check, or baseline
  once at script start and treat in-script ops as clean (preferred: nested dispatch
  never hits the socket boundary — same as today's headless e2e harness).

### 6.2 Per-step vs per-script status/validate

| Concern | Per DSL step (inside `execute_command`) | Per script (receipt) |
|---------|----------------------------------------|----------------------|
| auto-validate (touched delta) | **Yes** — unchanged SPEC-16 path | Final validate over touched∪ or scene |
| feel_delta | **Yes**, but only attached to journal when WARN/FAIL or checkpoint/verbose | Not dumped every step by default |
| blender_status | Computed (needed for bounds on returns) | Final focus only in pretty-print |
| undo log | Prefer **one** push for the script, not N (or N internal + one user-visible) | Receipt names the unit |

Implementation note: today `execute_command` pushes undo per mutating tool. Script
mode should either (a) suppress per-step undo push and push once at end, or (b) group
undo steps. (a) is cleaner for the user-facing stack.

### 6.3 Failures and partial state

On abort:

- Journal includes all completed steps + the failing step with `flag=fail`.
- Receipt `result=aborted`.
- **Undo policy: transactional.** Restore to the pre-script snapshot so the scene is
  not left half-mutated. Receipt still carries the journal for diagnosis. Prefer
  implementing against the existing `state.push_undo_step` / undo stack so one user-
  visible undo unit and abort-restore share the same mechanism.

### 6.4 Budgets and limits (anti-megascript)

These are product decisions, not polite suggestions. The point of the cap is that you
**cannot get too far ahead** of a receipt.

| Limit | Default | Behavior |
|-------|---------|----------|
| **Hard step cap** (`batch` and `exec`) | **25** | At or under: run. Above: refuse before mutation — `result=rejected_budget` with a message that names the progressive style. Agent must split the work. **No soft oversize, no raise-the-cap param.** |
| **Inline `code` size** | e.g. 32–64 KiB | Oversize → reject; split phases or use `path=` *only if step count still respects the hard cap*. |
| **`path=`** | allowed | Not a loophole: expanded/executed step count still hits the same hard cap. |
| **Wall-clock** | cooperative with existing long-op handling | Runaway loops die with a partial journal + abort (then transactional restore). |
| **stdout/stderr** | captured, truncated | Must not become a second findings wall. |

**Counting steps:**

- **Batch:** `len(steps)`.
- **Exec:** number of DSL/`execute_command` invocations actually performed (loop
  iterations count). A 10-line script that loops 200 adds is a 200-step run — hard
  cap applies. `dry_run` cannot always know this; runtime enforcement still holds.

**Why 25, strict:** one readable receipt, one undo emotion, one phase. Dense work
(radial arrays, many small parts) is still progressive: multiple batches of ≤25, each
grounded on the prior receipt. 500-step "novels" and "just this once, 80 spokes" are
what we are building the product *against*.

### 6.5 Safety

- Same trust boundary as the rest of the server: the agent already drives the
  attached Blender. This does not expand network or cross-instance power.
- No new "ignore validate" for the agent.
- `dry_run` exists so a batch can be checked for bind/budget issues without mutation.
- Field-style AST sandbox is **not** the goal for `exec` — this is full Python with
  an intentional surface. Document that honestly.
- Budgets are safety for *cognition and scene integrity*, not a security boundary.

---

## 7. Interaction with existing systems

| System | Interaction |
|--------|-------------|
| **SPEC-16 validate / feel** | Unchanged per mutator via `execute_command`; receipt adds final + rollup + first-failure + journal flags |
| **SPEC-15 interlock** | One client turn per batch/exec; in-run ops are not "external" |
| **History / undo** | One labeled undo unit per batch/exec run (`script:<label>`). **No history-UI expansion** for v1 — label only if anything shows; full journal lives on the MCP receipt |
| **Collab panel** | Not required for v1 |
| **Techniques / recipes** | Techniques stay prose-first (REPL between steps). A recipe may emit a repetition phase as exec/batch; unique steps stay in the REPL |
| **Macros** | Unrelated — macros are named composites; batches/scripts are session-local |
| **Guidance** | REPL is the default; script is known countable repetition; hard cap 25; first-failure reading; anti-megascript |
| **ue-buttons** | Out of scope |

---

## 8. Anti-patterns (reject in design review)

1. **Receipt = success boolean.** Worthless for placement.
2. **Receipt = N full status blocks by default.** Context death; agents stop reading.
3. **Receipt = 860 validate lines.** Same death mode; use first-failure + counts (§5.9).
4. **API that only wraps raw bpy.** Loses the product.
5. **Agent mute for validate inside batch/exec.** SPEC-16 forbids it; not a loophole.
6. **Silent absolute coordinates as the house style.** Tag them; prefer relational `on=`.
7. **Auto-checkpoint every N steps.** Wallpaper; checkpoints must be intentional.
8. **Using batch/exec for look→claim→edit localization loops.** That's the REPL's job.
9. **Using script because you have more than one step.** Unique steps stay in the REPL
   even when already planned. Script is for the same primitive, N times, N known.
10. **The triumphant megascript.** One exec/batch that is "the whole build," validated
    only by a terminal findings wall. Server budgets + guidance reject this.
11. **`on_error=continue` as a build strategy.** Diagnostic only; not how phases ship.
12. **`path=` / loops to bypass the step cap.** Hard cap 25 counts dynamic steps; no
    raise-the-cap escape hatch.

---

## 9. Acceptance criteria

1. **Phase-sized batch:** a donut-class *phase* (or full small donut) runs as
   `script op=batch` with relational placement; receipt clean or intents declared.
2. **Progressive bulk:** two sequential batches, second authored from the first
   receipt's names/bounds; both undo independently.
3. **Receipt** includes created names, journal lines with dims/bounds on every create
   and place step, final validate, final focus — without full per-step panels.
4. **First failure:** a deliberate bad step yields a receipt whose pretty-print leads
   with `first failure`, not a undifferentiated findings dump.
5. **Intent-free defect** mid-run aborts (default); transactional restore leaves no
   partial geometry; receipt journals the failure.
6. **Undeclared clip** mid-run warns (default); still visible on final validate if present;
   `strict=true` aborts on undeclared clip.
7. **Budget refuse:** a batch with 26 steps returns `rejected_budget` and mutates nothing.
   No soft-oversize path.
8. **Exec step counting:** a short loop that would exceed 25 aborts with a clear budget
   error when the count is crossed (no silent 2000-add run); scene restored.
9. **In-exec returns:** `stem.bounds` / `stem.dims` usable for later steps in the same
   exec without an MCP round-trip.
10. **Full-surface map:** at least one non-add verb family (e.g. `transform` / `edit` /
    `material`) works via the same thin dispatch as `add` — no parallel op code.
11. **REPL handoff:** after a batch, `look` / `feel` on a `created` name works without
    re-deriving state from prose.
12. **e2e** covers: batch happy path, progressive two-batch, abort on non-manifold +
    transactional restore, first-failure formatting, 26-step reject, exec loop budget,
    undo unit.
13. **Guidance** teaches REPL as the default, script as known countable repetition,
    hard cap 25, and "do not megascript."

---

## 10. Implementation sketch (non-binding)

1. `extension/script_api.py` — `buttons` module (thin full-surface wrappers), Handle
   type, journal collector, checkpoint, Abort, step counter for cap.
2. `extension/server.py` — `script_batch` / `script_exec` / `script_dry_run` (or one
   tool with `op`); nested `execute_command` with undo grouping + transactional abort
   restore; hard cap gate before and during run.
3. `server/verbs/script.py` — MCP verb + receipt pretty-printer (first-failure lead;
   do not dump `_status` N times or findings walls).
4. Tests: `tests/e2e_spec23_script_runner.py`.
5. `GUIDANCE_FOR_LLMS.md` + `server/_instructions.py`: REPL is the default; script is
   known countable repetition; hard cap 25; progressive habit.
6. Optional follow-on: recipe segments emitted as batch JSON (not v1).

---

## 11. Closed questions (rev 4)

| # | Question | Decision |
|---|----------|----------|
| 1 | Undo on abort | **Transactional restore** to pre-script snapshot; receipt still journals the failure |
| 2 | Verb binding surface | **Full surface in v1** — thin map into existing `execute_command` / verb dispatch; **no reimplementation** of modeling ops |
| 3 | Undeclared clip default | **Warn + continue** by default; final validate still surfaces. **`strict=true`** for recipe CI. Progressive bulk is the point — mid-phase near-misses must not kill every assembly |
| 4 | Step budget | **Hard cap 25.** No soft tier. You cannot get too far ahead of a receipt |
| 5 | Oversize / `max_steps` | **None.** No raise-the-cap param; >25 → `rejected_budget`, no mutation |
| 6 | History UI | **None for v1.** One labeled undo unit only; journal lives on the MCP receipt |
| 7 | ue-buttons | **Out of scope.** Separate project |
| 8 | When is script the right tool | **Known, highly repetitive, obviously quantifiable work** — the same primitive N times, N already known (speaker holes, frets, a bolt ring). REPL is the default. Unique planned sequences stay in the REPL. (rev 4) |

---

## 12. Decision summary (for implementers)

| Decision | Choice |
|----------|--------|
| Gears | **REPL** (default) · **exec** (counted repetition) · **batch** (short enumerated list) |
| Transport verb | `script`: `batch` + `exec` + `dry_run` |
| Progressive bulk | Repetition in phase-sized chunks; receipt between chunks; no whole-build novels |
| Budgets | **Hard cap 25** (reject above); loops count; no soft oversize / no `max_steps` raise |
| Mutation path | Nested `execute_command` (DSL); **full surface**, thin map; bpy allowed but tagged |
| In-exec truth | Structured returns with bounds/validate every step |
| Out-of-run truth | Compact receipt: **first failure** + journal + counts + final validate + final focus |
| Placement ergonomics | Create/place lines carry dims + bounds (full in JSON); relations echoed |
| Density | Compact default; `checkpoint()`; `verbose` opt-in; never findings wallpaper |
| Floor abort | Intent-free → abort; undeclared clip → **warn** (default); `strict` → abort on undeclared clip |
| `on_error=continue` | Diagnostic only |
| Undo | One unit per run; **transactional restore on abort** |
| History UI | None for v1 |
| ue-buttons | Out of scope |
| Not a mute | No agent path to disable validate |

The success test is behavioral: an agent builds a multi-part assembly as **a sequence
of receipts**, each phase ≤25 steps and small enough to trust, batch-first unless
control flow demands exec — and never has a reason to throw a megascript at the floor
and call the resulting findings wall feedback.

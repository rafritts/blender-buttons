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

_G203–G216 (the bead-of-icing donut-dogfood autopsy) were fixed and verified against
headless scenes — see `git log -- gaps.md` and `tests/e2e_g203_g216_deform.py`,
`e2e_g204_g207_scatter.py`, `e2e_g209_g212_handles.py`. Live re-verify on the motivating
donut scene (2026-07-10): G208/G212/G213/G215 hold up._

_G217 (bud's failure mode is "success") closed by SPEC-21 §4: `bud` and the macro verbs
are DELETED; the missing primitive was native Bridge Edge Loops (`edit op=bridge`, long
shipped) and the drip is a technique (`guidance://techniques/drip`). G218 (declared
intents are scene facts) closed in SPEC-21 phase 5: the registry already persisted into
the .blend (G125) but an addon reinstall reset the module without a scene load — grounding
is now lazy, so the first registry access after a reload re-reads `scene["bb_intents"]`
and the tripwires re-arm. G219–G221 (the VRoid semantic-selection autopsy) shipped in
SPEC-21 phase 1. Live re-verify (2026-07-10, VRoid scene + fresh goblet): look→descend→claim
narrates and mints on real imported geometry (vgroup candidates included, coverage honest);
`edit op=spin` revolves live (the seam safety-weld caught a 32-way on-axis apex collapse the
headless test never exercised); trace-vs-authored-profile round-trips; `validate op=expect
check=open_boundary` declares and quiets; history undo restored a destroyed form byte-true.
G222–G224 (found in the same sweep + a left-pinky look drill) fixed and live-verified
2026-07-10 — see `git log -- gaps.md`._

---

## G225 — GN modifier menu/enum inputs silently don't latch, and the readback confirms the lie

**Verb:** `modifier op=add_asset` / `op=modify` with `inputs={…}` (and the `collection=` param) on a Geometry-Nodes modifier — hit driving the native **Scatter on Surface** asset.

**Friction (donut dogfood, 2026-07-10):** Setting a **menu/enum** node input is reported applied but never reaches the live modifier. `add_asset` with `collection=Sprinkles` echoed `set: {'Instance Type': 'Collection', …}` and the input dump read back `Instance Type (menu: Object|Collection = Collection)` and `Density Method (menu: … = Density)` — yet Blender kept evaluating `Instance Type = Object` (empty source → **0 instances scattered**) and `Density Method = Amount`. Nothing landed on the donut. Only the human, eyes on the native N-panel, caught it and flipped Instance Type→Collection by hand; the collection scatter then worked immediately.

**Why it's a gap (not operator error):** the agent had NO trustworthy read to catch this. The input dump / echo is generated from the value the tool *tried to write*, not the modifier's effective state — so a verification read **confirms a write that didn't happen** (unfalsifiable-but-wrong). Non-menu inputs (Int `Amount`, Float `Density`, Bool, Vector) *do* latch, so the failure is specific to menu/enum sockets and invisible from every server read. The agent burned ~a dozen calls (probe duplicate→apply cycles, a full remove + re-add) chasing a phantom binding because the tool insisted it was already bound. Compounding it, the `emits: N instance(s)` heuristic read 0 then 1000 (the `Amount` default) — also decoupled from the true evaluated count (a same-Density probe earlier realized 260).

**Fix direction:**
1. Write menu/enum GN inputs through the representation that actually latches (menu sockets carry an int index / string identifier — the current path sets a value Blender ignores) and force a depsgraph update so the modifier re-evaluates.
2. Make the input **readback reflect the modifier's EFFECTIVE evaluated state**, not the intended write — so `modifier op=list` / the input dump can be trusted to catch a failed set. The honest read is the deeper fix: a write that fails must be *visible* to the agent, not papered over by echoing intent.
3. Report a **true evaluated instance count** for scatter/instancer GN modifiers (depsgraph realize-count), not a pre-eval guess off `Amount`.

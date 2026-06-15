# SPEC-01 — Strict-Relational Mode (no 3D dead-reckoning)

**Status:** OBE — overtaken by `SPEC-05` (the verb collapse). Retained for reference; not a live plan.
**Date:** 2026-06-14
**Depends on:** `vision.md` ("Coordinates Never Cross the Boundary")

## Goal

Remove the LLM's ability to place or move geometry by **dead-reckoning absolute
coordinates in 3D space**. Force every action through the relational / reference path.
Where the LLM reaches for a coordinate, *capture the reach as data* so it names the
relational verb we still owe it.

This is a forcing function, not a cleanup. As long as a coordinate escape hatch exists,
neither the LLM nor we ever confront the missing relational verb — the hatch silently
absorbs the failure. Removing it converts "LLM quietly used coords" into "LLM is stuck →
a logged, named gap."

## The principle: perceive in coords, act in labels

The ban is on coordinate **action**, not coordinate **sight**.

- **Allowed — perception.** A tool may *show* the LLM coordinates (in a local frame, as
  read-only ground truth). It can't gaslight; it helps the sculptor's mental model. See
  SPEC-02.
- **Banned — action.** The LLM may not *specify* an absolute world coordinate to place,
  move, or aim anything, and may not carry a coordinate between tool calls.

"Coordinate" here means an **absolute position in space**. It does **not** mean numbers in
general — dimensions, angles, counts, gaps, radii, and *relative* displacements are all
quantities the LLM legitimately knows and passes.

## Scope — the ripcord inventory

Verdicts: **KEEP** (not a coordinate-action), **REFUSE** (coordinate-action; refuse with
capture), **WATCH** (borderline; keep for now, instrument, revisit from capture data).

| Tool / param | Verdict | Note |
|---|---|---|
| `on={"at":[x,y,z]}` | REFUSE | the canonical dead-reckon placement |
| `on={"x":…}/{"y":…}/{"z":…}` literal axis override | REFUSE | single-axis dead-reckon |
| `on={"raise_to": z}` (literal world Z) | REFUSE | the most-used one — forces "rest on / flush with X"; expect the loudest capture signal |
| `on={"on_floor": true}` | KEEP | relational to the floor, not a literal Z |
| placement DSL: `on/under/between/centered_on/at_corner/left_of/right_of/behind/in_front_of/mirror_of/gap` | KEEP | the intended path |
| `set_camera_position(x,y,z,target…)` | REFUSE | → `orbit_viewport` (relational framing) |
| `add_curve` / `spline_tube` literal `[x,y,z]` points | REFUSE | require the `{"near":obj,"offset":…}` form (already supported) |
| `nudge(right/left/up/down/back/forward)` | KEEP | relative displacement, not a coordinate |
| edit-mode direction words (`out/inward/up/down/left/right/forward/back`, meters) | KEEP | relative, local-frame |
| `move_vertices` / `scale_vertices` / `extrude` legacy `x/y/z` (bbox fractions) | REFUSE | legacy coordinate-ish; the direction words replace them |
| `select_by_axis(factor)`, `select_between(lo,hi)` (0–1 factors) | WATCH | normalized, not absolute; positional but not coord-carrying |
| `snap_to_grid(size)` | WATCH | rounds origin to a grid; coord-ish but needs no coord knowledge |
| `snap_to(target, side, offset)` | KEEP | relational (face-to-face) |
| dimensions / angles / counts / `gap` / `bow` / radii / segments | KEEP | quantities the LLM knows |
| all reads / introspection | KEEP | reading relations back is the whole point |

## Mechanism — refuse with capture

A REFUSE path does not 404. It returns a diagnostic that (a) teaches the relational
vocabulary and (b) logs the intent:

```
✗ coordinate placement is disabled (strict-relational mode).
  You tried: at=[0.21, 0.0, 0.48]
  Express this relationally — available: on / under / between / at_corner /
  left_of / right_of / mirror_of / snap_to / on_floor. What were you placing against?
  [logged → painpoint #47]
```

The capture log is the deliverable. Each entry: `{tool, attempted_args, surrounding op,
timestamp}`. Aggregated and ranked by frequency, it **is** the prioritized build queue
for new relational verbs (e.g. a recurring "connect two points with a curve" reach →
build `connect(from, to, …)`).

## Flag

`STRICT_RELATIONAL` (default **on**). Forcing is identical with the flag on; the flag
exists so we (a) don't delete code we may need to reference, and (b) can re-enable a
*single* capability if capture data proves it a genuine dead-end with no relational
framing yet — while we build the replacement. Hard-delete only after the flagged
experiment proves nothing legitimate needed re-enabling.

## Capabilities that go dark (chosen costs)

- Exact camera placement → relational framing via `orbit_viewport` only.
- Literal placement heights → "rest on / flush with / between X".
- Exact first-object placement → defaults to origin.

These are *chosen*, not discovered. If capture data shows a fourth that genuinely can't
be expressed relationally yet, that's a SPEC-02-adjacent verb to build, not a reason to
restore the ripcord.

## Acceptance

- Every REFUSE path returns the diagnostic + writes a capture entry (headless test:
  assert refuse fires on `at=[…]`, does NOT fire on `on={"on":"seat"}`).
- Capture log is queryable/rankable.
- Existing relational e2e batches still pass with the flag on (anything that breaks is a
  real gap, logged, not worked around).

## Open questions

- `select_by_axis` / `select_between` factors and `snap_to_grid`: keep as WATCH, or
  refuse? Decide from capture data after one real modeling session.
- Capture-log storage: in-memory + `get_history`-style surface, or a file under the
  session dir? (Leaning file, so it survives a server restart and can be reviewed.)

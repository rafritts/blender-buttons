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
One new gap found in the sweep: G222._

---

## G222 — zero-centered field presets are destructive under multiply-mode channels

Following `guidance://techniques/revolved-vessel` **verbatim** — `edit op=field
channel=radial preset=lobes freq=12 amp=0.05` on a goblet bowl — collapsed the band to a
spike: `lobes` emits `amp·cos(freq·θ)` (zero-centered, F∈[−0.05, 0.05]) and
`channel=radial` defaults `field_mode=multiply`, so every radius was multiplied by ≈0 (and
half by a *negative*), yielding 857 self-intersections in one call. The op did exactly what
it was told, and what it was told is what the server's own technique doc prescribes.

General framing: a preset knows its own **zero-line**. Zero-centered presets (lobes, sine,
bell) composed with a multiply-identity channel (identity = 1) should either (a) emit
`1 + F` under multiply so `amp` reads as relative depth, (b) default that combination to
`add`, or (c) refuse with the correction spelled out. Any of those keeps the agent in
intent-space ("12 lobes, 2mm deep"); today's silent collapse hands back a destroyed form
with no warning. Whatever ships, the revolved-vessel technique's `amp=<depth>` line must
match it.

(Live workaround verified: `field_mode=add amp=<meters>` cut the gadroons correctly.)

## G223 — claimed vgroup candidates are silently window-clipped

Drilling to a VRoid fingertip window and claiming its offered `J_Bip_L_Little1/2/3`
vgroup candidates yielded 27 verts — but the finger is an 81-vert shell, and the full
vgroup union is 162 verts. The offer lists each candidate's *in-window* portion with no
signal that the vgroup extends beyond the window, so claiming a **semantic** candidate
(a named rig part) quietly mints a handle on a fragment of it. The claim narration's
shell-coverage line ("27 of 81 verts of shell #14") was the only tell — it rescued this
build, but the trap should not exist.

General framing: a window clips **perception**, but a vgroup is a whole **entity** — an
offer that names an entity should either cover it fully or say it's showing a fragment
("24 of 162 verts in window; claim takes all 162 / claim takes the fragment"). Related
friction from the same drill: re-pointing an existing handle at the live selection has no
first-class path (a bare `claim name=` refuses; the workaround is the self-union dance
`claim add=<handle> name=<handle>`).

## G224 — look's orient line stops short of character handedness

`look` reports `front=−Y · bilateral across X`, and its position tokens are world-axis
("left" = −X). Asked for the character's **left** hand, the agent must derive that
character-left = +X = window-"right" — or, as happened live, descend into the wrong arm
and be corrected by rig vgroup names (`J_Bip_R_*`). The server already knows the answer:
`feel op=topology method=facing` computes the signed frame. The root window's orient line
should finish the sentence — "front=−Y ⇒ subject's left = +X (window right)" — so "the
character's left X" translates to a token without a wasted descent. Position tokens
staying world-axis is fine; the missing piece is the one-line translation.

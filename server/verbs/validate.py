"""validate — the always-on correctness floor (SPEC-16).

`validate` is the second of the two forced senses (`feel` is the other). It runs
AUTOMATICALLY after every geometry op — you do not have to call it, and its findings
ride the status block. This verb is for the deliberate moves the automatic floor can't
make for you:

  • declare an intersection INTENDED, so a known-good clip stops crying wolf
    (`op=expect` — there is no `ignore`; the only affordance is a positive, justified
    assertion);
  • read the live registry of those declarations (`op=intended`);
  • run the floor on demand over the WHOLE scene, not just the touched delta (`op=run`);
  • read the cross-session telemetry that tunes what each check is worth (`op=stats`).

The intent-free defects — z-fighting, non-manifold edges, flipped normals, degenerate
faces — are NEVER OK and have no suppression path at all. If you see one, fix it before
you build on top of it. Clipping/penetration is the ONLY suppressible check, and only by
declaring intent. See docs/SPEC-16-agent-feedback.md.
"""

from typing import Literal

from server._core import mcp, call_blender
from ._common import tag, unknown

_OPS = ["run", "expect", "intend", "forget", "intended", "stats"]


@mcp.tool(name="validate")
def validate(
    op: Literal["run", "expect", "intend", "forget", "intended", "stats"] = "run",
    a: tag(str, "[expect/intend/forget] first object of the clip pair (may name a "
                "COLLECTION to cover a whole scatter, e.g. Sprinkles↔Icing)") = "",
    b: tag(str, "[expect/intend/forget] second object (or collection) of the clip pair") = "",
    reason: tag(str, "[expect/intend] WHY the clip is intended — a falsifiable design "
                     "claim ('hair roots seat under the scalp'). Required; an assertion "
                     "you can't justify is a bug you're hiding.") = "",
    targets: tag(str, "[run] object(s) to sweep ('' = whole scene)") = "",
    verbose: tag(bool, "[run] list EVERY finding instead of capping the line") = False,
) -> str:
    """
    The always-on correctness floor (SPEC-16). It runs after every geometry op on its
    own; use this verb for the deliberate moves. `op` selects:

      run      — run the floor NOW over the whole scene (or `targets=`), not just the
                 last touched delta. Reports by exception: clean checks collapse to a
                 line; defects and undeclared clips are listed. `verbose` lists EVERY
                 finding (no cap).
      expect   — DECLARE a clip/penetration intended (alias `intend`). Name the pair
                 (a, b) and the `reason`. a or b may be a COLLECTION to cover a whole
                 scatter in one call (Sprinkles↔Icing). This is the ONLY way to quiet a clipping
                 finding — there is deliberately no "ignore". The declaration is scoped
                 to the (a,b) RELATIONSHIP (so Hair↔Body intended does NOT also hide a
                 later Hair↔Hat clip), it collapses the finding to a COUNT (never
                 silences it), and it becomes a TRIPWIRE: if the intended overlap ever
                 vanishes, that is itself a finding. Declare the few real ones; never
                 paper over the noisy ones — the noise is the mesh telling you it's broken.
      forget   — retire a declaration (a, b) — clears its tripwire. (Deleting a declared
                 object auto-clears it too; use this to drop one you no longer mean.)
      intended — list the live registry of declarations (pair, reason, holding/vanished),
                 and whether the human has the floor globally OFF.
      stats    — the cross-session telemetry: per-check finding-yield (a check that has
                 surfaced zero findings across many runs is pure cost) and intend-rate;
                 plus which perceptual ops `feel` callers exclude most.

    Intent-free defects (z-fight / non-manifold / flipped normals / degenerate) have NO
    suppression path — they are never wanted. Only clipping is governed by declared intent.
    """
    o = op.lower().strip()

    if o == "run":
        r = call_blender("validate_run", {"targets": targets, "verbose": verbose})
        if r.get("error"):
            return r["error"]
        return _format_run(r)

    if o in ("expect", "intend"):
        r = call_blender("validate_expect", {"a": a, "b": b, "reason": reason})
        if r.get("error"):
            return r["error"]
        e = r["intent"]
        return (f'declared intended: {e["check"]} {e["a"]}↔{e["b"]} — "{e["reason"]}". '
                f"It now collapses to a count, and will fire if it ever vanishes.")

    if o == "forget":
        r = call_blender("validate_forget", {"a": a, "b": b})
        if r.get("error"):
            return r["error"]
        return f"forgot the {a}↔{b} declaration — its tripwire is cleared."

    if o == "intended":
        r = call_blender("validate_intended")
        if r.get("error"):
            return r["error"]
        return _format_intended(r)

    if o == "stats":
        r = call_blender("validate_stats")
        if r.get("error"):
            return r["error"]
        return _format_stats(r)

    return unknown("validate", "op", op, _OPS)


def _format_run(r):
    if r.get("off"):
        return "validate: OFF (human override) — floor is down. You are blind; feel deliberately."
    if r.get("passed") and not r.get("excluded"):
        return "validate: clean — no defects, no undeclared clips."
    return r.get("line") or "validate: clean"


def _format_intended(r):
    intents = r.get("intents") or []
    lines = []
    if r.get("global_off"):
        lines.append("⚠ validate is globally OFF (human override) — the floor is down.")
    if not intents:
        lines.append("declared intents: (none)")
        return "\n".join(lines)
    lines.append(f"declared intents ({len(intents)}):")
    for e in intents:
        mark = "●" if e.get("status") == "holding" else "⚠ VANISHED —"
        lines.append(f'  {mark} {e["check"]} {e["a"]}↔{e["b"]} — "{e["reason"]}"')
    return "\n".join(lines)


def _format_stats(r):
    lines = ["validate — finding-yield per check (zero yield over many runs = pure cost):"]
    for c in r.get("validate") or []:
        y = "—" if c["yield"] is None else f"{c['yield'] * 100:.0f}%"
        lines.append(f"  {c['check']}: {c['findings']}/{c['runs']} runs (yield {y}), "
                     f"intend×{c['intend']}")
    feel = r.get("feel") or []
    if feel:
        lines.append("feel — exclusion rate per perceptual op (tunes op=all defaults):")
        for f in feel:
            lines.append(f"  {f['op']}: excluded×{f['excluded']}, auto-skipped×{f['auto_skipped']}")
    return "\n".join(lines)

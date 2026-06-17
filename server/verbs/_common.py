"""Shared helpers for the verb dispatch layer."""

from typing import Annotated
from pydantic import Field


def tag(t, desc: str):
    """Annotate a verb parameter with a schema `description`.

    SPEC-05 addendum (schema ergonomics): the structured JSON Schema FastMCP emits
    is otherwise flat — every param an equal citizen with no hint which subcommand
    it belongs to (that coupling lived only in the docstring). `tag` attaches a
    per-param description, by convention prefixed with the op(s) it serves —
    `tag(float, "[bevel/round] edge width (m)")` — so the model can filter the fat
    signature down to the params for the op it picked. Pair with a `Literal[...]`
    discriminator (which emits the valid-op `enum`).
    """
    return Annotated[t, Field(description=desc)]


def unknown(verb: str, field: str, value: str, valid) -> str:
    """Uniform error for an unrecognized discriminator value."""
    opts = " | ".join(valid)
    got = f"'{value}'" if value else "(empty)"
    return f"{verb}: unknown {field}={got}. Valid: {opts}"


def teach(verb: str, field: str, value: str, table: dict):
    """G23 move 3 — teaching error for a valid op missing a structural param.

    `unknown()` catches a bad discriminator; this catches the next class of mistake:
    the op IS valid but a param it structurally needs (a handle, a target, a point
    list — something with no safe default) is absent, so the handler would either
    silently no-op (move_to with no destination reports "moved" and changes nothing)
    or crash deep inside Blender. `table` maps the discriminator value →
    (ok, requirement, example): when the picked op is present but `ok` is False,
    hand back a one-line `needs … e.g. …` with a canonical call to copy. Returns
    None when satisfied, so call sites read:

        bad = teach("transform", "op", o, {...}); \\
        if bad: return bad
    """
    g = table.get(value)
    if g and not g[0]:
        return f"{verb} {field}={value}: needs {g[1]} — got none. e.g. {g[2]}"
    return None

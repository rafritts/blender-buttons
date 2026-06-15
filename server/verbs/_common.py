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

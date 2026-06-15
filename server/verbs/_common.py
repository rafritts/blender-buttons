"""Shared helpers for the verb dispatch layer."""


def unknown(verb: str, field: str, value: str, valid) -> str:
    """Uniform error for an unrecognized discriminator value."""
    opts = " | ".join(valid)
    got = f"'{value}'" if value else "(empty)"
    return f"{verb}: unknown {field}={got}. Valid: {opts}"

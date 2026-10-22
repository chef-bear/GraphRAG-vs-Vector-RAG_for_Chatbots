"""Scale levels: timestamp windows over the full dataset (SPEC §3.2)."""

from __future__ import annotations

# scale name -> inclusive max step
SCALES: dict[str, int] = {"s25": 24, "s50": 49, "s100": 99, "full": 199}


def max_step(scale: str) -> int:
    try:
        return SCALES[scale]
    except KeyError:
        raise ValueError(f"unknown scale {scale!r}; expected one of {list(SCALES)}") from None


def pg_database(scale: str) -> str:
    """One Postgres database per scale."""
    max_step(scale)
    return f"fraud_{scale}"

"""Answer types: the canonical JSON form of each, and how to parse a raw answer into it.

Canonical forms (also what ground truth stores):
  number         float
  integer        int
  ordered_list   [id, ...]                       order matters
  set            [id, ...]                       sorted ascending
  bool_set       {"in_loop": bool, "accounts": [id, ...]}
  set_of_cycles  [[id, ...], ...]                each cycle rotated to start at its smallest id
  set_label      {"accounts": [id, ...], "type": "cycle" | "fan_in" | "none"}
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

ANSWER_TYPES = (
    "number",
    "integer",
    "ordered_list",
    "set",
    "bool_set",
    "set_of_cycles",
    "set_label",
)
SCHEME_TYPES = ("cycle", "fan_in", "none")

FORMAT_HINTS = {
    "number": "a single number, e.g. 1234.56",
    "integer": "a single integer, e.g. 42",
    "ordered_list": "a JSON list of account_ids in rank order, e.g. [17, 4, 99]",
    "set": "a JSON list of account_ids (order does not matter; [] if none), e.g. [4, 17]",
    "bool_set": 'a JSON object {"in_loop": true|false, "accounts": [account_ids]}; '
    "accounts is [] when in_loop is false",
    "set_of_cycles": "a JSON list of loops, each loop a list of account_ids in transfer order, "
    "e.g. [[3, 8, 5], [10, 12, 11, 14]]; [] if none",
    "set_label": 'a JSON object {"accounts": [account_ids], "type": "cycle"|"fan_in"|"none"}',
}


class AnswerFormatError(ValueError):
    """The raw answer can't be read as the expected answer type."""


def _account_id(v: Any) -> int:
    if isinstance(v, bool):
        raise AnswerFormatError(f"expected an account_id, got {v!r}")
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    raise AnswerFormatError(f"expected an account_id, got {v!r}")


def _id_list(v: Any) -> list[int]:
    if not isinstance(v, list | tuple):
        raise AnswerFormatError(f"expected a list of account_ids, got {type(v).__name__}")
    return [_account_id(x) for x in v]


def _id_set(v: Any) -> list[int]:
    return sorted(set(_id_list(v)))


def rotate_cycle(cycle: Iterable[int]) -> list[int]:
    """Rotate a loop so it starts at its smallest account_id (direction is kept)."""
    c = list(cycle)
    if len(c) > 1 and c[0] == c[-1]:
        c = c[:-1]  # accept loops written with the start repeated at the end
    if not c:
        raise AnswerFormatError("empty loop")
    i = c.index(min(c))
    return c[i:] + c[:i]


def _number(v: Any) -> float:
    if isinstance(v, bool):
        raise AnswerFormatError(f"expected a number, got {v!r}")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise AnswerFormatError(f"expected a number, got {v!r}") from None
    if not math.isfinite(x):
        raise AnswerFormatError(f"expected a finite number, got {v!r}")
    return x


def _dict(v: Any, keys: tuple[str, ...]) -> dict:
    if not isinstance(v, dict) or not set(keys) <= set(v):
        raise AnswerFormatError(f"expected an object with keys {list(keys)}, got {v!r}")
    return v


def canonicalize(answer_type: str, value: Any) -> Any:
    """Parse `value` into the canonical form of `answer_type`, or raise AnswerFormatError."""
    if answer_type == "number":
        return _number(value)
    if answer_type == "integer":
        x = _number(value)
        if not x.is_integer():
            raise AnswerFormatError(f"expected an integer, got {value!r}")
        return int(x)
    if answer_type == "ordered_list":
        return _id_list(value)
    if answer_type == "set":
        return _id_set(value)
    if answer_type == "bool_set":
        d = _dict(value, ("in_loop", "accounts"))
        if not isinstance(d["in_loop"], bool):
            raise AnswerFormatError(f"in_loop must be true or false, got {d['in_loop']!r}")
        return {"in_loop": d["in_loop"], "accounts": _id_set(d["accounts"])}
    if answer_type == "set_of_cycles":
        if not isinstance(value, list):
            raise AnswerFormatError(f"expected a list of loops, got {type(value).__name__}")
        cycles = {tuple(rotate_cycle(_id_list(c))) for c in value}
        return [list(c) for c in sorted(cycles)]
    if answer_type == "set_label":
        d = _dict(value, ("accounts", "type"))
        if d["type"] not in SCHEME_TYPES:
            raise AnswerFormatError(f"type must be one of {SCHEME_TYPES}, got {d['type']!r}")
        return {"accounts": _id_set(d["accounts"]), "type": d["type"]}
    raise ValueError(f"unknown answer type {answer_type!r}")

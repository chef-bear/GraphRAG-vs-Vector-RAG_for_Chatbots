"""Score a predicted answer against ground truth (SPEC §6.2)."""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable
from dataclasses import asdict, dataclass
from typing import Any

from bench.answers import AnswerFormatError, canonicalize

NUMBER_ABS_TOL = 0.01
NUMBER_REL_TOL = 1e-6


@dataclass(frozen=True)
class Score:
    correct: bool
    f1: float | None = None
    precision: float | None = None
    recall: float | None = None
    kendall_tau: float | None = None
    failure: str | None = None  # "bad_answer_format" when the answer can't be parsed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def set_prf(predicted: Iterable[Hashable], truth: Iterable[Hashable]) -> tuple[float, float, float]:
    """Precision, recall, F1. Two empty sets agree perfectly."""
    p, t = set(predicted), set(truth)
    if not p and not t:
        return 1.0, 1.0, 1.0
    hits = len(p & t)
    precision = hits / len(p) if p else 0.0
    recall = hits / len(t) if t else 0.0
    f1 = 2 * precision * recall / (precision + recall) if hits else 0.0
    return precision, recall, f1


def kendall_tau(predicted: list[int], truth: list[int]) -> float | None:
    """Tau-a over the items both lists contain; None if fewer than 2 are shared."""
    in_pred = set(predicted)
    shared = [x for x in truth if x in in_pred]
    if len(shared) < 2:
        return None
    pos = {x: i for i, x in enumerate(predicted)}
    concordant = discordant = 0
    for i in range(len(shared)):
        for j in range(i + 1, len(shared)):
            if pos[shared[i]] < pos[shared[j]]:
                concordant += 1
            else:
                discordant += 1
    return (concordant - discordant) / (concordant + discordant)


def _set_score(predicted, truth, *, extra_ok: bool = True) -> Score:
    p, r, f = set_prf(predicted, truth)
    return Score(correct=extra_ok and f == 1.0, f1=f, precision=p, recall=r)


def score(answer_type: str, predicted_raw: Any, truth: Any) -> Score:
    """`truth` must already be canonical (as stored by the generator)."""
    try:
        pred = canonicalize(answer_type, predicted_raw)
    except AnswerFormatError:
        return Score(correct=False, failure="bad_answer_format")

    if answer_type == "number":
        ok = math.isclose(pred, truth, rel_tol=NUMBER_REL_TOL, abs_tol=NUMBER_ABS_TOL)
        return Score(correct=ok)
    if answer_type == "integer":
        return Score(correct=pred == truth)
    if answer_type == "ordered_list":
        return Score(correct=pred == truth, kendall_tau=kendall_tau(pred, truth))
    if answer_type == "set":
        return _set_score(pred, truth)
    if answer_type == "bool_set":
        return _set_score(
            pred["accounts"], truth["accounts"], extra_ok=pred["in_loop"] == truth["in_loop"]
        )
    if answer_type == "set_of_cycles":
        return _set_score(map(tuple, pred), map(tuple, truth))
    if answer_type == "set_label":
        return _set_score(pred["accounts"], truth["accounts"], extra_ok=pred["type"] == truth["type"])
    raise ValueError(f"unknown answer type {answer_type!r}")

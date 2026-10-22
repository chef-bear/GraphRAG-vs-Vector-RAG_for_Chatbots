"""The Family interface: one template per task family (SPEC §6.1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from bench.answers import FORMAT_HINTS, canonicalize
from bench.context import Context

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
# Literal placeholder for Cypher variable-length bounds, which can't be parameters.
K_TOKEN = "__K__"


class Family(ABC):
    name: str
    level: int
    answer_type: str
    reference: str | None = None  # reference query file stem; defaults to `name`

    @abstractmethod
    def sample(self, ctx: Context, rng: np.random.Generator, n: int) -> list[dict[str, Any]]:
        """Draw `n` parameter dicts. Each may carry "negative_control": True."""

    @abstractmethod
    def question(self, p: dict[str, Any]) -> str:
        """The natural-language task, without the answer-format line."""

    @abstractmethod
    def ground_truth(self, ctx: Context, p: dict[str, Any]) -> Any:
        """Canonical answer computed from staged data only (never from a DB)."""

    def prompt(self, p: dict[str, Any]) -> str:
        return f"{self.question(p)}\n\nAnswer format: {FORMAT_HINTS[self.answer_type]}."

    # --- reference queries -------------------------------------------------------------
    def _read(self, ext: str) -> str:
        return (REFERENCE_DIR / f"{self.reference or self.name}.{ext}").read_text()

    def query_params(self, p: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in p.items() if k != "negative_control"}

    def sql(self, p: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        params = self.query_params(p)
        if "amount" in params:  # exact NUMERIC comparison in Postgres
            params["amount"] = Decimal(f"{params['amount']:.2f}")
        return self._read("sql"), params

    def cypher(self, p: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        query = self._read("cypher")
        if "k" in p:
            query = query.replace(K_TOKEN, str(int(p["k"])))
        return query, self.query_params(p)

    def from_rows(self, rows: list[tuple]) -> Any:
        """Turn a reference query's rows into the canonical answer."""
        t = self.answer_type
        if t in ("number", "integer"):
            value = rows[0][0] if rows else 0
            return canonicalize(t, float(value) if t == "number" else value)
        if t in ("set", "ordered_list"):
            return canonicalize(t, [r[0] for r in rows])
        if t == "bool_set":
            ids = [r[0] for r in rows]
            return canonicalize(t, {"in_loop": bool(ids), "accounts": ids})
        if t == "set_of_cycles":
            return canonicalize(t, [list(r[0]) for r in rows])
        raise NotImplementedError(f"{self.name} must implement from_rows for {t}")


def pick(rng: np.random.Generator, pool, n: int, *, replace: bool = False) -> list:
    """Deterministic sample from a pool (sorted first so set order can't leak in)."""
    pool = sorted(pool)
    if not pool:
        return []
    n = min(n, len(pool)) if not replace else n
    idx = rng.choice(len(pool), size=n, replace=replace)
    return [pool[i] for i in idx]


def py(v: Any) -> Any:
    """numpy scalar -> plain Python, so params serialize to JSON."""
    return v.item() if isinstance(v, np.generic) else v

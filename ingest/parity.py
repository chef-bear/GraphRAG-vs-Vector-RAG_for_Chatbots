"""Cross-check Postgres and Neo4j against each other and against the staged Parquet.

Each check is written three ways (SQL, Cypher, pandas). All three must agree, so a
loader bug that affects both databases the same way still gets caught.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd

from ingest.stage import StagedData

log = logging.getLogger(__name__)

Number = int | float


@dataclass(frozen=True)
class Check:
    name: str
    sql: str
    cypher: str
    frame: Callable[[StagedData], Number]
    kind: str = "checksum"  # "count" for row/edge counts


def _tx(s: StagedData) -> pd.DataFrame:
    return s.transactions


def _clean(s: StagedData) -> pd.DataFrame:
    return s.transactions[~s.transactions.amount_is_sentinel]


def _pairs(s: StagedData) -> set[tuple[int, int]]:
    t = s.transactions
    return set(zip(t.sender_id.tolist(), t.receiver_id.tolist(), strict=True))


def _reciprocal_pairs(s: StagedData) -> int:
    pairs = _pairs(s)
    return sum((r, a) in pairs for a, r in pairs)


CHECKS: list[Check] = [
    Check(
        "accounts",
        "SELECT count(*) FROM accounts",
        "MATCH (a:Account) RETURN count(a)",
        lambda s: len(s.accounts),
        "count",
    ),
    Check(
        "transactions",
        "SELECT count(*) FROM transactions",
        "MATCH ()-[t:TRANSFER]->() RETURN count(t)",
        lambda s: len(s.transactions),
        "count",
    ),
    Check(
        "tx_id_sum",
        "SELECT sum(tx_id::bigint) FROM transactions",
        "MATCH ()-[t:TRANSFER]->() RETURN sum(t.tx_id)",
        lambda s: int(_tx(s).tx_id.sum()),
    ),
    Check(
        "amount_sum_non_sentinel",
        "SELECT sum(amount) FROM transactions WHERE NOT amount_is_sentinel",
        "MATCH ()-[t:TRANSFER]->() WHERE NOT t.amount_is_sentinel RETURN sum(t.amount)",
        lambda s: float(_clean(s).amount.sum()),
    ),
    Check(
        "amount_max_non_sentinel",
        "SELECT max(amount) FROM transactions WHERE NOT amount_is_sentinel",
        "MATCH ()-[t:TRANSFER]->() WHERE NOT t.amount_is_sentinel RETURN max(t.amount)",
        lambda s: float(_clean(s).amount.max()),
    ),
    Check(
        "sentinel_count",
        "SELECT count(*) FROM transactions WHERE amount_is_sentinel",
        "MATCH ()-[t:TRANSFER]->() WHERE t.amount_is_sentinel RETURN count(t)",
        lambda s: int(_tx(s).amount_is_sentinel.sum()),
    ),
    Check(
        "self_loop_count",
        "SELECT count(*) FROM transactions WHERE is_self_loop",
        "MATCH (a)-[t:TRANSFER]->(a) RETURN count(t)",
        lambda s: int(_tx(s).is_self_loop.sum()),
    ),
    Check(
        "distinct_pairs",
        "SELECT count(*) FROM (SELECT DISTINCT sender_id, receiver_id FROM transactions) p",
        "MATCH (a)-[:TRANSFER]->(b) WITH DISTINCT a, b RETURN count(*)",
        lambda s: len(_pairs(s)),
    ),
    Check(
        "reciprocal_pairs",
        "SELECT count(*) FROM (SELECT DISTINCT sender_id, receiver_id FROM transactions) p "
        "WHERE EXISTS (SELECT 1 FROM transactions t "
        "WHERE t.sender_id = p.receiver_id AND t.receiver_id = p.sender_id)",
        "MATCH (a)-[:TRANSFER]->(b) WITH DISTINCT a, b "
        "WHERE EXISTS { (b)-[:TRANSFER]->(a) } RETURN count(*)",
        _reciprocal_pairs,
    ),
    Check(
        "step_min",
        "SELECT min(step) FROM transactions",
        "MATCH ()-[t:TRANSFER]->() RETURN min(t.step)",
        lambda s: int(_tx(s).step.min()),
    ),
    Check(
        "step_max",
        "SELECT max(step) FROM transactions",
        "MATCH ()-[t:TRANSFER]->() RETURN max(t.step)",
        lambda s: int(_tx(s).step.max()),
    ),
    Check(
        "step_sum",
        "SELECT sum(step) FROM transactions",
        "MATCH ()-[t:TRANSFER]->() RETURN sum(t.step)",
        lambda s: int(_tx(s).step.astype("int64").sum()),
    ),
    Check(
        "init_balance_sum",
        "SELECT sum(init_balance) FROM accounts",
        "MATCH (a:Account) RETURN sum(a.init_balance)",
        lambda s: float(s.accounts.init_balance.sum()),
    ),
    Check(
        "behavior_id_sum",
        "SELECT sum(behavior_id) FROM accounts",
        "MATCH (a:Account) RETURN sum(a.behavior_id)",
        lambda s: int(s.accounts.behavior_id.astype("int64").sum()),
    ),
    Check(
        "distinct_customers",
        "SELECT count(DISTINCT customer_id) FROM accounts",
        "MATCH (a:Account) RETURN count(DISTINCT a.customer_id)",
        lambda s: int(s.accounts.customer_id.nunique()),
    ),
    Check(
        "distinct_senders",
        "SELECT count(DISTINCT sender_id) FROM transactions",
        "MATCH (a:Account) WHERE EXISTS { (a)-[:TRANSFER]->() } RETURN count(a)",
        lambda s: int(_tx(s).sender_id.nunique()),
    ),
    Check(
        "distinct_receivers",
        "SELECT count(DISTINCT receiver_id) FROM transactions",
        "MATCH (a:Account) WHERE EXISTS { ()-[:TRANSFER]->(a) } RETURN count(a)",
        lambda s: int(_tx(s).receiver_id.nunique()),
    ),
    Check(
        "accounts_without_outgoing",
        "SELECT count(*) FROM accounts a WHERE NOT EXISTS "
        "(SELECT 1 FROM transactions t WHERE t.sender_id = a.account_id)",
        "MATCH (a:Account) WHERE NOT EXISTS { (a)-[:TRANSFER]->() } RETURN count(a)",
        lambda s: int((~s.accounts.account_id.isin(_tx(s).sender_id)).sum()),
    ),
    Check(
        "amount_gt_1e6",
        "SELECT count(*) FROM transactions WHERE amount > 1000000",
        "MATCH ()-[t:TRANSFER]->() WHERE t.amount > 1000000 RETURN count(t)",
        lambda s: int((_tx(s).amount > 1e6).sum()),
    ),
    Check(
        "amount_zero",
        "SELECT count(*) FROM transactions WHERE amount = 0",
        "MATCH ()-[t:TRANSFER]->() WHERE t.amount = 0 RETURN count(t)",
        lambda s: int((_tx(s).amount == 0).sum()),
    ),
    Check(
        "max_out_degree",
        "SELECT max(c) FROM (SELECT count(*) AS c FROM transactions GROUP BY sender_id) x",
        "MATCH (a:Account)-[t:TRANSFER]->() WITH a, count(t) AS c RETURN max(c)",
        lambda s: int(_tx(s).groupby("sender_id").size().max()),
    ),
    Check(
        "endpoint_checksum",
        "SELECT sum(sender_id::bigint * 10007 + receiver_id) FROM transactions",
        "MATCH (a)-[t:TRANSFER]->(b) RETURN sum(a.account_id * 10007 + b.account_id)",
        lambda s: int(
            (_tx(s).sender_id.astype("int64") * 10007 + _tx(s).receiver_id.astype("int64")).sum()
        ),
    ),
    Check(
        "tx_step_checksum",
        "SELECT sum(tx_id::bigint * step) FROM transactions",
        "MATCH ()-[t:TRANSFER]->() RETURN sum(t.tx_id * t.step)",
        lambda s: int((_tx(s).tx_id.astype("int64") * _tx(s).step.astype("int64")).sum()),
    ),
    Check(
        "window_small_amounts",
        "SELECT count(*) FROM transactions WHERE step BETWEEN 10 AND 20 "
        "AND amount < 100 AND NOT amount_is_sentinel",
        "MATCH ()-[t:TRANSFER]->() WHERE 10 <= t.step <= 20 AND t.amount < 100 "
        "AND NOT t.amount_is_sentinel RETURN count(t)",
        lambda s: int(_clean(s).query("10 <= step <= 20 and amount < 100").shape[0]),
    ),
]


def normalize(value: Any) -> Number | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        # Postgres returns sum(bigint) as NUMERIC; keep whole numbers exact
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, bool):
        return int(value)
    return value


def values_match(a: Number | None, b: Number | None) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=0.01)


@dataclass(frozen=True)
class CheckResult:
    name: str
    kind: str
    staged: Number | None
    postgres: Number | None
    neo4j: Number | None

    @property
    def ok(self) -> bool:
        return values_match(self.staged, self.postgres) and values_match(self.staged, self.neo4j)


def run_parity(
    staged: StagedData,
    run_sql: Callable[[str], Any],
    run_cypher: Callable[[str], Any],
    checks: list[Check] = CHECKS,
) -> list[CheckResult]:
    """`run_sql`/`run_cypher` take a query and return its single scalar result."""
    results = []
    for c in checks:
        r = CheckResult(
            c.name,
            c.kind,
            normalize(c.frame(staged)),
            normalize(run_sql(c.sql)),
            normalize(run_cypher(c.cypher)),
        )
        (log.info if r.ok else log.error)(
            "%-26s staged=%s pg=%s neo4j=%s %s",
            r.name,
            r.staged,
            r.postgres,
            r.neo4j,
            "ok" if r.ok else "MISMATCH",
        )
        results.append(r)
    return results

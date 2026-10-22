"""Load staged data into Neo4j with batched UNWIND (SPEC §4.2).

Community Edition has a single user database, so each load replaces the graph.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

import neo4j
import pandas as pd

from core.db import neo4j_driver
from core.settings import Settings
from ingest.stage import AGENT_ACCOUNT_COLUMNS, AGENT_TRANSACTION_COLUMNS, StagedData

log = logging.getLogger(__name__)

BATCH_ROWS = 20_000

SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT account_id_unique IF NOT EXISTS "
    "FOR (a:Account) REQUIRE a.account_id IS UNIQUE",
]
INDEX_STATEMENTS = [
    "CREATE INDEX transfer_step IF NOT EXISTS FOR ()-[t:TRANSFER]-() ON (t.step)",
    "CREATE INDEX transfer_amount IF NOT EXISTS FOR ()-[t:TRANSFER]-() ON (t.amount)",
]
CREATE_ACCOUNTS = """
UNWIND $rows AS row
CREATE (:Account {account_id: row.account_id, customer_id: row.customer_id,
                  init_balance: row.init_balance, country: row.country,
                  account_type: row.account_type, behavior_id: row.behavior_id})
"""
CREATE_TRANSFERS = """
UNWIND $rows AS row
MATCH (s:Account {account_id: row.sender_id})
MATCH (r:Account {account_id: row.receiver_id})
CREATE (s)-[:TRANSFER {tx_id: row.tx_id, amount: row.amount, step: row.step,
                       tx_type: row.tx_type, amount_is_sentinel: row.amount_is_sentinel,
                       is_self_loop: row.is_self_loop}]->(r)
"""


def batches(df: pd.DataFrame, columns: list[str], size: int = BATCH_ROWS) -> Iterator[list[dict]]:
    """Yield lists of plain-Python row dicts (the driver can't send numpy scalars)."""
    for start in range(0, len(df), size):
        yield df[columns].iloc[start : start + size].to_dict("records")


def clear_graph(session: neo4j.Session) -> None:
    session.run("MATCH ()-[r]->() CALL (r) { DELETE r } IN TRANSACTIONS OF 50000 ROWS").consume()
    session.run("MATCH (n) CALL (n) { DELETE n } IN TRANSACTIONS OF 50000 ROWS").consume()


def load_neo4j(settings: Settings, staged: StagedData) -> dict[str, float]:
    """Replace the graph with `staged`. Returns timings in seconds."""
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    with neo4j_driver(settings) as driver, driver.session() as session:
        clear_graph(session)
        timings["clear_s"] = time.perf_counter() - t0
        for stmt in SCHEMA_STATEMENTS:
            session.run(stmt).consume()

        t1 = time.perf_counter()
        for rows in batches(staged.accounts, AGENT_ACCOUNT_COLUMNS):
            session.execute_write(
                lambda tx, rows=rows: tx.run(CREATE_ACCOUNTS, rows=rows).consume()
            )
        for rows in batches(staged.transactions, AGENT_TRANSACTION_COLUMNS):
            session.execute_write(
                lambda tx, rows=rows: tx.run(CREATE_TRANSFERS, rows=rows).consume()
            )
        timings["create_s"] = time.perf_counter() - t1

        t2 = time.perf_counter()
        for stmt in INDEX_STATEMENTS:
            session.run(stmt).consume()
        session.run("CALL db.awaitIndexes(600)").consume()
        timings["index_s"] = time.perf_counter() - t2

    timings["total_s"] = time.perf_counter() - t0
    log.info("neo4j loaded in %.1fs", timings["total_s"])
    return timings

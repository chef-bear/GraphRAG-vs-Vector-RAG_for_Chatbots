"""Run one query read-only with a timeout, on either DB, and time it.

Used by reference-query verification now and by the agent's run_query tool later.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import neo4j
import psycopg


@dataclass(frozen=True)
class QueryResult:
    rows: list[tuple]
    db_ms: float


def run_sql(
    conn: psycopg.Connection, query: str, params: dict[str, Any] | None = None
) -> QueryResult:
    """Execute in a READ ONLY transaction; the connection's role sets statement_timeout."""
    t0 = time.perf_counter()
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(query, params)
            rows = [tuple(r) for r in cur.fetchall()] if cur.description else []
    finally:
        db_ms = (time.perf_counter() - t0) * 1000
    return QueryResult(rows, db_ms)


def run_cypher(
    session: neo4j.Session, query: str, params: dict[str, Any] | None = None, *, timeout_s: float
) -> QueryResult:
    """Execute in a managed read transaction with a transaction timeout."""

    @neo4j.unit_of_work(timeout=timeout_s)
    def work(tx: neo4j.ManagedTransaction) -> list[tuple]:
        return [tuple(r.values()) for r in tx.run(query, params or {})]

    t0 = time.perf_counter()
    try:
        rows = session.execute_read(work)
    finally:
        db_ms = (time.perf_counter() - t0) * 1000
    return QueryResult(rows, db_ms)

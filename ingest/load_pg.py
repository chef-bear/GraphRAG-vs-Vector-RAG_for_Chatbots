"""Load staged data into Postgres: one database per scale, COPY, then indexes (SPEC §4.1)."""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path

import pandas as pd
import psycopg
from psycopg import sql

from core.db import pg_connect
from core.scales import pg_database
from core.settings import Settings
from ingest.stage import AGENT_ACCOUNT_COLUMNS, AGENT_TRANSACTION_COLUMNS, StagedData

log = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent / "sql"
COPY_CHUNK_ROWS = 200_000


def to_copy_csv(df: pd.DataFrame, columns: list[str]) -> str:
    """Serialize rows for COPY ... (FORMAT csv). Floats get exactly 2 decimals."""
    out = df[columns].copy()
    for col in columns:
        if pd.api.types.is_bool_dtype(out[col]):
            out[col] = out[col].map({True: "t", False: "f"})
    buf = io.StringIO()
    out.to_csv(buf, index=False, header=False, float_format="%.2f")
    return buf.getvalue()


def copy_frame(conn: psycopg.Connection, table: str, df: pd.DataFrame, columns: list[str]) -> None:
    stmt = sql.SQL("COPY {} ({}) FROM STDIN (FORMAT csv)").format(
        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns))
    )
    with conn.cursor() as cur, cur.copy(stmt) as copy:
        for start in range(0, len(df), COPY_CHUNK_ROWS):
            copy.write(to_copy_csv(df.iloc[start : start + COPY_CHUNK_ROWS], columns))


def recreate_database(settings: Settings, dbname: str) -> None:
    with pg_connect(settings, "postgres", autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(dbname))
        )
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))


def ensure_agent_role(settings: Settings) -> None:
    """Read-only login role with a statement timeout. Roles are cluster-wide."""
    role = sql.Identifier(settings.pg_agent_user)
    password = sql.Literal(settings.pg_agent_password)
    timeout = sql.Literal(f"{int(settings.query_timeout_s * 1000)}ms")
    with pg_connect(settings, "postgres", autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (settings.pg_agent_user,)
        ).fetchone()
        verb = "ALTER" if exists else "CREATE"
        conn.execute(
            sql.SQL(verb + " ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                role, password
            )
        )
        conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(role, timeout))
        conn.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(role))


def grant_agent(conn: psycopg.Connection, settings: Settings, dbname: str) -> None:
    role = sql.Identifier(settings.pg_agent_user)
    conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(dbname)))
    conn.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(dbname), role))
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
    conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(role))


def load_postgres(settings: Settings, scale: str, staged: StagedData) -> dict[str, float]:
    """Rebuild fraud_{scale} from staged data. Returns timings in seconds."""
    dbname = pg_database(scale)
    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    recreate_database(settings, dbname)
    ensure_agent_role(settings)
    with pg_connect(settings, dbname) as conn:
        conn.execute((SQL_DIR / "postgres_schema.sql").read_text())
        copy_frame(conn, "accounts", staged.accounts, AGENT_ACCOUNT_COLUMNS)
        copy_frame(conn, "transactions", staged.transactions, AGENT_TRANSACTION_COLUMNS)
        conn.commit()
        timings["copy_s"] = time.perf_counter() - t0

        t1 = time.perf_counter()
        conn.execute((SQL_DIR / "postgres_indexes.sql").read_text())
        grant_agent(conn, settings, dbname)
        conn.commit()
        timings["index_s"] = time.perf_counter() - t1

    with pg_connect(settings, dbname, autocommit=True) as conn:
        t2 = time.perf_counter()
        conn.execute("VACUUM ANALYZE")
        timings["analyze_s"] = time.perf_counter() - t2

    timings["total_s"] = time.perf_counter() - t0
    log.info("postgres %s loaded in %.1fs", dbname, timings["total_s"])
    return timings

"""SPEC §3.3: no label column, table, label or property may reach an agent-facing DB."""

import pytest

from core.db import pg_connect
from core.scales import SCALES, pg_database
from ingest.stage import LABEL_NAMES

pytestmark = pytest.mark.integration


def _existing_pg_databases(settings):
    with pg_connect(settings, "postgres", autocommit=True) as conn:
        rows = conn.execute("SELECT datname FROM pg_database").fetchall()
    names = {r[0] for r in rows}
    return [pg_database(s) for s in SCALES if pg_database(s) in names]


def test_postgres_has_no_label_columns_or_tables(settings):
    dbs = _existing_pg_databases(settings)
    assert dbs, "no fraud_* databases loaded"
    for db in dbs:
        with pg_connect(settings, db, autocommit=True) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
                )
            }
            columns = {
                r[0]
                for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
                )
            }
        assert tables == {"accounts", "transactions"}, db
        assert not columns & LABEL_NAMES, db


def test_neo4j_has_no_label_keys(neo4j_session):
    keys = {r[0].lower() for r in neo4j_session.run("CALL db.propertyKeys()")}
    labels = {r[0].lower() for r in neo4j_session.run("CALL db.labels()")}
    rel_types = {r[0].lower() for r in neo4j_session.run("CALL db.relationshipTypes()")}
    assert not keys & LABEL_NAMES
    assert labels == {"account"}
    assert rel_types == {"transfer"}

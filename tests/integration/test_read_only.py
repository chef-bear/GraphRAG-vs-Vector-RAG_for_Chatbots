"""The agent's DB access is read-only and time-limited (SPEC §4.1, §4.2)."""

import neo4j
import psycopg
import pytest

pytestmark = pytest.mark.integration


def test_pg_agent_role_can_read(pg_agent):
    assert pg_agent.execute("SELECT count(*) FROM accounts").fetchone()[0] == 10_000


def test_pg_agent_role_cannot_write(pg_agent):
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        pg_agent.execute("UPDATE accounts SET country = 'XX' WHERE account_id = 0")


def test_pg_agent_role_cannot_create(pg_agent):
    with pytest.raises(psycopg.Error):
        pg_agent.execute("CREATE TABLE t_hack (x int)")


def test_pg_agent_statement_timeout_set(pg_agent, settings):
    value = pg_agent.execute("SHOW statement_timeout").fetchone()[0]
    assert value == f"{int(settings.query_timeout_s)}s"


def test_neo4j_read_transaction_rejects_writes(neo4j_session):
    with pytest.raises(neo4j.exceptions.ClientError):
        neo4j_session.execute_read(lambda tx: tx.run("CREATE (:Hack)").consume())
    assert neo4j_session.run("MATCH (h:Hack) RETURN count(h)").single()[0] == 0

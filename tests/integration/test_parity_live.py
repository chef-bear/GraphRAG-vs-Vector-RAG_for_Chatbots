import pytest

from ingest.parity import run_parity
from ingest.stage import read_staged

pytestmark = pytest.mark.integration


def test_live_parity(settings, scale, pg_admin, neo4j_session):
    staged = read_staged(settings.staged_dir / scale)
    results = run_parity(
        staged,
        run_sql=lambda q: pg_admin.execute(q).fetchone()[0],
        run_cypher=lambda q: neo4j_session.run(q).single()[0],
    )
    assert [r.name for r in results if not r.ok] == []

"""One task per family, three-way, against the live DBs (Neo4j must hold the scale)."""

import pytest

from bench.generate import TASKS_DIR, read_tasks
from bench.verify import check_task
from core.db import pg_connect
from core.readonly import run_cypher, run_sql
from core.scales import pg_database

pytestmark = pytest.mark.integration


def test_reference_queries_agree_with_ground_truth(settings, scale, neo4j_session):
    tasks = read_tasks(TASKS_DIR / f"{scale}.jsonl")
    one_per_family = list({t["family"]: t for t in tasks}.values())

    with pg_connect(settings, pg_database(scale), agent=True) as conn:
        results = [
            check_task(
                t,
                lambda q, p: run_sql(conn, q, p),
                lambda q, p: run_cypher(neo4j_session, q, p, timeout_s=settings.query_timeout_s),
            )
            for t in one_per_family
        ]
    assert [r["task_id"] for r in results if not r["ok"]] == []

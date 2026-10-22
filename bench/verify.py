"""Three-way ground-truth agreement: python -m bench.verify --scale s50 (SPEC §6.3).

For every task, run the family's reference SQL (as the read-only agent role) and
reference Cypher (in a read transaction), convert the rows to a canonical answer, and
require Python ground truth == SQL == Cypher. Neo4j must hold the same scale.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from bench.families import FAMILIES
from bench.generate import TASKS_DIR, read_tasks
from bench.score import score
from core.db import neo4j_driver, pg_connect
from core.readonly import run_cypher, run_sql
from core.scales import SCALES, max_step, pg_database
from core.settings import load_settings

log = logging.getLogger(__name__)


def check_task(task: dict[str, Any], run_sql_fn, run_cypher_fn) -> dict[str, Any]:
    family = FAMILIES[task["family"]]
    p = task["params"]
    out: dict[str, Any] = {"task_id": task["task_id"], "family": task["family"]}
    for db, (query, params), runner in (
        ("postgres", family.sql(p), run_sql_fn),
        ("neo4j", family.cypher(p), run_cypher_fn),
    ):
        try:
            result = runner(query, params)
            answer = family.from_rows(result.rows)
            ok = score(task["answer_type"], answer, task["ground_truth"]).correct
            out[db] = {"ok": ok, "db_ms": round(result.db_ms, 1)}
            if not ok:
                out[db]["answer"] = answer
        except Exception as e:  # noqa: BLE001 - report every failure, keep going
            out[db] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:500]}
    out["ok"] = out["postgres"]["ok"] and out["neo4j"]["ok"]
    return out


def neo4j_loaded_scale(session) -> int:
    return session.run("MATCH ()-[t:TRANSFER]->() RETURN max(t.step)").single()[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bench.verify")
    parser.add_argument("--scale", required=True, choices=list(SCALES))
    parser.add_argument("--family", action="append", help="only these families (repeatable)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    settings = load_settings()
    tasks = read_tasks(TASKS_DIR / f"{args.scale}.jsonl")
    if args.family:
        tasks = [t for t in tasks if t["family"] in args.family]

    results = []
    with (
        pg_connect(settings, pg_database(args.scale), agent=True) as conn,
        neo4j_driver(settings) as driver,
        driver.session() as session,
    ):
        loaded = neo4j_loaded_scale(session)
        if loaded != max_step(args.scale):
            raise SystemExit(
                f"Neo4j holds max step {loaded}, not {args.scale}; run "
                f"`make ingest SCALE={args.scale}` first"
            )
        for task in tasks:
            r = check_task(
                task,
                lambda q, prm: run_sql(conn, q, prm),
                lambda q, prm: run_cypher(session, q, prm, timeout_s=settings.query_timeout_s),
            )
            (log.info if r["ok"] else log.error)(
                "%-40s pg=%s neo4j=%s", r["task_id"],
                r["postgres"].get("db_ms", r["postgres"].get("error")),
                r["neo4j"].get("db_ms", r["neo4j"].get("error")),
            )
            results.append(r)

    failed = [r for r in results if not r["ok"]]
    report = settings.reports_dir / f"verify_{args.scale}.json"
    report.write_text(json.dumps({
        "scale": args.scale, "n": len(results), "agree": len(results) - len(failed),
        "failed": failed, "results": results,
    }, indent=2, default=str) + "\n")
    log.info("%d/%d tasks agree three ways; report: %s", len(results) - len(failed),
             len(results), report)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

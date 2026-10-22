"""CLI: python -m ingest {validate,stage,load-pg,load-neo4j,parity,all} [--scale S]."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from core.scales import SCALES, pg_database
from core.settings import Settings, load_settings

log = logging.getLogger("ingest")


def update_json(path: Path, key: str, value: Any) -> None:
    """Merge `value` under `key` in a JSON report, keeping other keys."""
    data = json.loads(path.read_text()) if path.exists() else {}
    data[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def cmd_validate(settings: Settings, _scale: str) -> None:
    from ingest.raw import read_raw
    from ingest.validate import validate

    validate(read_raw(settings.raw_dir), settings.reports_dir / "data_profile.json")
    log.info("validate: all SPEC §2 facts reproduced")


def cmd_stage(settings: Settings, scale: str) -> None:
    from ingest.raw import read_raw
    from ingest.stage import build_staged, write_staged

    raw = read_raw(settings.raw_dir)
    for s in SCALES if scale == "all" else [scale]:
        staged = build_staged(raw, s)
        write_staged(staged, settings.staged_dir / s)
        update_json(
            settings.reports_dir / "scales.json",
            s,
            {
                "transactions": len(staged.transactions),
                "patterns": len(staged.patterns),
                "patterns_by_type": staged.patterns.alert_type.value_counts()
                .sort_index()
                .to_dict(),
            },
        )


def cmd_load_pg(settings: Settings, scale: str) -> None:
    from ingest.load_pg import load_postgres
    from ingest.stage import read_staged

    timings = load_postgres(settings, scale, read_staged(settings.staged_dir / scale))
    update_json(settings.reports_dir / "load_times.json", f"postgres/{scale}", timings)


def cmd_load_neo4j(settings: Settings, scale: str) -> None:
    from ingest.load_neo4j import load_neo4j
    from ingest.stage import read_staged

    timings = load_neo4j(settings, read_staged(settings.staged_dir / scale))
    update_json(settings.reports_dir / "load_times.json", f"neo4j/{scale}", timings)


def cmd_parity(settings: Settings, scale: str) -> None:
    from core.db import neo4j_driver, pg_connect
    from ingest.parity import run_parity
    from ingest.stage import read_staged

    staged = read_staged(settings.staged_dir / scale)
    with (
        pg_connect(settings, pg_database(scale)) as conn,
        neo4j_driver(settings) as driver,
        driver.session() as session,
    ):
        results = run_parity(
            staged,
            run_sql=lambda q: conn.execute(q).fetchone()[0],
            run_cypher=lambda q: session.run(q).single()[0],
        )
    failed = [r.name for r in results if not r.ok]
    update_json(
        settings.reports_dir / "parity.json",
        scale,
        {
            "ok": not failed,
            "checks": {
                r.name: {
                    "kind": r.kind,
                    "staged": r.staged,
                    "postgres": r.postgres,
                    "neo4j": r.neo4j,
                    "ok": r.ok,
                }
                for r in results
            },
        },
    )
    if failed:
        raise SystemExit(f"parity FAILED for {scale}: {failed}")
    log.info("parity: %d/%d checks agree for %s", len(results), len(results), scale)


def cmd_all(settings: Settings, scale: str) -> None:
    for step in (cmd_validate, cmd_stage, cmd_load_pg, cmd_load_neo4j, cmd_parity):
        step(settings, scale)


COMMANDS = {
    "validate": cmd_validate,
    "stage": cmd_stage,
    "load-pg": cmd_load_pg,
    "load-neo4j": cmd_load_neo4j,
    "parity": cmd_parity,
    "all": cmd_all,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ingest")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--scale", default="s25", choices=[*SCALES, "all"])
    args = parser.parse_args(argv)
    if args.scale == "all" and args.command not in ("stage", "validate"):
        parser.error("--scale all is only supported for `stage`; use `make ingest-all`")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    COMMANDS[args.command](load_settings(), args.scale)
    return 0


if __name__ == "__main__":
    sys.exit(main())

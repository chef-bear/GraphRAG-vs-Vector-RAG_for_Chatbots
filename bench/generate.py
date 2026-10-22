"""Generate benchmark tasks: python -m bench.generate --scale s50 --seed 42.

Writes bench/tasks/{scale}.jsonl, one task per line:
task_id, level, family, params, prompt, answer_type, ground_truth, negative_control.
Output is deterministic for a given (scale, seed).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from bench.context import Context
from bench.families import FAMILIES, PLAN
from core.scales import SCALES
from core.settings import load_settings

log = logging.getLogger(__name__)

TASKS_DIR = Path(__file__).resolve().parent / "tasks"


def answer_size(answer_type: str, truth: Any) -> int | None:
    if answer_type in ("set", "ordered_list", "set_of_cycles"):
        return len(truth)
    if answer_type in ("bool_set", "set_label"):
        return len(truth["accounts"])
    return None


def generate(ctx: Context, seed: int) -> list[dict[str, Any]]:
    tasks = []
    for index, (cls, n) in enumerate(PLAN):
        family = FAMILIES[cls.name]
        rng = np.random.default_rng([seed, index])
        params = family.sample(ctx, rng, n)
        if len(params) < n:
            log.warning("%s: only %d of %d instances available", family.name, len(params), n)
        for i, p in enumerate(params):
            tasks.append({
                "task_id": f"{ctx.scale}-{family.name}-{i:03d}",
                "level": family.level,
                "family": family.name,
                "params": {k: v for k, v in p.items() if k != "negative_control"},
                "prompt": family.prompt(p),
                "answer_type": family.answer_type,
                "ground_truth": family.ground_truth(ctx, p),
                "negative_control": bool(p.get("negative_control", False)),
            })
        if getattr(family, "stats", None):
            log.info("%s: %s", family.name, family.stats)
    return tasks


def summarize(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    by_family: dict[str, Any] = {}
    for t in tasks:
        f = by_family.setdefault(t["family"], {"level": t["level"], "n": 0, "negative_controls": 0,
                                               "sizes": []})
        f["n"] += 1
        f["negative_controls"] += t["negative_control"]
        size = answer_size(t["answer_type"], t["ground_truth"])
        if size is not None:
            f["sizes"].append(size)
    for f in by_family.values():
        sizes = f.pop("sizes")
        if sizes:
            f.update(size_min=min(sizes), size_median=float(np.median(sizes)),
                     size_max=max(sizes), empty=sum(s == 0 for s in sizes))
    return {
        "n_tasks": len(tasks),
        "by_level": dict(sorted(Counter(t["level"] for t in tasks).items())),
        "negative_controls": sum(t["negative_control"] for t in tasks),
        "families": by_family,
    }


def write_tasks(tasks: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for t in tasks:
            f.write(json.dumps(t, sort_keys=True) + "\n")


def read_tasks(path: Path) -> list[dict[str, Any]]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bench.generate")
    parser.add_argument("--scale", required=True, choices=list(SCALES))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    settings = load_settings()
    ctx = Context.load(settings.staged_dir, args.scale)
    tasks = generate(ctx, args.seed)
    write_tasks(tasks, TASKS_DIR / f"{args.scale}.jsonl")
    summary = summarize(tasks) | {"scale": args.scale, "seed": args.seed}
    report = settings.reports_dir / "tasks.json"
    data = json.loads(report.read_text()) if report.exists() else {}
    data[args.scale] = summary
    report.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    log.info("wrote %d tasks to %s", len(tasks), TASKS_DIR / f"{args.scale}.jsonl")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

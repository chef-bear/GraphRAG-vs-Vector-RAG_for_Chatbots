"""Family templates, the generator, and reference-query plumbing (no DB)."""

import json

import pytest

from bench.answers import FORMAT_HINTS, canonicalize
from bench.context import Context
from bench.families import FAMILIES, PLAN
from bench.families.base import K_TOKEN, REFERENCE_DIR
from bench.generate import generate, read_tasks, summarize, write_tasks
from bench.verify import check_task
from core.readonly import QueryResult
from core.settings import load_settings

STAGED = load_settings({}).staged_dir
needs_s25 = pytest.mark.skipif(
    not (STAGED / "s25" / "labels" / "patterns.parquet").exists(), reason="s25 not staged"
)


def test_registry_matches_plan():
    assert [cls.name for cls, _ in PLAN] == list(FAMILIES)
    assert {f.level for f in FAMILIES.values()} == {1, 2, 3, 4, 5}
    assert 100 <= sum(n for _, n in PLAN) <= 130


@pytest.mark.parametrize("family", FAMILIES.values(), ids=lambda f: f.name)
def test_reference_files_exist(family):
    stem = family.reference or family.name
    for ext in ("sql", "cypher"):
        assert (REFERENCE_DIR / f"{stem}.{ext}").read_text().strip()


def test_cypher_k_token_substituted():
    fam = FAMILIES["same_amount_chain_k"]
    query, params = fam.cypher({"x": 1, "amount": 5.0, "a": 0, "b": 10, "k": 3})
    assert K_TOKEN not in query and "*1..3]" in query
    assert "negative_control" not in params


def test_sql_amount_is_exact_decimal():
    from decimal import Decimal

    _, params = FAMILIES["same_amount_chain_k"].sql(
        {"x": 1, "amount": 17.17, "a": 0, "b": 10, "k": 2}
    )
    assert params["amount"] == Decimal("17.17")


def test_ring_queries_get_rule_constants():
    _, params = FAMILIES["ring_from_seed"].sql({"x": 4})
    assert {"span", "width", "min_senders", "cap"} <= set(params)


@pytest.mark.parametrize(
    "name,rows,expected",
    [
        ("acct_total_out", [(12.5,)], 12.5),
        ("acct_total_out", [], 0.0),
        ("acct_counterparties", [(3,)], 3),
        ("top_receivers", [(9,), (2,)], [9, 2]),
        ("fan_in_candidates", [(9,), (2,)], [2, 9]),
        ("cycle_membership", [], {"in_loop": False, "accounts": []}),
        ("cycle_membership", [(3,), (1,)], {"in_loop": True, "accounts": [1, 3]}),
        ("cycle_enumeration_window", [([4, 9, 6],)], [[4, 9, 6]]),
        ("ring_from_seed", [(5, "cycle"), (2, "fan_in")], [2, 5]),
        ("ring_type", [(5, "cycle"), (2, "cycle")], {"accounts": [2, 5], "type": "cycle"}),
        ("ring_type", [], {"accounts": [], "type": "none"}),
    ],
)
def test_from_rows(name, rows, expected):
    assert FAMILIES[name].from_rows(rows) == expected


def test_ring_type_rejects_mixed_types():
    with pytest.raises(ValueError):
        FAMILIES["ring_type"].from_rows([(1, "cycle"), (2, "fan_in")])


def test_check_task_reports_each_db():
    task = {
        "task_id": "t",
        "family": "acct_counterparties",
        "params": {"x": 1},
        "answer_type": "integer",
        "ground_truth": 4,
    }
    ok = check_task(
        task, lambda q, p: QueryResult([(4,)], 1.0), lambda q, p: QueryResult([(4,)], 2.0)
    )
    assert ok["ok"] and ok["neo4j"]["db_ms"] == 2.0

    def boom(q, p):
        raise RuntimeError("syntax")

    bad = check_task(task, lambda q, p: QueryResult([(5,)], 1.0), boom)
    assert not bad["ok"]
    assert bad["postgres"]["answer"] == 5 and "syntax" in bad["neo4j"]["error"]


@pytest.fixture(scope="module")
def tasks():
    return generate(Context.load(STAGED, "s25"), seed=42)


@needs_s25
class TestGeneratorOnRealData:
    def test_counts_and_ids(self, tasks):
        assert len(tasks) == sum(n for _, n in PLAN)
        assert len({t["task_id"] for t in tasks}) == len(tasks)

    def test_ground_truth_is_canonical_and_prompts_have_format(self, tasks):
        for t in tasks:
            assert canonicalize(t["answer_type"], t["ground_truth"]) == t["ground_truth"]
            assert FORMAT_HINTS[t["answer_type"]] in t["prompt"]

    def test_no_duplicate_instances(self, tasks):
        keys = [json.dumps([t["family"], t["params"]], sort_keys=True) for t in tasks]
        assert len(keys) == len(set(keys))

    def test_negative_controls_are_empty(self, tasks):
        for t in tasks:
            if t["negative_control"]:
                gt = t["ground_truth"]
                assert (gt if isinstance(gt, list) else gt["accounts"]) == [], t["task_id"]

    def test_prompts_do_not_leak_labels(self, tasks):
        for t in tasks:
            assert "alert" not in t["prompt"].lower() and "is_fraud" not in t["prompt"].lower()

    def test_deterministic(self, tasks):
        again = generate(Context.load(STAGED, "s25"), seed=42)
        assert json.dumps(again, sort_keys=True) == json.dumps(tasks, sort_keys=True)

    def test_jsonl_roundtrip_and_summary(self, tasks, tmp_path):
        write_tasks(tasks, tmp_path / "s25.jsonl")
        assert read_tasks(tmp_path / "s25.jsonl") == tasks
        s = summarize(tasks)
        assert s["n_tasks"] == len(tasks) and set(s["by_level"]) == {1, 2, 3, 4, 5}

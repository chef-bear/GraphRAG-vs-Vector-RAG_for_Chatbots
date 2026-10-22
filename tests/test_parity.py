from decimal import Decimal

from ingest.parity import CHECKS, normalize, run_parity, values_match
from ingest.stage import build_staged


def test_check_catalog():
    names = [c.name for c in CHECKS]
    assert len(names) == len(set(names))
    assert {c.name for c in CHECKS if c.kind == "count"} == {"accounts", "transactions"}
    assert sum(c.kind == "checksum" for c in CHECKS) >= 20
    assert all(c.sql.strip() and c.cypher.strip() for c in CHECKS)


def test_pandas_side_on_fixture(raw):
    s = build_staged(raw, "full")
    by_name = {c.name: c.frame(s) for c in CHECKS}
    assert by_name["transactions"] == 15
    assert by_name["sentinel_count"] == 1
    assert by_name["self_loop_count"] == 1
    # (6,8)/(8,6), (9,0)/(0,9) and the self-loop (8,8) are reciprocal
    assert by_name["reciprocal_pairs"] == 5
    assert by_name["accounts_without_outgoing"] == 1  # account 7 only receives


def test_values_match():
    assert values_match(3, 3) and not values_match(3, 4)
    assert values_match(1e10, 1e10 + 0.001)
    assert values_match(None, None) and not values_match(None, 0)


def test_normalize():
    assert normalize(Decimal("2.50")) == 2.5
    assert normalize(True) == 1


def test_run_parity_all_agree(raw):
    s = build_staged(raw, "full")
    truth = {c.sql: c.frame(s) for c in CHECKS} | {c.cypher: c.frame(s) for c in CHECKS}
    results = run_parity(s, truth.__getitem__, truth.__getitem__)
    assert all(r.ok for r in results)


def test_run_parity_detects_one_db_off(raw):
    s = build_staged(raw, "full")
    truth = {c.sql: c.frame(s) for c in CHECKS} | {c.cypher: c.frame(s) for c in CHECKS}
    off = CHECKS[1].cypher
    results = run_parity(s, truth.__getitem__, lambda q: truth[q] + (1 if q == off else 0))
    assert [r.name for r in results if not r.ok] == [CHECKS[1].name]

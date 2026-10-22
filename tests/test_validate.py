import json

import pytest

from ingest.profile import compute_profile
from ingest.validate import ValidationError, compare, flatten, validate


def test_profile_on_fixture(raw):
    p = compute_profile(raw)
    assert p["patterns"] == {
        "total": 3,
        "cycle": 2,
        "fan_in": 1,
        "tx_per_pattern_min": 1,
        "tx_per_pattern_max": 5,
        "tx_per_pattern_median": 4.0,
        "span_steps_min": 0,
        "span_steps_max": 4,
    }
    assert p["cycles"]["closed_length_5"] == 1
    assert p["cycles"]["not_closed"] == 1
    assert p["cycles"]["closed_time_ordered"] == 1
    assert p["fan_in"]["identical_amounts"] == 0
    assert p["fraud_accounts"]["never_in_pattern"] == 1  # account 9
    assert p["fraud_accounts"]["in_multiple_patterns"] == 4  # 1, 2, 3, 5
    dq = p["data_quality"]
    # the sentinel itself is also > 1e6
    assert (dq["sentinel_amount"], dq["self_loops"], dq["amount_gt_1e6"], dq["amount_zero"]) == (
        1,
        1,
        2,
        1,
    )
    assert p["alerts"]["fields_agree_with_transaction"]
    assert p["scales"]["s25"]["patterns_fully_inside"] == 2
    assert p["scales"]["s50"]["patterns_fully_inside"] == 3


def test_flatten():
    assert flatten({"a": {"b": 1, "c": {"d": 2}}, "e": 3}) == {"a.b": 1, "a.c.d": 2, "e": 3}


def test_compare_reports_mismatch_and_missing():
    problems = compare({"a": {"b": 1}}, {"a": {"b": 2, "c": 3}})
    assert any("a.b: expected 2, got 1" in p for p in problems)
    assert any("a.c: missing" in p for p in problems)


def test_compare_ignores_extra_profile_keys():
    assert compare({"a": 1, "extra": 5}, {"a": 1}) == []


def test_validate_fails_loudly_on_fixture_and_writes_report(raw, tmp_path):
    # The fixture is not the real dataset, so validation against SPEC §2 must fail.
    report = tmp_path / "profile.json"
    with pytest.raises(ValidationError, match="transactions.rows"):
        validate(raw, report)
    data = json.loads(report.read_text())
    assert data["ok"] is False and data["problems"]

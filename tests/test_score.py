import pytest

from bench.answers import AnswerFormatError, canonicalize, rotate_cycle
from bench.score import kendall_tau, score, set_prf

# --- canonicalize -----------------------------------------------------------------------


def test_rotate_cycle():
    assert rotate_cycle([5, 2, 9]) == [2, 9, 5]
    assert rotate_cycle([5, 2, 9, 5]) == [2, 9, 5]  # closing repeat dropped
    with pytest.raises(AnswerFormatError):
        rotate_cycle([])


@pytest.mark.parametrize("answer_type,raw,expected", [
    ("number", "12.5", 12.5),
    ("integer", 7.0, 7),
    ("ordered_list", [3, "1", 2.0], [3, 1, 2]),
    ("set", [3, 1, 3], [1, 3]),
    ("bool_set", {"in_loop": True, "accounts": [2, 1]}, {"in_loop": True, "accounts": [1, 2]}),
    ("set_of_cycles", [[5, 2, 9], [9, 5, 2], [1, 4]], [[1, 4], [2, 9, 5]]),
    ("set_label", {"accounts": [9, 1], "type": "fan_in"}, {"accounts": [1, 9], "type": "fan_in"}),
])
def test_canonicalize(answer_type, raw, expected):
    assert canonicalize(answer_type, raw) == expected


@pytest.mark.parametrize("answer_type,raw", [
    ("number", "abc"), ("number", True), ("number", float("nan")),
    ("integer", 2.5), ("set", 5), ("set", [1, True]), ("ordered_list", ["x"]),
    ("bool_set", {"in_loop": "yes", "accounts": []}), ("bool_set", {"accounts": []}),
    ("set_of_cycles", "loops"), ("set_label", {"accounts": [], "type": "ring"}),
])
def test_canonicalize_rejects(answer_type, raw):
    with pytest.raises(AnswerFormatError):
        canonicalize(answer_type, raw)


def test_unknown_type():
    with pytest.raises(ValueError):
        canonicalize("matrix", 1)


# --- score: one block per answer type ---------------------------------------------------


def test_number_tolerances():
    assert score("number", 100.005, 100.0).correct  # within 0.01 absolute
    assert not score("number", 100.02, 100.0).correct
    assert score("number", 1e9 + 500, 1e9).correct  # within 1e-6 relative
    assert not score("number", 1e9 + 5000, 1e9).correct


def test_integer_exact():
    assert score("integer", 42, 42).correct
    assert not score("integer", 41, 42).correct


def test_ordered_list_exact_and_tau():
    s = score("ordered_list", [1, 2, 3], [1, 2, 3])
    assert s.correct and s.kendall_tau == 1.0
    s = score("ordered_list", [3, 2, 1], [1, 2, 3])
    assert not s.correct and s.kendall_tau == -1.0
    assert score("ordered_list", [9, 8], [1, 2]).kendall_tau is None


def test_set_prf():
    s = score("set", [1, 2, 3], [2, 3, 4])
    assert not s.correct
    assert s.precision == pytest.approx(2 / 3) and s.recall == pytest.approx(2 / 3)
    assert score("set", [3, 1], [1, 3]).correct
    assert score("set", [], []).correct and score("set", [], []).f1 == 1.0
    assert score("set", [1], []).f1 == 0.0


def test_bool_set_needs_both_parts():
    truth = {"in_loop": True, "accounts": [1, 2]}
    assert score("bool_set", {"in_loop": True, "accounts": [2, 1]}, truth).correct
    s = score("bool_set", {"in_loop": False, "accounts": [1, 2]}, truth)
    assert not s.correct and s.f1 == 1.0


def test_set_of_cycles_rotation_invariant():
    truth = [[1, 4, 2], [3, 5, 6]]
    assert score("set_of_cycles", [[4, 2, 1], [6, 3, 5]], truth).correct
    s = score("set_of_cycles", [[1, 2, 4]], truth)  # reversed direction is a different loop
    assert not s.correct and s.f1 == 0.0


def test_set_label_needs_label():
    truth = {"accounts": [1, 2], "type": "cycle"}
    assert score("set_label", {"accounts": [1, 2], "type": "cycle"}, truth).correct
    assert not score("set_label", {"accounts": [1, 2], "type": "fan_in"}, truth).correct


def test_malformed_answer_is_bad_answer_format():
    s = score("set", "not a list", [1])
    assert not s.correct and s.failure == "bad_answer_format"


def test_helpers():
    assert set_prf([], [1]) == (0.0, 0.0, 0.0)
    assert kendall_tau([1, 3, 2], [1, 2, 3]) == pytest.approx(1 / 3)

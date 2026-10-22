import pytest

from ingest.stage import (
    AGENT_ACCOUNT_COLUMNS,
    AGENT_TRANSACTION_COLUMNS,
    LABEL_NAMES,
    build_staged,
    read_staged,
    write_staged,
)


def test_agent_columns_contain_no_labels():
    assert not LABEL_NAMES & set(AGENT_ACCOUNT_COLUMNS)
    assert not LABEL_NAMES & set(AGENT_TRANSACTION_COLUMNS)


def test_agent_frames_have_exact_columns(raw):
    s = build_staged(raw, "full")
    assert list(s.accounts.columns) == AGENT_ACCOUNT_COLUMNS
    assert list(s.transactions.columns) == AGENT_TRANSACTION_COLUMNS


def test_window_filters_transactions_not_accounts(raw):
    s = build_staged(raw, "s25")
    assert s.transactions.step.max() <= 24
    assert len(s.accounts) == 10
    assert len(s.tx_labels) == len(s.transactions)


def test_patterns_only_if_fully_inside_window(raw):
    assert sorted(build_staged(raw, "s25").patterns.alert_id) == [1, 2]
    s50 = build_staged(raw, "s50")
    assert sorted(s50.patterns.alert_id) == [1, 2, 3]
    assert set(s50.pattern_members.alert_id) == {1, 2, 3}
    assert set(build_staged(raw, "s25").pattern_members.alert_id) == {1, 2}


def test_flags(raw):
    t = build_staged(raw, "full").transactions
    assert t.amount_is_sentinel.sum() == 1
    assert t[t.amount_is_sentinel].amount.iloc[0] == pytest.approx(21474836.47)
    assert t[t.is_self_loop][["sender_id", "receiver_id"]].values.tolist() == [[8, 8]]


def test_labels_are_real_booleans(raw):
    s = build_staged(raw, "full")
    assert s.account_labels.is_fraud.dtype == bool
    assert s.account_labels.is_fraud.sum() == 9
    assert s.tx_labels.is_fraud.sum() == 10
    assert (s.tx_labels[s.tx_labels.is_fraud].alert_id != -1).all()


def test_roundtrip_and_agent_read_excludes_labels(raw, tmp_path):
    staged = build_staged(raw, "s50")
    write_staged(staged, tmp_path / "s50")
    agent = read_staged(tmp_path / "s50")
    assert agent.tx_labels is None and agent.patterns is None
    assert agent.transactions.equals(staged.transactions)
    full = read_staged(tmp_path / "s50", labels=True)
    assert full.pattern_members.equals(staged.pattern_members)


def test_read_staged_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="make stage"):
        read_staged(tmp_path / "s25")

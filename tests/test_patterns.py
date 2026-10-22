import pandas as pd

from ingest.patterns import is_time_ordered, loop_order, pattern_members, pattern_summary


def edges(*triples):
    """(sender, receiver, step) -> edges frame; TX_ID follows argument order."""
    return pd.DataFrame(
        {
            "SENDER_ACCOUNT_ID": [t[0] for t in triples],
            "RECEIVER_ACCOUNT_ID": [t[1] for t in triples],
            "TIMESTAMP": [t[2] for t in triples],
            "TX_ID": range(1, len(triples) + 1),
        }
    )


def test_loop_order_closed_cycle_starts_at_earliest_tx():
    e = edges((2, 3, 0), (3, 1, 0), (1, 2, 0))
    assert loop_order(e) == [2, 3, 1]


def test_loop_order_rejects_open_chain():
    assert loop_order(edges((1, 2, 0), (2, 3, 0))) is None


def test_loop_order_rejects_two_disjoint_loops():
    assert loop_order(edges((1, 2, 0), (2, 1, 0), (3, 4, 0), (4, 3, 0))) is None


def test_loop_order_rejects_self_loop_and_single_edge():
    assert loop_order(edges((1, 1, 0))) is None
    assert loop_order(edges((1, 2, 0))) is None


def test_time_ordered_walks_from_start():
    e = edges((1, 2, 1), (2, 3, 2), (3, 1, 3))
    assert is_time_ordered(e, [1, 2, 3])
    e = edges((1, 2, 5), (2, 3, 2), (3, 1, 3))
    assert not is_time_ordered(e, [1, 2, 3])


def test_pattern_summary_on_fixture(raw):
    p = pattern_summary(raw.alerts).set_index("alert_id")
    assert p.loc[1, "is_closed_cycle"] and p.loc[1, "cycle_length"] == 5
    assert p.loc[1, "is_time_ordered"]
    assert not p.loc[2, "is_closed_cycle"]
    assert p.loc[3, "n_receivers"] == 1 and p.loc[3, "n_senders"] == 4
    assert p.loc[3, "min_step"] == 30 and p.loc[3, "max_step"] == 33


def test_pattern_members_dedupes(raw):
    m = pattern_members(raw.alerts)
    assert m[m.alert_id == 1].account_id.tolist() == [0, 1, 2, 3, 4]
    assert m[m.alert_id == 3].account_id.tolist() == [1, 2, 3, 5, 7]
    assert not m.duplicated().any()

"""Ground-truth algorithms on tiny graphs with hand-checked answers."""

import pandas as pd

from bench import algorithms as alg

SENTINEL = 21474836.47


def tx(*rows):
    """(sender, receiver, amount, step) rows -> transactions frame."""
    df = pd.DataFrame(rows, columns=["sender_id", "receiver_id", "amount", "step"])
    df["tx_id"] = range(1, len(df) + 1)
    df["is_self_loop"] = df.sender_id == df.receiver_id
    df["amount_is_sentinel"] = df.amount == SENTINEL
    return df


def test_total_out_excludes_sentinel_and_window():
    t = tx((1, 2, 10.0, 0), (1, 3, 5.5, 5), (1, 4, SENTINEL, 5), (1, 2, 99.0, 9), (2, 1, 7.0, 5))
    assert alg.total_out(t, 1, 0, 5) == 15.5


def test_counterparties_excludes_self():
    t = tx((1, 2, 1, 0), (1, 2, 1, 1), (1, 3, 1, 0), (1, 1, 1, 0))
    assert alg.counterparties(t, 1) == 2


def test_top_receivers_ties_and_self_loops():
    t = tx(
        (1, 5, 1, 0),
        (2, 5, 1, 0),
        (1, 4, 1, 0),
        (2, 4, 1, 0),
        (3, 3, 1, 0),
        (1, 3, 1, 0),
        (1, 6, 1, 9),
    )
    # 4 and 5 tie at 2 senders -> smaller id first; 3's self-transfer doesn't count
    assert alg.top_receivers(t, 0, 5, 3) == [4, 5, 3]


def test_fan_in_candidates():
    rows = [(s, 9, 2.0, s) for s in (1, 2, 3, 4)]  # 4 senders, steps 1..4, one each
    rows += [(5, 8, 2.0, 1), (6, 8, 2.0, 1), (7, 8, 2.0, 2), (7, 8, 2.0, 3), (1, 8, 2.0, 2)]
    rows += [(1, 7, 50.0, 1), (2, 7, 2.0, 1), (3, 7, 2.0, 1), (4, 7, 2.0, 1)]  # one over cap
    t = tx(*rows)
    assert alg.fan_in_candidates(t, 0, 10, 7, 4, 5.0) == [9]


def test_same_amount_reach():
    t = tx(
        (1, 2, 5.0, 3),
        (2, 3, 5.0, 1),
        (3, 4, 5.0, 2),
        (3, 1, 5.0, 2),
        (2, 9, 6.0, 1),
        (4, 5, 5.0, 30),
    )
    assert alg.same_amount_reach(t, 1, 5.0, 0, 10, 1) == [2]
    assert alg.same_amount_reach(t, 1, 5.0, 0, 10, 3) == [2, 3, 4]  # 1 itself excluded


def test_time_respecting_reach_needs_strictly_increasing_steps():
    t = tx((1, 2, 1, 2), (2, 3, 1, 2), (2, 4, 1, 3), (4, 5, 1, 4), (1, 6, 1, 4), (6, 7, 1, 3))
    # 2->3 at the same step as 1->2 is not allowed; 6->7 happens before 1->6
    assert alg.time_respecting_reach(t, 1, 0, 5, 3) == [2, 4, 5, 6]
    assert alg.time_respecting_reach(t, 1, 0, 5, 1) == [2, 6]


def test_time_respecting_uses_earliest_arrival():
    # 2 is reachable at step 1 (via 1->2) and at step 3 (via 1->3->2); only the early
    # arrival lets 2->4 at step 2 be used
    t = tx((1, 2, 1, 1), (1, 3, 1, 2), (3, 2, 1, 3), (2, 4, 1, 2))
    assert alg.time_respecting_reach(t, 1, 0, 5, 2) == [2, 3, 4]


def test_loops_through():
    t = tx(
        (1, 2, 7.0, 1),
        (2, 3, 7.0, 9),
        (3, 1, 7.0, 4),  # loop, any time order
        (1, 4, 8.0, 1),
        (4, 1, 8.0, 2),  # 2-loop
        (1, 5, 9.0, 1),
        (5, 1, 3.0, 2),  # amounts differ
        (2, 2, 7.0, 3),
    )  # self-loop ignored
    assert alg.loops_through(t, 1, 0, 10) == [[1, 2, 3], [1, 4]]
    assert alg.loops_through(t, 1, 0, 8) == [[1, 4]]  # 2->3 at step 9 is outside


def test_loops_through_rejects_revisits_and_long_loops():
    t = tx(*[(a, b, 1.0, 0) for a, b in ((1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 1))])
    assert alg.loops_through(t, 1, 0, 10) == []  # 6 transfers > 5


def test_loops_in_window_canonical_and_lengths():
    t = tx(
        (5, 3, 2.0, 0),
        (3, 4, 2.0, 1),
        (4, 5, 2.0, 2),  # 3-loop -> [3, 4, 5]
        (1, 2, 4.0, 0),
        (2, 1, 4.0, 0),  # 2-loop excluded
        (7, 8, 6.0, 0),
        (8, 9, 6.0, 0),
        (9, 7, 6.0, 30),
    )  # outside window
    assert alg.loops_in_window(t, 0, 10) == [[3, 4, 5]]


def test_loops_within_span():
    t = tx(
        (1, 2, 3.0, 0),
        (2, 3, 3.0, 10),
        (3, 1, 3.0, 5),
        (1, 4, 3.0, 50),
        (4, 5, 3.0, 50),
        (5, 1, 3.0, 61),
    )
    assert alg.loops_within_span(t, 1, 10) == [[1, 2, 3]]  # second loop spans 11


def test_scheme_members_fan_in_from_sender_and_receiver():
    rows = [(s, 9, 2.0, 10 + 2 * i) for i, s in enumerate((1, 2, 3, 4))]
    rows += [(5, 9, 2.0, 40)]  # outside the 7-step window
    t = tx(*rows)
    kw = dict(cycle_span=10, fan_width=7, fan_min_senders=4, fan_cap=5.0)
    assert alg.scheme_members(t, 9, **kw) == {"cycle": [], "fan_in": [1, 2, 3, 4, 9]}
    assert alg.scheme_members(t, 2, **kw)["fan_in"] == [1, 2, 3, 4, 9]
    assert alg.scheme_members(t, 5, **kw) == {"cycle": [], "fan_in": []}

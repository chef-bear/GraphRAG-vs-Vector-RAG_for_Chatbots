"""Fraud-pattern structure derived from alerts.csv (one row per fraudulent transaction)."""

from __future__ import annotations

import pandas as pd


def loop_order(edges: pd.DataFrame) -> list[int] | None:
    """Return the loop's accounts if `edges` form one simple directed cycle, else None.

    `edges` has SENDER_ACCOUNT_ID, RECEIVER_ACCOUNT_ID, TX_ID. The walk starts at the
    sender of the earliest TX_ID, so the order is deterministic.
    """
    senders = edges["SENDER_ACCOUNT_ID"].tolist()
    receivers = edges["RECEIVER_ACCOUNT_ID"].tolist()
    if len(edges) < 2 or len(set(senders)) != len(edges) or set(senders) != set(receivers):
        return None
    if any(s == r for s, r in zip(senders, receivers, strict=True)):
        return None
    nxt = dict(zip(senders, receivers, strict=True))
    start = edges.sort_values("TX_ID")["SENDER_ACCOUNT_ID"].iloc[0]
    order, node = [start], nxt[start]
    while node != start:
        if node in order:
            return None
        order.append(node)
        node = nxt[node]
    return order if len(order) == len(edges) else None


def is_time_ordered(edges: pd.DataFrame, order: list[int]) -> bool:
    """True if timestamps never decrease when walking the loop in `order`."""
    step_by_sender = dict(zip(edges["SENDER_ACCOUNT_ID"], edges["TIMESTAMP"], strict=True))
    steps = [step_by_sender[a] for a in order]
    return all(b >= a for a, b in zip(steps, steps[1:], strict=False))


def pattern_summary(alerts: pd.DataFrame) -> pd.DataFrame:
    """One row per ALERT_ID with the structural facts used by validation and ground truth."""
    rows = []
    for alert_id, edges in alerts.groupby("ALERT_ID", sort=True):
        alert_type = edges["ALERT_TYPE"].iloc[0]
        order = loop_order(edges) if alert_type == "cycle" else None
        rows.append(
            {
                "alert_id": int(alert_id),
                "alert_type": alert_type,
                "n_tx": len(edges),
                "min_step": int(edges["TIMESTAMP"].min()),
                "max_step": int(edges["TIMESTAMP"].max()),
                "n_senders": edges["SENDER_ACCOUNT_ID"].nunique(),
                "n_receivers": edges["RECEIVER_ACCOUNT_ID"].nunique(),
                "n_distinct_amounts": edges["TX_AMOUNT"].nunique(),
                "is_closed_cycle": order is not None,
                "cycle_length": len(order) if order else 0,
                "is_time_ordered": bool(order) and is_time_ordered(edges, order),
            }
        )
    return pd.DataFrame(rows)


def pattern_members(alerts: pd.DataFrame) -> pd.DataFrame:
    """Distinct (alert_id, account_id) pairs: every sender and receiver in each pattern."""
    parts = [
        alerts[["ALERT_ID", col]].rename(columns={"ALERT_ID": "alert_id", col: "account_id"})
        for col in ("SENDER_ACCOUNT_ID", "RECEIVER_ACCOUNT_ID")
    ]
    members = pd.concat(parts).drop_duplicates()
    return members.sort_values(["alert_id", "account_id"]).reset_index(drop=True)

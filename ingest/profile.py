"""Compute the dataset facts listed in SPEC §2 from raw data (pure; no I/O)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from core.scales import SCALES
from ingest.patterns import pattern_members, pattern_summary
from ingest.raw import RawData

SENTINEL_AMOUNT = 21474836.47  # INT32_MAX / 100, AMLSim overflow sentinel
LARGE_AMOUNT = 1e6


def _tokens(s: pd.Series) -> list[str]:
    return sorted(s.astype(str).unique().tolist())


def compute_profile(raw: RawData) -> dict[str, Any]:
    acc, tx, al = raw.accounts, raw.transactions, raw.alerts
    pat = pattern_summary(al)
    members = pattern_members(al)
    cycles = pat[pat.alert_type == "cycle"]
    closed = cycles[cycles.is_closed_cycle]
    fan_in = pat[pat.alert_type == "fan_in"]

    acc_fraud = acc.loc[acc.IS_FRAUD == "true", "ACCOUNT_ID"]
    tx_fraud = tx.IS_FRAUD == "True"
    alert_accounts = set(members.account_id)
    patterns_per_account = members.groupby("account_id").alert_id.nunique()
    out_degree = tx.groupby("SENDER_ACCOUNT_ID").size()
    joined = al.merge(tx, on="TX_ID", how="left", suffixes=("", "_tx"), indicator=True)
    same_cols = ["SENDER_ACCOUNT_ID", "RECEIVER_ACCOUNT_ID", "TX_AMOUNT", "TIMESTAMP", "ALERT_ID"]

    return {
        "accounts": {
            "rows": len(acc),
            "account_id_min": int(acc.ACCOUNT_ID.min()),
            "account_id_max": int(acc.ACCOUNT_ID.max()),
            "account_id_unique": bool(acc.ACCOUNT_ID.is_unique),
            "customer_id_one_to_one": bool(acc.CUSTOMER_ID.is_unique),
            "behavior_id_min": int(acc.TX_BEHAVIOR_ID.min()),
            "behavior_id_max": int(acc.TX_BEHAVIOR_ID.max()),
            "is_fraud_tokens": _tokens(acc.IS_FRAUD),
            "country_values": _tokens(acc.COUNTRY),
            "account_type_values": _tokens(acc.ACCOUNT_TYPE),
        },
        "transactions": {
            "rows": len(tx),
            "tx_id_min": int(tx.TX_ID.min()),
            "tx_id_max": int(tx.TX_ID.max()),
            "tx_id_unique": bool(tx.TX_ID.is_unique),
            "step_min": int(tx.TIMESTAMP.min()),
            "step_max": int(tx.TIMESTAMP.max()),
            "is_fraud_tokens": _tokens(tx.IS_FRAUD),
            "is_fraud_true": int(tx_fraud.sum()),
            "with_alert_id": int((tx.ALERT_ID != -1).sum()),
            "tx_type_values": _tokens(tx.TX_TYPE),
            "unknown_account_refs": int(
                (~tx.SENDER_ACCOUNT_ID.isin(acc.ACCOUNT_ID)).sum()
                + (~tx.RECEIVER_ACCOUNT_ID.isin(acc.ACCOUNT_ID)).sum()
            ),
            "distinct_pairs": int(
                len(tx[["SENDER_ACCOUNT_ID", "RECEIVER_ACCOUNT_ID"]].drop_duplicates())
            ),
            "out_degree_senders": int(len(out_degree)),
            "out_degree_mean": round(float(out_degree.mean()), 2),
            "out_degree_min": int(out_degree.min()),
            "out_degree_max": int(out_degree.max()),
        },
        "alerts": {
            "rows": len(al),
            "is_fraud_tokens": _tokens(al.IS_FRAUD),
            "all_match_a_transaction": bool((joined._merge == "both").all()),
            "fields_agree_with_transaction": bool(
                all((joined[c] == joined[f"{c}_tx"]).all() for c in same_cols)
            ),
            "matched_transactions_all_fraud": bool((joined.IS_FRAUD_tx == "True").all()),
        },
        "patterns": {
            "total": len(pat),
            "cycle": int((pat.alert_type == "cycle").sum()),
            "fan_in": int((pat.alert_type == "fan_in").sum()),
            "tx_per_pattern_min": int(pat.n_tx.min()),
            "tx_per_pattern_max": int(pat.n_tx.max()),
            "tx_per_pattern_median": float(pat.n_tx.median()),
            "span_steps_min": int((pat.max_step - pat.min_step).min()),
            "span_steps_max": int((pat.max_step - pat.min_step).max()),
        },
        "cycles": {
            "closed": len(closed),
            "closed_length_5": int((closed.cycle_length == 5).sum()),
            "not_closed": int(len(cycles) - len(closed)),
            "not_closed_max_tx": int(cycles[~cycles.is_closed_cycle].n_tx.max()),
            "same_amount": int((cycles.n_distinct_amounts == 1).sum()),
            "closed_time_ordered": int(closed.is_time_ordered.sum()),
        },
        "fan_in": {
            "single_receiver": int((fan_in.n_receivers == 1).sum()),
            "four_distinct_senders": int((fan_in.n_senders == 4).sum()),
            "identical_amounts": int((fan_in.n_distinct_amounts == 1).sum()),
        },
        "fraud_accounts": {
            "total": int(len(acc_fraud)),
            "in_alerts": int(acc_fraud.isin(alert_accounts).sum()),
            "never_in_pattern": int((~acc_fraud.isin(alert_accounts)).sum()),
            "alert_accounts_not_flagged": int(len(alert_accounts - set(acc_fraud))),
            "in_multiple_patterns": int((patterns_per_account > 1).sum()),
        },
        "data_quality": {
            "sentinel_amount": int((tx.TX_AMOUNT == SENTINEL_AMOUNT).sum()),
            "amount_gt_1e6": int((tx.TX_AMOUNT > LARGE_AMOUNT).sum()),
            "amount_gt_1e6_fraud": int(((tx.TX_AMOUNT > LARGE_AMOUNT) & tx_fraud).sum()),
            "amount_zero": int((tx.TX_AMOUNT == 0).sum()),
            "amount_negative": int((tx.TX_AMOUNT < 0).sum()),
            "amount_more_than_2_decimals": int(
                ((tx.TX_AMOUNT * 100).round() != (tx.TX_AMOUNT * 100).round(6)).sum()
            ),
            "self_loops": int((tx.SENDER_ACCOUNT_ID == tx.RECEIVER_ACCOUNT_ID).sum()),
        },
        "scales": {
            name: {
                "max_step": last,
                "transactions": int((last >= tx.TIMESTAMP).sum()),
                "patterns_fully_inside": int((pat.max_step <= last).sum()),
            }
            for name, last in SCALES.items()
        },
    }

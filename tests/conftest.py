"""Shared fixtures: a tiny hand-built AMLSim-shaped dataset with known answers.

Accounts 0-9. Patterns:
  alert 1 (cycle, closed, time-ordered): 0->1->2->3->4->0, amount 50, steps 2-6
  alert 2 (cycle, not closed):           5->6, amount 20, step 3
  alert 3 (fan_in):                      1,2,3,5 -> 7, steps 30-33 (outside s25)
Background: a sentinel, a self-loop, a >1e6 amount and a zero amount.
Account 9 is flagged fraud but is in no pattern.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ingest.raw import RawData, read_raw

SENTINEL = 21474836.47

# (sender, receiver, amount, step, alert_id, alert_type)
FRAUD_TX = [
    (0, 1, 50.0, 2, 1, "cycle"),
    (1, 2, 50.0, 3, 1, "cycle"),
    (2, 3, 50.0, 4, 1, "cycle"),
    (3, 4, 50.0, 5, 1, "cycle"),
    (4, 0, 50.0, 6, 1, "cycle"),
    (5, 6, 20.0, 3, 2, "cycle"),
    (1, 7, 11.0, 30, 3, "fan_in"),
    (2, 7, 12.0, 31, 3, "fan_in"),
    (3, 7, 13.0, 32, 3, "fan_in"),
    (5, 7, 14.0, 33, 3, "fan_in"),
]
BACKGROUND_TX = [
    (6, 8, 10.5, 0),
    (8, 6, SENTINEL, 1),
    (8, 8, 7.25, 2),
    (9, 0, 2_000_000.0, 60),
    (0, 9, 0.0, 100),
]
FRAUD_ACCOUNTS = {0, 1, 2, 3, 4, 5, 6, 7, 9}


def make_raw_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    accounts = pd.DataFrame(
        {
            "ACCOUNT_ID": range(10),
            "CUSTOMER_ID": [f"C_{i}" for i in range(10)],
            "INIT_BALANCE": [100.0 + i for i in range(10)],
            "COUNTRY": "US",
            "ACCOUNT_TYPE": "I",
            "IS_FRAUD": ["true" if i in FRAUD_ACCOUNTS else "false" for i in range(10)],
            "TX_BEHAVIOR_ID": [1 + i % 5 for i in range(10)],
        }
    )
    rows = [(s, r, a, t, True, al) for s, r, a, t, al, _ in FRAUD_TX]
    rows += [(s, r, a, t, False, -1) for s, r, a, t in BACKGROUND_TX]
    transactions = pd.DataFrame(
        {
            "TX_ID": range(1, len(rows) + 1),
            "SENDER_ACCOUNT_ID": [r[0] for r in rows],
            "RECEIVER_ACCOUNT_ID": [r[1] for r in rows],
            "TX_TYPE": "TRANSFER",
            "TX_AMOUNT": [r[2] for r in rows],
            "TIMESTAMP": [r[3] for r in rows],
            "IS_FRAUD": ["True" if r[4] else "False" for r in rows],
            "ALERT_ID": [r[5] for r in rows],
        }
    )
    fraud = transactions[transactions.IS_FRAUD == "True"]
    alerts = pd.DataFrame(
        {
            "ALERT_ID": fraud.ALERT_ID.to_numpy(),
            "ALERT_TYPE": [t[5] for t in FRAUD_TX],
            "IS_FRAUD": "True",
            "TX_ID": fraud.TX_ID.to_numpy(),
            "SENDER_ACCOUNT_ID": fraud.SENDER_ACCOUNT_ID.to_numpy(),
            "RECEIVER_ACCOUNT_ID": fraud.RECEIVER_ACCOUNT_ID.to_numpy(),
            "TX_TYPE": "TRANSFER",
            "TX_AMOUNT": fraud.TX_AMOUNT.to_numpy(),
            "TIMESTAMP": fraud.TIMESTAMP.to_numpy(),
        }
    )
    return accounts, transactions, alerts


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    accounts, transactions, alerts = make_raw_frames()
    accounts.to_csv(tmp_path / "accounts.csv", index=False, float_format="%.2f")
    transactions.to_csv(tmp_path / "transactions.csv", index=False, float_format="%.2f")
    alerts.to_csv(tmp_path / "alerts.csv", index=False, float_format="%.2f")
    return tmp_path


@pytest.fixture
def raw(raw_dir: Path) -> RawData:
    return read_raw(raw_dir)

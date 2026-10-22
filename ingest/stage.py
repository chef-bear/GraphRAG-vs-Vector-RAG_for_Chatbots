"""Normalize raw data into per-scale Parquet (SPEC §3.1, §3.3).

Layout of data/staged/{scale}/:
  accounts.parquet, transactions.parquet   agent-facing; the only files the loaders read
  labels/account_labels.parquet            account_id, is_fraud
  labels/tx_labels.parquet                 tx_id, is_fraud, alert_id (-1 = none)
  labels/patterns.parquet                  patterns fully inside the scale window
  labels/pattern_members.parquet           alert_id, account_id for those patterns

Keeping labels in a separate directory makes label hygiene structural: loaders never
see a label column.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from core.scales import max_step
from ingest.patterns import pattern_members, pattern_summary
from ingest.profile import SENTINEL_AMOUNT
from ingest.raw import RawData, parse_bool

log = logging.getLogger(__name__)

AGENT_ACCOUNT_COLUMNS = [
    "account_id",
    "customer_id",
    "init_balance",
    "country",
    "account_type",
    "behavior_id",
]
AGENT_TRANSACTION_COLUMNS = [
    "tx_id",
    "sender_id",
    "receiver_id",
    "tx_type",
    "amount",
    "step",
    "amount_is_sentinel",
    "is_self_loop",
]
# Must never appear in an agent-facing table, node, relationship or property.
LABEL_NAMES = frozenset({"is_fraud", "alert_id", "alert_type", "alert", "alerts"})

_AGENT_FILES = {"accounts": "accounts.parquet", "transactions": "transactions.parquet"}
_LABEL_FILES = {
    "account_labels": "labels/account_labels.parquet",
    "tx_labels": "labels/tx_labels.parquet",
    "patterns": "labels/patterns.parquet",
    "pattern_members": "labels/pattern_members.parquet",
}


@dataclass(frozen=True)
class StagedData:
    accounts: pd.DataFrame
    transactions: pd.DataFrame
    account_labels: pd.DataFrame | None = None
    tx_labels: pd.DataFrame | None = None
    patterns: pd.DataFrame | None = None
    pattern_members: pd.DataFrame | None = None


def build_staged(raw: RawData, scale: str) -> StagedData:
    last = max_step(scale)
    acc, tx = raw.accounts, raw.transactions[last >= raw.transactions.TIMESTAMP]

    accounts = pd.DataFrame(
        {
            "account_id": acc.ACCOUNT_ID.astype("int32"),
            "customer_id": acc.CUSTOMER_ID,
            "init_balance": acc.INIT_BALANCE.astype("float64"),
            "country": acc.COUNTRY,
            "account_type": acc.ACCOUNT_TYPE,
            "behavior_id": acc.TX_BEHAVIOR_ID.astype("int16"),
        }
    )
    transactions = pd.DataFrame(
        {
            "tx_id": tx.TX_ID.astype("int32"),
            "sender_id": tx.SENDER_ACCOUNT_ID.astype("int32"),
            "receiver_id": tx.RECEIVER_ACCOUNT_ID.astype("int32"),
            "tx_type": tx.TX_TYPE,
            "amount": tx.TX_AMOUNT.astype("float64"),
            "step": tx.TIMESTAMP.astype("int16"),
            "amount_is_sentinel": tx.TX_AMOUNT == SENTINEL_AMOUNT,
            "is_self_loop": tx.SENDER_ACCOUNT_ID == tx.RECEIVER_ACCOUNT_ID,
        }
    ).reset_index(drop=True)

    account_labels = pd.DataFrame(
        {"account_id": accounts.account_id, "is_fraud": parse_bool(acc.IS_FRAUD, "true", "false")}
    )
    tx_labels = pd.DataFrame(
        {
            "tx_id": transactions.tx_id,
            "is_fraud": parse_bool(tx.IS_FRAUD, "True", "False").to_numpy(),
            "alert_id": tx.ALERT_ID.astype("int32").to_numpy(),
        }
    )
    # A pattern belongs to a scale only if all of its transactions fall in the window.
    patterns = pattern_summary(raw.alerts)
    patterns = patterns[patterns.max_step <= last].reset_index(drop=True)
    members = pattern_members(raw.alerts)
    members = members[members.alert_id.isin(patterns.alert_id)].reset_index(drop=True)

    log.info(
        "%s: %d accounts, %d transactions, %d patterns",
        scale,
        len(accounts),
        len(transactions),
        len(patterns),
    )
    return StagedData(accounts, transactions, account_labels, tx_labels, patterns, members)


def write_staged(staged: StagedData, out_dir: Path) -> None:
    for attr, rel in {**_AGENT_FILES, **_LABEL_FILES}.items():
        df = getattr(staged, attr)
        if df is None:
            continue
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
    log.info("wrote %s", out_dir)


def read_staged(scale_dir: Path, *, labels: bool = False) -> StagedData:
    """Read agent-facing tables; also read labels only when `labels=True`."""
    if not (scale_dir / _AGENT_FILES["transactions"]).exists():
        raise FileNotFoundError(f"no staged data in {scale_dir}; run `make stage` first")
    files = {**_AGENT_FILES, **(_LABEL_FILES if labels else {})}
    return StagedData(**{attr: pd.read_parquet(scale_dir / rel) for attr, rel in files.items()})

"""Read the three AMLSim CSVs exactly as shipped.

Boolean columns stay as raw strings here so validation can check their casing;
`parse_bool` converts them during staging.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ACCOUNT_COLUMNS = [
    "ACCOUNT_ID",
    "CUSTOMER_ID",
    "INIT_BALANCE",
    "COUNTRY",
    "ACCOUNT_TYPE",
    "IS_FRAUD",
    "TX_BEHAVIOR_ID",
]
TRANSACTION_COLUMNS = [
    "TX_ID",
    "SENDER_ACCOUNT_ID",
    "RECEIVER_ACCOUNT_ID",
    "TX_TYPE",
    "TX_AMOUNT",
    "TIMESTAMP",
    "IS_FRAUD",
    "ALERT_ID",
]
ALERT_COLUMNS = [
    "ALERT_ID",
    "ALERT_TYPE",
    "IS_FRAUD",
    "TX_ID",
    "SENDER_ACCOUNT_ID",
    "RECEIVER_ACCOUNT_ID",
    "TX_TYPE",
    "TX_AMOUNT",
    "TIMESTAMP",
]

_STR = {
    "IS_FRAUD": str,
    "CUSTOMER_ID": str,
    "COUNTRY": str,
    "ACCOUNT_TYPE": str,
    "TX_TYPE": str,
    "ALERT_TYPE": str,
}


@dataclass(frozen=True)
class RawData:
    accounts: pd.DataFrame
    transactions: pd.DataFrame
    alerts: pd.DataFrame


def _read(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"missing raw file: {path}")
    df = pd.read_csv(path, dtype={c: t for c, t in _STR.items() if c in columns})
    if list(df.columns) != columns:
        raise ValueError(f"{path.name}: expected columns {columns}, got {list(df.columns)}")
    return df


def read_raw(raw_dir: Path) -> RawData:
    return RawData(
        accounts=_read(raw_dir / "accounts.csv", ACCOUNT_COLUMNS),
        transactions=_read(raw_dir / "transactions.csv", TRANSACTION_COLUMNS),
        alerts=_read(raw_dir / "alerts.csv", ALERT_COLUMNS),
    )


def parse_bool(values: pd.Series, true: str, false: str) -> pd.Series:
    """Map exact `true`/`false` tokens to bool; any other value is an error."""
    mapped = values.map({true: True, false: False})
    bad = values[mapped.isna()]
    if not bad.empty:
        raise ValueError(
            f"{values.name}: unexpected boolean tokens {sorted(bad.astype(str).unique())[:5]} "
            f"(expected {true!r}/{false!r})"
        )
    return mapped.astype(bool)

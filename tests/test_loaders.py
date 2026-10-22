"""Pure parts of the loaders (no DB needed)."""

import csv
import io

from ingest.load_neo4j import CREATE_TRANSFERS, batches
from ingest.load_pg import SQL_DIR, to_copy_csv
from ingest.stage import AGENT_TRANSACTION_COLUMNS, LABEL_NAMES, build_staged


def test_copy_csv_formats_bools_and_amounts(raw):
    t = build_staged(raw, "full").transactions
    rows = list(csv.reader(io.StringIO(to_copy_csv(t, AGENT_TRANSACTION_COLUMNS))))
    assert len(rows) == len(t)
    by_id = {int(r[0]): r for r in rows}
    sentinel = by_id[int(t[t.amount_is_sentinel].tx_id.iloc[0])]
    assert sentinel[4] == "21474836.47" and sentinel[6] == "t" and sentinel[7] == "f"
    assert by_id[1][4] == "50.00"


def test_batches_yield_native_python_types(raw):
    t = build_staged(raw, "full").transactions
    chunks = list(batches(t, AGENT_TRANSACTION_COLUMNS, size=4))
    assert [len(c) for c in chunks] == [4, 4, 4, 3]
    row = chunks[0][0]
    assert type(row["tx_id"]) is int and type(row["amount"]) is float
    assert type(row["amount_is_sentinel"]) is bool


def test_schema_sql_has_no_label_columns():
    text = (SQL_DIR / "postgres_schema.sql").read_text().lower()
    assert not any(name in text.split() for name in LABEL_NAMES)


def test_neo4j_transfer_properties_match_agent_columns():
    for col in AGENT_TRANSACTION_COLUMNS:
        if col not in ("sender_id", "receiver_id"):
            assert f"{col}: row.{col}" in CREATE_TRANSFERS
    assert not any(name in CREATE_TRANSFERS.lower() for name in ("is_fraud", "alert_id"))

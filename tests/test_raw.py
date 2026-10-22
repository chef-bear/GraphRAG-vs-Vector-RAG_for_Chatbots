import pandas as pd
import pytest

from ingest.raw import parse_bool, read_raw


def test_read_raw_keeps_boolean_tokens_as_strings(raw):
    assert set(raw.accounts.IS_FRAUD) == {"true", "false"}
    assert set(raw.transactions.IS_FRAUD) == {"True", "False"}


def test_read_raw_rejects_wrong_columns(raw_dir):
    df = pd.read_csv(raw_dir / "accounts.csv").drop(columns=["COUNTRY"])
    df.to_csv(raw_dir / "accounts.csv", index=False)
    with pytest.raises(ValueError, match="expected columns"):
        read_raw(raw_dir)


def test_read_raw_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_raw(tmp_path)


def test_parse_bool_strict():
    s = pd.Series(["True", "False", "True"], name="IS_FRAUD")
    assert parse_bool(s, "True", "False").tolist() == [True, False, True]


def test_parse_bool_rejects_wrong_casing():
    s = pd.Series(["true", "False"], name="IS_FRAUD")
    with pytest.raises(ValueError, match="unexpected boolean tokens"):
        parse_bool(s, "True", "False")

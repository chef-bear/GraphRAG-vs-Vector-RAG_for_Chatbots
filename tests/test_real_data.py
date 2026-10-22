"""Runs against the real AMLSim CSVs when they are present in data/raw/."""

import pytest

from core.settings import load_settings
from ingest.raw import read_raw
from ingest.stage import build_staged
from ingest.validate import validate

RAW = load_settings({}).raw_dir
pytestmark = [
    pytest.mark.data,
    pytest.mark.skipif(not (RAW / "transactions.csv").exists(), reason="data/raw not present"),
]


@pytest.fixture(scope="module")
def real_raw():
    return read_raw(RAW)


def test_real_data_matches_spec(real_raw):
    validate(real_raw)


@pytest.mark.parametrize(
    "scale,n_tx,n_patterns",
    [
        ("s25", 160_480, 39),
        ("s50", 326_374, 91),
        ("s100", 657_561, 196),
        ("full", 1_323_234, 391),
    ],
)
def test_real_scales(real_raw, scale, n_tx, n_patterns):
    s = build_staged(real_raw, scale)
    assert len(s.transactions) == n_tx
    assert len(s.patterns) == n_patterns

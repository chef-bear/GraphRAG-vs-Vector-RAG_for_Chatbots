from pathlib import Path

import pytest

from core.scales import SCALES, max_step, pg_database
from core.settings import REPO_ROOT, load_settings


def test_scales_are_nested_windows():
    assert list(SCALES.values()) == sorted(SCALES.values())
    assert max_step("full") == 199


def test_unknown_scale_raises():
    with pytest.raises(ValueError, match="unknown scale"):
        max_step("s10")
    with pytest.raises(ValueError):
        pg_database("nope")


def test_pg_database_name():
    assert pg_database("s50") == "fraud_s50"


def test_settings_from_mapping():
    s = load_settings({"PG_PORT": "6000", "QUERY_TIMEOUT_S": "12.5", "DATA_DIR": "/x/data"})
    assert s.pg_port == 6000
    assert s.query_timeout_s == 12.5
    assert s.raw_dir == Path("/x/data/raw")


def test_relative_data_dir_resolves_to_repo():
    assert load_settings({}).data_dir == REPO_ROOT / "data"

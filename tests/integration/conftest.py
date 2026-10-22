"""Integration fixtures. Needs `make up` and `make ingest SCALE=$INTEGRATION_SCALE` first."""

from __future__ import annotations

import os

import pytest

from core.db import neo4j_driver, pg_connect
from core.scales import pg_database
from core.settings import load_settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def scale():
    return os.environ.get("INTEGRATION_SCALE", "s25")


@pytest.fixture(scope="session")
def pg_admin(settings, scale):
    with pg_connect(settings, pg_database(scale), autocommit=True) as conn:
        yield conn


@pytest.fixture
def pg_agent(settings, scale):
    with pg_connect(settings, pg_database(scale), agent=True) as conn:
        yield conn


@pytest.fixture(scope="session")
def neo4j_session(settings):
    with neo4j_driver(settings) as driver, driver.session() as session:
        yield session

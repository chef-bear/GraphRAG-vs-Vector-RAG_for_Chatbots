"""Runtime settings read from the environment (and `.env` when present)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    pg_host: str
    pg_port: int
    pg_admin_user: str
    pg_admin_password: str
    pg_agent_user: str
    pg_agent_password: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    query_timeout_s: float

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def staged_dir(self) -> Path:
        return self.data_dir / "staged"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from `env`, or from os.environ after loading `.env`."""
    if env is None:
        load_dotenv(REPO_ROOT / ".env")
        env = os.environ

    data_dir = Path(env.get("DATA_DIR", "data"))
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir

    return Settings(
        data_dir=data_dir,
        pg_host=env.get("PG_HOST", "localhost"),
        pg_port=int(env.get("PG_PORT", "5433")),
        pg_admin_user=env.get("PG_ADMIN_USER", "fraud_admin"),
        pg_admin_password=env.get("PG_ADMIN_PASSWORD", ""),
        pg_agent_user=env.get("PG_AGENT_USER", "fraud_agent"),
        pg_agent_password=env.get("PG_AGENT_PASSWORD", ""),
        neo4j_uri=env.get("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=env.get("NEO4J_USER", "neo4j"),
        neo4j_password=env.get("NEO4J_PASSWORD", ""),
        query_timeout_s=float(env.get("QUERY_TIMEOUT_S", "30")),
    )

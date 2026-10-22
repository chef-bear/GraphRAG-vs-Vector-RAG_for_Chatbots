"""Connection factories for Postgres and Neo4j."""

from __future__ import annotations

import neo4j
import psycopg

from core.settings import Settings


def pg_connect(
    settings: Settings, dbname: str, *, agent: bool = False, autocommit: bool = False
) -> psycopg.Connection:
    """Connect as the admin role, or as the read-only agent role when `agent=True`."""
    user, password = (
        (settings.pg_agent_user, settings.pg_agent_password)
        if agent
        else (settings.pg_admin_user, settings.pg_admin_password)
    )
    return psycopg.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        user=user,
        password=password,
        dbname=dbname,
        autocommit=autocommit,
    )


def neo4j_driver(settings: Settings) -> neo4j.Driver:
    return neo4j.GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )

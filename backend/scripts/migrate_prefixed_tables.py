"""Copy memorySystem prefixed tables from one database to another.

Usage:
    SOURCE_DATABASE_URL=... TARGET_DATABASE_URL=... python scripts/migrate_prefixed_tables.py
"""

from __future__ import annotations

import os
from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy import MetaData, Table, create_engine, text

TABLES = [
    "memory_system_users",
    "memory_system_job_runs",
    "memory_system_audit_logs",
    "memory_system_threads",
    "memory_system_sessions",
    "memory_system_messages",
    "memory_system_memories",
    "memory_system_model_providers",
]


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def reflect_tables(engine: sa.Engine, names: Iterable[str]) -> dict[str, Table]:
    metadata = MetaData()
    metadata.reflect(bind=engine, only=list(names))
    missing = [name for name in names if name not in metadata.tables]
    if missing:
        raise RuntimeError(f"Missing tables in {engine.url.render_as_string(hide_password=True)}: {missing}")
    return {name: metadata.tables[name] for name in names}


def table_rows(connection: sa.Connection, table: Table) -> list[dict]:
    return [dict(row._mapping) for row in connection.execute(sa.select(table)).all()]


def set_mysql_foreign_key_checks(connection: sa.Connection, enabled: bool) -> None:
    if connection.dialect.name == "mysql":
        connection.execute(text(f"SET FOREIGN_KEY_CHECKS={1 if enabled else 0}"))


def main() -> None:
    source_engine = create_engine(require_env("SOURCE_DATABASE_URL"), pool_pre_ping=True)
    target_engine = create_engine(require_env("TARGET_DATABASE_URL"), pool_pre_ping=True)
    source_tables = reflect_tables(source_engine, TABLES)
    target_tables = reflect_tables(target_engine, TABLES)

    with source_engine.connect() as source, target_engine.begin() as target:
        copied: dict[str, int] = {}
        set_mysql_foreign_key_checks(target, False)
        try:
            for name in reversed(TABLES):
                target.execute(target_tables[name].delete())
            for name in TABLES:
                rows = table_rows(source, source_tables[name])
                if rows:
                    target.execute(target_tables[name].insert(), rows)
                copied[name] = len(rows)
        finally:
            set_mysql_foreign_key_checks(target, True)

    for name, count in copied.items():
        print(f"{name}: {count}")


if __name__ == "__main__":
    main()

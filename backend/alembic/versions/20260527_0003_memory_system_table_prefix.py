"""prefix application tables

Revision ID: 20260527_0003
Revises: 20260526_0002
Create Date: 2026-05-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260527_0003"
down_revision: Union[str, None] = "20260526_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PREFIX = "memory_system_"
TABLES = [
    "users",
    "job_runs",
    "audit_logs",
    "threads",
    "sessions",
    "messages",
    "memories",
    "model_providers",
]


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def _rename_tables(pairs: list[tuple[str, str]]) -> None:
    if not pairs:
        return
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        rename_sql = ", ".join(f"`{old}` TO `{new}`" for old, new in pairs)
        op.execute(sa.text(f"RENAME TABLE {rename_sql}"))
        return
    for old, new in pairs:
        op.rename_table(old, new)


def upgrade() -> None:
    existing = _existing_tables()
    pairs = [
        (table, f"{PREFIX}{table}")
        for table in TABLES
        if table in existing and f"{PREFIX}{table}" not in existing
    ]
    _rename_tables(pairs)


def downgrade() -> None:
    existing = _existing_tables()
    pairs = [
        (f"{PREFIX}{table}", table)
        for table in reversed(TABLES)
        if f"{PREFIX}{table}" in existing and table not in existing
    ]
    _rename_tables(pairs)

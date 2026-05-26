"""add model providers

Revision ID: 20260526_0002
Revises: 20260526_0001
Create Date: 2026-05-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260526_0002"
down_revision: Union[str, None] = "20260526_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("chat_model", sa.String(length=120), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("protocol", sa.String(length=60), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_model_providers_is_default", "model_providers", ["is_default"])
    op.create_index("ix_model_providers_is_enabled", "model_providers", ["is_enabled"])
    op.create_index("ix_model_providers_name", "model_providers", ["name"])


def downgrade() -> None:
    op.drop_index("ix_model_providers_name", table_name="model_providers")
    op.drop_index("ix_model_providers_is_enabled", table_name="model_providers")
    op.drop_index("ix_model_providers_is_default", table_name="model_providers")
    op.drop_table("model_providers")

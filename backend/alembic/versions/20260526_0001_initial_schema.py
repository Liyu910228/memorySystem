"""initial schema

Revision ID: 20260526_0001
Revises:
Create Date: 2026-05-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260526_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PREFIX = "memory_system_"


def tn(name: str) -> str:
    return f"{PREFIX}{name}"


def upgrade() -> None:
    op.create_table(
        tn("users"),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("ldap_id", sa.String(length=120), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("ldap_id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_memory_system_users_ldap_id", tn("users"), ["ldap_id"])
    op.create_index("ix_memory_system_users_username", tn("users"), ["username"])

    op.create_table(
        tn("job_runs"),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        tn("audit_logs"),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey(f"{tn('users')}.id"), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=80), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        tn("threads"),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(f"{tn('users')}.id"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("is_main", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "is_main", name="uq_memory_system_user_main_thread"),
    )
    op.create_index("ix_memory_system_threads_user_id", tn("threads"), ["user_id"])

    op.create_table(
        tn("sessions"),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(f"{tn('users')}.id"), nullable=False),
        sa.Column("thread_id", sa.Integer(), sa.ForeignKey(f"{tn('threads')}.id"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_system_sessions_thread_id", tn("sessions"), ["thread_id"])
    op.create_index("ix_memory_system_sessions_user_id", tn("sessions"), ["user_id"])

    op.create_table(
        tn("messages"),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(f"{tn('users')}.id"), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey(f"{tn('sessions')}.id"), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_system_messages_session_id", tn("messages"), ["session_id"])
    op.create_index("ix_memory_system_messages_user_id", tn("messages"), ["user_id"])

    op.create_table(
        tn("memories"),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(f"{tn('users')}.id"), nullable=False),
        sa.Column("source_session_id", sa.Integer(), sa.ForeignKey(f"{tn('sessions')}.id"), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("layer", sa.String(length=40), nullable=False),
        sa.Column("memory_type", sa.String(length=60), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_system_memories_layer", tn("memories"), ["layer"])
    op.create_index("ix_memory_system_memories_status", tn("memories"), ["status"])
    op.create_index("ix_memory_system_memories_user_id", tn("memories"), ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_system_memories_user_id", table_name=tn("memories"))
    op.drop_index("ix_memory_system_memories_status", table_name=tn("memories"))
    op.drop_index("ix_memory_system_memories_layer", table_name=tn("memories"))
    op.drop_table(tn("memories"))
    op.drop_index("ix_memory_system_messages_user_id", table_name=tn("messages"))
    op.drop_index("ix_memory_system_messages_session_id", table_name=tn("messages"))
    op.drop_table(tn("messages"))
    op.drop_index("ix_memory_system_sessions_user_id", table_name=tn("sessions"))
    op.drop_index("ix_memory_system_sessions_thread_id", table_name=tn("sessions"))
    op.drop_table(tn("sessions"))
    op.drop_index("ix_memory_system_threads_user_id", table_name=tn("threads"))
    op.drop_table(tn("threads"))
    op.drop_table(tn("audit_logs"))
    op.drop_table(tn("job_runs"))
    op.drop_index("ix_memory_system_users_username", table_name=tn("users"))
    op.drop_index("ix_memory_system_users_ldap_id", table_name=tn("users"))
    op.drop_table(tn("users"))

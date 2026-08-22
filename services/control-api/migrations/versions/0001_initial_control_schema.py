"""schema control: runs, events, agent_tasks, idempotency_keys

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "control"

# O log auditavel nao pode ser reescrito. Constraint nao cobre UPDATE/DELETE, entao a
# garantia fica no banco, valendo para qualquer cliente — inclusive psql manual.
APPEND_ONLY_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {SCHEMA}.reject_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'control.events e append-only: % nao e permitido', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("briefing", sa.Text(), nullable=False),
        sa.Column("client_reference", sa.String(length=120)),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("current_task_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "last_sequence", sa.BigInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("last_sequence >= 0", name="ck_runs_last_sequence_non_negative"),
        schema=SCHEMA,
    )

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("task_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "meta",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], [f"{SCHEMA}.runs.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("run_id", "sequence", name="uq_events_run_sequence"),
        sa.CheckConstraint("sequence >= 1", name="ck_events_sequence_positive"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_events_run_sequence", "events", ["run_id", "sequence"], schema=SCHEMA
    )

    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(
        f"""
        CREATE TRIGGER trg_events_append_only
        BEFORE UPDATE OR DELETE ON {SCHEMA}.events
        FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.reject_event_mutation();
        """
    )

    op.create_table(
        "agent_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=71)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], [f"{SCHEMA}.runs.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_agent_tasks_attempt_positive"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_tasks_pending", "agent_tasks", ["state", "created_at"], schema=SCHEMA
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(length=255), primary_key=True),
        sa.Column("endpoint", sa.String(length=120), primary_key=True),
        sa.Column("request_hash", sa.String(length=71), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys", schema=SCHEMA)
    op.drop_index("ix_agent_tasks_pending", table_name="agent_tasks", schema=SCHEMA)
    op.drop_table("agent_tasks", schema=SCHEMA)
    op.execute(f"DROP TRIGGER IF EXISTS trg_events_append_only ON {SCHEMA}.events")
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.reject_event_mutation()")
    op.drop_index("ix_events_run_sequence", table_name="events", schema=SCHEMA)
    op.drop_table("events", schema=SCHEMA)
    op.drop_table("runs", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

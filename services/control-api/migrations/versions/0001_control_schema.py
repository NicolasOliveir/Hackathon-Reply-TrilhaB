"""Schema control: runs, events, agent_tasks e idempotency_keys.

Revision ID: 0001_control_schema
Revises:
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID

revision = "0001_control_schema"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "control"

# Sem este trigger, "append-only" seria apenas uma convenção de código: qualquer
# UPDATE direto no banco reescreveria a auditoria que o avaliador vai inspecionar.
APPEND_ONLY_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {SCHEMA}.deny_event_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'control.events e append-only: % nao e permitido', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

APPEND_ONLY_TRIGGER = f"""
CREATE TRIGGER events_append_only
BEFORE UPDATE OR DELETE ON {SCHEMA}.events
FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.deny_event_mutation();
"""


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "runs",
        sa.Column("run_id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("briefing", sa.Text(), nullable=False),
        sa.Column("briefing_hash", sa.String(71), nullable=False),
        sa.Column("client_reference", sa.String(120), nullable=True),
        sa.Column("current_task_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column(
            "last_sequence", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "last_sequence >= 0", name="ck_runs_last_sequence_non_negative"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_runs_state_created_at", "runs", ["state", "created_at"], schema=SCHEMA
    )

    op.create_table(
        "events",
        sa.Column("event_id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("actor", sa.String(32), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(120), nullable=False),
        sa.Column("causation_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("task_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("meta", JSONB(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{SCHEMA}.runs.run_id"],
            name="fk_events_run_id_runs",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("run_id", "sequence", name="uq_events_run_id_sequence"),
        sa.CheckConstraint("sequence >= 1", name="ck_events_sequence_starts_at_one"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_events_run_id_sequence", "events", ["run_id", "sequence"], schema=SCHEMA
    )
    op.create_index("ix_events_task_id", "events", ["task_id"], schema=SCHEMA)

    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(APPEND_ONLY_TRIGGER)

    op.create_table(
        "agent_tasks",
        sa.Column("task_id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempt", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("max_attempts", sa.SmallInteger(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(71), nullable=True),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{SCHEMA}.runs.run_id"],
            name="fk_agent_tasks_run_id_runs",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_agent_tasks_attempt_starts_at_one"),
        sa.CheckConstraint(
            "attempt <= max_attempts", name="ck_agent_tasks_attempt_within_max"
        ),
        sa.CheckConstraint("timeout_seconds > 0", name="ck_agent_tasks_timeout_positive"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_tasks_state_available_at",
        "agent_tasks",
        ["state", "available_at"],
        schema=SCHEMA,
    )
    op.create_index("ix_agent_tasks_run_id", "agent_tasks", ["run_id"], schema=SCHEMA)

    op.create_table(
        "idempotency_keys",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column("run_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("response_status", sa.SmallInteger(), nullable=False),
        sa.Column("response_body", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("scope", "key", name="uq_idempotency_keys_scope_key"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys", schema=SCHEMA)
    op.drop_index("ix_agent_tasks_run_id", table_name="agent_tasks", schema=SCHEMA)
    op.drop_index(
        "ix_agent_tasks_state_available_at", table_name="agent_tasks", schema=SCHEMA
    )
    op.drop_table("agent_tasks", schema=SCHEMA)
    op.execute(f"DROP TRIGGER IF EXISTS events_append_only ON {SCHEMA}.events")
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.deny_event_mutation()")
    op.drop_index("ix_events_task_id", table_name="events", schema=SCHEMA)
    op.drop_index("ix_events_run_id_sequence", table_name="events", schema=SCHEMA)
    op.drop_table("events", schema=SCHEMA)
    op.drop_index("ix_runs_state_created_at", table_name="runs", schema=SCHEMA)
    op.drop_table("runs", schema=SCHEMA)

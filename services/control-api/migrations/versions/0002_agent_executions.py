"""agent_executions: container, imagem, inicio/fim, exit code e motivo.

Revision ID: 0002_agent_executions
Revises: 0001_control_schema
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "0002_agent_executions"
down_revision = "0001_control_schema"
branch_labels = None
depends_on = None

SCHEMA = "control"


def upgrade() -> None:
    op.create_table(
        "agent_executions",
        sa.Column("execution_id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("run_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("attempt", sa.SmallInteger(), nullable=False),
        sa.Column("image", sa.String(255), nullable=False),
        sa.Column("container_id", sa.String(64), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("logs_tail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            [f"{SCHEMA}.agent_tasks.task_id"],
            name="fk_agent_executions_task_id_agent_tasks",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{SCHEMA}.runs.run_id"],
            name="fk_agent_executions_run_id_runs",
            ondelete="RESTRICT",
        ),
        # Idempotencia do despacho: uma tentativa, um container.
        sa.UniqueConstraint(
            "task_id", "attempt", name="uq_agent_executions_task_attempt"
        ),
        sa.CheckConstraint(
            "attempt >= 1", name="ck_agent_executions_attempt_starts_at_one"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_executions_run_id", "agent_executions", ["run_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_executions_run_id", table_name="agent_executions", schema=SCHEMA
    )
    op.drop_table("agent_executions", schema=SCHEMA)

"""model_invocations: auditoria de uso de modelo por tarefa.

Revision ID: 0003_model_invocations
Revises: 0002_agent_executions
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "0003_model_invocations"
down_revision = "0002_agent_executions"
branch_labels = None
depends_on = None

SCHEMA = "control"


def upgrade() -> None:
    op.create_table(
        "model_invocations",
        sa.Column("invocation_id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("task_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("effort", sa.String(16), nullable=True),
        # Hash, nao o texto: o prompt pode conter o briefing e esta tabela e
        # projetada no painel.
        sa.Column("prompt_hash", sa.String(71), nullable=False),
        sa.Column("prompt_chars", sa.Integer(), nullable=False),
        sa.Column("response_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stop_reason", sa.String(32), nullable=True),
        sa.Column("refusal_category", sa.String(64), nullable=True),
        sa.Column("route_reason", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{SCHEMA}.runs.run_id"],
            name="fk_model_invocations_run_id_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            [f"{SCHEMA}.agent_tasks.task_id"],
            name="fk_model_invocations_task_id_agent_tasks",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "prompt_chars >= 0", name="ck_model_invocations_prompt_chars_non_negative"
        ),
        sa.CheckConstraint(
            "input_tokens >= 0", name="ck_model_invocations_input_tokens_non_negative"
        ),
        sa.CheckConstraint(
            "output_tokens >= 0", name="ck_model_invocations_output_tokens_non_negative"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_model_invocations_run_id", "model_invocations", ["run_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_model_invocations_task_id", "model_invocations", ["task_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_invocations_task_id", table_name="model_invocations", schema=SCHEMA
    )
    op.drop_index(
        "ix_model_invocations_run_id", table_name="model_invocations", schema=SCHEMA
    )
    op.drop_table("model_invocations", schema=SCHEMA)

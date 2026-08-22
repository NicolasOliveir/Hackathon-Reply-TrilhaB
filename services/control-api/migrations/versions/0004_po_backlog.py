"""PO backlog projections and filtered task handoffs.

Revision ID: 0004_po_backlog
Revises: 0003_model_invocations
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_po_backlog"
down_revision = "0003_model_invocations"
branch_labels = None
depends_on = None

SCHEMA = "control"

def upgrade() -> None:
    op.add_column("agent_tasks", sa.Column("input_payload", postgresql.JSONB(), nullable=True), schema=SCHEMA)
    op.create_table("backlogs",
        sa.Column("backlog_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control.runs.run_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("backlog_hash", sa.String(71), nullable=False), sa.Column("briefing_hash", sa.String(71), nullable=False),
        sa.Column("product_goal", sa.Text(), nullable=False), sa.Column("constraints", postgresql.JSONB(), nullable=False),
        sa.Column("assumptions", postgresql.JSONB(), nullable=False), sa.Column("out_of_scope", postgresql.JSONB(), nullable=False),
        sa.Column("needs_human", postgresql.JSONB(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", name="uq_backlogs_run_id"), schema=SCHEMA)
    op.create_table("stories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control.runs.run_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("story_id", sa.String(32), nullable=False), sa.Column("title", sa.String(160), nullable=False), sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False), sa.Column("depends_on", postgresql.JSONB(), nullable=False), sa.Column("ready", sa.Boolean(), nullable=False), sa.Column("story_hash", sa.String(71), nullable=False),
        sa.UniqueConstraint("run_id", "story_id", name="uq_stories_run_story"), schema=SCHEMA)
    op.create_index("ix_stories_run_id", "stories", ["run_id"], schema=SCHEMA)
    op.create_table("acceptance_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control.runs.run_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("story_id", sa.String(32), nullable=False), sa.Column("criterion_id", sa.String(32), nullable=False), sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False), sa.Column("verification", sa.Text(), nullable=False),
        sa.UniqueConstraint("run_id", "story_id", "criterion_id", name="uq_criteria_run_story_criterion"), schema=SCHEMA)
    for name, text_column in (("po_decisions", "text"), ("backlog_coverage", "briefing_item")):
        columns = [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control.runs.run_id", ondelete="RESTRICT"), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.Column(text_column, sa.Text(), nullable=False)]
        if name == "backlog_coverage": columns.append(sa.Column("story_ids", postgresql.JSONB(), nullable=False))
        columns.append(sa.UniqueConstraint("run_id", "position", name=f"uq_{name}_run_position"))
        op.create_table(name, *columns, schema=SCHEMA)

def downgrade() -> None:
    for table in ("backlog_coverage", "po_decisions", "acceptance_criteria", "stories", "backlogs"):
        op.drop_table(table, schema=SCHEMA)
    op.drop_column("agent_tasks", "input_payload", schema=SCHEMA)

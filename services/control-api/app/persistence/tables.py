"""Schema `control` — as quatro tabelas da primeira iteracao.

`stories`, `acceptance_criteria`, `technical_decisions`, `test_executions`,
`agent_executions` e `artifacts` (ORQUESTRADOR.md secao 9.3) entram quando o fluxo real
PO -> Dev -> QA existir. Tabela vazia versionada antes do uso vira schema nao validado.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

CONTROL_SCHEMA = "control"


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(schema=CONTROL_SCHEMA)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    briefing: Mapped[str] = mapped_column(Text, nullable=False)
    client_reference: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    current_task_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))

    #: Contador monotonico por run. A alocacao de `sequence` acontece com UPDATE ...
    #: RETURNING nesta coluna, o que serializa concorrentes na propria linha e mantem a
    #: sequencia sem buraco.
    last_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint("last_sequence >= 0", name="ck_runs_last_sequence_non_negative"),
    )


class Event(Base):
    """Log append-only. UPDATE e DELETE sao bloqueados por trigger na migration."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(f"{CONTROL_SCHEMA}.runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    actor: Mapped[str] = mapped_column(String(32), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    task_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_events_run_sequence"),
        CheckConstraint("sequence >= 1", name="ck_events_sequence_positive"),
        Index("ix_events_run_sequence", "run_id", "sequence"),
    )


class AgentTask(Base):
    """Fila duravel. O consumo em I1-005 usa FOR UPDATE SKIP LOCKED sobre esta tabela."""

    __tablename__ = "agent_tasks"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(f"{CONTROL_SCHEMA}.runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Somente o hash do bearer token efemero (ORQUESTRADOR.md secao 8.1). O valor em
    #: claro existe apenas no momento da emissao, em I1-005.
    token_hash: Mapped[str | None] = mapped_column(String(71))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint("attempt >= 1", name="ck_agent_tasks_attempt_positive"),
        Index("ix_agent_tasks_pending", "state", "created_at"),
    )


class IdempotencyKey(Base):
    """Deduplicacao de comandos. Mesma chave + mesmo payload devolve a resposta gravada;
    mesma chave + payload diferente e conflito."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(120), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

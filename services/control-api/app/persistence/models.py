"""Modelo relacional do schema `control`.

Cobre o subconjunto da iteração 1 das tabelas mínimas de ORQUESTRADOR.md §9.3:
`runs`, `events`, `agent_tasks` e `idempotency_keys`. As demais tabelas entram
nas iterações que produzirem stories, ADRs e execuções de teste.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..config import CONTROL_SCHEMA

# Convenção de nomes explícita: sem ela o Alembic gera constraints anônimas e
# um autogenerate futuro não consegue removê-las por nome.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(schema=CONTROL_SCHEMA, naming_convention=NAMING_CONVENTION)


def _uuid_column(*args, **kwargs) -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), *args, **kwargs)


class Run(Base):
    __tablename__ = "runs"

    run_id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    briefing: Mapped[str] = mapped_column(Text, nullable=False)
    briefing_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    client_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    current_task_id: Mapped[uuid.UUID | None] = _uuid_column(nullable=True)
    # Contador de sequência do event log deste run. Vive na linha do run para que
    # o lock da linha serialize a numeração sem lock de tabela.
    last_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("last_sequence >= 0", name="last_sequence_non_negative"),
        Index("ix_runs_state_created_at", "state", "created_at"),
    )


class Event(Base):
    """Log append-only.

    A imutabilidade não é convenção: a migration instala um trigger que recusa
    UPDATE e DELETE nesta tabela. Sem ele, "append-only" seria apenas uma
    promessa no README.
    """

    __tablename__ = "events"

    event_id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = _uuid_column(
        ForeignKey(f"{CONTROL_SCHEMA}.runs.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor: Mapped[str] = mapped_column(String(32), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    causation_id: Mapped[uuid.UUID | None] = _uuid_column(nullable=True)
    task_id: Mapped[uuid.UUID | None] = _uuid_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_events_run_id_sequence"),
        CheckConstraint("sequence >= 1", name="sequence_starts_at_one"),
        Index("ix_events_run_id_sequence", "run_id", "sequence"),
        Index("ix_events_task_id", "task_id"),
    )


class AgentTask(Base):
    """Fila durável de tarefas.

    `available_at`, `locked_at` e `locked_by` existem para que I1-005 consuma
    com `FOR UPDATE SKIP LOCKED` sem alterar o schema.
    """

    __tablename__ = "agent_tasks"

    task_id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = _uuid_column(
        ForeignKey(f"{CONTROL_SCHEMA}.runs.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    # Somente o hash do token de tarefa é persistido; o valor em claro existe
    # apenas na resposta que entrega o token ao container.
    token_hash: Mapped[str | None] = mapped_column(String(71), nullable=True)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("attempt >= 1", name="attempt_starts_at_one"),
        CheckConstraint("attempt <= max_attempts", name="attempt_within_max"),
        CheckConstraint("timeout_seconds > 0", name="timeout_positive"),
        Index("ix_agent_tasks_state_available_at", "state", "available_at"),
        Index("ix_agent_tasks_run_id", "run_id"),
    )


class IdempotencyKey(Base):
    """Deduplicação de comandos.

    `scope` separa chaves de endpoints diferentes: o mesmo header
    `Idempotency-Key` é exigido em `POST /api/v1/runs` e em
    `POST /internal/v1/tasks/{task_id}/outputs`, e uma colisão entre os dois
    faria um comando responder com o resultado do outro.
    """

    __tablename__ = "idempotency_keys"

    id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    run_id: Mapped[uuid.UUID | None] = _uuid_column(nullable=True)
    response_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("scope", "key", name="uq_idempotency_keys_scope_key"),
    )

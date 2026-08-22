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
    # Contexto de handoff já filtrado pelo plano de controle. Para PO é nulo;
    # para Dev contém somente a story congelada, nunca o briefing bruto.
    input_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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


class AgentExecution(Base):
    """Uma tentativa de execução em container.

    A unique `(task_id, attempt)` é o que torna o despacho idempotente: um nó
    do grafo pode ser retomado, e o get-or-create por essa chave impede que a
    retomada suba um segundo container para a mesma tentativa.
    """

    __tablename__ = "agent_executions"

    execution_id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = _uuid_column(
        ForeignKey(f"{CONTROL_SCHEMA}.agent_tasks.task_id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID] = _uuid_column(
        ForeignKey(f"{CONTROL_SCHEMA}.runs.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    image: Mapped[str] = mapped_column(String(255), nullable=False)
    container_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("task_id", "attempt", name="uq_agent_executions_task_attempt"),
        CheckConstraint("attempt >= 1", name="attempt_starts_at_one"),
        Index("ix_agent_executions_run_id", "run_id"),
    )


class ModelInvocation(Base):
    """Auditoria de uso de modelo.

    O prompt **não** é persistido em claro: ele pode conter o briefing, e esta
    tabela é projetada no painel. O hash prova o que foi enviado sem transportar
    o conteúdo — mesma regra que mantém o briefing fora do event log.
    """

    __tablename__ = "model_invocations"

    invocation_id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = _uuid_column(
        ForeignKey(f"{CONTROL_SCHEMA}.runs.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = _uuid_column(
        ForeignKey(f"{CONTROL_SCHEMA}.agent_tasks.task_id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    effort: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prompt_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    prompt_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    response_chars: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    stop_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    refusal_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    route_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("prompt_chars >= 0", name="prompt_chars_non_negative"),
        CheckConstraint("input_tokens >= 0", name="input_tokens_non_negative"),
        CheckConstraint("output_tokens >= 0", name="output_tokens_non_negative"),
        Index("ix_model_invocations_run_id", "run_id"), Index("ix_model_invocations_task_id", "task_id"),
    )


class Backlog(Base):
    __tablename__ = "backlogs"
    backlog_id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = _uuid_column(
        ForeignKey(f"{CONTROL_SCHEMA}.runs.run_id", ondelete="RESTRICT"), nullable=False
    )
    backlog_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    briefing_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    product_goal: Mapped[str] = mapped_column(Text, nullable=False)
    constraints: Mapped[list] = mapped_column(JSONB, nullable=False)
    assumptions: Mapped[list] = mapped_column(JSONB, nullable=False)
    out_of_scope: Mapped[list] = mapped_column(JSONB, nullable=False)
    needs_human: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("run_id", name="uq_backlogs_run_id"),)


class Story(Base):
    __tablename__ = "stories"
    id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = _uuid_column(ForeignKey(f"{CONTROL_SCHEMA}.runs.run_id", ondelete="RESTRICT"), nullable=False)
    story_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    depends_on: Mapped[list] = mapped_column(JSONB, nullable=False)
    ready: Mapped[bool] = mapped_column(nullable=False)
    story_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    __table_args__ = (UniqueConstraint("run_id", "story_id", name="uq_stories_run_story"), Index("ix_stories_run_id", "run_id"))


class AcceptanceCriterion(Base):
    __tablename__ = "acceptance_criteria"
    id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = _uuid_column(ForeignKey(f"{CONTROL_SCHEMA}.runs.run_id", ondelete="RESTRICT"), nullable=False)
    story_id: Mapped[str] = mapped_column(String(32), nullable=False)
    criterion_id: Mapped[str] = mapped_column(String(32), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    verification: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("run_id", "story_id", "criterion_id", name="uq_criteria_run_story_criterion"),)


class PoDecision(Base):
    __tablename__ = "po_decisions"
    id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = _uuid_column(ForeignKey(f"{CONTROL_SCHEMA}.runs.run_id", ondelete="RESTRICT"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("run_id", "position", name="uq_po_decisions_run_position"),)


class BacklogCoverage(Base):
    __tablename__ = "backlog_coverage"
    id: Mapped[uuid.UUID] = _uuid_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = _uuid_column(ForeignKey(f"{CONTROL_SCHEMA}.runs.run_id", ondelete="RESTRICT"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    briefing_item: Mapped[str] = mapped_column(Text, nullable=False)
    story_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("run_id", "position", name="uq_backlog_coverage_run_position"),)


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

"""Event store append-only com sequencia por run, sem buraco e sem repeticao."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts import state_machine
from app.contracts.models import (
    CONTRACT_VERSION,
    EventActor,
    EventEnvelope,
    EventMeta,
    EventType,
    RunState,
)
from app.persistence.tables import Event, Run


class RunNotFound(Exception):
    def __init__(self, run_id: uuid.UUID) -> None:
        super().__init__(f"Run {run_id} nao encontrada")
        self.run_id = run_id


async def _allocate_sequence(session: AsyncSession, run_id: uuid.UUID) -> int:
    """Incrementa e devolve `last_sequence` da run.

    O `UPDATE ... RETURNING` trava a linha da run pelo restante da transacao, o que
    serializa dois appends concorrentes sem tabela de contador separada.
    """
    result = await session.execute(
        update(Run)
        .where(Run.id == run_id)
        .values(last_sequence=Run.last_sequence + 1)
        .returning(Run.last_sequence)
    )
    sequence = result.scalar_one_or_none()
    if sequence is None:
        raise RunNotFound(run_id)
    return int(sequence)


async def append(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    actor: EventActor,
    event_type: EventType,
    payload: dict[str, Any] | None = None,
    causation_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
    latency_ms: int = 0,
    container_id: str | None = None,
    model: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> EventEnvelope:
    """Anexa um evento e devolve o envelope ja no formato do contrato.

    Nao faz commit: o chamador decide o limite transacional. Isso e o que permite criar
    run, eventos e primeira tarefa de forma atomica.
    """
    sequence = await _allocate_sequence(session, run_id)

    envelope = EventEnvelope(
        contract_version=CONTRACT_VERSION,
        event_id=uuid.uuid4(),
        sequence=sequence,
        run_id=run_id,
        ts=datetime.now(tz=timezone.utc),
        actor=actor,
        type=event_type,
        correlation_id=correlation_id or str(run_id),
        causation_id=causation_id,
        task_id=task_id,
        payload=payload or {},
        meta=EventMeta(
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            container_id=container_id,
        ),
    )

    session.add(
        Event(
            id=envelope.event_id,
            run_id=envelope.run_id,
            sequence=envelope.sequence,
            ts=envelope.ts,
            actor=envelope.actor.value,
            type=envelope.type.value,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            task_id=envelope.task_id,
            payload=envelope.payload,
            meta=envelope.meta.model_dump(),
        )
    )
    await session.flush()
    return envelope


async def apply_transition(
    session: AsyncSession, *, run: Run, event_type: EventType
) -> RunState:
    """Move a run para o estado que o contrato define para o evento.

    Evento de registro puro (`RUN_CREATED`, `BRIEFING_RECEIVED`) nao aparece como gatilho
    de transicao e mantem o estado atual. Evento que deveria transicionar mas nao tem
    transicao valida a partir do estado atual levanta `InvalidTransition`.
    """
    current = RunState(run.state)
    if not state_machine.advances_state(event_type):
        return current

    target = state_machine.next_state(current, event_type)
    run.state = target.value
    await session.flush()
    return target


async def list_events(
    session: AsyncSession, *, run_id: uuid.UUID, after_sequence: int = 0
) -> list[EventEnvelope]:
    """Eventos em ordem de sequencia. `after_sequence` suporta a retomada de I1-006."""
    rows = (
        await session.execute(
            select(Event)
            .where(Event.run_id == run_id, Event.sequence > after_sequence)
            .order_by(Event.sequence)
        )
    ).scalars()

    return [
        EventEnvelope(
            contract_version=CONTRACT_VERSION,
            event_id=row.id,
            sequence=row.sequence,
            run_id=row.run_id,
            ts=row.ts,
            actor=EventActor(row.actor),
            type=EventType(row.type),
            correlation_id=row.correlation_id,
            causation_id=row.causation_id,
            task_id=row.task_id,
            payload=row.payload,
            meta=EventMeta.model_validate(row.meta),
        )
        for row in rows
    ]

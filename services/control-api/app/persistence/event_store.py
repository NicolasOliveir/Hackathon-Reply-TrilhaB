"""Event store append-only.

Regras que este módulo garante:

- `sequence` é contíguo e começa em 1 dentro de cada run;
- toda gravação acontece com a linha do run travada, o que serializa a
  numeração sem lock de tabela e sem depender de retry otimista;
- a transição de estado do run é validada contra o contrato antes de o evento
  ser gravado, e não depois.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Event, Run
from .state_machine import StateMachine

DEFAULT_META: dict[str, Any] = {
    "model": None,
    "tokens_in": 0,
    "tokens_out": 0,
    "latency_ms": 0,
    "container_id": None,
}


def sha256_of(text: str) -> str:
    """Hash no formato do contrato (`common.schema.json#/$defs/sha256`)."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class EventDraft:
    type: str
    actor: str = "system"
    payload: dict[str, Any] = field(default_factory=dict)
    task_id: uuid.UUID | None = None
    meta: dict[str, Any] | None = None
    # Quando True, a transição de estado do run é aplicada a partir do
    # contrato. Eventos puramente informativos (RUN_CREATED,
    # BRIEFING_RECEIVED) não constam na tabela de transições e passam False.
    drives_transition: bool = False


class EventStore:
    def __init__(self, session: AsyncSession, state_machine: StateMachine) -> None:
        self._session = session
        self._state_machine = state_machine

    async def lock_run(self, run_id: uuid.UUID) -> Run | None:
        """Trava a linha do run para o restante da transação."""
        result = await self._session.execute(
            select(Run).where(Run.run_id == run_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def append(
        self,
        run: Run,
        drafts: list[EventDraft],
        *,
        causation_id: uuid.UUID | None = None,
    ) -> list[Event]:
        """Grava eventos em ordem, encadeando causa e aplicando transições.

        A linha de `run` precisa estar travada nesta transação. Isso é
        automático quando o run acabou de ser inserido aqui; para um run
        existente, carregue-o com `lock_run` antes. Sem o lock, duas requisições
        concorrentes alocam o mesmo `sequence` e colidem na unique constraint.
        """
        appended: list[Event] = []
        sequence = run.last_sequence
        previous_id = causation_id
        if previous_id is None and sequence > 0:
            # Uma chamada posterior continua a cadeia do run em vez de criar
            # uma nova raiz visual para cada transação (scheduler/callback).
            previous_id = await self._session.scalar(
                select(Event.event_id).where(
                    Event.run_id == run.run_id,
                    Event.sequence == sequence,
                )
            )

        for draft in drafts:
            if draft.drives_transition:
                # Valida antes de gravar: um evento persistido que descreve uma
                # transição impossível corrompe a auditoria de forma permanente,
                # já que a tabela é append-only.
                run.state = self._state_machine.next_state(run.state, draft.type)

            sequence += 1
            event = Event(
                event_id=uuid.uuid4(),
                run_id=run.run_id,
                sequence=sequence,
                ts=utc_now(),
                actor=draft.actor,
                type=draft.type,
                correlation_id=str(run.run_id),
                causation_id=previous_id,
                task_id=draft.task_id,
                payload=draft.payload,
                meta={**DEFAULT_META, **(draft.meta or {})},
            )
            self._session.add(event)
            appended.append(event)
            previous_id = event.event_id

        run.last_sequence = sequence
        run.updated_at = utc_now()
        await self._session.flush()
        return appended

    async def list_events(
        self, run_id: uuid.UUID, *, after_sequence: int = 0, limit: int | None = None
    ) -> list[Event]:
        """Lê o log em ordem total, retomável por `sequence`.

        `after_sequence` é o contrato de retomada do SSE (`Last-Event-ID`) que
        I1-006 vai consumir.
        """
        statement = (
            select(Event)
            .where(Event.run_id == run_id, Event.sequence > after_sequence)
            .order_by(Event.sequence)
        )
        if limit is not None:
            statement = statement.limit(limit)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

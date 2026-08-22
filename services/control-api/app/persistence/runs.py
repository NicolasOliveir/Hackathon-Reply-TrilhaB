"""Casos de uso de execução (`run`).

A criação de um run é uma única transação: run, `RUN_CREATED`,
`BRIEFING_RECEIVED`, primeira `agent_task` e `TASK_QUEUED`. Ou tudo é gravado,
ou nada é — não existe estado intermediário em que um run exista sem o evento
que o explica.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from .event_store import EventDraft, EventStore, sha256_of, utc_now
from .models import AgentTask, Run
from .state_machine import StateMachine

# Papel do worker desta iteração. O fake worker prova a fatia distribuída antes
# de existir qualquer chamada a LLM.
FIRST_TASK_ROLE = "fake"


@dataclass(frozen=True)
class CreateRunCommand:
    briefing: str
    client_reference: str | None = None


class RunService:
    def __init__(
        self,
        session: AsyncSession,
        state_machine: StateMachine,
        settings: Settings,
    ) -> None:
        self._session = session
        self._settings = settings
        self._state_machine = state_machine
        self._events = EventStore(session, state_machine)

    async def create(self, command: CreateRunCommand) -> Run:
        run = Run(
            run_id=uuid.uuid4(),
            state=self._state_machine.initial_state,
            briefing=command.briefing,
            briefing_hash=sha256_of(command.briefing),
            client_reference=command.client_reference,
            current_task_id=None,
            last_sequence=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self._session.add(run)
        await self._session.flush()

        task = AgentTask(
            task_id=uuid.uuid4(),
            run_id=run.run_id,
            role=FIRST_TASK_ROLE,
            state="PENDING",
            attempt=1,
            max_attempts=self._settings.task_max_attempts,
            timeout_seconds=self._settings.task_timeout_seconds,
            token_hash=None,
            available_at=utc_now(),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self._session.add(task)
        await self._session.flush()

        await self._events.append(
            run,
            [
                EventDraft(
                    type="RUN_CREATED",
                    payload={"state": run.state},
                ),
                EventDraft(
                    type="BRIEFING_RECEIVED",
                    payload={
                        # O briefing bruto não entra no payload do evento. Ele
                        # vive apenas em `runs.briefing`, cujo acesso é do
                        # control-api; o log é projetado no painel e não deve
                        # carregar o texto do cliente.
                        "briefing_hash": run.briefing_hash,
                        "length": len(command.briefing),
                        "client_reference": command.client_reference,
                    },
                ),
                EventDraft(
                    type="TASK_QUEUED",
                    task_id=task.task_id,
                    payload={
                        "role": task.role,
                        "attempt": task.attempt,
                        "max_attempts": task.max_attempts,
                        "timeout_seconds": task.timeout_seconds,
                    },
                    drives_transition=True,
                ),
            ],
        )

        run.current_task_id = task.task_id
        await self._session.flush()
        return run

    async def get(self, run_id: uuid.UUID) -> Run | None:
        result = await self._session.execute(select(Run).where(Run.run_id == run_id))
        return result.scalar_one_or_none()

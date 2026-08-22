"""Criacao de execucao: run + eventos + primeira tarefa, em uma transacao."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.contracts import state_machine
from app.contracts.models import (
    CONTRACT_VERSION,
    AgentRole,
    CreateRunRequest,
    EventActor,
    EventType,
    RunLinks,
    RunResponse,
    RunState,
    TaskState,
)
from app.persistence import event_store
from app.persistence.tables import AgentTask, Run

CREATE_RUN_ENDPOINT = "POST /api/v1/runs"


def _links(run_id: uuid.UUID) -> RunLinks:
    base = get_settings().public_base_url.rstrip("/")
    return RunLinks(
        self=f"{base}/api/v1/runs/{run_id}",
        events=f"{base}/api/v1/runs/{run_id}/events",
    )


def to_response(run: Run) -> RunResponse:
    return RunResponse(
        contract_version=CONTRACT_VERSION,
        run_id=run.id,
        state=RunState(run.state),
        created_at=run.created_at,
        updated_at=run.updated_at,
        current_task_id=run.current_task_id,
        links=_links(run.id),
    )


def briefing_digest(briefing: str) -> str:
    return "sha256:" + hashlib.sha256(briefing.encode("utf-8")).hexdigest()


async def create_run(session: AsyncSession, request: CreateRunRequest) -> RunResponse:
    """Cria a execucao e enfileira a primeira tarefa.

    Cadeia de causalidade gravada, nesta ordem:

        RUN_CREATED -> BRIEFING_RECEIVED -> TASK_QUEUED

    `TASK_QUEUED` e o unico dos tres que move o estado: `RECEIVED -> WORKER_QUEUED`,
    conforme `packages/contracts/state-machine/v1.json`. Os dois primeiros sao registro.
    """
    run = Run(
        id=uuid.uuid4(),
        briefing=request.briefing,
        client_reference=request.client_reference,
        state=state_machine.initial_state().value,
        current_task_id=None,
        last_sequence=0,
    )
    session.add(run)
    await session.flush()

    created = await event_store.append(
        session,
        run_id=run.id,
        actor=EventActor.SYSTEM,
        event_type=EventType.RUN_CREATED,
        payload={"state": run.state},
    )

    briefing_event = await event_store.append(
        session,
        run_id=run.id,
        actor=EventActor.SYSTEM,
        event_type=EventType.BRIEFING_RECEIVED,
        payload={
            "briefing_hash": briefing_digest(request.briefing),
            "briefing_length": len(request.briefing),
            "client_reference": request.client_reference,
        },
        causation_id=created.event_id,
    )

    task = AgentTask(
        id=uuid.uuid4(),
        run_id=run.id,
        role=AgentRole.FAKE.value,
        state=TaskState.PENDING.value,
        attempt=1,
        timeout_seconds=get_settings().task_timeout_seconds,
        token_hash=None,
    )
    session.add(task)
    await session.flush()

    await event_store.append(
        session,
        run_id=run.id,
        actor=EventActor.SYSTEM,
        event_type=EventType.TASK_QUEUED,
        payload={
            "role": task.role,
            "attempt": task.attempt,
            "timeout_seconds": task.timeout_seconds,
        },
        causation_id=briefing_event.event_id,
        task_id=task.id,
    )
    await event_store.apply_transition(session, run=run, event_type=EventType.TASK_QUEUED)

    run.current_task_id = task.id
    await session.flush()

    return to_response(run)


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> Run | None:
    return (
        await session.execute(select(Run).where(Run.id == run_id))
    ).scalar_one_or_none()

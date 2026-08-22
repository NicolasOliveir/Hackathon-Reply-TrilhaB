"""Endpoints públicos de execução.

Contrato: `packages/contracts/openapi/v1/openapi.yaml`. Os modelos de
requisição e resposta são gerados a partir dos JSON Schemas — nenhuma regra de
validação é reescrita aqui.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...config import CONTRACT_VERSION, Settings, get_settings
from ...contracts.v1.create_run_request_schema import CreateRunRequest
from ...contracts.v1.run_response_schema import Links, RunResponse
from ...db import session_dependency, transaction
from ...persistence import idempotency
from ...persistence.models import AgentTask, Run
from ...persistence.event_store import EventDraft, EventStore, utc_now
from ...persistence.runs import CreateRunCommand, RunService
from ...persistence.state_machine import load_state_machine

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])

IDEMPOTENCY_SCOPE = "create_run"


def _to_response(run: Run, settings: Settings) -> RunResponse:
    base = f"{settings.public_base_url}/api/v1/runs/{run.run_id}"
    return RunResponse(
        contract_version=CONTRACT_VERSION,
        run_id=run.run_id,
        state=run.state,
        created_at=run.created_at,
        updated_at=run.updated_at,
        current_task_id=run.current_task_id,
        links=Links(self=base, events=f"{base}/events"),
    )


def _serialize(response: RunResponse) -> dict[str, Any]:
    """Serializa no formato do contrato.

    `mode="json"` desembrulha os RootModel gerados (uuid, timestamp, uri) para
    string, que é o que o schema declara.
    """
    return response.model_dump(mode="json", by_alias=True)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=None,
    summary="Cria uma execução a partir de um briefing.",
    responses={
        status.HTTP_202_ACCEPTED: {"description": "Execução aceita."},
        status.HTTP_409_CONFLICT: {
            "description": "Idempotency key já usada com payload diferente."
        },
    },
)
async def create_run(
    payload: CreateRunRequest,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=255)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    request_hash = idempotency.hash_request(_serialize(payload))

    async with transaction() as session:
        try:
            replay = await idempotency.claim(
                session,
                scope=IDEMPOTENCY_SCOPE,
                key=idempotency_key,
                request_hash=request_hash,
            )
        except idempotency.IdempotencyConflict as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc

        if replay is not None:
            response.status_code = replay.status
            return replay.body

        service = RunService(
            session,
            load_state_machine(settings.state_machine_path),
            settings,
        )
        run = await service.create(
            CreateRunCommand(
                briefing=payload.briefing,
                client_reference=payload.client_reference,
            )
        )
        body = _serialize(_to_response(run, settings))
        await idempotency.record_response(
            session,
            scope=IDEMPOTENCY_SCOPE,
            key=idempotency_key,
            status=status.HTTP_202_ACCEPTED,
            body=body,
            run_id=run.run_id,
        )
        return body


@router.get(
    "/{run_id}",
    status_code=status.HTTP_200_OK,
    response_model=None,
    summary="Consulta o estado atual da execução.",
    responses={
        status.HTTP_200_OK: {"description": "Estado atual."},
        status.HTTP_404_NOT_FOUND: {"description": "Execução não encontrada."},
    },
)
async def get_run(
    run_id: uuid.UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(session_dependency)],
) -> dict[str, Any]:
    service = RunService(
        session, load_state_machine(settings.state_machine_path), settings
    )
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execução {run_id} não encontrada.",
        )
    return _serialize(_to_response(run, settings))


@router.post("/{run_id}/cancel", status_code=status.HTTP_200_OK, response_model=None)
async def cancel_run(
    run_id: uuid.UUID,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Interrompe logicamente uma execução e revoga sua tarefa ativa."""
    async with transaction() as session:
        run = await session.get(Run, run_id, with_for_update=True)
        if run is None:
            raise HTTPException(status_code=404, detail="Criação não encontrada.")
        if run.state in {"COMPLETED", "FAILED", "CANCELED"}:
            return _serialize(_to_response(run, settings))

        machine = load_state_machine(settings.state_machine_path)
        if not machine.accepts(run.state, "RUN_CANCELED"):
            raise HTTPException(status_code=409, detail="Esta criação não pode mais ser cancelada.")

        tasks = (await session.execute(select(AgentTask).where(
            AgentTask.run_id == run_id,
            AgentTask.state.in_(["WAITING", "PENDING", "RUNNING"]),
        ))).scalars().all()
        for task in tasks:
            task.state = "CANCELED"
            task.token_hash = None
            task.updated_at = utc_now()

        await EventStore(session, machine).append(run, [EventDraft(
            type="RUN_CANCELED",
            actor="system",
            payload={"reason": "Cancelado pelo usuário"},
            drives_transition=True,
        )])
        return _serialize(_to_response(run, settings))

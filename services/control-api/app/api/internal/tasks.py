"""Endpoints internos consumidos pelos containers de agente.

Contrato: `packages/contracts/openapi/v1` — `/internal/v1/tasks/{task_id}/context`
e `/internal/v1/tasks/{task_id}/outputs`.

Regra que sustenta o desenho (ORQUESTRADOR §8.3): agentes **não escrevem
eventos**. Eles submetem saída de domínio; a API valida a transição e emite o
evento. É isso que impede um agente de se declarar aprovado.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from ...config import CONTRACT_VERSION, Settings, get_settings
from ...contracts.v1.fake_worker_output_schema import FakeWorkerOutput
from ...db import transaction
from ...model_gateway.gateway import usage_for_task
from ...orchestration import tokens
from ...persistence import idempotency
from ...persistence.event_store import EventDraft, EventStore, utc_now
from ...persistence.models import AgentTask, Run
from ...persistence.state_machine import load_state_machine

router = APIRouter(prefix="/internal/v1/tasks", tags=["internal"])

IDEMPOTENCY_SCOPE = "task_output"


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token de tarefa ausente.",
        )
    return authorization.split(" ", 1)[1].strip()


async def _authenticate(
    session,
    task_id: uuid.UUID,
    authorization: str | None,
    *,
    allow_terminal_replay: bool = False,
):
    """Autentica o portador contra a tarefa pedida.

    A mesma resposta 403 cobre token inválido e tarefa inexistente: distinguir
    os dois casos permitiria a um container enumerar tarefas de outros papéis.
    """
    presented = _bearer(authorization)
    task = (
        await session.execute(select(AgentTask).where(AgentTask.task_id == task_id))
    ).scalar_one_or_none()
    expired = (
        task is None
        or task.locked_at is None
        or utc_now() >= task.locked_at + timedelta(seconds=task.timeout_seconds)
    )
    if (
        task is None
        or not tokens.matches(presented, task.token_hash)
        or expired
        or (not allow_terminal_replay and task.state != "RUNNING")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token sem escopo ou vinculado a outra tarefa.",
        )
    return task


@router.get(
    "/{task_id}/context",
    status_code=status.HTTP_200_OK,
    response_model=None,
    summary="Retorna somente o contexto autorizado para a tarefa autenticada.",
    responses={
        status.HTTP_200_OK: {"description": "Contexto filtrado por papel e tarefa."},
        status.HTTP_403_FORBIDDEN: {
            "description": "Token sem escopo ou vinculado a outra tarefa."
        },
    },
)
async def get_task_context(
    task_id: uuid.UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    async with transaction() as session:
        task = await _authenticate(session, task_id, authorization)
        run = (
            await session.execute(select(Run).where(Run.run_id == task.run_id))
        ).scalar_one()
        issued = utc_now()
        receives_briefing = task.role in {"llm", "po"}
        context_manifest = (
            [
                {
                    "source_id": f"run:{run.run_id}:briefing",
                    "source_type": "briefing",
                    "hash": run.briefing_hash,
                }
            ]
            if receives_briefing
            else []
        )
        if task.role == "fake":
            task_input = {"echo": "first-distributed-slice"}
        elif receives_briefing:
            task_input = {"briefing": run.briefing}
        else:
            task_input = {}
        return {
            "contract_version": CONTRACT_VERSION,
            "task_id": str(task.task_id),
            "run_id": str(task.run_id),
            "role": task.role,
            "issued_at": issued.isoformat().replace("+00:00", "Z"),
            "expires_at": (task.locked_at + timedelta(seconds=task.timeout_seconds))
            .isoformat()
            .replace("+00:00", "Z"),
            "scopes": tokens.scopes_for(task.role),
            "context_manifest": context_manifest,
            "input": task_input,
        }


@router.post("/{task_id}/heartbeat", status_code=status.HTTP_200_OK, response_model=None)
async def heartbeat(
    task_id: uuid.UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Renova a lease sem expor tempo de banco ou alterar o event log."""
    async with transaction() as session:
        task = await _authenticate(session, task_id, authorization)
        if "heartbeat:write" not in settings.scopes_for_role(task.role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="papel sem heartbeat:write")
        task.locked_at = utc_now()
        task.updated_at = utc_now()
        return {"accepted": True, "expires_at": (task.locked_at + timedelta(seconds=task.timeout_seconds)).isoformat().replace("+00:00", "Z")}


@router.post(
    "/{task_id}/outputs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=None,
    summary="Submete a saída validada do fake worker.",
    responses={
        status.HTTP_202_ACCEPTED: {"description": "Saída aceita para processamento."},
        status.HTTP_403_FORBIDDEN: {"description": "Token inválido."},
        status.HTTP_409_CONFLICT: {
            "description": "Saída duplicada ou incompatível com o estado atual."
        },
    },
)
async def submit_task_output(
    task_id: uuid.UUID,
    payload: FakeWorkerOutput,
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=255)
    ],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    async with transaction() as session:
        task = await _authenticate(
            session, task_id, authorization, allow_terminal_replay=True
        )

        if str(payload.task_id.root) != str(task.task_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="task_id do payload não corresponde à tarefa autenticada.",
            )
        if str(payload.run_id.root) != str(task.run_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="run_id do payload não corresponde à tarefa autenticada.",
            )

        body = payload.model_dump(mode="json")
        try:
            replay = await idempotency.claim(
                session,
                scope=IDEMPOTENCY_SCOPE,
                key=idempotency_key,
                request_hash=idempotency.hash_request(body),
            )
        except idempotency.IdempotencyConflict as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc

        if replay is not None:
            return replay.body

        machine = load_state_machine(settings.state_machine_path)
        run = (
            await session.execute(
                select(Run).where(Run.run_id == task.run_id).with_for_update()
            )
        ).scalar_one()

        event_type = (
            "FAKE_WORKER_COMPLETED" if payload.status == "SUCCEEDED" else "AGENT_FAILED"
        )
        if not machine.accepts(run.state, event_type):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Estado {run.state} não aceita {event_type}; a saída chegou "
                    "fora da ordem esperada."
                ),
            )

        # LLM-01: "uso gera metadados no evento". O agregado de tokens e
        # latencia da tarefa entra no `meta` do evento de conclusao, que e o
        # campo que o EventEnvelope ja reserva para isso.
        usage = await usage_for_task(session, task.task_id)

        store = EventStore(session, machine)
        drafts = [
            EventDraft(
                type=event_type,
                actor="fake_worker" if task.role == "fake" else task.role,
                meta=usage.as_event_meta(),
                task_id=task.task_id,
                payload={
                    "status": payload.status,
                    "message": payload.message,
                    "received_context_hash": payload.received_context_hash.root,
                    "emitted_at": payload.emitted_at.root.isoformat().replace(
                        "+00:00", "Z"
                    ),
                },
                drives_transition=True,
            )
        ]
        # Evento informativo para a timeline do painel: não consta na tabela de
        # transições, e por isso não move estado.
        if event_type == "FAKE_WORKER_COMPLETED":
            drafts.append(
                EventDraft(type="RUN_COMPLETED", payload={"state": "COMPLETED"})
            )
        else:
            drafts.append(EventDraft(type="RUN_FAILED", payload={"state": "FAILED"}))

        await store.append(run, drafts)

        task.state = "SUCCEEDED" if payload.status == "SUCCEEDED" else "FAILED"
        task.updated_at = utc_now()
        # O estado terminal revoga as capacidades de contexto. O hash fica
        # somente para autenticar uma repetição idempotente do mesmo callback;
        # uma nova saída continua recusada pela máquina de estados.

        accepted = {"accepted": True, "run_state": run.state}
        await idempotency.record_response(
            session,
            scope=IDEMPOTENCY_SCOPE,
            key=idempotency_key,
            status=status.HTTP_202_ACCEPTED,
            body=accepted,
            run_id=run.run_id,
        )
        return accepted

"""Falhas explícitas reportadas pelos workers reais.

O worker descreve a falha; somente o plano de controle encerra a tarefa e
emite ``AGENT_FAILED``. Assim, Dev e QA não escrevem diretamente no event log.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ...config import Settings, get_settings
from ...db import transaction
from ...persistence.event_store import EventDraft, EventStore, utc_now
from ...persistence.models import Run
from ...persistence.state_machine import load_state_machine
from .tasks import _authenticate

router = APIRouter(prefix="/internal/v1/tasks", tags=["internal"])


class WorkerFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=4000)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


@router.post(
    "/{task_id}/failure",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=None,
    summary="Registra uma falha de worker e encerra a tentativa pelo control-api.",
)
async def report_worker_failure(
    task_id: uuid.UUID,
    payload: WorkerFailure,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    async with transaction() as session:
        task = await _authenticate(session, task_id, authorization)
        run = (
            await session.execute(
                select(Run).where(Run.run_id == task.run_id).with_for_update()
            )
        ).scalar_one()
        machine = load_state_machine(settings.state_machine_path)
        if not machine.accepts(run.state, "AGENT_FAILED"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Estado {run.state} não aceita AGENT_FAILED.",
            )

        body = payload.model_dump(mode="json")
        await EventStore(session, machine).append(
            run,
            [
                EventDraft(
                    type="AGENT_FAILED",
                    actor=task.role,
                    task_id=task.task_id,
                    payload=body,
                    drives_transition=True,
                )
            ],
        )
        task.state = "FAILED"
        task.token_hash = None
        task.updated_at = utc_now()
        return {"accepted": True, "task_state": task.state, "run_state": run.state}

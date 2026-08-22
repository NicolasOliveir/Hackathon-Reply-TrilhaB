from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.models import CreateRunRequest, RunResponse
from app.persistence import idempotency
from app.persistence.database import get_session
from app.services import run_service

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.post(
    "",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"description": "Idempotency key ja usada com payload diferente."}},
)
async def create_run(
    request: CreateRunRequest,
    response: Response,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=8, max_length=255
    ),
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    fingerprint = idempotency.request_fingerprint(request.model_dump(mode="json"))

    try:
        replay = await idempotency.lookup(
            session,
            key=idempotency_key,
            endpoint=run_service.CREATE_RUN_ENDPOINT,
            fingerprint=fingerprint,
        )
    except idempotency.IdempotencyConflict as conflict:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(conflict)) from conflict

    if replay is not None:
        # Repeticao legitima: devolve a mesma resposta sem criar segunda execucao.
        response.headers["Idempotency-Replayed"] = "true"
        return RunResponse.model_validate(replay)

    created = await run_service.create_run(session, request)
    await idempotency.store(
        session,
        key=idempotency_key,
        endpoint=run_service.CREATE_RUN_ENDPOINT,
        fingerprint=fingerprint,
        response=created.model_dump(mode="json"),
        run_id=created.run_id,
    )
    await session.commit()
    return created


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    responses={404: {"description": "Execucao nao encontrada."}},
)
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    run = await run_service.get_run(session, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Execucao nao encontrada")
    return run_service.to_response(run)

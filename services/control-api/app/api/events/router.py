"""Endpoint SSE público para acompanhar uma execução."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from ...config import get_settings
from ...db import get_session_factory
from ...persistence.models import Run
from .stream import iter_run_events

router = APIRouter(prefix="/api/v1/runs", tags=["events"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get(
    "/{run_id}/events",
    response_class=StreamingResponse,
    summary="Acompanha eventos e permite retomada pelo sequence.",
    responses={
        status.HTTP_200_OK: {
            "description": "Stream de EventEnvelope serializado como SSE.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        status.HTTP_404_NOT_FOUND: {"description": "Execução não encontrada."},
    },
)
async def stream_run_events(
    run_id: uuid.UUID,
    last_event_id: Annotated[
        int | None,
        Header(alias="Last-Event-ID", ge=0),
    ] = None,
) -> StreamingResponse:
    # A existência precisa ser validada antes de iniciar o response. Depois do
    # primeiro byte SSE, o status HTTP 200 já não pode ser trocado por 404.
    async with get_session_factory()() as session:
        if await session.get(Run, run_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Execução {run_id} não encontrada.",
            )

    settings = get_settings()
    return StreamingResponse(
        iter_run_events(
            run_id,
            settings,
            after_sequence=last_event_id or 0,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )

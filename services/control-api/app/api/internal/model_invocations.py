"""Endpoint de invocação de modelo — `POST /internal/v1/tasks/{id}/model-invocations`.

É por aqui que a chamada real acontece. O container de agente está na
`agent_net`, que é `internal: true`: ele **não alcança** o provedor nem a
internet. A credencial vive só neste processo.

Duas travas de escopo:

- o token da tarefa precisa carregar `model:invoke`; o fake worker desta
  iteração não tem esse escopo e recebe 403;
- toda invocação, inclusive a que falhou, gera linha em `model_invocations`.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from ...config import CONTRACT_VERSION, Settings, get_settings
from ...db import transaction
from ...model_gateway.base import (
    ModelGatewayError,
    ModelRequest,
    ProviderNotConfigured,
    ProviderRefused,
)
from ...model_gateway.gateway import ModelGateway
from ...model_gateway.factory import build_providers, build_router
from .tasks import _authenticate

router = APIRouter(prefix="/internal/v1/tasks", tags=["internal"])

REQUIRED_SCOPE = "model:invoke"


class ModelInvocationRequest(BaseModel):
    """Contrato do gateway.

    Não vive em `packages/contracts` ainda: acrescentar um schema versionado
    exige coordenação com o frontend e um bump de `contract_version`. Está
    anotado no README como pendência de contrato.
    """

    contract_version: str = Field(default=CONTRACT_VERSION)
    prompt: str = Field(min_length=1, max_length=200_000)
    system: str | None = Field(default=None, max_length=100_000)
    model: str | None = None
    effort: str | None = Field(default=None, pattern="^(low|medium|high|xhigh|max)$")
    max_output_tokens: int = Field(default=16_000, ge=1, le=128_000)
    output_schema: dict[str, Any] | None = None


def _gateway(settings: Settings) -> ModelGateway:
    return ModelGateway(
        providers=build_providers(settings), router=build_router(settings)
    )


@router.post(
    "/{task_id}/model-invocations",
    status_code=status.HTTP_200_OK,
    response_model=None,
    summary="Invoca o provedor de modelo em nome da tarefa autenticada.",
    responses={
        status.HTTP_200_OK: {"description": "Resposta do modelo e uso registrado."},
        status.HTTP_403_FORBIDDEN: {
            "description": "Token inválido ou sem escopo model:invoke."
        },
        status.HTTP_409_CONFLICT: {"description": "Tarefa não está em execução."},
        status.HTTP_502_BAD_GATEWAY: {"description": "Falha no provedor de modelo."},
    },
)
async def invoke_model(
    task_id: uuid.UUID,
    payload: ModelInvocationRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    outcome = None
    gateway_error: HTTPException | None = None
    async with transaction() as session:
        task = await _authenticate(session, task_id, authorization)

        if REQUIRED_SCOPE not in settings.scopes_for_role(task.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"papel '{task.role}' não possui o escopo {REQUIRED_SCOPE}; "
                    "o gateway não é aberto a qualquer tarefa."
                ),
            )
        if task.state != "RUNNING":
            # Invocar por conta de uma tarefa já encerrada gastaria token sem
            # que nada consuma o resultado.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"tarefa está em {task.state}; só tarefa RUNNING pode invocar.",
            )

        try:
            outcome = await _gateway(settings).invoke(
                session,
                run_id=task.run_id,
                task_id=task.task_id,
                role=task.role,
                request=ModelRequest(
                    prompt=payload.prompt,
                    system=payload.system,
                    model=payload.model,
                    max_output_tokens=payload.max_output_tokens,
                    effort=payload.effort,
                    output_schema=payload.output_schema,
                    timeout_seconds=task.timeout_seconds,
                ),
            )
        except ProviderRefused as exc:
            gateway_error = HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "provider_refused", "category": exc.category},
            )
        except ProviderNotConfigured as exc:
            gateway_error = HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "provider_not_configured", "message": str(exc)},
            )
        except ModelGatewayError as exc:
            gateway_error = HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "provider_failed", "message": str(exc)},
            )

    # O erro precisa sair somente depois do commit. Se escapar de
    # ``transaction()`` acima, o rollback apaga justamente a auditoria FAILED
    # ou REFUSED registrada pelo gateway.
    if gateway_error is not None:
        raise gateway_error

    assert outcome is not None
    response = outcome.response
    return {
        "contract_version": CONTRACT_VERSION,
        "invocation_id": str(outcome.invocation_id),
        "provider": response.provider,
        "model": response.model,
        "text": response.text,
        "parsed": response.parsed,
        "stop_reason": response.stop_reason,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read_tokens": response.usage.cache_read_tokens,
            "cache_write_tokens": response.usage.cache_write_tokens,
            "latency_ms": response.latency_ms,
        },
    }

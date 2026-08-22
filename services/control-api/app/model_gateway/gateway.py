"""Gateway de modelo auditável.

Responsabilidade (ORQUESTRADOR.md:424 — `LLM-01`): *"chave fica só na API e uso
gera metadados no evento"*.

O gateway faz três coisas que nenhum provedor faz:

1. escolhe a rota pelo papel da tarefa;
2. persiste toda invocação — inclusive as que falharam;
3. agrega uso por tarefa, para que `meta` do evento de conclusão carregue
   modelo, tokens e latência reais.

Falha de provedor é registrada, não engolida: uma invocação sem linha na
auditoria seria um gasto invisível.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..persistence.event_store import sha256_of, utc_now
from ..persistence.models import ModelInvocation
from .base import (
    ModelGatewayError,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderNotConfigured,
    ProviderRefused,
)
from .routing import ModelRouter

MAX_PROMPT_CHARS = 200_000


@dataclass(frozen=True)
class InvocationOutcome:
    invocation_id: uuid.UUID
    response: ModelResponse
    route_reason: str


@dataclass(frozen=True)
class UsageTotals:
    """Agregado por tarefa, no formato de `meta` do EventEnvelope."""

    model: str | None
    tokens_in: int
    tokens_out: int
    latency_ms: int

    def as_event_meta(self) -> dict:
        return {
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "latency_ms": self.latency_ms,
        }


class ModelGateway:
    def __init__(
        self, providers: dict[str, ModelProvider], router: ModelRouter
    ) -> None:
        self._providers = providers
        self._router = router

    def available_providers(self) -> list[str]:
        return sorted(self._providers)

    async def invoke(
        self,
        session: AsyncSession,
        *,
        run_id: uuid.UUID,
        task_id: uuid.UUID,
        role: str,
        request: ModelRequest,
    ) -> InvocationOutcome:
        if not request.prompt.strip():
            raise ModelGatewayError("prompt vazio")
        if len(request.prompt) > MAX_PROMPT_CHARS:
            # Truncar silenciosamente produziria uma resposta sobre um pedido
            # que ninguem escreveu.
            raise ModelGatewayError(
                f"prompt excede {MAX_PROMPT_CHARS} caracteres; reduza o contexto "
                "em vez de deixar o gateway cortar."
            )

        route = self._router.route(role)
        effective = ModelRequest(
            prompt=request.prompt,
            system=request.system,
            model=request.model or route.model,
            max_output_tokens=request.max_output_tokens,
            effort=request.effort or route.effort,
            output_schema=request.output_schema,
            timeout_seconds=request.timeout_seconds,
        )

        invocation = ModelInvocation(
            invocation_id=uuid.uuid4(),
            run_id=run_id,
            task_id=task_id,
            role=role,
            provider=route.provider,
            model=effective.model,
            effort=effective.effort,
            # O prompt nao e persistido em claro: ele pode conter o briefing, e
            # o painel projeta esta tabela. O hash prova o que foi enviado sem
            # transportar o conteudo.
            prompt_hash=sha256_of(effective.prompt),
            prompt_chars=len(effective.prompt),
            state="RUNNING",
            route_reason=route.reason,
            created_at=utc_now(),
        )
        session.add(invocation)
        await session.flush()

        provider = self._providers.get(route.provider)
        if provider is None:
            error = ProviderNotConfigured(
                f"provedor '{route.provider}' nao configurado; disponiveis: "
                + ", ".join(self.available_providers())
            )
            invocation.state = "FAILED"
            invocation.error = str(error)[:1000]
            invocation.finished_at = utc_now()
            await session.flush()
            raise error

        try:
            response = await provider.invoke(effective)
        except ProviderRefused as exc:
            invocation.state = "REFUSED"
            invocation.error = str(exc)
            invocation.refusal_category = exc.category
            invocation.finished_at = utc_now()
            await session.flush()
            raise
        except ModelGatewayError as exc:
            invocation.state = "FAILED"
            invocation.error = str(exc)[:1000]
            invocation.finished_at = utc_now()
            await session.flush()
            raise
        except Exception as exc:  # noqa: BLE001 - provedor nao previsto
            invocation.state = "FAILED"
            invocation.error = f"{type(exc).__name__}: {exc}"[:1000]
            invocation.finished_at = utc_now()
            await session.flush()
            raise ModelGatewayError(
                f"falha nao tratada no provedor {route.provider}: {type(exc).__name__}"
            ) from exc

        invocation.state = "SUCCEEDED"
        invocation.model = response.model
        invocation.input_tokens = response.usage.input_tokens
        invocation.output_tokens = response.usage.output_tokens
        invocation.cache_read_tokens = response.usage.cache_read_tokens
        invocation.cache_write_tokens = response.usage.cache_write_tokens
        invocation.latency_ms = response.latency_ms
        invocation.stop_reason = response.stop_reason
        invocation.response_chars = len(response.text)
        invocation.finished_at = utc_now()
        await session.flush()

        return InvocationOutcome(
            invocation_id=invocation.invocation_id,
            response=response,
            route_reason=route.reason,
        )


async def usage_for_task(session: AsyncSession, task_id: uuid.UUID) -> UsageTotals:
    """Agrega o uso de uma tarefa para o `meta` do evento de conclusão."""
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(ModelInvocation.input_tokens), 0),
                func.coalesce(func.sum(ModelInvocation.output_tokens), 0),
                func.coalesce(func.sum(ModelInvocation.latency_ms), 0),
                func.max(ModelInvocation.model),
            ).where(ModelInvocation.task_id == task_id)
        )
    ).one()
    tokens_in, tokens_out, latency_ms, model = row
    return UsageTotals(
        model=model,
        tokens_in=int(tokens_in),
        tokens_out=int(tokens_out),
        latency_ms=int(latency_ms),
    )

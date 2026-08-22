"""Provedor Anthropic via SDK oficial.

Usa `AsyncAnthropic`, que resolve credencial na ordem do SDK — `ANTHROPIC_API_KEY`,
`ANTHROPIC_AUTH_TOKEN`, perfil de `ant auth login`. A chave nunca sai deste
processo: containers de agente recebem apenas o token de tarefa.
"""

from __future__ import annotations

import json
import time

from .base import (
    ModelGatewayError,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ProviderNotConfigured,
    ProviderRefused,
)

DEFAULT_MODEL = "claude-opus-5"

# Efeito prático do contrato do gateway: quando o chamador pede JSON, a resposta
# precisa ser JSON e nada mais. Structured outputs faz isso no servidor, em vez
# de depender de instrução em prosa e de parsing tolerante.
_JSON_INSTRUCTION = (
    "Responda exclusivamente com JSON válido que satisfaça o schema fornecido. "
    "Não inclua comentário, cerca de código nem texto fora do JSON."
)


class AnthropicProvider(ModelProvider):
    name = "anthropic"

    def __init__(
        self,
        client=None,
        default_model: str = DEFAULT_MODEL,
        profile: str | None = None,
    ) -> None:
        self._client = client
        self._default_model = default_model
        self._profile = profile

    def _ensure_client(self):
        """Constrói o cliente uma vez.

        Sem `profile`, o SDK resolve na ordem dele: `ANTHROPIC_API_KEY`,
        `ANTHROPIC_AUTH_TOKEN`, perfil de `ant auth login`, federação.

        **Com plano (assinatura) não existe chave a passar** — a credencial vem
        do perfil, e o construtor sem argumento já faz isso. `profile` só é
        necessário para escolher um perfil nomeado entre vários.
        """
        if self._client is not None:
            return self._client
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise ProviderNotConfigured(
                "SDK `anthropic` não instalado; use o extra control-api."
            ) from exc
        self._client = (
            AsyncAnthropic(profile=self._profile) if self._profile else AsyncAnthropic()
        )
        return self._client

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        client = self._ensure_client()
        model = request.model or self._default_model

        system = request.system
        if request.output_schema is not None:
            schema = json.dumps(request.output_schema, ensure_ascii=False)
            system = "\n\n".join(
                part for part in (system, _JSON_INSTRUCTION, f"Schema:\n{schema}") if part
            )

        payload: dict = {
            "model": model,
            "max_tokens": request.max_output_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
            # Pensamento adaptativo: o modelo decide quando e quanto pensar. Em
            # decomposição de backlog e análise de critério isso muda o
            # resultado, não só o custo.
            "thinking": {"type": "adaptive"},
        }
        if system:
            payload["system"] = system
        if request.effort:
            payload["output_config"] = {"effort": request.effort}

        started = time.perf_counter()
        try:
            message = await client.messages.create(
                **payload, timeout=float(request.timeout_seconds)
            )
        except Exception as exc:  # noqa: BLE001 - traduzido para erro do gateway
            raise self._translate(exc) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        if getattr(message, "stop_reason", None) == "refusal":
            details = getattr(message, "stop_details", None)
            raise ProviderRefused(
                "Provedor recusou o pedido por política de segurança.",
                category=getattr(details, "category", None),
            )

        text = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        )
        usage = getattr(message, "usage", None)
        return ModelResponse(
            provider=self.name,
            model=getattr(message, "model", model),
            text=text,
            usage=ModelUsage(
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            ),
            stop_reason=getattr(message, "stop_reason", None),
            latency_ms=latency_ms,
            parsed=_maybe_json(text) if request.output_schema is not None else None,
        )

    @staticmethod
    def _translate(exc: Exception) -> ModelGatewayError:
        """Traduz exceção do SDK sem vazar cabeçalho nem credencial na mensagem."""
        name = type(exc).__name__
        if name in {"AuthenticationError", "PermissionDeniedError"}:
            return ProviderNotConfigured(
                "Credencial Anthropic ausente ou sem permissão."
            )
        # Sem nenhuma credencial resolvível o SDK levanta `TypeError` cru, não
        # uma exceção tipada. Sem este ramo o operador recebe apenas
        # "TypeError" — e esse é o primeiro erro de quem ainda não configurou a
        # chave, justamente o caso em que a mensagem precisa dizer o que fazer.
        if isinstance(exc, TypeError) and "authentication method" in str(exc).lower():
            return ProviderNotConfigured(
                "Credencial Anthropic não resolvida. Defina ANTHROPIC_API_KEY ou "
                "autentique um perfil com `ant auth login` no ambiente do control-api."
            )
        return ModelGatewayError(f"Falha na chamada ao provedor anthropic: {name}")


def _maybe_json(text: str) -> dict | None:
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None

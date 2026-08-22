"""Provedor determinístico, sem rede.

Existe para dois casos concretos:

- CI e testes de integração, que não podem depender de credencial nem gastar
  token;
- demonstração local antes de a equipe ter chave.

Não é um mock genérico: respeita o contrato inteiro da porta, inclusive
`output_schema` e contabilidade de uso, para que trocar de provedor não mude o
comportamento do gateway.
"""

from __future__ import annotations

import json
import time

from .base import ModelProvider, ModelRequest, ModelResponse, ModelUsage

# Aproximação grosseira e declarada: 4 caracteres por token. Serve para exercitar
# o caminho de auditoria sem fingir precisão de tokenizador real.
CHARS_PER_TOKEN = 4


class EchoProvider(ModelProvider):
    name = "echo"

    def __init__(self, default_model: str = "echo-1") -> None:
        self._default_model = default_model

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        started = time.perf_counter()

        if request.output_schema is not None:
            payload = {
                "echo": request.prompt[:200],
                "schema_title": request.output_schema.get("title", "sem-titulo"),
            }
            text = json.dumps(payload, ensure_ascii=False)
            parsed = payload
        else:
            text = f"echo: {request.prompt}"
            parsed = None

        latency_ms = int((time.perf_counter() - started) * 1000)
        return ModelResponse(
            provider=self.name,
            model=request.model or self._default_model,
            text=text,
            usage=ModelUsage(
                input_tokens=max(1, len(request.prompt) // CHARS_PER_TOKEN),
                output_tokens=max(1, len(text) // CHARS_PER_TOKEN),
            ),
            stop_reason="end_turn",
            latency_ms=latency_ms,
            parsed=parsed,
        )

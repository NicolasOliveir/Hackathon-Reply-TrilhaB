"""Porta de provedor de modelo.

Regra que define este módulo (ORQUESTRADOR.md §16): *"agentes não acessam
diretamente internet ou provedor LLM"*. A `agent_net` é `internal: true`, então
o container de agente **não consegue** sair — a chamada obrigatoriamente passa
pelo `control-api`, que é o único a possuir credencial.

Cada provedor implementa esta porta. Nenhum deles conhece banco, evento ou
tarefa: recebem um pedido e devolvem texto mais uso. A auditoria é do gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class ModelGatewayError(Exception):
    """Falha na invocação do modelo."""


class ProviderNotConfigured(ModelGatewayError):
    """Provedor selecionado sem credencial ou dependência disponível."""


class ProviderRefused(ModelGatewayError):
    """O provedor recusou o pedido por política."""

    def __init__(self, message: str, category: str | None = None) -> None:
        self.category = category
        super().__init__(message)


@dataclass(frozen=True)
class ModelRequest:
    prompt: str
    system: str | None = None
    model: str | None = None
    max_output_tokens: int = 16_000
    effort: str | None = None
    # Schema JSON opcional: quando presente, o provedor deve devolver JSON que
    # o valide. É assim que o PO Agent vai receber o envelope de backlog sem
    # depender de parsing de texto livre.
    output_schema: dict | None = None
    timeout_seconds: int = 300


@dataclass(frozen=True)
class ModelUsage:
    """Metadados que vão para `meta` do evento e para a tabela de auditoria."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ModelResponse:
    provider: str
    model: str
    text: str
    usage: ModelUsage = field(default_factory=ModelUsage)
    stop_reason: str | None = None
    latency_ms: int = 0
    # Presente apenas quando `output_schema` foi pedido e o provedor respondeu
    # JSON válido.
    parsed: dict | None = None


@runtime_checkable
class ModelProvider(Protocol):
    name: str

    async def invoke(self, request: ModelRequest) -> ModelResponse: ...

"""Contrato de runtime de container.

O scheduler fala com esta interface, nunca com o Docker diretamente. Isso
permite testar o despacho inteiro sem daemon e mantém a promessa da
ORQUESTRADOR §10: somente o módulo de runtime toca o socket.

O ciclo é `create` → `start` → `wait` → `remove`, e não um único `run`. A
separação existe porque o `container_id` precisa ser conhecido **antes** de o
worker poder chamar a API: `AGENT_STARTED` é gravado entre `create` e `start`,
o que fecha a corrida em que o callback chegaria antes do evento que o explica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

# Nomes que jamais podem chegar a um container de agente. A checagem é feita
# na montagem do spec, e não por revisão de código.
FORBIDDEN_ENV = frozenset({"DATABASE_URL", "DOCKER_HOST", "POSTGRES_PASSWORD"})


class RuntimeError_(Exception):
    """Falha de infraestrutura do runtime."""


class ImageNotAllowed(RuntimeError_):
    """Imagem fora da allowlist."""


class ForbiddenEnvironment(RuntimeError_):
    """Tentativa de passar credencial de plano de controle ao agente."""


@dataclass(frozen=True)
class ResourceLimits:
    memory: str = "128m"
    cpus: float = 0.5
    pids: int = 64


@dataclass(frozen=True)
class ContainerSpec:
    image: str
    environment: dict[str, str]
    network: str
    labels: dict[str, str] = field(default_factory=dict)
    limits: ResourceLimits = field(default_factory=ResourceLimits)
    read_only: bool = True

    def __post_init__(self) -> None:
        leaked = FORBIDDEN_ENV.intersection(self.environment)
        if leaked:
            raise ForbiddenEnvironment(
                "variáveis proibidas em container de agente: "
                + ", ".join(sorted(leaked))
            )


@dataclass(frozen=True)
class ContainerHandle:
    container_id: str
    image: str


@dataclass(frozen=True)
class ContainerResult:
    container_id: str
    exit_code: int | None
    started_at: datetime
    finished_at: datetime
    timed_out: bool
    logs_tail: str

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@runtime_checkable
class ContainerRuntime(Protocol):
    async def create(self, spec: ContainerSpec) -> ContainerHandle: ...

    async def start(self, handle: ContainerHandle) -> datetime: ...

    async def wait(
        self, handle: ContainerHandle, *, timeout_seconds: int
    ) -> ContainerResult: ...

    async def remove(self, handle: ContainerHandle) -> None: ...

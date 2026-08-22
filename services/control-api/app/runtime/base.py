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
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol, runtime_checkable

# Nomes que jamais podem chegar a um container de agente. A checagem é feita
# na montagem do spec, e não por revisão de código.
FORBIDDEN_ENV = frozenset({"DATABASE_URL", "DOCKER_HOST", "POSTGRES_PASSWORD"})


class RuntimeError_(Exception):
    """Falha de infraestrutura do runtime."""


class ImageNotAllowed(RuntimeError_):
    """Imagem fora da allowlist."""


class ForbiddenEnvironment(RuntimeError_):
    """Tentativa de passar credencial de plano de controle ao agente."""


class InvalidMount(RuntimeError_):
    """Mount inválido ou incompatível com o papel do worker."""


@dataclass(frozen=True)
class ResourceLimits:
    memory: str = "128m"
    cpus: float = 0.5
    pids: int = 64


MOUNT_TARGETS = frozenset({"/workspace", "/tests"})


@dataclass(frozen=True)
class ContainerMount:
    """Bind mount explícito entregue a um container efêmero.

    O host path precisa ser absoluto e os destinos são intencionalmente
    limitados às duas raízes públicas dos workers. Isso evita transformar o
    runtime numa forma indireta de montar o repositório ou o socket Docker.
    """

    source: str | Path
    target: str
    read_only: bool

    def __post_init__(self) -> None:
        source = Path(self.source)
        if not source.is_absolute():
            raise InvalidMount(f"origem do mount precisa ser absoluta: {self.source!r}")
        if self.target not in MOUNT_TARGETS:
            allowed = ", ".join(sorted(MOUNT_TARGETS))
            raise InvalidMount(
                f"destino do mount precisa ser uma raiz permitida ({allowed}): "
                f"{self.target!r}"
            )


def validate_worker_mounts(
    role: Literal["dev", "qa"], mounts: tuple[ContainerMount, ...]
) -> None:
    """Valida a matriz mínima de acesso dos workers que alteram arquivos."""

    by_target = {mount.target: mount for mount in mounts}
    if len(by_target) != len(mounts):
        raise InvalidMount("destinos de mounts precisam ser distintos")
    if len({str(Path(mount.source).resolve()) for mount in mounts}) != len(mounts):
        raise InvalidMount("origens de mounts precisam ser distintas")

    if role == "dev":
        expected = by_target.get("/workspace")
        if len(mounts) != 1 or expected is None or expected.read_only:
            raise InvalidMount("Dev requer somente /workspace com leitura e escrita")
        return

    workspace = by_target.get("/workspace")
    tests = by_target.get("/tests")
    if (
        len(mounts) != 2
        or workspace is None
        or not workspace.read_only
        or tests is None
        or tests.read_only
    ):
        raise InvalidMount("QA requer /workspace somente leitura e /tests gravável")


def worker_mounts(
    role: Literal["dev", "qa"],
    *,
    workspace: str | Path,
    tests: str | Path | None = None,
) -> tuple[ContainerMount, ...]:
    """Monta e valida os binds canônicos de Dev ou QA."""

    if role == "dev":
        if tests is not None:
            raise InvalidMount("Dev não recebe um mount separado de testes")
        mounts = (
            ContainerMount(
                source=str(workspace), target="/workspace", read_only=False
            ),
        )
    elif role == "qa":
        if tests is None:
            raise InvalidMount("QA requer a origem do mount /tests")
        mounts = (
            ContainerMount(source=str(workspace), target="/workspace", read_only=True),
            ContainerMount(source=str(tests), target="/tests", read_only=False),
        )
    else:  # pragma: no cover - protegido também pelo tipo em consumidores tipados
        raise InvalidMount(f"papel sem política de mounts: {role!r}")

    validate_worker_mounts(role, mounts)
    return mounts


@dataclass(frozen=True)
class ContainerSpec:
    image: str
    environment: dict[str, str]
    network: str
    labels: dict[str, str] = field(default_factory=dict)
    limits: ResourceLimits = field(default_factory=ResourceLimits)
    read_only: bool = True
    mounts: tuple[ContainerMount, ...] = ()
    user: str = "10001:10001"
    working_dir: str | None = None

    def __post_init__(self) -> None:
        leaked = FORBIDDEN_ENV.intersection(self.environment)
        if leaked:
            raise ForbiddenEnvironment(
                "variáveis proibidas em container de agente: "
                + ", ".join(sorted(leaked))
            )
        targets = [mount.target for mount in self.mounts]
        if len(set(targets)) != len(targets):
            raise InvalidMount("destinos de mounts precisam ser distintos")
        if len(
            {str(Path(mount.source).resolve()) for mount in self.mounts}
        ) != len(self.mounts):
            raise InvalidMount("origens de mounts precisam ser distintas")

        if not self.user.strip():
            raise RuntimeError_("usuário do container não pode ser vazio")

        if self.working_dir is not None:
            workdir = PurePosixPath(self.working_dir)
            if not workdir.is_absolute() or ".." in workdir.parts:
                raise InvalidMount(
                    f"working_dir precisa ser absoluto e confinado: {self.working_dir!r}"
                )
            if not any(
                self.working_dir == target
                or self.working_dir.startswith(f"{target}/")
                for target in targets
            ):
                raise InvalidMount("working_dir precisa estar dentro de um mount declarado")


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

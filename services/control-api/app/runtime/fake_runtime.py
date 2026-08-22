"""Runtime em memória para testar o scheduler sem daemon Docker.

Não é um mock genérico: reproduz as invariantes que importam — allowlist,
proibição de variável de plano de controle, `container_id` conhecido antes do
start, e a possibilidade de simular saída não-zero, timeout e callback.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .base import (
    ContainerHandle,
    ContainerResult,
    ContainerSpec,
    ImageNotAllowed,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RecordedContainer:
    handle: ContainerHandle
    spec: ContainerSpec
    started: bool = False
    removed: bool = False


@dataclass
class FakeContainerRuntime:
    """Runtime determinístico.

    `on_start` recebe o spec e permite ao teste simular o worker chamando a API
    de callback enquanto o container "roda".
    """

    allowed_images: frozenset[str]
    exit_code: int = 0
    timed_out: bool = False
    logs_tail: str = ""
    on_start: Callable[[ContainerSpec], Awaitable[None]] | None = None
    containers: list[RecordedContainer] = field(default_factory=list)

    @property
    def created_count(self) -> int:
        return len(self.containers)

    @property
    def started_count(self) -> int:
        return sum(1 for item in self.containers if item.started)

    @property
    def removed_count(self) -> int:
        return sum(1 for item in self.containers if item.removed)

    def _find(self, handle: ContainerHandle) -> RecordedContainer:
        return next(
            item
            for item in self.containers
            if item.handle.container_id == handle.container_id
        )

    async def create(self, spec: ContainerSpec) -> ContainerHandle:
        if spec.image not in self.allowed_images:
            raise ImageNotAllowed(f"imagem '{spec.image}' fora da allowlist")
        handle = ContainerHandle(
            container_id=f"fake-{uuid.uuid4().hex[:12]}", image=spec.image
        )
        self.containers.append(RecordedContainer(handle=handle, spec=spec))
        return handle

    async def start(self, handle: ContainerHandle) -> datetime:
        record = self._find(handle)
        record.started = True
        if self.on_start is not None:
            await self.on_start(record.spec)
        return _utc_now()

    async def wait(
        self, handle: ContainerHandle, *, timeout_seconds: int
    ) -> ContainerResult:
        moment = _utc_now()
        return ContainerResult(
            container_id=handle.container_id,
            exit_code=None if self.timed_out else self.exit_code,
            started_at=moment,
            finished_at=moment,
            timed_out=self.timed_out,
            logs_tail=self.logs_tail,
        )

    async def remove(self, handle: ContainerHandle) -> None:
        self._find(handle).removed = True

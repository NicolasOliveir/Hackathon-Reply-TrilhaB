"""Implementação com Docker SDK.

Único módulo do control-api que toca o socket do Docker (ORQUESTRADOR §10). O
SDK é síncrono; cada chamada roda em `asyncio.to_thread` para não bloquear o
loop que serve a API e o callback do worker — que chega **durante** o `wait`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .base import (
    ContainerHandle,
    ContainerResult,
    ContainerSpec,
    ImageNotAllowed,
    RuntimeError_,
)

LOGS_TAIL_LINES = 50
# Sem isto o `docker wait` fica pendurado indefinidamente quando o daemon
# perde o container, e o scheduler nunca libera a task.
WAIT_POLL_SECONDS = 0.5


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DockerContainerRuntime:
    def __init__(self, client, allowed_images: frozenset[str]) -> None:
        self._client = client
        self._allowed_images = allowed_images

    @classmethod
    def from_environment(cls, allowed_images: frozenset[str]):
        try:
            import docker
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise RuntimeError_(
                "docker SDK não instalado; use o extra control-api ou selecione "
                "o runtime fake."
            ) from exc
        return cls(docker.from_env(), allowed_images)

    def _assert_allowed(self, image: str) -> None:
        if image not in self._allowed_images:
            raise ImageNotAllowed(
                f"imagem '{image}' fora da allowlist "
                f"({', '.join(sorted(self._allowed_images)) or 'vazia'})"
            )

    async def create(self, spec: ContainerSpec) -> ContainerHandle:
        self._assert_allowed(spec.image)

        def _create():
            return self._client.containers.create(
                image=spec.image,
                environment=dict(spec.environment),
                network=spec.network,
                labels=dict(spec.labels),
                detach=True,
                # auto_remove impediria a leitura do exit code e dos logs, que
                # são a evidência da execução.
                auto_remove=False,
                read_only=spec.read_only,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=16m"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit=spec.limits.memory,
                nano_cpus=int(spec.limits.cpus * 1_000_000_000),
                pids_limit=spec.limits.pids,
                network_disabled=False,
            )

        container = await asyncio.to_thread(_create)
        return ContainerHandle(container_id=container.id, image=spec.image)

    async def start(self, handle: ContainerHandle) -> datetime:
        def _start() -> None:
            self._client.containers.get(handle.container_id).start()

        await asyncio.to_thread(_start)
        return _utc_now()

    async def wait(
        self, handle: ContainerHandle, *, timeout_seconds: int
    ) -> ContainerResult:
        started_at = _utc_now()

        def _wait() -> int | None:
            container = self._client.containers.get(handle.container_id)
            status = container.wait(timeout=timeout_seconds)
            return status.get("StatusCode")

        timed_out = False
        exit_code: int | None = None
        try:
            exit_code = await asyncio.wait_for(
                asyncio.to_thread(_wait),
                # Margem sobre o timeout do SDK: se o daemon perder o container,
                # `docker wait` fica pendurado e o scheduler nunca libera a task.
                timeout=timeout_seconds + WAIT_POLL_SECONDS,
            )
        except asyncio.TimeoutError:
            timed_out = True
            await self._kill(handle)
        except Exception as exc:  # noqa: BLE001 - o SDK sinaliza timeout por texto
            if "timeout" not in str(exc).lower():
                raise RuntimeError_(
                    f"falha ao aguardar container {handle.container_id}: {exc}"
                ) from exc
            timed_out = True
            await self._kill(handle)

        return ContainerResult(
            container_id=handle.container_id,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=_utc_now(),
            timed_out=timed_out,
            logs_tail=await self._logs(handle),
        )

    async def _kill(self, handle: ContainerHandle) -> None:
        def _do() -> None:
            try:
                self._client.containers.get(handle.container_id).kill()
            except Exception:  # noqa: BLE001 - container pode já ter morrido
                pass

        await asyncio.to_thread(_do)

    async def _logs(self, handle: ContainerHandle) -> str:
        def _do() -> str:
            try:
                raw = self._client.containers.get(handle.container_id).logs(
                    tail=LOGS_TAIL_LINES, stdout=True, stderr=True
                )
            except Exception:  # noqa: BLE001 - log é evidência, não pré-condição
                return ""
            return raw.decode("utf-8", errors="replace") if raw else ""

        return await asyncio.to_thread(_do)

    async def remove(self, handle: ContainerHandle) -> None:
        def _do() -> None:
            try:
                self._client.containers.get(handle.container_id).remove(force=True)
            except Exception:  # noqa: BLE001 - remoção é idempotente por natureza
                pass

        await asyncio.to_thread(_do)

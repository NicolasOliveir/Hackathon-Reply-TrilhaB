"""Implementação com Docker SDK.

Único módulo do control-api que toca o socket do Docker (ORQUESTRADOR §10). O
SDK é síncrono; cada chamada roda em `asyncio.to_thread` para não bloquear o
loop que serve a API e o callback do worker — que chega **durante** o `wait`.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from .base import (
    ContainerHandle,
    ContainerResult,
    ContainerSpec,
    ImageNotAllowed,
    InvalidMount,
    RuntimeError_,
)

LOGS_TAIL_LINES = 50
# Sem isto o `docker wait` fica pendurado indefinidamente quando o daemon
# perde o container, e o scheduler nunca libera a task.
WAIT_POLL_SECONDS = 0.5


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DockerContainerRuntime:
    def __init__(
        self,
        client,
        allowed_images: frozenset[str],
        mount_translations: dict[str | Path, str | Path] | None = None,
        require_translated_mounts: bool = False,
    ) -> None:
        self._client = client
        self._allowed_images = allowed_images
        self._mount_translations = tuple(
            sorted(
                (
                    (Path(container_path), Path(daemon_path))
                    for container_path, daemon_path in (mount_translations or {}).items()
                ),
                key=lambda item: len(item[0].parts),
                reverse=True,
            )
        )
        self._require_translated_mounts = require_translated_mounts

    @classmethod
    def from_environment(cls, allowed_images: frozenset[str]):
        try:
            import docker
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise RuntimeError_(
                "docker SDK não instalado; use o extra control-api ou selecione "
                "o runtime fake."
            ) from exc
        client = docker.from_env()
        translations = cls._discover_mount_translations(client)
        return cls(
            client,
            allowed_images,
            mount_translations=translations,
            # Dentro do control-api, um path não traduzido pertence ao
            # namespace do container e não é uma origem válida para o daemon.
            require_translated_mounts=Path("/.dockerenv").exists(),
        )

    @staticmethod
    def _discover_mount_translations(client) -> dict[Path, Path]:
        """Mapeia paths do control-api para paths vistos pelo daemon.

        O control-api escreve em ``/var/lib/rivexx/workspaces`` dentro de um
        volume nomeado. Um bind criado pelo daemon, porém, precisa usar o
        ``Source`` host desse volume. O container atual é identificado pelo
        hostname e seus mounts fornecem exatamente essa tradução.
        """
        hostname = os.getenv("HOSTNAME", "").strip()
        if not hostname:
            return {}
        try:
            mounts = client.containers.get(hostname).attrs.get("Mounts", [])
        except Exception:  # noqa: BLE001 - fora de container não há self para inspecionar
            return {}
        translations: dict[Path, Path] = {}
        for mount in mounts:
            destination = mount.get("Destination")
            source = mount.get("Source")
            if destination and source:
                translations[Path(destination)] = Path(source)
        return translations

    def _daemon_mount_source(self, source: str | Path) -> str:
        container_source = Path(source)
        for container_root, daemon_root in self._mount_translations:
            try:
                relative = container_source.relative_to(container_root)
            except ValueError:
                continue
            return str(daemon_root / relative)
        if self._require_translated_mounts:
            raise InvalidMount(
                f"origem {container_source} não pertence a um volume do control-api"
            )
        return str(container_source)

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
                volumes={
                    self._daemon_mount_source(mount.source): {
                        "bind": mount.target,
                        "mode": "ro" if mount.read_only else "rw",
                    }
                    for mount in spec.mounts
                },
                user=spec.user,
                working_dir=spec.working_dir,
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

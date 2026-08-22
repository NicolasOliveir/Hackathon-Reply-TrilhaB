"""Laço do scheduler e montagem do runtime.

ORQUESTRADOR §4.1: um único processo de scheduler no MVP. Vários workers HTTP
do Uvicorn criariam múltiplos laços de despacho competindo pela mesma fila.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from ..config import Settings
from ..db import get_session_factory
from ..persistence.state_machine import load_state_machine
from ..runtime.base import ContainerRuntime
from ..runtime.fake_runtime import FakeContainerRuntime
from .scheduler import Scheduler

logger = logging.getLogger(__name__)


def build_runtime(settings: Settings) -> ContainerRuntime:
    if settings.runtime_backend == "fake":
        return FakeContainerRuntime(allowed_images=settings.allowed_images)
    from ..runtime.docker_runtime import DockerContainerRuntime

    return DockerContainerRuntime.from_environment(settings.allowed_images)


def build_scheduler(settings: Settings, runtime: ContainerRuntime) -> Scheduler:
    return Scheduler(
        session_factory=get_session_factory(),
        runtime=runtime,
        state_machine=load_state_machine(settings.state_machine_path),
        settings=settings,
    )


async def run_forever(scheduler: Scheduler, settings: Settings) -> None:
    """Consome a fila até ser cancelado.

    Uma falha de despacho não derruba o laço: ela é registrada e a próxima
    iteração continua. Um scheduler que morre no primeiro erro deixaria a fila
    parada sem sinal visível no painel.
    """
    while True:
        try:
            dispatched = await scheduler.dispatch_next()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - laço não pode morrer por uma task
            logger.exception("falha ao despachar tarefa")
            dispatched = None

        if dispatched is None:
            await asyncio.sleep(settings.scheduler_idle_seconds)


@contextlib.asynccontextmanager
async def scheduler_task(settings: Settings):
    """Sobe o laço junto com a aplicação e o encerra de forma limpa."""
    if not settings.scheduler_enabled:
        yield None
        return

    runtime = build_runtime(settings)
    scheduler = build_scheduler(settings, runtime)
    task = asyncio.create_task(run_forever(scheduler, settings), name="scheduler")
    try:
        yield scheduler
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

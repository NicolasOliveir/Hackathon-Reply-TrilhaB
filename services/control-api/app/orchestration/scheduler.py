"""Despacho de tarefas para containers.

Ciclo de uma tentativa:

1. reivindica uma `agent_task` pendente com `FOR UPDATE SKIP LOCKED`;
2. get-or-create de `agent_executions` por `(task_id, attempt)` — é isso que
   torna o despacho idempotente quando o nó é retomado;
3. para uma execução nova, emite o token de tarefa e grava só o hash;
4. `create` do container, para obter o `container_id`;
5. grava `AGENT_STARTED` e **commita** antes do `start` — o worker não pode
   chamar de volta antes de existir o evento que explica sua execução;
6. `start`, `wait`, registro do exit code, remoção do container.

O veredito da execução não é do container: `FAKE_WORKER_COMPLETED` vem do
callback validado, e o exit code é evidência complementar. Um container que sai
com 0 sem ter chamado de volta não conclui o run.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..persistence.event_store import EventDraft, EventStore, utc_now
from ..persistence.models import AgentExecution, AgentTask, Run
from ..persistence.state_machine import StateMachine
from ..runtime.base import ContainerRuntime, ContainerSpec, ResourceLimits
from . import tokens


@dataclass(frozen=True)
class DispatchResult:
    task_id: uuid.UUID
    run_id: uuid.UUID
    container_id: str | None
    exit_code: int | None
    timed_out: bool
    reused_execution: bool


class Scheduler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        runtime: ContainerRuntime,
        state_machine: StateMachine,
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._runtime = runtime
        self._state_machine = state_machine
        self._settings = settings

    # ------------------------------------------------------------------ claim

    async def _claim(self, session: AsyncSession) -> AgentTask | None:
        """Reivindica uma tarefa pendente.

        `SKIP LOCKED` permite mais de um consumidor no futuro sem que dois
        peguem a mesma linha; no MVP há um único scheduler, mas mudar isso
        depois não exige tocar no schema.
        """
        result = await session.execute(
            select(AgentTask)
            .where(
                AgentTask.state == "PENDING",
                AgentTask.available_at <= utc_now(),
            )
            .order_by(AgentTask.available_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        task = result.scalar_one_or_none()
        if task is None:
            # Handoffs ficam WAITING durante a transação do PO. O scheduler
            # promove um por vez, preservando ordem e o contrato observado.
            task = (
                await session.execute(
                    select(AgentTask)
                    .where(AgentTask.state == "WAITING", AgentTask.role == "dev",
                           AgentTask.available_at <= utc_now())
                    .order_by(AgentTask.available_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
        if task is None:
            return None

        task.state = "RUNNING"
        task.locked_at = utc_now()
        task.locked_by = self._settings.scheduler_id
        task.updated_at = utc_now()
        await session.flush()
        return task

    # ------------------------------------------------------------- execution

    async def _get_or_create_execution(
        self, session: AsyncSession, task: AgentTask, image: str
    ) -> tuple[AgentExecution, bool]:
        existing = (
            await session.execute(
                select(AgentExecution).where(
                    AgentExecution.task_id == task.task_id,
                    AgentExecution.attempt == task.attempt,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, True

        execution = AgentExecution(
            execution_id=uuid.uuid4(),
            task_id=task.task_id,
            run_id=task.run_id,
            attempt=task.attempt,
            image=image,
            state="STARTING",
            created_at=utc_now(),
        )
        session.add(execution)
        await session.flush()
        return execution, False

    def _build_spec(
        self, task: AgentTask, run_id: uuid.UUID, token: str, image: str
    ) -> ContainerSpec:
        """Monta o ambiente do container por lista explícita.

        Nada é herdado do processo do control-api. `ContainerSpec` recusa
        `DATABASE_URL` e `DOCKER_HOST` na construção, de modo que um vazamento
        vira exceção em vez de achado de revisão.
        """
        return ContainerSpec(
            image=image,
            environment={
                "RUN_ID": str(run_id),
                "TASK_ID": str(task.task_id),
                "CONTROL_API_URL": self._settings.internal_base_url,
                "TASK_TOKEN": token,
            },
            network=self._settings.agent_network,
            labels={
                "rivexx.run_id": str(run_id),
                "rivexx.task_id": str(task.task_id),
                "rivexx.attempt": str(task.attempt),
                "rivexx.role": task.role,
            },
            limits=ResourceLimits(
                memory=self._settings.worker_memory_limit,
                cpus=self._settings.worker_cpu_limit,
                pids=self._settings.worker_pids_limit,
            ),
        )

    # -------------------------------------------------------------- dispatch

    async def dispatch_next(self) -> DispatchResult | None:
        """Executa uma tentativa. Retorna `None` quando não há tarefa pendente."""
        async with self._sessions() as session:
            async with session.begin():
                task = await self._claim(session)
                if task is None:
                    return None

                run = (
                    await session.execute(
                        select(Run).where(Run.run_id == task.run_id).with_for_update()
                    )
                ).scalar_one()

                image = {
                    "po": self._settings.po_worker_image,
                    "dev": self._settings.dev_worker_image,
                }.get(task.role, self._settings.fake_worker_image)
                execution, reused = await self._get_or_create_execution(session, task, image)
                already_started = execution.container_id is not None
                token: str | None = None
                if not already_started:
                    issued = tokens.issue()
                    task.token_hash = issued.hashed
                    token = issued.plaintext

                claimed = _ClaimedTask(
                    task_id=task.task_id,
                    run_id=run.run_id,
                    attempt=task.attempt,
                    timeout_seconds=task.timeout_seconds,
                    role=task.role,
                    execution_id=execution.execution_id,
                    reused=reused,
                    token=token,
                    existing_container_id=execution.container_id,
                    already_started=already_started,
                    image=image,
                )

        if claimed.already_started:
            # Retomada de um nó que já subiu container para esta tentativa.
            # Não sobe outro; apenas devolve o que existe.
            return DispatchResult(
                task_id=claimed.task_id,
                run_id=claimed.run_id,
                container_id=claimed.existing_container_id,
                exit_code=None,
                timed_out=False,
                reused_execution=True,
            )

        if claimed.role == "dev" and self._settings.dev_worker_mode == "local":
            return await self._run_local_dev(claimed)
        return await self._run_container(claimed)

    async def _run_local_dev(self, claimed: "_ClaimedTask") -> DispatchResult:
        """Executa Dev no host/control-api, sem Docker e com ambiente explícito."""
        if claimed.token is None:
            raise RuntimeError("despacho local sem token")
        process_id = f"local-dev-{claimed.execution_id}"
        await self._record_started(claimed, process_id)
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "RUN_ID": str(claimed.run_id),
            "TASK_ID": str(claimed.task_id),
            "CONTROL_API_URL": self._settings.public_base_url,
            "TASK_TOKEN": claimed.token,
            "DEV_WORKSPACE_ROOT": str(self._settings.workspace_root / "generated"),
        }
        started = utc_now()
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(self._settings.dev_worker_script),
                env=environment, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            try:
                output, _ = await asyncio.wait_for(process.communicate(), claimed.timeout_seconds)
                timed_out = False
            except TimeoutError:
                process.kill(); await process.wait(); output = b""; timed_out = True
            result = _LocalResult(process_id, None if timed_out else process.returncode,
                                  timed_out, utc_now(), output.decode(errors="replace")[-8000:])
            await self._record_finished(claimed, result)
            return DispatchResult(claimed.task_id, claimed.run_id, process_id,
                                  result.exit_code, result.timed_out, claimed.reused)
        except Exception as exc:
            await self._record_runtime_failure(claimed, container_id=process_id,
                                               reason=f"{type(exc).__name__}: {exc}")
            raise

    async def _run_container(self, claimed: "_ClaimedTask") -> DispatchResult:
        if claimed.token is None:  # defesa: retomadas não chegam a este método
            raise RuntimeError("despacho novo sem token de tarefa")

        spec = self._build_spec(
            _TaskView(claimed), claimed.run_id, claimed.token, claimed.image
        )
        handle = None
        try:
            handle = await self._runtime.create(spec)

            # Commitado antes do start: o callback do worker só pode chegar depois
            # de AGENT_STARTED existir no log.
            await self._record_started(claimed, handle.container_id)
            await self._runtime.start(handle)
            result = await self._runtime.wait(
                handle, timeout_seconds=claimed.timeout_seconds
            )
        except Exception as exc:
            if handle is not None:
                try:
                    await self._runtime.remove(handle)
                except Exception:  # noqa: BLE001 - preserva a falha original
                    pass
            await self._record_runtime_failure(
                claimed,
                container_id=handle.container_id if handle is not None else None,
                reason=f"{type(exc).__name__}: {exc}",
            )
            raise

        await self._runtime.remove(handle)

        await self._record_finished(claimed, result)
        return DispatchResult(
            task_id=claimed.task_id,
            run_id=claimed.run_id,
            container_id=handle.container_id,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            reused_execution=claimed.reused,
        )

    async def _record_started(
        self, claimed: "_ClaimedTask", container_id: str
    ) -> None:
        async with self._sessions() as session:
            async with session.begin():
                execution = await session.get(AgentExecution, claimed.execution_id)
                execution.container_id = container_id
                execution.state = "RUNNING"
                execution.started_at = utc_now()

                run = (
                    await session.execute(
                        select(Run)
                        .where(Run.run_id == claimed.run_id)
                        .with_for_update()
                    )
                ).scalar_one()
                store = EventStore(session, self._state_machine)
                await store.append(
                    run,
                    [
                        EventDraft(
                            type="AGENT_STARTED",
                            task_id=claimed.task_id,
                            payload={
                                "role": claimed.role,
                                "attempt": claimed.attempt,
                                "image": claimed.image,
                                "execution_id": str(claimed.execution_id),
                            },
                            meta={"container_id": container_id},
                            # O primeiro worker move o agregado; workers de
                            # story posteriores enriquecem a mesma timeline.
                            drives_transition=claimed.role in {"fake", "po", "llm"},
                        )
                    ],
                )

    async def _record_finished(self, claimed: "_ClaimedTask", result) -> None:
        async with self._sessions() as session:
            async with session.begin():
                execution = await session.get(AgentExecution, claimed.execution_id)
                execution.exit_code = result.exit_code
                execution.finished_at = result.finished_at
                execution.logs_tail = result.logs_tail or None
                if result.timed_out:
                    execution.state = "TIMED_OUT"
                    execution.reason = (
                        f"timeout apos {claimed.timeout_seconds}s sem encerrar"
                    )
                elif result.exit_code == 0:
                    execution.state = "EXITED"
                else:
                    execution.state = "FAILED"
                    execution.reason = f"exit code {result.exit_code}"

                task = await session.get(AgentTask, claimed.task_id)
                run = (
                    await session.execute(
                        select(Run)
                        .where(Run.run_id == claimed.run_id)
                        .with_for_update()
                    )
                ).scalar_one()

                # Saída limpa não conclui nada por si: quem conclui é o callback
                # validado, que já pode ter movido o run para COMPLETED.
                if result.succeeded:
                    return

                if task.state == "RUNNING":
                    task.state = "TIMED_OUT" if result.timed_out else "FAILED"
                    task.token_hash = None
                    task.updated_at = utc_now()
                if self._state_machine.accepts(run.state, "AGENT_FAILED"):
                    store = EventStore(session, self._state_machine)
                    await store.append(
                        run,
                        [
                            EventDraft(
                                type="AGENT_FAILED",
                                task_id=claimed.task_id,
                                payload={
                                    "attempt": claimed.attempt,
                                    "exit_code": result.exit_code,
                                    "timed_out": result.timed_out,
                                    "reason": execution.reason,
                                },
                                meta={"container_id": result.container_id},
                                drives_transition=True,
                            )
                        ],
                    )

    async def _record_runtime_failure(
        self,
        claimed: "_ClaimedTask",
        *,
        container_id: str | None,
        reason: str,
    ) -> None:
        """Finaliza uma tentativa cuja infraestrutura falhou.

        Sem esta compensação, falhas de imagem, socket, rede ou `start` deixam
        a linha reivindicada em `RUNNING` para sempre e o laço nunca a encontra
        novamente.
        """
        async with self._sessions() as session:
            async with session.begin():
                execution = await session.get(AgentExecution, claimed.execution_id)
                if execution is not None:
                    if execution.container_id is None:
                        execution.container_id = container_id
                    execution.state = "FAILED"
                    execution.reason = reason
                    execution.finished_at = utc_now()

                task = await session.get(AgentTask, claimed.task_id)
                if task is not None and task.state == "RUNNING":
                    task.state = "FAILED"
                    task.token_hash = None
                    task.updated_at = utc_now()

                run = (
                    await session.execute(
                        select(Run)
                        .where(Run.run_id == claimed.run_id)
                        .with_for_update()
                    )
                ).scalar_one()
                if self._state_machine.accepts(run.state, "AGENT_FAILED"):
                    store = EventStore(session, self._state_machine)
                    await store.append(
                        run,
                        [
                            EventDraft(
                                type="AGENT_FAILED",
                                task_id=claimed.task_id,
                                payload={
                                    "attempt": claimed.attempt,
                                    "exit_code": None,
                                    "timed_out": False,
                                    "reason": reason,
                                },
                                meta={"container_id": container_id},
                                drives_transition=True,
                            )
                        ],
                    )


@dataclass(frozen=True)
class _ClaimedTask:
    task_id: uuid.UUID
    run_id: uuid.UUID
    attempt: int
    timeout_seconds: int
    role: str
    execution_id: uuid.UUID
    reused: bool
    token: str | None
    existing_container_id: str | None
    already_started: bool
    image: str


class _TaskView:
    """Adaptador mínimo para reaproveitar `_build_spec` fora da sessão."""

    def __init__(self, claimed: _ClaimedTask) -> None:
        self.task_id = claimed.task_id
        self.run_id = claimed.run_id
        self.attempt = claimed.attempt
        self.role = claimed.role
        self.timeout_seconds = claimed.timeout_seconds


@dataclass(frozen=True)
class _LocalResult:
    container_id: str
    exit_code: int | None
    timed_out: bool
    finished_at: object
    logs_tail: str

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

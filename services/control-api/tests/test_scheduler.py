"""Testes de integração do despacho.

Cobrem os critérios de conclusão de `I1-005`: uma task persistida inicia
exatamente um container, o callback gera evento, um retry não cria segunda
execução ativa e o worker nunca recebe banco ou socket.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.asyncio

BRIEFING = (
    "Centralizar não conformidades da Rivexx e rastrear lotes do insumo "
    "recebido ao produto expedido."
)


async def _create_run(client, key: str) -> dict:
    response = await client.post(
        "/api/v1/runs",
        json={"contract_version": "1.0.0", "briefing": BRIEFING},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


def _scheduler(runtime):
    from app.config import get_settings
    from app.db import get_session_factory
    from app.orchestration.scheduler import Scheduler
    from app.persistence.state_machine import load_state_machine

    settings = get_settings()
    return Scheduler(
        session_factory=get_session_factory(),
        runtime=runtime,
        state_machine=load_state_machine(settings.state_machine_path),
        settings=settings,
    )


def _runtime(**kwargs):
    from app.config import get_settings
    from app.runtime.fake_runtime import FakeContainerRuntime

    return FakeContainerRuntime(
        allowed_images=get_settings().allowed_images, **kwargs
    )


async def _events(run_id: str):
    from app.db import get_session_factory
    from app.persistence.models import Event

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Event).where(Event.run_id == run_id).order_by(Event.sequence)
        )
        return list(result.scalars().all())


async def test_dispatch_starts_exactly_one_container(client):
    from app.persistence.models import AgentExecution

    run = await _create_run(client, "sched-key-0001")
    runtime = _runtime()

    dispatched = await _scheduler(runtime).dispatch_next()

    assert dispatched is not None
    assert str(dispatched.run_id) == run["run_id"]
    assert runtime.created_count == 1
    assert runtime.started_count == 1
    assert runtime.removed_count == 1

    from app.db import get_session_factory

    async with get_session_factory()() as session:
        executions = await session.scalar(
            select(func.count()).select_from(AgentExecution)
        )
    assert executions == 1


async def test_dispatch_emits_agent_started_with_container_id(client):
    run = await _create_run(client, "sched-key-0002")
    runtime = _runtime()

    await _scheduler(runtime).dispatch_next()
    events = await _events(run["run_id"])

    started = [event for event in events if event.type == "AGENT_STARTED"]
    assert len(started) == 1
    assert started[0].meta["container_id"] == runtime.containers[0].handle.container_id
    assert started[0].payload["image"] == "rivexx/fake-worker:local"


async def test_agent_started_is_committed_before_the_container_runs(client):
    """Fecha a corrida do callback.

    O worker só pode chamar de volta depois de `AGENT_STARTED` existir. O
    runtime fake consulta o log no exato momento do `start`.
    """
    run = await _create_run(client, "sched-key-0003")
    seen: list[str] = []

    async def _on_start(spec):
        seen.extend(event.type for event in await _events(run["run_id"]))

    await _scheduler(_runtime(on_start=_on_start)).dispatch_next()

    assert "AGENT_STARTED" in seen


async def test_worker_never_receives_database_or_socket(client):
    run = await _create_run(client, "sched-key-0004")
    runtime = _runtime()

    await _scheduler(runtime).dispatch_next()

    environment = runtime.containers[0].spec.environment
    assert set(environment) == {
        "RUN_ID",
        "TASK_ID",
        "CONTROL_API_URL",
        "TASK_TOKEN",
    }
    assert environment["RUN_ID"] == run["run_id"]
    assert "DATABASE_URL" not in environment
    assert "DOCKER_HOST" not in environment
    assert "postgres" not in str(environment).lower()


async def test_container_is_labeled_for_traceability(client):
    run = await _create_run(client, "sched-key-0005")
    runtime = _runtime()

    await _scheduler(runtime).dispatch_next()

    labels = runtime.containers[0].spec.labels
    assert labels["rivexx.run_id"] == run["run_id"]
    assert labels["rivexx.role"] == "fake"
    assert labels["rivexx.attempt"] == "1"


async def test_container_runs_on_the_internal_agent_network(client):
    from app.config import get_settings

    await _create_run(client, "sched-key-0006")
    runtime = _runtime()

    await _scheduler(runtime).dispatch_next()

    spec = runtime.containers[0].spec
    assert spec.network == get_settings().agent_network
    assert spec.read_only is True


async def test_second_dispatch_finds_no_pending_task(client):
    await _create_run(client, "sched-key-0007")
    runtime = _runtime()
    scheduler = _scheduler(runtime)

    assert await scheduler.dispatch_next() is not None
    assert await scheduler.dispatch_next() is None
    assert runtime.created_count == 1


async def test_retry_does_not_create_a_second_execution(client):
    """Idempotência por `(task_id, attempt)`.

    Simula a retomada de um nó do grafo: a task volta a `PENDING`, mas a
    execução daquela tentativa já existe com container registrado.
    """
    from app.db import get_session_factory
    from app.persistence.models import AgentExecution, AgentTask

    await _create_run(client, "sched-key-0008")
    runtime = _runtime()
    scheduler = _scheduler(runtime)
    first = await scheduler.dispatch_next()

    async with get_session_factory()() as session:
        async with session.begin():
            task = (await session.execute(select(AgentTask))).scalar_one()
            original_token_hash = task.token_hash
            task.state = "PENDING"

    second = await scheduler.dispatch_next()

    assert second is not None
    assert second.reused_execution is True
    assert second.container_id == first.container_id
    assert runtime.created_count == 1, "não pode subir um segundo container"

    async with get_session_factory()() as session:
        executions = await session.scalar(
            select(func.count()).select_from(AgentExecution)
        )
        task = (await session.execute(select(AgentTask))).scalar_one()
    assert executions == 1
    assert task.token_hash == original_token_hash, (
        "retomada não pode invalidar o token que já está no container"
    )


async def test_clean_exit_without_callback_keeps_task_awaiting_output(client):
    from app.db import get_session_factory
    from app.persistence.models import AgentTask, Run

    await _create_run(client, "sched-key-clean-exit")
    await _scheduler(_runtime()).dispatch_next()

    async with get_session_factory()() as session:
        task = (await session.execute(select(AgentTask))).scalar_one()
        run = (await session.execute(select(Run))).scalar_one()

    assert task.state == "RUNNING"
    assert run.state == "WORKER_RUNNING"


async def test_create_failure_does_not_leave_task_claimed_forever(client):
    from app.db import get_session_factory
    from app.persistence.models import AgentExecution, AgentTask, Run
    from app.runtime.base import RuntimeError_
    from app.runtime.fake_runtime import FakeContainerRuntime

    class CreateFailureRuntime(FakeContainerRuntime):
        async def create(self, spec):
            raise RuntimeError_("imagem indisponível")

    await _create_run(client, "sched-key-create-failure")
    runtime = CreateFailureRuntime(
        allowed_images=_runtime().allowed_images
    )

    with pytest.raises(RuntimeError_, match="imagem indisponível"):
        await _scheduler(runtime).dispatch_next()

    async with get_session_factory()() as session:
        task = (await session.execute(select(AgentTask))).scalar_one()
        run = (await session.execute(select(Run))).scalar_one()
        execution = (await session.execute(select(AgentExecution))).scalar_one()

    assert task.state == "FAILED"
    assert run.state == "FAILED"
    assert execution.state == "FAILED"
    assert execution.container_id is None


async def test_start_failure_removes_container_and_finalizes_task(client):
    from app.db import get_session_factory
    from app.persistence.models import AgentExecution, AgentTask, Run
    from app.runtime.base import RuntimeError_
    from app.runtime.fake_runtime import FakeContainerRuntime

    class StartFailureRuntime(FakeContainerRuntime):
        async def start(self, handle):
            raise RuntimeError_("daemon recusou start")

    await _create_run(client, "sched-key-start-failure")
    runtime = StartFailureRuntime(
        allowed_images=_runtime().allowed_images
    )

    with pytest.raises(RuntimeError_, match="daemon recusou start"):
        await _scheduler(runtime).dispatch_next()

    async with get_session_factory()() as session:
        task = (await session.execute(select(AgentTask))).scalar_one()
        run = (await session.execute(select(Run))).scalar_one()
        execution = (await session.execute(select(AgentExecution))).scalar_one()

    assert runtime.removed_count == 1
    assert task.state == "FAILED"
    assert run.state == "FAILED"
    assert execution.state == "FAILED"
    assert execution.container_id is not None


async def test_non_zero_exit_fails_the_run(client):
    from app.db import get_session_factory
    from app.persistence.models import AgentExecution, AgentTask, Run

    run = await _create_run(client, "sched-key-0009")
    runtime = _runtime(exit_code=3)

    await _scheduler(runtime).dispatch_next()

    events = await _events(run["run_id"])
    assert [event.type for event in events][-1] == "AGENT_FAILED"

    async with get_session_factory()() as session:
        stored = (await session.execute(select(Run))).scalar_one()
        execution = (await session.execute(select(AgentExecution))).scalar_one()
        task = (await session.execute(select(AgentTask))).scalar_one()

    assert stored.state == "FAILED"
    assert execution.state == "FAILED"
    assert execution.exit_code == 3
    assert task.state == "FAILED"


async def test_timeout_marks_the_task_and_fails_the_run(client):
    from app.db import get_session_factory
    from app.persistence.models import AgentExecution, AgentTask

    run = await _create_run(client, "sched-key-0010")

    await _scheduler(_runtime(timed_out=True)).dispatch_next()

    async with get_session_factory()() as session:
        execution = (await session.execute(select(AgentExecution))).scalar_one()
        task = (await session.execute(select(AgentTask))).scalar_one()

    assert execution.state == "TIMED_OUT"
    assert task.state == "TIMED_OUT"
    assert "timeout" in (execution.reason or "")
    assert [event.type for event in await _events(run["run_id"])][-1] == "AGENT_FAILED"


async def test_container_is_removed_even_when_the_worker_fails(client):
    await _create_run(client, "sched-key-0011")
    runtime = _runtime(exit_code=1)

    await _scheduler(runtime).dispatch_next()

    assert runtime.removed_count == 1


async def test_task_token_is_stored_only_as_hash(client):
    from app.db import get_session_factory
    from app.persistence.models import AgentTask

    await _create_run(client, "sched-key-0012")
    runtime = _runtime()

    await _scheduler(runtime).dispatch_next()

    plaintext = runtime.containers[0].spec.environment["TASK_TOKEN"]
    async with get_session_factory()() as session:
        task = (await session.execute(select(AgentTask))).scalar_one()

    assert task.token_hash is not None
    assert task.token_hash.startswith("sha256:")
    assert plaintext not in task.token_hash

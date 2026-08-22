"""Testes dos endpoints internos consumidos pelo container de agente.

O callback é o ponto onde um agente poderia tentar se declarar aprovado. Estes
testes cobrem autenticação, ordem, duplicidade e o formato do contexto.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

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


def _runtime(**kwargs):
    from app.config import get_settings
    from app.runtime.fake_runtime import FakeContainerRuntime

    return FakeContainerRuntime(allowed_images=get_settings().allowed_images, **kwargs)


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


async def _dispatch(client, key: str) -> tuple[dict, str, str]:
    """Cria run, despacha e devolve (run, task_id, token em claro)."""
    run = await _create_run(client, key)
    runtime = _runtime()
    await _scheduler(runtime).dispatch_next()
    spec = runtime.containers[0].spec
    return run, spec.environment["TASK_ID"], spec.environment["TASK_TOKEN"]


def _output(task_id: str, run_id: str, status: str = "SUCCEEDED") -> dict:
    return {
        "contract_version": "1.0.0",
        "task_id": task_id,
        "run_id": run_id,
        "status": status,
        "message": "Context received and callback submitted through the central API.",
        "received_context_hash": "sha256:" + "b" * 64,
        "emitted_at": "2026-08-22T16:00:03Z",
    }


# ------------------------------------------------------------------- contexto


async def test_context_matches_the_versioned_contract(client, schema_validator):
    _, task_id, token = await _dispatch(client, "int-key-0001")

    response = await client.get(
        f"/internal/v1/tasks/{task_id}/context",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    schema_validator("agent-task-context.schema.json", response.json())


async def test_context_carries_role_and_minimum_scopes(client):
    _, task_id, token = await _dispatch(client, "int-key-0002")

    body = (
        await client.get(
            f"/internal/v1/tasks/{task_id}/context",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()

    assert body["role"] == "fake"
    assert {"context:read", "output:write"}.issubset(body["scopes"])
    assert body["task_id"] == task_id


async def test_context_does_not_leak_the_briefing(client):
    """O fake worker não é um nó autorizado a ler o problema do cliente."""
    _, task_id, token = await _dispatch(client, "int-key-0003")

    body = (
        await client.get(
            f"/internal/v1/tasks/{task_id}/context",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()

    assert BRIEFING not in str(body)
    assert body["context_manifest"] == []


async def test_context_without_token_is_forbidden(client):
    _, task_id, _ = await _dispatch(client, "int-key-0004")
    response = await client.get(f"/internal/v1/tasks/{task_id}/context")
    assert response.status_code == 403


async def test_context_with_wrong_token_is_forbidden(client):
    _, task_id, _ = await _dispatch(client, "int-key-0005")
    response = await client.get(
        f"/internal/v1/tasks/{task_id}/context",
        headers={"Authorization": "Bearer token-de-outra-tarefa"},
    )
    assert response.status_code == 403


async def test_unknown_task_is_forbidden_not_found(client):
    """403 e não 404: distinguir permitiria enumerar tarefas de outros papéis."""
    response = await client.get(
        f"/internal/v1/tasks/{uuid.uuid4()}/context",
        headers={"Authorization": "Bearer qualquer"},
    )
    assert response.status_code == 403


# -------------------------------------------------------------------- outputs


async def test_successful_output_completes_the_run(client):
    run, task_id, token = await _dispatch(client, "int-key-0006")

    response = await client.post(
        f"/internal/v1/tasks/{task_id}/outputs",
        json=_output(task_id, run["run_id"]),
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "callback-key-0001",
        },
    )

    assert response.status_code == 202, response.text
    assert response.json()["run_state"] == "COMPLETED"

    state = (await client.get(f"/api/v1/runs/{run['run_id']}")).json()["state"]
    assert state == "COMPLETED"


async def test_successful_output_emits_the_completion_events(client):
    from app.db import get_session_factory
    from app.persistence.models import Event

    run, task_id, token = await _dispatch(client, "int-key-0007")
    await client.post(
        f"/internal/v1/tasks/{task_id}/outputs",
        json=_output(task_id, run["run_id"]),
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "callback-key-0002",
        },
    )

    async with get_session_factory()() as session:
        events = list(
            (
                await session.execute(
                    select(Event)
                    .where(Event.run_id == run["run_id"])
                    .order_by(Event.sequence)
                )
            )
            .scalars()
            .all()
        )

    types = [event.type for event in events]
    assert types[-2:] == ["FAKE_WORKER_COMPLETED", "RUN_COMPLETED"]

    completed = events[-2]
    assert completed.actor == "fake_worker"
    assert str(completed.task_id) == task_id


async def test_repeated_callback_does_not_duplicate_events(client):
    from app.db import get_session_factory
    from app.persistence.models import Event
    from sqlalchemy import func

    run, task_id, token = await _dispatch(client, "int-key-0008")
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": "callback-key-0003",
    }
    payload = _output(task_id, run["run_id"])

    first = await client.post(
        f"/internal/v1/tasks/{task_id}/outputs", json=payload, headers=headers
    )
    async with get_session_factory()() as session:
        after_first = await session.scalar(select(func.count()).select_from(Event))

    second = await client.post(
        f"/internal/v1/tasks/{task_id}/outputs", json=payload, headers=headers
    )
    async with get_session_factory()() as session:
        after_second = await session.scalar(select(func.count()).select_from(Event))

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json() == second.json()
    assert after_first == after_second


async def test_callback_for_another_task_is_rejected(client):
    run, task_id, token = await _dispatch(client, "int-key-0009")

    response = await client.post(
        f"/internal/v1/tasks/{task_id}/outputs",
        json=_output(str(uuid.uuid4()), run["run_id"]),
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "callback-key-0004",
        },
    )

    assert response.status_code == 409


async def test_callback_out_of_order_is_rejected(client):
    """Segundo callback depois de COMPLETED não pode reabrir o run."""
    run, task_id, token = await _dispatch(client, "int-key-0010")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        f"/internal/v1/tasks/{task_id}/outputs",
        json=_output(task_id, run["run_id"]),
        headers={**headers, "Idempotency-Key": "callback-key-0005"},
    )
    late = await client.post(
        f"/internal/v1/tasks/{task_id}/outputs",
        json=_output(task_id, run["run_id"]),
        headers={**headers, "Idempotency-Key": "callback-key-0006"},
    )

    assert late.status_code == 409


async def test_failed_output_fails_the_run(client):
    run, task_id, token = await _dispatch(client, "int-key-0011")

    response = await client.post(
        f"/internal/v1/tasks/{task_id}/outputs",
        json=_output(task_id, run["run_id"], status="FAILED"),
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "callback-key-0007",
        },
    )

    assert response.status_code == 202
    assert (await client.get(f"/api/v1/runs/{run['run_id']}")).json()[
        "state"
    ] == "FAILED"


async def test_token_is_revoked_after_the_callback(client):
    """ORQUESTRADOR §8.1: validade curta e revogação no término."""
    run, task_id, token = await _dispatch(client, "int-key-0012")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        f"/internal/v1/tasks/{task_id}/outputs",
        json=_output(task_id, run["run_id"]),
        headers={**headers, "Idempotency-Key": "callback-key-0008"},
    )
    after = await client.get(f"/internal/v1/tasks/{task_id}/context", headers=headers)

    assert after.status_code == 403


async def test_malformed_output_is_rejected_by_the_contract(client):
    run, task_id, token = await _dispatch(client, "int-key-0013")
    payload = _output(task_id, run["run_id"])
    payload["status"] = "TALVEZ"

    response = await client.post(
        f"/internal/v1/tasks/{task_id}/outputs",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "callback-key-0009",
        },
    )

    assert response.status_code == 422

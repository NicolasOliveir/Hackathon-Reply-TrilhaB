"""Testes de integração do endpoint de invocação de modelo.

Cobrem a regra dura de ORQUESTRADOR.md §16 — *"agentes não acessam diretamente
internet ou provedor LLM"* — e o critério do `LLM-01`: *"chave fica só na API e
uso gera metadados no evento"*.
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


async def _dispatch(client, key: str, *, role: str = "llm"):
    """Cria run, despacha e devolve (run, task_id, token).

    `role` sobrescreve o papel da task para exercitar a trava de escopo: o
    papel `fake` não recebe `model:invoke`.
    """
    from app.db import get_session_factory
    from app.persistence.models import AgentTask

    response = await client.post(
        "/api/v1/runs",
        json={"contract_version": "1.0.0", "briefing": BRIEFING},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    run = response.json()

    if role != "fake":
        async with get_session_factory()() as session:
            async with session.begin():
                task = (await session.execute(select(AgentTask))).scalar_one()
                task.role = role

    runtime = _runtime()
    await _scheduler(runtime).dispatch_next()
    spec = runtime.containers[0].spec
    return run, spec.environment["TASK_ID"], spec.environment["TASK_TOKEN"]


def _payload(prompt: str = "Resuma o problema da Rivexx em uma frase.", **extra):
    body = {"contract_version": "1.0.0", "prompt": prompt}
    body.update(extra)
    return body


async def _invoke(client, task_id, token, **extra):
    return await client.post(
        f"/internal/v1/tasks/{task_id}/model-invocations",
        json=_payload(**extra),
        headers={"Authorization": f"Bearer {token}"},
    )


# ------------------------------------------------------------------- caminho ok


async def test_invocation_returns_text_and_usage(client):
    _, task_id, token = await _dispatch(client, "llm-key-0001")

    response = await _invoke(client, task_id, token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "echo"
    assert body["text"]
    assert body["usage"]["input_tokens"] > 0
    assert body["usage"]["output_tokens"] > 0
    assert uuid.UUID(body["invocation_id"])


async def test_invocation_with_schema_returns_parsed_json(client):
    _, task_id, token = await _dispatch(client, "llm-key-0002")

    body = (
        await _invoke(
            client, task_id, token, output_schema={"title": "Backlog", "type": "object"}
        )
    ).json()

    assert body["parsed"] is not None
    assert body["parsed"]["schema_title"] == "Backlog"


# ---------------------------------------------------------------- auditoria


async def test_invocation_is_persisted_with_route_reason(client):
    from app.db import get_session_factory
    from app.persistence.models import ModelInvocation

    _, task_id, token = await _dispatch(client, "llm-key-0003")
    await _invoke(client, task_id, token)

    async with get_session_factory()() as session:
        invocation = (await session.execute(select(ModelInvocation))).scalar_one()

    assert invocation.state == "SUCCEEDED"
    assert invocation.provider == "echo"
    assert invocation.role == "llm"
    assert invocation.route_reason
    assert invocation.input_tokens > 0


async def test_prompt_is_never_stored_in_clear(client):
    """A tabela é projetada no painel; o prompt pode conter o briefing."""
    from app.db import get_session_factory
    from app.persistence.models import ModelInvocation

    _, task_id, token = await _dispatch(client, "llm-key-0004")
    await _invoke(client, task_id, token, prompt=BRIEFING)

    async with get_session_factory()() as session:
        invocation = (await session.execute(select(ModelInvocation))).scalar_one()

    assert BRIEFING not in str(invocation.__dict__)
    assert invocation.prompt_hash.startswith("sha256:")
    assert invocation.prompt_chars == len(BRIEFING)


async def test_usage_reaches_the_completion_event_meta(client):
    """LLM-01: 'uso gera metadados no evento'."""
    from app.db import get_session_factory
    from app.persistence.models import Event

    run, task_id, token = await _dispatch(client, "llm-key-0005")
    await _invoke(client, task_id, token)
    await _invoke(client, task_id, token, prompt="Segunda chamada da mesma tarefa.")

    await client.post(
        f"/internal/v1/tasks/{task_id}/outputs",
        json={
            "contract_version": "1.0.0",
            "task_id": task_id,
            "run_id": run["run_id"],
            "status": "SUCCEEDED",
            "message": "Context received and callback submitted through the central API.",
            "received_context_hash": "sha256:" + "c" * 64,
            "emitted_at": "2026-08-22T16:00:03Z",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "llm-callback-0001",
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

    completed = next(e for e in events if e.type == "FAKE_WORKER_COMPLETED")
    assert completed.meta["model"] == "echo-1"
    assert completed.meta["tokens_in"] > 0
    assert completed.meta["tokens_out"] > 0
    # Duas chamadas na mesma tarefa somam no agregado.
    assert completed.meta["latency_ms"] >= 0


async def test_failed_invocation_is_still_audited(client, monkeypatch):
    """Invocação sem linha na auditoria seria um gasto invisível."""
    from app.api.internal import model_invocations as endpoint
    from app.db import get_session_factory
    from app.model_gateway.base import ModelGatewayError
    from app.model_gateway.gateway import ModelGateway
    from app.model_gateway.routing import ModelRouter
    from app.persistence.models import ModelInvocation

    class FailingProvider:
        name = "failing"

        async def invoke(self, request):
            raise ModelGatewayError("falha induzida do provedor")

    gateway = ModelGateway(
        providers={"failing": FailingProvider()},
        router=ModelRouter(default_provider="failing"),
    )
    monkeypatch.setattr(endpoint, "_gateway", lambda settings: gateway)

    _, task_id, token = await _dispatch(client, "llm-key-0006")

    response = await _invoke(client, task_id, token)
    assert response.status_code == 502

    async with get_session_factory()() as session:
        invocation = (await session.execute(select(ModelInvocation))).scalar_one()

    assert invocation.state == "FAILED"
    assert invocation.provider == "failing"
    assert invocation.error == "falha induzida do provedor"


async def test_unconfigured_provider_is_still_audited(client, monkeypatch):
    from app.api.internal import model_invocations as endpoint
    from app.db import get_session_factory
    from app.model_gateway.gateway import ModelGateway
    from app.model_gateway.routing import ModelRouter
    from app.persistence.models import ModelInvocation

    gateway = ModelGateway(providers={}, router=ModelRouter(default_provider="missing"))
    monkeypatch.setattr(endpoint, "_gateway", lambda settings: gateway)

    _, task_id, token = await _dispatch(client, "llm-key-0006b")
    response = await _invoke(client, task_id, token)

    assert response.status_code == 502
    assert response.json()["detail"]["error"] == "provider_not_configured"
    async with get_session_factory()() as session:
        invocation = (await session.execute(select(ModelInvocation))).scalar_one()

    assert invocation.state == "FAILED"
    assert invocation.provider == "missing"
    assert (
        "não configurado" in invocation.error or "nao configurado" in invocation.error
    )


# ------------------------------------------------------------------- travas


async def test_fake_role_has_no_model_invoke_scope(client):
    """O gateway não é aberto a qualquer tarefa."""
    _, task_id, token = await _dispatch(client, "llm-key-0007", role="fake")

    response = await _invoke(client, task_id, token)

    assert response.status_code == 403
    assert "model:invoke" in response.json()["detail"]


async def test_invocation_without_token_is_forbidden(client):
    _, task_id, _ = await _dispatch(client, "llm-key-0008")
    response = await client.post(
        f"/internal/v1/tasks/{task_id}/model-invocations", json=_payload()
    )
    assert response.status_code == 403


async def test_invocation_with_another_task_token_is_forbidden(client):
    _, task_id, _ = await _dispatch(client, "llm-key-0009")
    response = await _invoke(client, task_id, "token-de-outra-tarefa")
    assert response.status_code == 403


async def test_empty_prompt_is_rejected_by_the_contract(client):
    _, task_id, token = await _dispatch(client, "llm-key-0010")
    response = await _invoke(client, task_id, token, prompt="")
    assert response.status_code == 422


async def test_invalid_effort_is_rejected(client):
    _, task_id, token = await _dispatch(client, "llm-key-0011")
    response = await _invoke(client, task_id, token, effort="turbo")
    assert response.status_code == 422


async def test_invocation_after_the_task_ends_is_rejected(client):
    """Invocar por uma tarefa encerrada gastaria token sem consumidor."""
    run, task_id, token = await _dispatch(client, "llm-key-0012")

    await client.post(
        f"/internal/v1/tasks/{task_id}/outputs",
        json={
            "contract_version": "1.0.0",
            "task_id": task_id,
            "run_id": run["run_id"],
            "status": "SUCCEEDED",
            "message": "Context received and callback submitted through the central API.",
            "received_context_hash": "sha256:" + "d" * 64,
            "emitted_at": "2026-08-22T16:00:03Z",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "llm-callback-0002",
        },
    )

    # O token é revogado no encerramento, então a trava aparece como 403.
    response = await _invoke(client, task_id, token)
    assert response.status_code == 403


async def test_context_scopes_follow_the_task_role(client):
    _, task_id, token = await _dispatch(client, "llm-key-0013")

    body = (
        await client.get(
            f"/internal/v1/tasks/{task_id}/context",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()

    assert "model:invoke" in body["scopes"]


@pytest.mark.parametrize("role", ["dev", "qa"])
async def test_only_po_receives_the_raw_briefing(client, role):
    _, task_id, token = await _dispatch(
        client, f"context-no-briefing-{role}", role=role
    )

    response = await client.get(
        f"/internal/v1/tasks/{task_id}/context",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["input"] == {}
    assert body["context_manifest"] == []
    assert BRIEFING not in response.text


async def test_po_receives_the_raw_briefing(client):
    _, task_id, token = await _dispatch(client, "context-po-briefing", role="po")

    body = (
        await client.get(
            f"/internal/v1/tasks/{task_id}/context",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()

    assert body["input"] == {"briefing": BRIEFING}
    assert body["context_manifest"][0]["source_type"] == "briefing"

"""Testes de integração de `POST /api/v1/runs` e `GET /api/v1/runs/{run_id}`."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text

pytestmark = pytest.mark.asyncio

BRIEFING = (
    "Centralizar não conformidades da Rivexx e rastrear lotes do insumo "
    "recebido ao produto expedido."
)


def _payload(briefing: str = BRIEFING, reference: str | None = "rivexx-demo-001"):
    body = {"contract_version": "1.0.0", "briefing": briefing}
    if reference is not None:
        body["client_reference"] = reference
    return body


async def _create(client, key: str, **kwargs):
    return await client.post(
        "/api/v1/runs", json=_payload(**kwargs), headers={"Idempotency-Key": key}
    )


async def test_create_run_returns_202_and_matches_contract(client, schema_validator):
    response = await _create(client, "idem-key-0001")

    assert response.status_code == 202, response.text
    body = response.json()
    schema_validator("run-response.schema.json", body)
    assert body["state"] == "WORKER_QUEUED"
    assert body["current_task_id"] is not None
    assert body["links"]["self"].endswith(f"/api/v1/runs/{body['run_id']}")
    assert body["links"]["events"].endswith("/events")


async def test_briefing_shorter_than_contract_minimum_is_rejected(client):
    response = await _create(client, "idem-key-0002", briefing="curto demais")
    assert response.status_code == 422


async def test_missing_idempotency_key_is_rejected(client):
    response = await client.post("/api/v1/runs", json=_payload())
    assert response.status_code == 422


async def test_repeating_key_with_same_payload_does_not_duplicate(client):
    from app.persistence.models import AgentTask, Event, Run

    first = await _create(client, "idem-key-0003")
    second = await _create(client, "idem-key-0003")

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json() == second.json()

    from app.db import get_session_factory

    async with get_session_factory()() as session:
        runs = await session.scalar(select(func.count()).select_from(Run))
        tasks = await session.scalar(select(func.count()).select_from(AgentTask))
        events = await session.scalar(select(func.count()).select_from(Event))

    assert runs == 1
    assert tasks == 1
    assert events == 3


async def test_repeating_key_with_different_payload_returns_409(client):
    await _create(client, "idem-key-0004")
    conflict = await _create(
        client, "idem-key-0004", briefing=BRIEFING + " Com escopo diferente."
    )
    assert conflict.status_code == 409


async def test_distinct_keys_create_distinct_runs(client):
    first = await _create(client, "idem-key-0005")
    second = await _create(client, "idem-key-0006")
    assert first.json()["run_id"] != second.json()["run_id"]


async def test_get_run_returns_current_state(client, schema_validator):
    created = (await _create(client, "idem-key-0007")).json()

    response = await client.get(f"/api/v1/runs/{created['run_id']}")

    assert response.status_code == 200
    schema_validator("run-response.schema.json", response.json())
    assert response.json()["run_id"] == created["run_id"]


async def test_get_unknown_run_returns_404(client):
    response = await client.get(f"/api/v1/runs/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_run_with_malformed_id_returns_422(client):
    response = await client.get("/api/v1/runs/not-a-uuid")
    assert response.status_code == 422


async def test_raw_briefing_never_reaches_the_event_log(client):
    """Isolamento: o log é projetado no painel e não pode carregar o briefing.

    O texto do cliente vive apenas em `runs.briefing`, cujo acesso é do
    control-api. `BRIEFING_RECEIVED` transporta hash e tamanho.
    """
    from app.db import get_session_factory
    from app.persistence.models import Event

    await _create(client, "idem-key-0008")

    async with get_session_factory()() as session:
        payloads = (await session.execute(select(Event.payload))).scalars().all()

    assert payloads
    assert all(BRIEFING not in str(payload) for payload in payloads)

    briefing_event = next(
        payload for payload in payloads if "briefing_hash" in payload
    )
    assert briefing_event["length"] == len(BRIEFING)
    assert briefing_event["briefing_hash"].startswith("sha256:")


async def test_events_are_append_only(client):
    """O trigger da migration recusa UPDATE e DELETE em `control.events`."""
    from sqlalchemy.exc import DBAPIError

    from app.db import get_session_factory

    await _create(client, "idem-key-0009")

    async with get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                text("UPDATE control.events SET type = 'TAMPERED'")
            )
        await session.rollback()

        with pytest.raises(DBAPIError):
            await session.execute(text("DELETE FROM control.events"))
        await session.rollback()
